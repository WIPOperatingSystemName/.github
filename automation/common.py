"""Bounded HTTP and credential handling for trusted controller jobs."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ORG = "WIPOperatingSystemName"
CONTROL = f"{ORG}/.github"
DISTRO = f"{ORG}/distro"
MODULES = {
    "telorgon": "sources/telorgon",
    "bootloader": "sources/telorgon-bootloader",
    "shell": "sources/test-shell",
    "file-explorer": "sources/telorgon-file-explorer",
    "settings": "sources/telorgon-settings-app",
    "portal-picker": "sources/telorgon-portal-picker",
}
CONTEXT = "distro/integration"
WORKFLOW = ".github/workflows/integration.yml"
SECRETS: list[str] = []


class Failure(Exception):
    """An error safe to display without a remote response body."""


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise Failure(f"Configure {name} before running integration")
    return value


def remember_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise Failure("Authentication returned an empty credential")
    SECRETS.append(value)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::add-mask::{escaped}", flush=True)
    return value


def redact(text: str) -> str:
    for value in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTP:
    def request(self, url, *, token=None, payload=None, method=None,
                accept="application/json", limit=2_000_000):
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        allowed = host in {"api.github.com", "api.openai.com", "auth.openai.com"}
        allowed |= host.endswith(".actions.githubusercontent.com")
        if (parsed.scheme != "https" or not allowed or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment):
            raise Failure("Refusing an unexpected authentication/API endpoint")
        headers = {"Accept": accept, "User-Agent": "distro-integration-controller"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if host == "api.github.com":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=180) as response:
                body = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            raise Failure(f"{host} returned HTTP {error.code}; response body withheld") from None
        except (urllib.error.URLError, TimeoutError):
            raise Failure(f"Could not reach {host}") from None
        if len(body) > limit:
            raise Failure("API response exceeds the configured size limit")
        try:
            text = body.decode("utf-8")
            return json.loads(text) if accept == "application/json" else text
        except (UnicodeError, json.JSONDecodeError):
            raise Failure("API returned an invalid response") from None


class GitHub:
    def __init__(self, token=None, http=None):
        self.token, self.http = remember_secret(token) if token else None, http or HTTP()

    def call(self, path, **kwargs):
        return self.http.request("https://api.github.com" + path, token=self.token, **kwargs)

    def repo(self, name, suffix="", **kwargs):
        if name not in {CONTROL, DISTRO, *(f"{ORG}/{r}" for r in MODULES)}:
            raise Failure("Repository is outside the distro allowlist")
        return self.call(f"/repos/{name}{suffix}", **kwargs)


def trusted_dispatch():
    expected = f"{CONTROL}/{WORKFLOW}@refs/heads/main"
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != CONTROL
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") not in {"workflow_dispatch", "schedule"}
            or os.environ.get("GITHUB_WORKFLOW_REF") != expected):
        raise Failure("Privileged integration only runs from the trusted main workflow")
    if os.environ.get("INTEGRATION_ENABLED") != "true":
        raise Failure("Complete setup, then set INTEGRATION_ENABLED=true")
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and os.environ.get("AUTO_MERGE_ENABLED") != "true":
        raise Failure("Scheduled integration requires AUTO_MERGE_ENABLED=true")
    owner = required("MAINTAINER_LOGIN").casefold()
    if (os.environ.get("GITHUB_ACTOR", "").casefold() != owner
            or os.environ.get("GITHUB_TRIGGERING_ACTOR", "").casefold() != owner):
        raise Failure("Only the configured maintainer may dispatch integration")


def app_client(http=None):
    http = http or HTTP()
    app_id = required("INTEGRATION_APP_ID")
    installation = required("INTEGRATION_INSTALLATION_ID")
    if not app_id.isdecimal() or not installation.isdecimal():
        raise Failure("GitHub App identifiers must be numeric")
    private_key = remember_secret(required("INTEGRATION_APP_PRIVATE_KEY"))
    now = int(time.time())
    encode = lambda body: base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=")
    unsigned = encode({"alg": "RS256", "typ": "JWT"}) + b"." + encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id})
    with tempfile.TemporaryDirectory(prefix="integration-auth-") as directory:
        key = Path(directory) / "key.pem"
        key.touch(mode=0o600)
        key.write_text(private_key + "\n")
        signed = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)],
                                input=unsigned, capture_output=True, check=False)
        if signed.returncode:
            raise Failure("Could not sign GitHub App authentication; key details withheld")
    jwt = remember_secret((unsigned + b"." + base64.urlsafe_b64encode(signed.stdout).rstrip(b"=")).decode())
    identity = http.request("https://api.github.com/app", token=jwt)
    response = http.request(f"https://api.github.com/app/installations/{installation}/access_tokens",
                            token=jwt, payload={"repositories": ["distro", *MODULES],
                            "permissions": {"contents": "write", "pull_requests": "write",
                                            "statuses": "write",
                                            "administration": "read"}})
    client = GitHub(remember_secret(response["token"]), http)
    client.app_id, client.bot_login = int(app_id), identity["slug"] + "[bot]"
    return client


def openai_token(http=None):
    http = http or HTTP()
    mode = os.environ.get("OPENAI_AUTH_MODE", "oidc") or "oidc"
    if mode == "api-key":
        return remember_secret(required("OPENAI_API_KEY"))
    if mode != "oidc":
        raise Failure("OPENAI_AUTH_MODE must be oidc or api-key")
    provider, account = required("OPENAI_IDENTITY_PROVIDER_ID"), required("OPENAI_SERVICE_ACCOUNT_ID")
    audience = os.environ.get("OPENAI_WIF_AUDIENCE") or "https://api.openai.com/v1"
    url = urllib.parse.urlsplit(required("ACTIONS_ID_TOKEN_REQUEST_URL"))
    query = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
    query["audience"] = audience
    request_url = urllib.parse.urlunsplit(url._replace(query=urllib.parse.urlencode(query)))
    oidc = http.request(request_url, token=remember_secret(required("ACTIONS_ID_TOKEN_REQUEST_TOKEN")))
    subject = remember_secret(oidc["value"])
    exchange = http.request("https://auth.openai.com/oauth/token", payload={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token": subject, "identity_provider_id": provider, "service_account_id": account,
    })
    if exchange.get("token_type", "").casefold() != "bearer":
        raise Failure("Unexpected OpenAI token exchange result")
    return remember_secret(exchange["access_token"])
