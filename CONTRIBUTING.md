# Contributing

MODEL 40n is the only device physically tested by the developer. Help from other
owners is welcome; mocks/documents never become hardware-validation claims.
Developed and tested on Marantz MODEL 40n. Compatibility with other Marantz devices is experimental or unverified unless explicitly documented.

## Checks

Bash 3.2+, Python 3.9+, `mandoc`, `man` and standard system utilities are required
on macOS/Linux; no Python packages. ShellCheck runs when available locally and is
required in CI and the Docker matrix. Debian/Ubuntu test tools:

```sh
sudo apt-get install python3 bash mawk mandoc man-db shellcheck
```

macOS ships `mandoc`/`man`; provide ShellCheck on PATH to include shell lint.
No tool is installed automatically on the development host.

```sh
./tests/check.sh
python3 -B -m unittest discover -s tests -v
./tests/docker-test.sh
```

Automated receivers must use loopback TCP/UDP/HTTP and temporary HOME/cache paths.
Clear inherited XDG cache overrides or point them inside the test's temporary
directory. Test macOS and Linux paths separately, retaining all original cases.
The Docker runner exports current working files into temporary storage, uses
official images and unprivileged test users, and removes only its own containers.
It does not test physical LAN multicast through Docker Desktop. Distinguish image
dependency problems, emulation limits and real application failures.
Never add automatic physical writes, LAN multicast tests or subnet scans. Mark
other-model behavior as simulation and cite a reference. Physical MODEL 40n
query examples are in `tests/fixtures/model40n.json`; AVR simulations are separate.

Preserve short connections, deadlines, aliases, stdout/stderr conventions,
help/man pages and installation. Never replay an ambiguous setter, execute raw
payloads, source untrusted config or add factory resets. Justify dependencies.

## Compatibility reports

Use the compatibility template and supply model/region/firmware, OS/distribution,
CPU architecture, Bash/Python,
whether evidence is a physical owner test/document/simulation, exact read-only
replies with framing, and a manufacturer reference where available:

```sh
MARANTZ_HOST=receiver.local ./bin/marantz raw 'PW?'
MARANTZ_HOST=receiver.local ./bin/marantz raw 'MV?'
MARANTZ_HOST=receiver.local ./bin/marantz raw 'MU?'
MARANTZ_HOST=receiver.local ./bin/marantz raw 'SI?'
MARANTZ_HOST=receiver.local ./bin/marantz capabilities
```

Report redacted discovery/identity behavior, VPN status, and whether direct-host
access works without multicast. Replace addresses, UDN/serials, personal room
names, usernames and paths. Do not post a complete cache/capture without review.
Silence means Unknown and can reflect standby/network settings.

Physical write checks are optional owner actions. Choose a safe listening level
and device limiter; test one feature at a time: integer level/padding, up/down
step, mute, power/wake delay, and soft cycle if desired. Check resulting state;
never repeat an ambiguous setter blindly or try a factory reset. Record each
feature separately instead of claiming blanket model support.

## Sources and licensing

Record source document/sheet/section in `docs/COMPATIBILITY.md`. Do not vendor
copyrighted manuals or implementation code without appropriate rights and
attribution. The project uses the [MIT License](LICENSE); see
[LICENSING.md](LICENSING.md) for third-party boundaries. Submit only implementation
that you have the rights to license under these terms.
