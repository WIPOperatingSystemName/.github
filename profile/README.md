# What we're building

We're building an independent Linux distribution with our own desktop,
application SDK (Telorgon), everyday apps and build tools. The goal is a complete
desktop system with modular parts that contributors can build, test and improve
together. It's still experimental.

You can contribute to any part. The `distro` repository brings all seven
repositories together with pinned Git submodules.

**Build status (2026-10-08):** a local Ubuntu 24.04 WSL2 build completed all 72
runtime packages, passed 97 tests and booted the systemd image in a Windows-visible
QEMU window through WSLg, using the bootstrap/recipe/launcher fixes from that run.
The current Telorgon, Shell and Settings source pins are incompatible, so a fresh
desktop build is blocked. Full remote CI and desktop rendering for these pins
remain unverified. See the [current build status](../docs/emulator.md#current-build-status).

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
wsl --install -d Ubuntu-24.04
```

Restart if prompted, open **Ubuntu 24.04**, and create your Linux user. Then run
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
emulation when KVM is unavailable. Distro bootstrap supplies pinned Meson 1.9.2
under `out/`; upgrading Ubuntu for its host Meson version is unnecessary. The
systemd boot check is verified locally under WSLg; the emulator guide includes
its launch command while the desktop pins are being corrected. Downloadable
Windows/Linux test bundles are planned.

## Run the emulator

Follow the **[QEMU emulator guide](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md)**
to build the OS image, open the desktop and test the apps:

- [Linux instructions](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md#linux)
- [Windows instructions (WSL2 and WSLg)](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md#windows-wsl2-and-wslg)

## Contribution workflow

Each repository's root `AGENTS.md` points coding agents to the
[shared contribution instructions](../AGENTS.md). After making and checking
changes, an agent offers to commit them and open a PR to the owning organization
repository. It waits for your approval unless you already requested submission.

1. Pick an issue and say you're working on it.
2. In the repo you’re editing, inspect local work, then run `git fetch origin`
   and `git fetch fork`. For sequential contributions, use your existing
   `main`: from a clean checkout on that branch, run
   `git pull --ff-only origin main`. If branches diverge, preserve pending work
   and integrate upstream as described in the shared instructions. Use separate
   branches for independent concurrent work. Use `distro` for packaging/build
   tools, or the owning SDK/app repository for requested component changes.
3. Make the change and run that repo’s relevant tests. The setup checks above
   cover distro tooling.
4. Before submission, fetch `origin` again and verify
   `git merge-base --is-ancestor origin/main HEAD` succeeds; integrate upstream
   and rerun affected checks if needed. Once submission is approved, commit and
   run `git push -u fork HEAD`. Open a PR from your fork to that organization
   repo’s `main`, or update the existing PR for the same work, with test results
   or reproduction steps and the verified upstream commit.
5. Once the maintainer enables automatic integration, the central controller
   groups ready PRs, requires lightweight static checks and one combined OpenAI
   security/correctness review, then merges exact commits and adopts reviewed pins.
   Build and boot verification are manual requirements before a release.
   Manual mode requires the maintainer's approval of the exact integration commit.

To refresh a clean distro checkout on `main`: `git pull --ff-only origin main`,
then `git submodule update --init --recursive`. Finish component branch work first.

Automatic flow: static source checks → one OpenAI security/correctness review →
controlled merge. A denied or incomplete source review blocks merging. PR checks
do not execute candidate code or require a self-hosted VM. An accepted source
review does not prove that the distro builds or boots.
The automation requires owner configuration before use; see
[maintainer setup](https://github.com/WIPOperatingSystemName/.github/tree/main/automation).
The maintainer controls merges and releases.
