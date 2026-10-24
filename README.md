# Marantz CLI

A macOS and Linux terminal utility for compatible Marantz amplifiers and AV receivers using
the Denon/Marantz ASCII TCP control protocol. Every primitive opens a connection,
sends one CR-terminated command, reads a response when available, and disconnects.
No GUI, background service or persistent session.

**Marantz MODEL 40n is the ONLY device physically tested by the developer.**
Developed and tested on Marantz MODEL 40n. Compatibility with other Marantz devices is experimental or unverified unless explicitly documented.
Other devices are documented candidates or experimental compatibility. Simulated
tests are not hardware validation. See the [compatibility matrix](docs/COMPATIBILITY.md)
and [release-readiness report](docs/RELEASE_READINESS.md).

## Requirements

- macOS (Intel/Apple Silicon) or Linux (AMD64/ARM64), with `/bin/bash` 3.2+
  and Python 3.9+ on `PATH`. Ubuntu 24.04 and Debian 12 are the tested Linux targets.
- Standard system tools including `awk`, `dirname`, `cat` and fractional `sleep`.
- No third-party runtime packages or Homebrew requirement.
- A compatible receiver on a trusted LAN, normally TCP port 23.

Python is not guaranteed on a fresh macOS installation. Apple's Command Line
Tools can provide it (`xcode-select --install`), or use another Python 3.
On Debian/Ubuntu, install missing runtime/manual tools with:

```sh
sudo apt-get update
sudo apt-get install python3 bash mawk coreutils man-db
```

No `nc`/netcat, telnet, GNU `timeout`, `readlink`, `stat`, `sed` or `grep` is
required by the runtime. Python sockets and POSIX timers bound TCP operations.
Windows is unsupported. See [platform verification](docs/PLATFORMS.md) for exact
versions, architectures and limits; container tests are distinct from native CI.

## Run, install and uninstall

From the checkout, without installation:

```sh
./bin/marantz --help
./bin/marantz discover
./bin/marantz status
```

No setup file or hardcoded receiver address is required. Keep `bin/` and
`libexec/` together. For blocked multicast or multiple devices:

```sh
MARANTZ_HOST=receiver.local ./bin/marantz status
MARANTZ_HOST=192.0.2.10 ./bin/marantz status
```

`192.0.2.10` is a documentation-only example; substitute your receiver's address.

```sh
./install.sh
marantz --help
man marantz
./uninstall.sh
```

Defaults: `/usr/local/bin/marantz`, two helpers in `/usr/local/libexec/`, and
`/usr/local/share/man/man1/marantz.1`. Use sudo if ownership requires it; scripts
never invoke sudo automatically. Installation replaces these four files atomically
one at a time, supports repeated installs/upgrades, assumes
no Homebrew prefix, and uninstall preserves other user files and the cache.
Ensure `/usr/local/bin` is on `PATH`. If needed, use
`man -M /usr/local/share/man marantz`.

A user-owned installation uses the same commands on macOS and Linux, without sudo:

```sh
./install.sh --prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
man -M "$HOME/.local/share/man" marantz
./uninstall.sh --prefix "$HOME/.local"
```

## Commands

```sh
marantz -h                    # Also --help or help; no network access
marantz discover              # Fresh candidate list; no setters
marantz identify              # Discovered identity or Unknown, address and power
marantz devices               # Alias for discover
marantz info                  # Alias for identify
marantz capabilities          # Read-only query observations; controls stay Unknown
marantz status
marantz power                 # Also power status
marantz power on
marantz power off             # Same as power standby
marantz volume                # Also volume status, vol, v
marantz v up
marantz vol down
marantz volume set 10
marantz volume 10             # Also v 10
marantz mute                  # Also mute status
marantz mute on
marantz mute off
marantz mute toggle
marantz input                 # Also input status; read-only
marantz reboot
marantz raw 'MV?'
marantz --debug status
```

Queries print concise values such as `On`, `Standby`, `10`, `Off`, and `NET`.
Status retains its aligned fields:

```text
Marantz MODEL 40n
Power:   On
Volume:  10
Mute:    Off
Input:   NET
```

The heading uses discovered metadata. An explicit host with no metadata uses
`Marantz`, and `identify` reports `Unknown`; a direct connection is never
mislabeled MODEL 40n. Metadata is not compatibility certification or authentication.

## Compatibility and safety

MODEL 40n physical query observations (`PWON`/`PWSTANDBY`, `MV10`, `MUON`/`MUOFF`,
`SINET`) are exact regression fixtures. Original read-only observations also
covered SSDP/cache resolution. Other models need owner validation.

