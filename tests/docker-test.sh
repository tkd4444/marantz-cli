#!/bin/bash
# Official Linux images; only a disposable source snapshot is mounted read-only.
set -eu
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
command -v docker >/dev/null || { printf 'Docker is required.\n' >&2; exit 1; }
docker version
docker info --format 'Docker server: {{.ServerVersion}} ({{.OSType}}/{{.Architecture}})'
temporary=$(mktemp -d)
containers=()
cleanup() {
    # Bash 3.2 treats expansion of an empty array as unset under set -u.
    if [ "${#containers[@]}" -gt 0 ]; then
        for container in "${containers[@]}"; do
            docker rm -f "$container" >/dev/null 2>&1 || true
        done
    fi
    rm -rf -- "$temporary"
}
trap 'cleanup' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Read the current working files, including uncommitted edits/new public files.
# Git's ignore rules exclude assistant state; no .git or developer HOME is copied.
python3 - "$root" "$temporary/source" <<'PY'
from pathlib import Path
import shutil
import subprocess
import sys
source, destination = map(Path, sys.argv[1:])
files = subprocess.check_output(["git", "-C", str(source), "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
for name in set(files.split(b"\0")) - {b""}:
    relative = Path(name.decode())
    original = source / relative
    if original.is_symlink():
        raise SystemExit("Source snapshots must not follow symlinks: " + str(relative))
    if original.is_file():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
print("Snapshot: current working files, without Git metadata or ignored files")
PY

failed=0
results=()
for target in ubuntu:24.04,linux/arm64 ubuntu:24.04,linux/amd64 debian:12,linux/arm64; do
    image=${target%,*}
    platform=${target#*,}
    printf '\nTesting %s on %s\n' "$image" "$platform"
    if ! docker pull --platform "$platform" "$image"; then
        results+=("$target: FAIL (image pull)")
        failed=1
        continue
    fi
    if ! container=$(docker create --platform "$platform" \
        --mount "type=bind,source=$temporary/source,target=/source,readonly" \
        "$image" /bin/bash -ceu '
            export DEBIAN_FRONTEND=noninteractive
            if ! apt-get update > /tmp/dependencies.log 2>&1 ||
               ! apt-get install -y --no-install-recommends python3 bash mawk mandoc man-db shellcheck passwd util-linux >> /tmp/dependencies.log 2>&1; then
                cat /tmp/dependencies.log
                exit 1
            fi
            # Ubuntu minimal images divert man to a placeholder even after
            # man-db installation. Restore only that viewer inside this container.
            if [ -x /usr/bin/man.REAL ]; then
                rm -f /usr/bin/man
                dpkg-divert --quiet --rename --remove /usr/bin/man
            fi
            mkdir /work /tmp/marantz-test-home
            cp -R /source/. /work/
            useradd --uid 10001 --no-create-home --home-dir /tmp/marantz-test-home marantz-test
            chown -R marantz-test /work /tmp/marantz-test-home
            uname -sm
            python3 --version
            bash --version
            shellcheck --version
            cd /work
            runuser -u marantz-test -- env HOME=/tmp/marantz-test-home XDG_CACHE_HOME= PYTHONDONTWRITEBYTECODE=1 ./tests/check.sh
        '); then
        results+=("$target: FAIL (container creation)")
        failed=1
        continue
    fi
    containers+=("$container")
    # Inspect exit status separately: docker start's attachment status is not the
    # test process result. An exec-format error identifies unavailable emulation.
    attached=0
    docker start -a "$container" || attached=$?
    status=$(docker inspect --format '{{.State.ExitCode}}' "$container")
    if [ "$status" = 0 ] && [ "$attached" = 0 ]; then
        results+=("$target: PASS")
    else
        results+=("$target: FAIL (exit $status; check dependency, emulation or test output above)")
        failed=1
    fi
    docker rm "$container" >/dev/null
done
printf '\nLinux matrix results:\n'
printf '%s\n' "${results[@]}"
cleanup
trap - EXIT
exit "$failed"
