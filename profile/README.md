# What we're building

We're building an independent Linux distribution with our own desktop,
application SDK (Telorgon), everyday apps and build tools. The goal is a complete
desktop system with modular parts that contributors can build, test and improve
together. It's still experimental.

You can contribute to any part. The `distro` repository brings all seven
repositories together with pinned Git submodules.

**Setup status:** source checkout and Linux tooling are available. Full remote
builds and Windows boot testing still need verification.

## Start with one workfolder

On Linux and Windows (WSL), use `~/wip-os` for the whole project. The setup below
clones distro with its pinned SDK, bootloader and apps under `distro/sources/`.
It signs you into GitHub, creates or reuses **your personal forks of all seven
code repos**, and connects them to these same checkouts. `.github` sits alongside
`distro` for organization docs and the setup helper.

Open **`~/wip-os`** in your editor, Codex or any other coding agent so it can work
across the whole project. `origin` points to the organization; `fork` is your push
destination. Contributor branches live in personal forks. Setup can be rerun
without resetting existing branches or work; `.gitmodules` keeps the organization
URLs. Already cloned? Update your `.github` checkout with `git pull --ff-only`,
then run the `setup.py` command below.

## Linux setup

Install Git, Python 3.11+ and [GitHub CLI](https://cli.github.com/), then run:

```sh
git clone https://github.com/WIPOperatingSystemName/.github.git ~/wip-os/.github
python3 ~/wip-os/.github/setup.py
```

Linux is the reference environment for full builds and boot tests. Follow the
[emulator guide](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md)
for QEMU installation, the first desktop build, launch commands and boot checks.
Check distro tooling from `~/wip-os/distro`:

```sh
python3 build.py validate
python3 -m unittest discover -s tests -v
```

To open the emulator once `out/images/custom-distro-desktop-use.img` is built:

```sh
cd ~/wip-os/distro
python3 build.py vm --use
```

This opens the Telorgon desktop in a QEMU window. Open File Explorer and Settings
from the launcher. Close QEMU to stop; your VM's files and settings are saved.
The emulator guide covers building the image if it is missing.

## Windows setup

Install [WSL2 with Ubuntu](https://ubuntu.com/wsl/docs/latest/howto/install-ubuntu-wsl2/)
from **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-26.04
```

Restart if prompted, open **Ubuntu 26.04**, and create your Linux user. Then run
in Ubuntu:

```sh
sudo apt update
sudo apt install -y git python3 gh
git clone https://github.com/WIPOperatingSystemName/.github.git ~/wip-os/.github
python3 ~/wip-os/.github/setup.py
```

Check that Python is 3.11+. Keep the checkout in your
[WSL home directory](https://learn.microsoft.com/en-us/windows/wsl/filesystems).
Use the [Windows emulator steps](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md#windows-wsl2-and-wslg)
to enable GUI support, install Linux QEMU inside Ubuntu and build the image.
Once the image exists, launch it **in the Ubuntu terminal**:

```sh
cd ~/wip-os/distro
python3 build.py vm --use
```

WSLg displays the QEMU window on your Windows desktop. The launcher uses software
emulation when KVM is unavailable. Ubuntu 26.04 supplies the Meson version needed
for desktop builds. Full distro builds and boot tests under WSL remain
unverified; downloadable Windows/Linux test bundles are planned.

## Run the emulator

Follow the **[QEMU emulator guide](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md)**
to build the OS image, open the desktop and test the apps:

- [Linux instructions](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md#linux)
- [Windows instructions (WSL2 and WSLg)](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md#windows-wsl2-and-wslg)

## Contribution workflow

1. Pick an issue and say you're working on it.
2. In the repo you’re editing, run `git fetch origin`, then
   `git switch -c fix/my-change origin/main`. Use `distro` for packaging/build tools,
   or the relevant repo under `distro/sources/` for SDK/app changes.
3. Make the change and run that repo’s relevant tests. The setup checks above
   cover distro tooling.
4. Commit, then run `git push -u fork HEAD`. On GitHub, open a PR from your fork
   to that organization repo’s `main`, with test results or reproduction steps.
5. The main maintainer groups related PRs into a distro integration PR, checks
   combined builds/boot tests and AI findings, then approves the exact commit.
   The central controller merges components and adopts the tested pins.

To refresh a clean distro checkout on `main`: `git pull --ff-only origin main`,
then `git submodule update --init --recursive`. Finish component branch work first.

Review flow: combined CI tests → AI review → maintainer approval → controlled merge.
The automation requires owner configuration before use; see
[maintainer setup](https://github.com/WIPOperatingSystemName/.github/tree/main/automation).
The maintainer controls merges and releases.
