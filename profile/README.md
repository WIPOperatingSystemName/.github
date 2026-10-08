# What we're building

We're building an independent Linux distribution with our own desktop, UI
framework (Telorgon), everyday apps and build tools. The goal is a complete
desktop system with modular parts that contributors can build, test and improve
together. It's still experimental.

## Contribute to the distro

You can contribute to any part. The `distro` repository will bring all seven
repositories together with pinned Git submodules.

**Setup status:** `distro` is currently empty. The instructions below become
usable after its first pinned baseline is published.

### Clone everything

```sh
git clone --recurse-submodules https://github.com/WIPOperatingSystemName/distro.git
cd distro
```

To update: `git pull --ff-only`, then `git submodule update --init --recursive`.

### Make a change

Pick an issue and say you’re working on it. Edit packaging/build tooling in
`distro`; edit apps or the framework in their repository under `sources/`.
Create a branch where you’re editing:

```sh
git -C sources/telorgon-file-explorer switch -c fix/my-change
```

Push to that repository or your fork. Open a small PR with test results or
reproduction steps. The main maintainer reviews and merges it, then updates the
distro’s source pin.

### Test

Use Linux with Git and Python 3.11+. On Windows, use
[WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) for development;
Linux is the reference build/test environment.

```sh
python3 build.py validate
python3 -m unittest discover -s tests -v
```

Follow the [build guide](https://github.com/WIPOperatingSystemName/distro#telorgon-desktop-build)
for full builds. With a built `desktop-use` image, QEMU and matching OVMF on Linux:

```sh
python3 build.py vm --use --name trial-1
```

Use a new VM name for each candidate. Downloadable Windows/Linux QEMU bundles
are planned; native Windows boot testing is not yet qualified.

### Planned merge flow

PR → CI tests → AI-assisted review → maintainer approval → merge → tested distro
pins → VM candidate. AI suggests fixes; the maintainer controls merges and releases.
