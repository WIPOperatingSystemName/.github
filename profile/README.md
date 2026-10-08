# What we're building

We're building an independent Linux distribution with our own desktop, UI
framework (Telorgon), everyday apps and build tools. The goal is a complete
desktop system with modular parts that contributors can build, test and improve
together. It's still experimental.

You can contribute to any part. The `distro` repository will bring all seven
repositories together with pinned Git submodules.

**Setup status:** `distro` is currently empty. The instructions below become
usable after its first pinned baseline is published.

## Start with one workfolder

On Linux and Windows (WSL), keep all distro-related repos in `~/wip-os`.
The recursive clone below will include the framework, bootloader and apps under
`distro/sources/`; `.github` sits alongside `distro` for organization docs.

Open **`~/wip-os`** in your editor, Codex or any other coding agent so it can work
across the whole project. Each repository keeps its own commits and PRs.

## Linux setup

Install Git and Python 3.11+, then run in a terminal:

```sh
mkdir -p ~/wip-os
cd ~/wip-os
git clone https://github.com/WIPOperatingSystemName/.github.git
git clone --recurse-submodules https://github.com/WIPOperatingSystemName/distro.git
cd distro
python3 build.py validate
python3 -m unittest discover -s tests -v
```

Linux is the reference environment for full builds and boot tests. Follow the
[build guide](https://github.com/WIPOperatingSystemName/distro#telorgon-desktop-build).
With a built `desktop-use` image, QEMU and matching OVMF:

```sh
python3 build.py vm --use --name trial-1
```

Use a new VM name for each candidate.

## Windows setup

Install [WSL2 with Ubuntu](https://learn.microsoft.com/en-us/windows/wsl/install)
from **PowerShell as Administrator**:

```powershell
wsl --install
```

Restart, open **Ubuntu**, and create your Linux user. Then run in Ubuntu:

```sh
sudo apt update
sudo apt install git python3
python3 --version
mkdir -p ~/wip-os
cd ~/wip-os
git clone https://github.com/WIPOperatingSystemName/.github.git
git clone --recurse-submodules https://github.com/WIPOperatingSystemName/distro.git
cd distro
python3 build.py validate
python3 -m unittest discover -s tests -v
```

Check that Python is 3.11+. Keep the checkout in your
[WSL home directory](https://learn.microsoft.com/en-us/windows/wsl/filesystems).
Full distro builds and boot tests under WSL are still unverified; downloadable
Windows/Linux test bundles are planned.

## Contribution workflow

1. Pick an issue and say you're working on it.
2. Create a branch in the repo you’re editing: `distro` for packaging/build tools,
   or the relevant repo under `sources/` for framework/app changes. Example:
   `git -C sources/telorgon-file-explorer switch -c fix/my-change`.
3. Make the change and run that repo’s relevant tests. The setup checks above
   cover distro tooling.
4. Commit and push in that repo (or your fork), then open a small PR with test
   results or reproduction steps.
5. The main maintainer reviews and merges. Component changes then get a distro
   pin-update PR and integration test.

To refresh a clean checkout: `git pull --ff-only`, then
`git submodule update --init --recursive`.

Planned review flow: CI tests → AI-assisted review → maintainer approval → merge.
AI suggests fixes; the maintainer controls merges and releases.
