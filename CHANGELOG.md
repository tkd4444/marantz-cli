# Changelog

## 1.0.0

- Release under the MIT License with the approved public copyright attribution.
- Cancel TCP transaction alarms before reporting errors, preventing a late signal
  from turning a socket timeout into a traceback; add deterministic regression
  coverage for query/raw timeout and connection/receive failure diagnostics.

**Marantz MODEL 40n is the ONLY device physically tested by the developer.**
Developed and tested on Marantz MODEL 40n. Compatibility with other Marantz devices is experimental or unverified unless explicitly documented.
Other models and physical setters are not certified by this preparation.

- Support macOS and Linux from the shared Bash/Python implementation, with native
  macOS and XDG Linux cache locations, environment fallback and OS-aware installs.
- Search active IPv4 interfaces with a shared SSDP send/receive deadline, retaining
  identity validation, exact selection and direct-host/validated VPN fallback.
- Add `devices`/`info` aliases for `discover`/`identify`; existing syntax is retained.
- Replace installation files atomically; verify repeated upgrades, permissions,
  installed manuals and uninstall preservation under temporary user prefixes.
- Add a reusable official-image Docker matrix: Ubuntu 24.04 ARM64/AMD64 and
  Debian 12 ARM64. Retain all 84 tests and expand the suite to 104 tests.
- Expand CI to macos-15-intel and ubuntu-24.04 with Python 3.9/3.14 and required
  shell lint. Local/container results do not imply hosted CI or hardware success.
- Accept documented half-step volume replies and wider source tokens; retain
  integer absolute writes and the existing configurable policy.
- Use discovered/generic identity instead of assuming MODEL 40n. Add read-only
  `identify` and `capabilities`; unobserved support stays Unknown.
- Preflight queries gate writes; explicit mute/volume state confirmation can fail
  without replay. Use a configurable four-second default wait after PWON.
- Add vendor-filtered root-device SSDP beside HEOS. Remove automatic model
  preference and add exact `MARANTZ_DEVICE` selection.
- Revalidate expired identity/protocol after failed/no-result discovery for VPN
  fallback; never mask ambiguity or changed identity.
- Preserve one primitive per connection, aliases, raw mode, soft standby/on cycle,
  installation and ambiguous-retry protection.
- Add compatibility evidence, contribution/security/licensing guidance, issue
  templates, ignore rules, macOS CI, fixtures and release checks.

Other-device tests are simulations. Physical write/range/wake/soft-cycle checks
remain manual. See [release verification](docs/RELEASE_READINESS.md) for local,
container and hosted CI results.
