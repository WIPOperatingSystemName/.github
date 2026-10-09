"""Structured OpenAI review helpers; never execute candidate source."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Failure, redact

def encode_input(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def schema(repositories):
    finding = {"type": "object", "additionalProperties": False, "properties": {
        "repository": {"type": "string", "enum": repositories},
        "path": {"type": "string"}, "line": {"type": "integer"},
        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "description": {"type": "string"},
    }, "required": ["repository", "path", "line", "severity", "description"]}
    return {"type": "object", "additionalProperties": False, "properties": {
        "summary": {"type": "string"}, "findings": {"type": "array", "items": finding},
        "limitations": {"type": "array", "items": {"type": "string"}},
    }, "required": ["summary", "findings", "limitations"]}


def validate_review(value, repositories):
    if not isinstance(value, dict) or set(value) != {"summary", "findings", "limitations"}:
        raise Failure("AI review has an invalid shape")
    if not isinstance(value["summary"], str) or len(value["summary"]) > 4000:
        raise Failure("AI review summary exceeds its limits")
    if not isinstance(value["findings"], list) or len(value["findings"]) > 12:
        raise Failure("AI returned too many findings")
    if (not isinstance(value["limitations"], list) or len(value["limitations"]) > 12
            or any(not isinstance(v, str) or len(v) > 2000 for v in value["limitations"])):
        raise Failure("AI review limitations have an invalid shape")
    for finding in value["findings"]:
        if not isinstance(finding, dict) or set(finding) != {"repository", "path", "line", "severity", "description"}:
            raise Failure("AI finding has an invalid shape")
        path = finding["path"]
        if (finding["repository"] not in repositories or not isinstance(path, str)
                or not path or len(path) > 400 or path.startswith(("/", "\\"))
                or ".." in path.replace("\\", "/").split("/")
                or not isinstance(finding["line"], int) or isinstance(finding["line"], bool)
                or not 1 <= finding["line"] <= 1_000_000
                or finding["severity"] not in {"high", "medium", "low"}
                or not isinstance(finding["description"], str) or len(finding["description"]) > 3000):
            raise Failure("AI finding has invalid source coordinates or content")
    return value


def structured_review(http, token, model, data, *, instructions, output_schema,
                      name, max_output_tokens=4000, usage=None):
    response = http.request("https://api.openai.com/v1/responses", token=token, payload={
        "model": model, "store": False, "max_output_tokens": max_output_tokens,
        "instructions": instructions, "input": redact(encode_input(data)),
        "text": {"format": {"type": "json_schema", "name": name,
                            "strict": True, "schema": output_schema}},
    })
    if usage is not None:
        counters = response.get("usage") or {}
        for key in ("input_tokens", "output_tokens"):
            value = counters.get(key)
            usage[key] = value if type(value) is int and value >= 0 else None
        value = (counters.get("input_tokens_details") or {}).get("cached_tokens")
        usage["cached_input_tokens"] = value if type(value) is int and value >= 0 else None
    if response.get("status") != "completed":
        raise Failure("OpenAI did not finish the review; merging remains blocked")
    messages = [item for item in response.get("output", []) if item.get("type") == "message"]
    contents = [content for item in messages for content in item.get("content", [])]
    parts = [content["text"] for content in contents if content.get("type") == "output_text"]
    if (len(messages) != 1 or len(parts) != 1
            or any(content.get("type") == "refusal" for content in contents)):
        raise Failure("OpenAI returned a refusal or ambiguous structured review")
    try:
        result = json.loads(parts[0])
    except (ValueError, TypeError):
        raise Failure("OpenAI returned no valid structured review") from None
    return result
