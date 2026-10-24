#!/bin/bash
# Local/CI checks. Network tests use loopback fakes exclusively.
set -eu
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
export PYTHONDONTWRITEBYTECODE=1
for script in bin/marantz install.sh uninstall.sh tests/check.sh tests/docker-test.sh; do
    /bin/bash -n "$script"
done
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck --shell=bash bin/marantz install.sh uninstall.sh tests/check.sh tests/docker-test.sh
else
    printf 'ShellCheck unavailable; Bash syntax checks passed.\n'
fi
python3 -B tests/check_public.py
mandoc -T lint man/marantz.1
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
mandoc -T ascii man/marantz.1 > "$temporary/man.txt"
for flag in -h --help help; do
    ./bin/marantz "$flag" > "$temporary/$flag.txt"
done
cmp "$temporary/-h.txt" "$temporary/--help.txt"
cmp "$temporary/-h.txt" "$temporary/help.txt"
if command -v git >/dev/null && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git diff --check
fi
python3 -B -m unittest discover -s tests -v
