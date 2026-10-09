# WIPOperatingSystemName

An independent Linux distribution with the Telorgon desktop, application SDK
and everyday apps.

Start with the [workspace setup](profile/README.md), then build and open an OS test image:

```sh
cd ~/wip-os/distro
python3 build.py run --profile systemd
```

- [Build guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md): host prerequisites, build stages and testing.
- [Emulator guide](docs/emulator.md): Linux/Windows GUI setup and QEMU troubleshooting.
- [Contribution instructions](AGENTS.md): repository synchronization and pull requests.
- [Maintainer automation](automation/README.md): integration and review configuration.
