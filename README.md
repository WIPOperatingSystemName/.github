# WIPOperatingSystemName

An independent Linux distribution with the Telorgon desktop, application SDK
and everyday apps.

Start with the [workspace setup](profile/README.md), then build and open the desktop development VM:

```sh
cd ~/wip-os/distro
./run --profile desktop-dev --name dev --jobs 4
```

- [Build guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md): host prerequisites, build stages and testing.
- [Environment setup](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md): Linux/WSL2, KVM and WSLg frame rate.
- [Contribution instructions](AGENTS.md): repository synchronization and pull requests.
- [Maintainer automation](automation/README.md): integration and review configuration.
