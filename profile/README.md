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

For a high-refresh Windows monitor, follow the optional
[WSLg refresh-rate setup](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md#wslg-frame-rate).

## Build and run

Complete the [host prerequisites](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md),
then run from Linux or the Ubuntu terminal in WSL:

```sh
cd ~/wip-os/distro
./run --profile desktop-dev --name dev --jobs 4
```

This builds the desktop development image from source and opens a named QEMU VM.
Use the [build and deployment guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md)
for saved VMs, incremental builds and installing edited source through guest pacman.
The [environment setup guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md)
covers Linux and WSL2 prerequisites, KVM, firmware and WSLg frame-rate configuration.

## Contributing

Pick an issue, synchronize with the organization, change the owning repository
and run its relevant checks. Keep framework/app changes in their component repos
and packaging/build changes in `distro`. Push to your personal fork and open a
PR to the organization's `main`.

Follow the [shared contribution instructions](https://github.com/WIPOperatingSystemName/.github/blob/main/AGENTS.md)
for preserving local work, updating an existing contribution and submitting PRs.
The [maintainer guide](https://github.com/WIPOperatingSystemName/.github/blob/main/automation/README.md)
covers source checks, manual PR merging and distro source-pin updates.
