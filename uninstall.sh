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
[ "$prefix" != / ] || { printf 'Use the same local prefix supplied to install.sh.\n' >&2; exit 2; }
if [ -d "$prefix" ] && [ "$(cd -- "$prefix" && pwd -P)" = / ]; then
    printf 'The filesystem root is not an installation prefix.\n' >&2; exit 2
fi
rm -f -- "$prefix/bin/marantz" "$prefix/libexec/marantz-transport.py" "$prefix/libexec/marantz-discovery.py" "$prefix/share/man/man1/marantz.1"
printf 'Removed marantz from %s. User files and disposable cache were preserved.\n' "$prefix"
