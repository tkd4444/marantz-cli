# Compatibility and protocol evidence

**Marantz MODEL 40n is the ONLY device physically tested by the developer.**
Developed and tested on Marantz MODEL 40n. Compatibility with other Marantz devices is experimental or unverified unless explicitly documented.
Vendor documents, metadata, probes and simulations never count as hardware tests.
Operating-system and CPU verification is tracked separately in
[platform compatibility](PLATFORMS.md). Passing Linux/macOS tests does not expand
the physically tested receiver list.

## Matrix

| Device/family | Classification | Evidence and scope | Limitations |
| --- | --- | --- | --- |
| MODEL 40n | Developer physically tested | PW/MV/MU/SI queries; original read-only SSDP/cache observations; exact fixtures | Physical setters, ranges, wake/audio timing and soft cycle remain manual |
| SR/NR/AV models in 2013/2014 charts, including NR1605, SR5009, SR6009, SR7009, AV7702 | Documented but untested | Manufacturer shared ASCII TCP commands and numeric/source syntax; selected simulations | No developer hardware tests; firmware/region/model differences remain |
| SR6015 / newer CINEMA receivers | Experimental | Example official sources establish network/IP control, not complete old-chart equivalence | Port-23 coverage, readiness, discovery and writes unverified by developer |
| PM7000N / other network stereo products | Experimental | Network/standby control documented; HEOS is only a discovery hint | Shared command coverage and scale remain unknown |
| Other Denon/Marantz ASCII TCP devices | Experimental | Parsers may work after observed queries | No vendor-wide claim or developer hardware tests |
| HEOS-only, AirPlay-only, legacy `@`, serial-only products | Transports/dialects not implemented | No port-1255 JSON, AirPlay control, legacy translation or serial I/O | Discovery is not command support; this boundary does not establish hardware capabilities |

## Primary sources inspected

1. [Official SR7005 downloads](https://www.marantz.com/product/archive-av-receivers/sr7005/SR7005.html)
   link the [2013 SR/NR workbook](https://www.marantz.com/on/demandware.static/-/Library-Sites-marantz_northamerica_shared/default/dw3e9bd206/archive-downloads/2013-marantz_av_sr_nr_protocol_v07.xls).
   `Control protocol` describes ASCII/CR on TCP 23. Rows 130–143 describe
   minimum/fractional encoding and four seconds after PWON. `Command List`
   distinguishes models and references a separate traditional `@` dialect.
2. The same page links the [2014 SR/NR workbook](https://www.marantz.com/on/demandware.static/-/Library-Sites-marantz_northamerica_shared/default/dwd4037f30/archive-downloads/marantz-2014-nr-series---sr-series-rs232-ip-protocol.xls).
   `Control protocol` rows 6–10 name NR1605/SR5009/SR6009/SR7009/AV7702.
   Rows 139–152 describe minimum codes, half-step examples and a one-second
   PWON delay. These differences preclude a universal dB conversion here.
3. [HEOS CLI specification, Connection section](https://assets.denon.com/DocumentMaster/us/HEOS_CLI_ProtocolSpecification-Version.pdf)
   documents ACT-Denon SSDP. HEOS JSON control is on port 1255; only discovery
   is reused here, not its control/reboot operations.
4. [UPnP Device Architecture 1.1, discovery](https://openconnectivity.org/upnp-specs/UPnP-arch-DeviceArchitecture-v1.1.pdf)
   defines root searches. Vendor-filtered results still need protocol checks.
5. [SR6015 specifications](https://www.marantz.com/en/product/archive-av-receivers/sr6015/SR6015.html)
   identify IP/RS232 control, which alone does not establish shared command coverage.
6. [CINEMA 40 Network Control](https://manuals.marantz.com/cinema40/NA/EN/HJWMSYmehwmguq.php)
   and [PM7000N manual, Network Control](https://manuals.marantz.com/PM7000N/EU/EN/pdf/PM7000N_EU_EN.pdf)
   describe different standby defaults. Owners must check network availability.

Inspected 2026-10-23. Vendor files were read in temporary storage and are not
redistributed. No third-party implementation code was imported.

## Contract and boundaries

- One CR-terminated primitive per connection, including preflight queries.
- Compact `PW?`, `MV?`, `MU?`, `SI?`; exact MODEL 40n regression fixtures.
- Query volume accepts `MVxx` or documented `MVxx5`. Output is an encoded level,
  not dB/percent. Sentinel/minimum semantics are model-specific.
- Absolute writes remain integer two-digit commands and the existing 0–98 policy,
  configurable within 0–99. This does not establish a safe hardware listening range.
  Relative/raw operations bypass the absolute-setting policy.
- Source tokens preserve known separators; no source writes/zone/reset APIs added.
- Spaced MV advisories are ignored as values. The advisory test is a defensive
  synthetic fixture, not an additional physical observation.
- Four-second default PWON delay covers the older inspected requirement. Owner
  firmware/audio readiness may need more time; the delay is configurable.
- Queries gate writes. Silence/malformed data means Unknown, not Unsupported.
  Successful queries do not certify setters; control capabilities stay Unknown.
- Devices silent for volume queries in standby need manual power-on before volume
  changes. No speculative wake follows an unknown volume query.
- `identify` uses metadata for automatic selection. Explicit hosts have Unknown
  identity; no identity protocol command is guessed. Bonjour resolves explicit
  `.local` names only; automatic Bonjour service browsing is not implemented.

Start owner validation with read-only queries, redact private details, and label
each observed feature separately. See [CONTRIBUTING.md](../CONTRIBUTING.md).
