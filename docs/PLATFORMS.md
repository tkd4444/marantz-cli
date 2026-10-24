# Platform compatibility

Verified 2026-10-24. Operating-system support is separate from
[receiver compatibility](COMPATIBILITY.md). MODEL 40n remains the only device
physically tested by the developer. No physical receiver was contacted for these
tests; other models and physical setters remain experimental/unverified.

## Executed checks

| Environment | Architecture | Bash / Python | Full suite result |
| --- | --- | --- | --- |
| Native macOS 26.7 | Apple Silicon ARM64 | 3.2.57 / 3.9.6 | 104 run: 102 passed, 2 Linux-only integration tests skipped |
| Official `ubuntu:24.04`, Docker | ARM64, native Linux VM execution | 5.2.21 / 3.12.3 | 104 passed, no skips |
| Official `ubuntu:24.04`, Docker | AMD64, emulated on Apple Silicon | 5.2.21 / 3.12.3 | 104 passed, no skips |
| Official `debian:12`, Docker | ARM64, native Linux VM execution | 5.2.15 / 3.11.2 | 104 passed, no skips |
| macOS Intel | x86_64 | CI configured for Python 3.9 / 3.14 | Configured CI coverage; see repository Actions runs |
| Native Ubuntu 24.04 hosted runner | AMD64 | CI configured for Python 3.9 / 3.14 | Configured CI coverage; see repository Actions runs |

All 84 original tests are retained, with 20 additional focused cases. Each full
check includes Bash/Python syntax, ShellCheck, documentation links/hygiene, all
help forms, manual lint/render, installed `man marantz`, temporary-prefix install,
upgrade/repeat/uninstall, permissions and loopback TCP/UDP/HTTP simulations.
macOS used ShellCheck 0.11.0 from temporary storage; containers used distribution
ShellCheck 0.9.0. No tool or CLI was installed into the development host's system.

The tests exercise commands, framing, absolute deadlines, unreachable receivers,
preflight/confirmation, no ambiguous setter retries, multiple-device selection,
identity changes, cache expiry, VPN fallback, both native cache conventions and
interface enumeration. Linux XDG integration tests run only on Linux; portable
unit tests verify both cache conventions on every OS.

## Dependencies and installation

Runtime: `/bin/bash` 3.2+, Python 3.9+ with its standard library, a normal Unix C
library providing `getifaddrs`, and system `awk`, `dirname`, `cat`, fractional
`sleep`. Installation additionally uses `uname`, `install`, `mktemp`, `mv`, `rm`.
BSD/macOS and GNU/Debian variants are exercised. No Python packages, `nc`, telnet,
`sed`, `grep`, `readlink`, external `stat` or `timeout` utility are needed.

Debian/Ubuntu runtime/manual tools, if missing:

```sh
sudo apt-get update
sudo apt-get install python3 bash mawk coreutils man-db
```

For local development add `mandoc` and `shellcheck`. Docker, Git and Python are
needed on the host only for the reusable Docker test runner. Docker installs
test dependencies inside temporary containers and runs tests as an unprivileged
user. CI installs test tools on disposable hosted runners.

On both macOS and Linux:

```sh
./install.sh --prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
marantz --help
man -M "$HOME/.local/share/man" marantz
./uninstall.sh --prefix "$HOME/.local"
```

No-prefix installation uses `/usr/local`; permission errors are returned normally,
and the scripts never invoke sudo. Four known files are replaced individually via
same-directory temporary files and atomic rename. Use the same prefix to upgrade
or uninstall. Uninstall preserves unrelated files and cache contents.

## Cache and networking

- macOS: `~/Library/Caches/marantz/device.json`; XDG is ignored.
- Linux: `${XDG_CACHE_HOME:-$HOME/.cache}/marantz/device.json`. Invalid relative or
  control-containing XDG values are ignored. Missing/invalid HOME uses the account
  home. Directories are created as needed; write failure does not prevent use.

No settings file or `~/.config` dependency is introduced. Cache permissions,
atomic replacement, HTTP identity checking and `PW?` validation are preserved.

TCP still sends one CR-terminated primitive per connection. Python sockets avoid
netcat option/EOF differences: [OpenBSD nc](https://man.openbsd.org/nc) documents
`-N` socket shutdown after EOF, while
[Debian traditional nc](https://manpages.debian.org/bookworm/netcat-traditional/nc.1.en.html)
documents `-q` delayed exit. macOS's local BSD nc help was inspected too. None of
these programs is invoked or required by the CLI.

SSDP enumerates active IPv4 addresses through `getifaddrs` using standard-library
`ctypes`, accounting for Darwin/Linux sockaddr layout. It sends bounded search
pairs on up to 32 interfaces, skips unusable links, deduplicates replies and keeps
one collection deadline. Enumeration failure uses OS multicast routing. No fixed
interface names, subnet scan, root privilege or network/VPN changes are required.
References: [Apple getifaddrs](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/getifaddrs.3.html),
[Linux getifaddrs](https://man7.org/linux/man-pages/man3/getifaddrs.3.html),
[Linux IP multicast sockets](https://man7.org/linux/man-pages/man7/ip.7.html),
[XDG cache convention](https://specifications.freedesktop.org/basedir/latest/).

Allow LAN UDP multicast/unicast SSDP replies, HTTP metadata and the configured TCP
port (normally 23). `.local` uses the system resolver: Bonjour on macOS, working
mDNS/NSS configuration such as Avahi on Linux. An IP avoids that dependency.
`MARANTZ_HOST`/`MARANTZ_PORT` bypass discovery; validated cache fallback remains
available when a VPN blocks multicast but direct identity/protocol checks work.

## Repeating verification and limits

```sh
./tests/check.sh
./tests/docker-test.sh
```

The Docker runner checks version/server availability, pulls official images,
snapshots current uncommitted working files using Git's file/ignore list, mounts
only that temporary snapshot read-only, and copies it inside each container.
It prints results per target and returns nonzero for failures. Own containers and
temporary files are cleaned up; shared image caches and unrelated resources stay
untouched. No privileged containers, host HOME/Git mounts or host installations.

Ubuntu minimal images divert `man` to a placeholder: the harness restores the real
viewer inside the container after installing man-db. Rosetta may create a runtime
XDG cache under emulation: the zero-setup test initializes runtime caches before
measuring the exact files added by Marantz. Neither issue changes application
behavior or removes original test coverage.

Docker Desktop's Linux VM/bridge does not establish physical LAN multicast
reachability. Multi-interface routing is simulated; actual interface enumeration
is exercised on macOS and in each container. Physical Linux hosts, real concurrent
LAN interfaces/VPNs and additional receiver hardware still need owner observations.
Windows and other Linux distributions are unverified. macOS Intel and native
Ubuntu GitHub results must be checked in repository Actions runs before publication;
Python 3.14 is covered by CI configuration, not these local test runs. See
[release readiness](RELEASE_READINESS.md).

CI uses explicit supported [GitHub runner labels](https://github.com/actions/runner-images),
`macos-15-intel` and `ubuntu-24.04`, each with Python 3.9/3.14. It requires
ShellCheck and runs the same local checks, without hardware or LAN access.
