#!/bin/bash
set -eu
case "$(uname -s)" in Darwin|Linux) ;; *) printf 'Supported systems: macOS and Linux.\n' >&2; exit 1 ;; esac
prefix=/usr/local
case "$#" in
    0) ;;
    2) [ "$1" = --prefix ] || { printf 'Usage: %s [--prefix /absolute/path]\n' "$0" >&2; exit 2; }; prefix=$2 ;;
    *) printf 'Usage: %s [--prefix /absolute/path]\n' "$0" >&2; exit 2 ;;
esac
case "$prefix" in /*) ;; *) printf 'Prefix must be an absolute path.\n' >&2; exit 2 ;; esac
[ "$prefix" != / ] || { printf 'Use a local prefix such as /usr/local or ~/.local.\n' >&2; exit 2; }
if [ -d "$prefix" ] && [ "$(cd -- "$prefix" && pwd -P)" = / ]; then
    printf 'The filesystem root is not an installation prefix.\n' >&2; exit 2
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v python3 >/dev/null || { printf 'Python 3 is required (see README.md).\n' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { printf 'Python 3.9 or later is required.\n' >&2; exit 1; }
install -d "$prefix/bin" "$prefix/libexec" "$prefix/share/man/man1"
temporary=
trap '[ -z "$temporary" ] || rm -f -- "$temporary"' EXIT
replace_file() {
    # Same-directory rename avoids truncating a file used by a running command.
    temporary=$(mktemp "$2/.marantz-install.XXXXXXXX")
    install -m "$3" "$source_dir/$1" "$temporary"
    mv -f -- "$temporary" "$2/${1##*/}"
    temporary=
}
replace_file libexec/marantz-transport.py "$prefix/libexec" 644
replace_file libexec/marantz-discovery.py "$prefix/libexec" 644
replace_file man/marantz.1 "$prefix/share/man/man1" 644
replace_file bin/marantz "$prefix/bin" 755
printf 'Installed %s/bin/marantz, its helpers and man page.\n' "$prefix"
printf 'Add %s/bin to PATH if needed.\n' "$prefix"
printf 'Man page: man -M "%s/share/man" marantz\n' "$prefix"
