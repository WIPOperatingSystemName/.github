# What we're building

An independent Linux distribution with the Telorgon desktop, application SDK,
everyday apps and build tools. The `distro` repository brings the six framework,
bootloader and application repositories together as pinned source submodules.

## Workspace setup

Keep the project in `~/wip-os` on Linux or inside WSL. Open that folder in your
editor so component repositories and organization docs are available together.

### Linux

Install Git, Python 3.11+ and [GitHub CLI](https://cli.github.com/), then run:

```sh
git clone https://github.com/WIPOperatingSystemName/.github.git ~/wip-os/.github
python3 ~/wip-os/.github/setup.py
```

### Windows setup

Install WSL from **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart if prompted, open Ubuntu and create your Linux user. Inside Ubuntu:

```sh
sudo apt update
sudo apt install -y git python3 gh
git clone https://github.com/WIPOperatingSystemName/.github.git ~/wip-os/.github
python3 ~/wip-os/.github/setup.py
```

The setup helper signs you into GitHub, clones the pinned source workspace,
and creates or reuses your personal forks. `origin` points to the organization;
`fork` is your push destination. It preserves existing branches and local work.
To rerun setup, use the existing `.github/setup.py` rather than cloning again.

## Build and run

Complete the [host prerequisites](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#host-setup),
then run from Linux or the Ubuntu terminal in WSL:

```sh
cd ~/wip-os/distro
python3 build.py run --profile systemd
```

This builds the systemd OS test image from source and opens it in QEMU.
Use the [build guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md)
for smaller profiles, offline builds and tests, and the
[emulator guide](https://github.com/WIPOperatingSystemName/.github/blob/main/docs/emulator.md)
for Linux and Windows GUI setup.

## Contributing

Pick an issue, synchronize with the organization, change the owning repository
and run its relevant checks. Keep framework/app changes in their component repos
and packaging/build changes in `distro`. Push to your personal fork and open a
PR to the organization's `main`.

Follow the [shared contribution instructions](https://github.com/WIPOperatingSystemName/.github/blob/main/AGENTS.md)
for preserving local work, updating an existing contribution and submitting PRs.
The [maintainer guide](https://github.com/WIPOperatingSystemName/.github/blob/main/automation/README.md)
covers review and controlled integration.
