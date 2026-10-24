# Security and privacy

LAN control may accept commands without authentication and uses unencrypted
plaintext. Network access can grant power/mute/volume control. Never expose TCP
23, discovery or receiver web endpoints through public port forwarding or an
unauthenticated proxy. Use trusted LAN access and normal network isolation.

Raw mode bypasses built-in semantics/volume policy. Its argument is never executed
locally and CR/LF injection is rejected, but the receiver interprets the supplied
single command. No reset feature is provided; do not send destructive commands.

Transactions have absolute deadlines and bounded responses. No ambiguous setter
is replayed. A lost reply may still mean an action occurred; query state first.
Unknown queries block corresponding built-in writes; observed queries do not
prove setter availability or safe volume levels on another model.

Discovery and XML are untrusted. Metadata GETs stay on the responding IPv4 address,
without redirects/proxies, and have time/size/declaration limits. Broad UPnP
results require vendor metadata; HEOS is only a hint. Automatic selection needs a
PW? reply. These measures do not authenticate devices on a hostile LAN. Printed
metadata/replies are sanitized to exclude terminal control bytes.

The cache contains private addresses, UDN, metadata URL and friendly name. It is
written atomically with restrictive file permissions. Identity/protocol checks
are required on reuse, including expired VPN fallback, but are not cryptographic
authentication. Delete `~/Library/Caches/marantz/` on macOS or
`${XDG_CACHE_HOME:-$HOME/.cache}/marantz/` on Linux safely, or set TTL 0 to disable.
No telemetry, account credentials or external service is required.

Debug/captures/cache files can expose room names, addresses and machine paths.
Redact before sharing and never commit them. Ignore rules cover common local
artifacts. Working-tree cleanup does not erase Git history or commit metadata;
the owner must review those separately before first publication.

No published private security contact or supported release series exists yet.
Do not post exploit details/private data in public bugs. Use a maintainer's private
reporting channel once one is established.
