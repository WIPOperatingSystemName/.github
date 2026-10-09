# Run the distro in QEMU

Use the [workspace setup](../profile/README.md) and the distro's
[build guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#host-setup)
for source/toolchain prerequisites. Run the build and launcher as your normal
user, in a Linux terminal or Ubuntu under WSL2. Setup clones sources and
configures forks; `build.py run` builds the image.

## Linux

Use an x86_64 Linux host with a graphical session. On Ubuntu 24.04:

```sh
sudo apt update
sudo apt install -y qemu-system-x86 qemu-system-gui ovmf
qemu-system-x86_64 --version
qemu-system-x86_64 -display help
```

The display list must include `gtk`. The launcher uses KVM when accessible and
working, and otherwise uses TCG software emulation.

## Windows (WSL2 and WSLg)

Use [WSLg GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)
so Linux QEMU windows appear on the Windows desktop. For a new installation,
follow [Windows workspace setup](../profile/README.md#windows-setup). For an
existing installation, save your WSL work, then run in PowerShell:

```powershell
wsl --update
wsl --shutdown
wsl --list --verbose
```

The Ubuntu distribution must show version 2. If needed, use
`wsl --set-version Ubuntu-24.04 2`, substituting your actual distribution name.
Install the QEMU packages from the Linux section **inside Ubuntu**. Keep the
checkout in the WSL Linux filesystem, such as `~/wip-os`, and run all remaining
commands in that Ubuntu terminal. KVM is optional; TCG works without it.

## Build and run an OS test image

```sh
cd ~/wip-os/distro
python3 build.py run --profile systemd
```

This builds the toolchain, runtime packages and Telorgon EFI loader, composes
the systemd image and opens QEMU. The window stays open after the startup checks
pass. Close QEMU or press Ctrl+C to stop. This test profile has locked accounts
and no interactive login. Use `--jobs 2` if memory is tight.

For a bounded boot check without a window:

```sh
python3 build.py run --profile systemd --headless
```

Use `--profile console` for the minimal console image. Startup has a 600-second
deadline; `--timeout` changes it. Results, image digests, serial logs and
framebuffer captures go to `out/verification/run-<profile>/`. Use `--output` to
retain a separate run. A timeout or missing assertion fails the command.

## Desktop testing

The full desktop pipeline is `python3 build.py run`. It requires compatible
framework/app sources; see the [desktop build guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#desktop-build)
for that requirement and the individual build stages.

After a successful build, Telorgon starts a local `custom` session automatically.
Open File Explorer and Settings from the launcher, test mouse/keyboard input and
move or resize windows. Close QEMU or press Ctrl+C to stop. A private disk and
firmware variables are saved under `out/vms/test-<image-digest>/`; the same image
resumes that disk, while a changed image gets a separate VM.

To deliberately keep one named desktop disk across builds:

```sh
python3 build.py run --name my-test
python3 build.py vm --use --name my-test
```

The second command reopens the saved VM without rebuilding. An existing name
keeps its original base; pick an unused name to test a fresh base. QEMU uses
private virtual disks and user networking. The normal desktop launcher has no
boot assertions or injected input. Use the [desktop qualification commands](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#desktop-qualification)
for repeatable app window, presentation and keyboard checks.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Build fails | Read the failing stage's log. Retry `run` after fixing the cause; completed stages are validated before reuse. |
| QEMU or GTK missing | Install `qemu-system-x86` and `qemu-system-gui` in the environment running Python; check `-display help`. |
| OVMF missing | Install `ovmf`, or set a matching firmware pair as shown below. |
| Cannot open a display | Use a graphical Linux session; on Windows, verify WSL2 and follow [WSLg troubleshooting](https://github.com/microsoft/wslg/wiki/Diagnosing-%22cannot-open-display%22-type-issues-with-WSLg). |
| Rust feature/API mismatch | Check the actual source revisions. Keep compatible component changes together in review; do not advance pins or remove features as build setup. |
| Rebuilt apps are absent | Check the VM name. An explicitly named saved disk keeps its old contents; use an unused name or let `run` choose from the image digest. |
| VM is slow or exits | Read `command.json`, `qemu.log` and `serial.log` in the VM/report directory. TCG is slower; include logs, host OS, source commit and image digest in bug reports. |

For explicit firmware selection, use code and variables from the same firmware
build and size, without Secure Boot enforcement. On Ubuntu, confirm these files
exist before running:

```sh
export OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
export OVMF_VARS=/usr/share/OVMF/OVMF_VARS_4M.fd
python3 build.py vm --use --name firmware-test
```

The launcher copies the variables template. A saved VM needs its original code;
choose a new name when changing firmware. Set `QEMU_SYSTEM_X86_64` if QEMU is
outside `PATH`.