Volume queries accept two-digit integers and manufacturer-documented half steps
(`MV795` → `79.5`), plus source tokens such as `SAT/CBL`, `NET/USB`, `USB DIRECT`
and `V.AUX`. Numeric volume is the **encoded protocol level, not a universal
percentage or dB value**. Minimum codes and dB offsets differ by family.

Absolute settings remain integers (`10` → `MV10`, `7` → `MV07`). The default
0–98 policy applies to absolute settings, not relative/raw commands, and is not
a hardware range claim. Configurable bounds stay within two-digit encoding 0–99.
Prefer a low policy maximum and the receiver's own volume limiter when testing.
Half-step setting is not added.

Before volume writes, `MV?` must work; the CLI then ensures power is on. Power and
mute writes also require their corresponding query. Missing/malformed replies
stop those writes. Models unable to query volume in standby need manual power-on
first. A query does not prove a setter exists; explicit volume/mute settings are
checked against the resulting state and fail on disagreement without replay.

`capabilities` probes only `PW?`, `MV?`, `MU?`, and `SI?`. Valid replies are
**Observed** query behavior for that invocation. Timeouts and invalid replies stay
**Unknown**, not Unsupported. Controls remain Unknown because no setter is probed.
Observations are not persisted or promoted into model-wide support claims.

After `PWON`, the CLI waits four seconds by default before the next command,
covering an older documented SR/NR requirement, then polls power within a deadline.
Owners can configure the delay after verification. On-state is not audio readiness.

`reboot` is **soft standby → on**, never a factory reset. It confirms standby,
waits, powers on, and confirms On. It may leave networking running; failure can
leave the unit in standby. No reset, source-setting translation, zone control,
legacy `@` dialect, serial transport, or HEOS port-1255 control is implemented.

## Discovery, selection and VPNs

Priority: explicit `MARANTZ_HOST` → validated cache → fresh SSDP. Explicit-host
failure never switches to another receiver. Hostnames use the operating system's
normal resolver. `.local` uses Bonjour on macOS; Linux needs working mDNS/NSS
configuration (often Avahi), or use an IP address. No guessed service name or
background `dns-sd` process is used.
Automatic Bonjour service browsing is not implemented: AirPlay/HEOS advertising
does not prove port-23 command support.

SSDP searches the documented HEOS target and standard `upnp:rootdevice`, with
bounded retransmissions. Broad UPnP responses need Marantz/Denon manufacturer
metadata; HEOS advertisements remain candidates. Metadata GETs are bounded and
restricted to the sender IP, with no redirects/proxies. The selected device must
answer `PW?` before automatic control. `discover` only lists candidates, without
certifying their commands. Discovery sends on active IPv4 interfaces (up to 32),
with at most three search pairs per interface in one shared collection deadline.
Interfaces come from the OS, without fixed names or `ip`/`ifconfig` dependencies.
An unusable interface does not block other links; OS routing is the fallback if
enumeration fails. Allow UDP multicast and unicast SSDP replies on the LAN and
HTTP metadata/TCP control access. No subnet scan or network changes are performed.

Multiple candidates always require selection; MODEL 40n is never silently preferred:

```sh
MARANTZ_HOST=receiver.local marantz status
MARANTZ_DEVICE='uuid:receiver-identity' marantz status
MARANTZ_DEVICE='Marantz SR7009 (Living room)' marantz status
```

`MARANTZ_DEVICE` matches an exact name, model, UDN or address ignoring case and
constrains cache reuse. Duplicate names/models remain ambiguous. Explicit
`MARANTZ_HOST` takes precedence.

Automatic selection caches a device with identity metadata atomically using
restrictive file permissions:

- macOS: `~/Library/Caches/marantz/device.json`
- Linux: `${XDG_CACHE_HOME:-$HOME/.cache}/marantz/device.json`

Empty, relative or control-containing XDG paths fall back to `$HOME/.cache`.
Missing/invalid HOME falls back to the OS account's home directory. XDG is ignored
on macOS. Cache directories are created as needed; write failures are non-fatal.
Each reuse refetches identity and probes `PW?`; this is not cryptographic
authentication. Missing/corrupt/unreachable/changed/port-mismatched cache entries
trigger discovery. Identity-less devices remain usable but are not cached.
Writes are best-effort. No `~/.config` directory is required or read.

