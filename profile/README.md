# WIPOperatingSystemName

An independent Linux distribution built from source, with the Telorgon desktop,
application framework and everyday apps. Our build pipeline brings the
bootloader, OS packages and applications together in a private QEMU VM.

## Start here

Follow the guides in order. Each guide explains the commands, the terminal to
use and how to check that the step succeeded.

1. **[Environment setup](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md)**
   — prepare Linux or WSL2, install host tools and Rustup, and create your workspace.
2. **[First build](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#first-build)**
   — build the OS from source, open a saved VM and check the desktop.
3. **[Daily development](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#update-changed-applications-automatically)**
   — edit source, rebuild changed applications and install them through guest pacman.

Already set up? Open the
[documentation index](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/README.md)
for saved VMs, build progress, cleanup, testing and troubleshooting.

## Project repositories

| Repository | Role |
| --- | --- |
| [distro](https://github.com/WIPOperatingSystemName/distro) | Source-built Linux system, package recipes, images and VM tools |
| [telorgon](https://github.com/WIPOperatingSystemName/telorgon) | Application framework and SDK |
| [bootloader](https://github.com/WIPOperatingSystemName/bootloader) | Telorgon EFI bootloader |
| [shell](https://github.com/WIPOperatingSystemName/shell) | Desktop shell and launcher |
| [file-explorer](https://github.com/WIPOperatingSystemName/file-explorer) | File Explorer |
| [settings](https://github.com/WIPOperatingSystemName/settings) | Settings application |
| [portal-picker](https://github.com/WIPOperatingSystemName/portal-picker) | Desktop portal picker |

## Contribute

Choose an issue, change the owning repository and test the affected behavior.
Framework and application changes belong in their component repositories;
packaging and build changes belong in `distro`.

Read the [contribution guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/contributing.md)
and [shared contribution instructions](https://github.com/WIPOperatingSystemName/.github/blob/main/AGENTS.md)
for preserving local work, synchronizing your fork and opening a pull request.
Maintainers use the [manual review and merge guide](https://github.com/WIPOperatingSystemName/.github/blob/main/automation/README.md).
