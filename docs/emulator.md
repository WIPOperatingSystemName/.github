# Run the distro in QEMU

QEMU boots the complete OS image, including the Telorgon desktop and apps.
These steps use the contributor workspace from the
[organization quickstart](../profile/README.md): `~/wip-os/distro` with its pinned
source submodules. Run the shell commands below from a Linux terminal or the
Ubuntu terminal in WSL, stopping if a build command fails.

Linux is the reference build and boot-test platform. The Windows route uses
WSL2 and WSLg; full distro builds and boot tests there still need verification.
There is currently no published ready-to-run test bundle. Cloning the repos or
running `setup.py` does not build an OS image. If you already have
`out/images/custom-distro-desktop-use.img`, skip the source build and go to
[opening the desktop](#open-the-desktop-and-test-it).

## Linux

Use an x86_64 Linux host with a graphical desktop. The package commands below
use Ubuntu 26.04 LTS. Other distributions need equivalent
[host seed tools](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/bootstrap.md),
Python 3.11+ and **Meson 1.5+ at `/usr/bin/meson`**; the build uses a restricted
tool path. Ubuntu 24.04's default Meson is too old for the desktop build.
Ubuntu 26.04's [Meson package](https://packages.ubuntu.com/resolute/meson)
meets this requirement. This host setup has not been qualified end to end on
every distribution.

Install QEMU's x86 system emulator, its GTK display backend and UEFI firmware:

```sh
sudo apt update
sudo apt install -y qemu-system-x86 qemu-system-gui ovmf
qemu-system-x86_64 --version
qemu-system-x86_64 -display help
```

The display list must include `gtk`. Continue with the shared
[source build](#build-the-first-desktop-image) if the image is missing, then
[launch QEMU](#open-the-desktop-and-test-it). Run builds and the VM as your
normal user. The launcher selects KVM when it is accessible and passes its
probe, otherwise TCG software emulation; software emulation is slower.

## Windows (WSL2 and WSLg)

Use Windows 11 or Windows 10 build 19044+ with
[WSLg GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps).
QEMU runs inside Ubuntu and its window appears on the Windows desktop. Install
the Linux QEMU packages inside WSL; this guide uses the distro's Linux Python
launcher, which requires Linux filesystem locking and Unix sockets.

For a new installation, run in **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-26.04
```

Restart if prompted and complete Ubuntu's user setup. For an existing WSL
installation, save your work and close running WSL VMs before updating WSLg:

```powershell
wsl --update
wsl --shutdown
wsl --list --verbose
```

The Ubuntu distribution must show `VERSION 2`. If Ubuntu 26.04 is listed as
version 1, run `wsl --set-version Ubuntu-26.04 2`. Use the actual distribution
name from the list for an existing installation. Ubuntu 26.04 is the example
because its packaged Meson satisfies the desktop build requirement; an older
Ubuntu installation needs compatible host seed tools before building.

Open **Ubuntu 26.04** from the Start menu and follow the
[workspace setup](../profile/README.md#windows-setup) if you have not cloned it.
Then run **inside Ubuntu**:

```sh
sudo apt update
sudo apt install -y qemu-system-x86 qemu-system-gui ovmf
cd ~/wip-os/distro
qemu-system-x86_64 --version
qemu-system-x86_64 -display help
```

Keep the workspace under `~/wip-os` in the WSL Linux filesystem. Follow the
shared build and launch steps below in this same Ubuntu terminal. WSL does not
need access to `/dev/kvm` to launch: the helper falls back to TCG. Allow extra
boot time when using software emulation. Record Windows results as new test
evidence; the existing Linux receipts do not establish WSL compatibility.

## Build the first desktop image

Skip this section when the normal desktop image already exists. A fresh desktop
build compiles the toolchain, kernel, runtime libraries and all apps from source.
Budget several hours and substantial disk space; the integration worker requires
16 GiB RAM and 128 GiB free disk. Use `--jobs 4` initially and lower it if memory
is tight. WSL needs sufficient memory assigned to its Linux VM as well.

Install the host build seeds in Ubuntu (native Linux or WSL):

```sh
sudo apt install -y build-essential bison bc m4 perl autoconf automake \
  libtool pkg-config meson ninja-build fakeroot zlib1g-dev xz-utils \
  e2fsprogs gnupg python3 python3-jinja2 cmake clang libclang-dev \
  curl ca-certificates git
python3 --version
/usr/bin/meson --version
```

Check Python is at least 3.11 and Meson at least 1.5 before proceeding. Install
[Rust through rustup](https://rust-lang.github.io/rustup/installation/index.html)
if `rustup` and `cargo` are missing, then load its environment and install the
distro's pinned compiler:

```sh
. "$HOME/.cargo/env"
rustup toolchain install nightly-2026-10-06 --profile minimal \
  --target x86_64-unknown-uefi --target x86_64-unknown-linux-gnu
```

From the distro checkout, build the source packages and EFI loader:

```sh
cd ~/wip-os/distro
git submodule update --init --recursive
python3 build.py doctor
python3 build.py validate
python3 build.py fetch --bootstrap
python3 build.py bootstrap --jobs 4
python3 build.py native-toolkit --fetch --jobs 4
python3 build.py build --jobs 4
python3 build.py loader --online
```

Then compose the desktop SDK, build the apps and create the normal desktop disk:

```sh
python3 tools/compose-desktop-sdk.py
CD_DESKTOP_SYSROOT=$(python3 -c 'import json; print(json.load(open("out/sdk/current.json"))["sysroot"])')
python3 build.py apps prepare
python3 build.py apps check --sysroot "$CD_DESKTOP_SYSROOT"
python3 build.py apps build --sysroot "$CD_DESKTOP_SYSROOT" --online --jobs 4
python3 build.py image --profile desktop-use
```

`apps check` must report `ready_to_build: true`. `--online` allows the first
loader/app build to fetch pinned Cargo inputs; omit it once those are cached.
The resulting base image is **`out/images/custom-distro-desktop-use.img`**.
All generated build and VM files stay under `distro/out/`.

## Open the desktop and test it

Run in a Linux desktop terminal or in Ubuntu under WSLg:

```sh
cd ~/wip-os/distro
python3 build.py vm --use
```

QEMU opens a window and the OS boots through OVMF and the Telorgon EFI loader.
The normal `desktop-use` profile starts Telorgon automatically as the local
`custom` user. There is no password prompt for this VM session. Test the desktop:

1. Open File Explorer and Settings from the desktop launcher.
2. Move and resize windows, and check mouse and keyboard input.
3. Create a folder in File Explorer and change a setting.
4. Close QEMU, rerun the same command, and check that your changes survived.

The launcher stays open until you close QEMU or press Ctrl+C in its terminal.
It uses a private writable disk and firmware variables under `out/vms/custom/`;
it does not write to your physical disks or host firmware. User-mode networking
provides a virtual wired adapter without forwarding host ports.

To test a newly rebuilt base without reusing your saved disk, pick a new name:

```sh
python3 build.py vm --use --name fresh-test
```

Reuse that name to resume that VM. An existing name keeps its disk even after
you rebuild the base image. Use a different unused name for each fresh test.

## Automated boot and desktop checks

Use the separate `desktop` qualification profile for repeatable tests. After the
desktop build above, run:

```sh
python3 tools/build-desktop-session-probe.py
python3 build.py image --profile desktop
python3 build.py vm --image out/images/custom-distro-desktop.img \
  --expect CUSTOM_DESKTOP_SESSION_OK --desktop-input --window \
  --output out/verification/desktop-manual --timeout 600
python3 tools/check-wayland-window.py \
  --vm-report out/verification/desktop-manual/result.json \
  --output out/verification/desktop-manual/windows.json
```

This VM uses a disposable disk snapshot, opens test apps, injects Q when the
input probe is ready, saves evidence and exits. Omit `--window` for headless
testing. Check the command exit statuses and `success: true` in `result.json`,
then require `passed: true` in `windows.json` for the app-window and input checks.
Logs and the QEMU framebuffer `screen.ppm` are in the same output directory.
A timeout or missing marker is
a failed check, even if a window appeared. The guest probes have their own
deadlines, so a larger host timeout alone may not fix slow TCG qualification.

For a smaller console boot check using the source packages and loader:

```sh
python3 build.py image
python3 build.py vm --window --output out/verification/console-manual --timeout 600
```

This checks `CUSTOM_DISTRO_PERSISTENT_ROOT_OK`; it does not test the desktop.
`vm --use` is for normal interactive use and does not produce qualification
receipts. See [desktop qualification](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/desktop-session-qualification.md)
for the exact checks and limits.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing `custom-distro-desktop-use.img` | Complete the source build and `image --profile desktop-use`. Setup alone only clones sources and configures forks. |
| QEMU missing or GTK display unavailable | Install `qemu-system-x86` and `qemu-system-gui` in the terminal environment running `build.py`; check `-display help` includes `gtk`. |
| OVMF missing | Install `ovmf`, or set `OVMF_CODE` and `OVMF_VARS` to a matching unsigned firmware pair as shown below. |
| GTK cannot open a display | On Linux, use a terminal in your graphical login. On Windows, check WSL version 2, update/restart WSL, and follow Microsoft's [WSLg troubleshooting](https://github.com/microsoft/wslg/wiki/Diagnosing-%22cannot-open-display%22-type-issues-with-WSLg). |
| Meson rejects a project version | Check `/usr/bin/meson --version` is at least 1.5. Installing only a newer Meson under `~/.local/bin` does not change the restricted build tool path. |
| VM is slow | Check `out/vms/custom/command.json` for the selected accelerator. TCG is expected when KVM is unavailable; allow more boot time. |
| Rebuilt apps do not appear | Rebuild app packages and `image --profile desktop-use`, then launch with a new, unused `--name`. |
| VM exits or test times out | Read `qemu.log` and `serial.log` in `out/vms/<name>/` for normal use, or your `--output` directory for automated tests. Include those logs, host OS, source commit and the image digest when reporting a bug. |

The helper normally discovers the firmware installed by `ovmf`. If you need to
select it explicitly, this is the usual Ubuntu 4 MiB pair (confirm both files
exist on your host):

```sh
export OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
export OVMF_VARS=/usr/share/OVMF/OVMF_VARS_4M.fd
python3 build.py vm --use --name firmware-test
```

Use code and variables from the same firmware build and size, without Secure
Boot enforcement. The helper copies the variables template for each VM. A saved
VM also requires its original firmware code; choose a new VM name if you change
the firmware pair. If QEMU is outside `PATH`, set `QEMU_SYSTEM_X86_64` to its
executable path. Refer to the [QEMU invocation reference](https://www.qemu.org/docs/master/system/invocation.html)
for emulator options.