Expiry normally refreshes discovery. If multicast fails or finds nothing, an
expired entry is usable **only after fresh HTTP identity and TCP protocol checks
both pass**. Fresh ambiguity is never hidden by fallback. Reuse does not extend
the timestamp. If a VPN also blocks direct validation, use an explicit host or
fix LAN routing. TTL 0 disables cache reads/writes. Deleting the cache is safe.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `MARANTZ_HOST` | unset | Explicit IP/hostname, otherwise automatic |
| `MARANTZ_DEVICE` | unset | Exact discovery selector |
| `MARANTZ_PORT` | `23` | Control TCP port, 1–65535 |
| `MARANTZ_DISCOVERY_TIMEOUT` | `3` | Collection and separate metadata budgets |
| `MARANTZ_VERIFY_TIMEOUT` | `1` | Cached validation or selected-device probe budget |
| `MARANTZ_CACHE_TTL` | `300` | Freshness, 0–3600 seconds; 0 disables |
| `MARANTZ_CONNECT_TIMEOUT` | `2` | Total resolution/connect deadline |
| `MARANTZ_RESPONSE_TIMEOUT` | `2` | Total send/receive deadline |
| `MARANTZ_POWER_TIMEOUT` | `20` | Each polling phase, integer seconds |
| `MARANTZ_POLL_INTERVAL` | `0.5` | Seconds between power polls |
| `MARANTZ_STABILIZE_DELAY` | `4` | Seconds after PWON before next command |
| `MARANTZ_REBOOT_DELAY` | `2` | Seconds between confirmed standby and on |
| `MARANTZ_VOLUME_MIN` | `0` | Minimum absolute setting policy |
| `MARANTZ_VOLUME_MAX` | `98` | Maximum absolute setting policy |

Network timeouts/poll intervals accept 0.01–300 seconds; delays 0–300; power timeout
integers 1–300. Discovery, initial queries, setters, delays and polling have
separate budgets, so a high-level operation may exceed one timeout. Empty or
malformed explicit values fail validation.

## Debug, raw mode and errors

`--debug` sends resolution/address and accepted `TX:`/`RX:` frames to stderr;
results stay on stdout. Redact private details before sharing. Transport handles
CR, CRLF, fragmentation/coalescing, bounded data and total deadlines even while
bytes trickle in. Unrelated notifications and spaced MV namespace advisories are
skipped; advisories are not used as the current volume or a safety limit.

`raw` sends one quoted printable ASCII argument literally plus CR and prints the
first complete frame. It rejects CR/LF, controls, empty input and over 1024 bytes.
It never executes payloads locally. It bypasses built-in semantics/volume policy;
use only known safe commands. A timeout does not prove the receiver ignored it.

No setter is replayed after ambiguous failure. A setter without acknowledgement
gets a separate state query; transport errors stop the operation. Read-only power
polls can retry within a deadline. Check status before manually repeating a change.

Exit codes: **0** success/help, or at least one observed query in `capabilities`;
**1** environment/dependency/discovery/network/response/readiness/confirmation
failure; **2** invalid command/arguments. Errors go to stderr.

## Development and troubleshooting

```sh
./tests/check.sh
./tests/docker-test.sh
```

Tests use loopback TCP/UDP/HTTP fakes and isolated homes, never LAN multicast or
physical writes. Protocol variants are simulations. See [CONTRIBUTING.md](CONTRIBUTING.md).
The Docker entry point checks official Ubuntu 24.04 ARM64/AMD64 and Debian 12
ARM64 images, with dependencies and unprivileged test installations inside
temporary containers. It snapshots current uncommitted working files, never mounts
your home or Git metadata, and removes its own containers and temporary files.
It requires Docker, Git and Python on the host; AMD64 on Apple Silicon requires
Docker emulation. Pulled official images remain cached; unrelated resources are
untouched. It exits nonzero for failures, including unavailable emulation.

GitHub Actions covers `macos-15-intel` and `ubuntu-24.04`, each with Python 3.9
and 3.14, including ShellCheck, manuals and loopback tests. Check the repository's
Actions runs for hosted results; local and container results are separate.

- No discovery: check VPN, firewall, VLAN or Wi-Fi isolation; try debug discovery,
  a validated cache or an explicit host.
- No standby access: check your model's Network Control setting. Defaults differ;
  the CLI does not change receiver configuration.
- Unknown query/timeout: inspect a safe raw query and submit a redacted report.
  Silence does not prove unsupported hardware. Do not repeat setters blindly.
- Query works, setter fails: firmware/readiness/family differences need owner
  testing. Adjust bounded wake delay if appropriate, without guessing volume scales.
- Missing helper/man page: reinstall all four files; check PATH/man search paths.
- Tests cannot bind: allow loopback access or run in a normal terminal.

The protocol may be unauthenticated and is unencrypted. Never expose it through
public port forwarding. Read [SECURITY.md](SECURITY.md).

## License and project status

Licensed under the [MIT License](LICENSE), copyright (c) 2026 tkd4444.
See [LICENSING.md](LICENSING.md) for third-party material boundaries. Manufacturer
references are linked, not redistributed or relicensed. No Marantz/Denon
affiliation or endorsement is claimed.
