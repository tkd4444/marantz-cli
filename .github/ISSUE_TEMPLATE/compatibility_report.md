---
name: Device compatibility report
about: Help validate a model without conflating documentation, simulations and hardware
title: "Compatibility: MODEL "
---

## Device and evidence

- Exact model, region and firmware:
- OS/distribution, CPU architecture, Bash/Python and CLI revision:
- Physical owner test / manufacturer document / simulation (choose explicitly):
- Manufacturer protocol reference and relevant section, if available:

MODEL 40n is the only device physically tested by the developer. An owner report
can validate individual features without certifying all commands on the model.

## Read-only results

- `PW?`:
- `MV?`:
- `MU?`:
- `SI?`:
- `capabilities` output, exit code and framing details:

Quote responses literally, noting CR or CRLF. Missing replies mean Unknown.

## Discovery and network

- SSDP / root discovery / explicit `.local` / cached address:
- Multiple candidates? Does exact selection work?
- VPN multicast behavior versus direct LAN TCP:
- Network Control/standby settings:

## Optional manual write observations

Leave blank unless the owner voluntarily tested a feature safely. List each
verified command, chosen safe level, resulting state and wake timing separately.
No automatic write tests or factory resets. Never replay ambiguous setters blindly.

## Privacy review

Remove actual IPs, UDN/serials, personal names, room names, credentials and machine
paths from all diagnostics before posting. Do not upload the complete cache.
