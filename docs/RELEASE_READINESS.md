# v1.0.0 release verification

This report describes the curated release candidate, separately from operating
system and receiver compatibility. The release repository uses a fresh Git
history. No development Git objects, reflogs, original commit attribution or
historical receiver address are imported. The original development repository
is preserved separately.

Developed and tested on Marantz MODEL 40n. Compatibility with other Marantz devices is experimental or unverified unless explicitly documented.

## Candidate audit

The selected files contain application code, fixtures/tests, installation scripts,
manuals, public documentation, GitHub CI/templates and release notes. Targeted
ignore rules exclude assistant instructions/sessions, prompts, local settings,
caches, logs and build output. No ignored local files are deleted or copied.

Runtime dependencies are Bash, system tools and Python standard-library modules.
No third-party implementation or manufacturer manuals are vendored. External
protocol references remain links with their own rights. The owner explicitly
approved the exact MIT text and Copyright (c) 2026 tkd4444 attribution on
2026-10-24. The root [LICENSE](../LICENSE) matches the approved text byte for byte.

Privacy review covers public files and new commit metadata: private home paths,
private LAN endpoints, personal email attribution, credentials/key signatures,
assistant transcripts and local development files. The CLI help uses an RFC 5737
documentation address. Loopback addresses and explicit synthetic rejection
fixtures are test inputs, not real receiver endpoints or credentials.

## Verification status

- Current suite: 103 tests; all original 84 test methods remain.
- Native macOS release-copy checks: 103 run, 101 passed and 2 Linux-only
  integration tests skipped; Apple Bash 3.2/Python 3.9, empty HOME. The final
  licensed-tree rerun passed in 81.817 seconds. One earlier local 1.5-second
  discovery wall-clock assertion failed once; six unchanged focused reruns and
  the full rerun passed. No deadline assertion or application behavior was changed.
- Official-image release-copy matrix: Ubuntu 24.04 ARM64, Ubuntu 24.04 AMD64
  (emulated) and Debian 12 ARM64 each passed all 103 tests, without skips.
- Source syntax/links, ShellCheck, all help forms, manual lint/render, installed
  manual, upgrades/repeated installation and uninstall checks passed.
- Gitleaks 8.30.1 directory scan found no secrets; targeted privacy review
  found no private home paths, RFC1918 endpoints, unapproved email or local
  development artifacts in the selected public files. Eight ignore-rule samples passed.
- Author/committer preflight uses public login tkd4444 and user-confirmed
  28397501+tkd4444@users.noreply.github.com. GitHub API and SSH identities match.
  Only a fresh initial commit of the curated tree is eligible for the remote;
  verify its author/committer metadata and reachable history before pushing.
- Hosted GitHub Actions is a separate publication gate. Inspect the completed
  checks for the exact release commit in the repository Actions runs; this local
  report does not substitute for those observed results.

All device simulations use loopback TCP/UDP/HTTP. No physical receiver is contacted
and no system installation is modified. Installation tests use temporary prefixes,
including upgrades, repeated installation and uninstall preservation. The full
matrix and scope are in [PLATFORMS.md](PLATFORMS.md).

## Publication gates

1. MIT text/attribution approved; the authorized root LICENSE is included.
2. Verify public Git author/committer identity and user-confirmed noreply email;
   create and audit one clean initial commit.
3. Obtain approval for the named private GitHub repository, push only curated
   history, and verify visibility, default branch, rendering and hosted CI.
4. Prepare v1.0.0 as a draft targeting the validated commit, with reviewed notes
   and any verified source archive.
5. Stop for explicit approval before making the repository public or publishing
   the release/tag. Verify public pages, tag and downloads only after approval.

## Compatibility boundaries

See [COMPATIBILITY.md](COMPATIBILITY.md) for physical MODEL 40n observations,
documented-but-untested families and experimental products. Platform test success
is not new receiver-model evidence. Physical writes, ranges, standby networking,
wake/audio timing, Linux LAN/VPN routing and additional devices need owner tests.
The unauthenticated plaintext control port must never be exposed to the internet.
