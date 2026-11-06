#!/usr/bin/env bash
# Compile espeak-ng for the Linux build and stage it into inflect_addon/espeak/.
#
# Copyright (C) 2026 Subtitld contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Why not the espeakng-loader wheel, as on macOS and Windows: its Linux
# libespeak-ng needs glibc 2.29 (pow and exp), although the wheel is tagged
# manylinux_2_17, and the add-on runs on glibc 2.28. So the Linux build compiles
# the same espeak-ng commit the wheel carries (1.52.0), with the same CMake
# options, on the build's own glibc. tools/build_linux.sh runs this inside the
# AlmaLinux 8 container; it also works on any Linux with git, cmake and gcc.
#
#     tools/build_espeak.sh [work dir]      # default: build/espeak-ng
#
# tools/build_source_tarball.py ships the same commit as Corresponding Source.

set -euo pipefail

# espeakng-loader 0.2.4's espeak-ng submodule: tag 1.52.0.
ESPEAK_NG_COMMIT=4870adfa25b1a32b4361592f1be8a40337c58d6c
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(realpath -m "${1:-$ROOT/build/espeak-ng}")"
SRC="$WORK/src"
PREFIX="$WORK/prefix"

if [ ! -d "$SRC/.git" ]; then
    rm -rf "$SRC"
    git clone --quiet https://github.com/espeak-ng/espeak-ng "$SRC"
fi
git -C "$SRC" checkout --quiet "$ESPEAK_NG_COMMIT"
head="$(git -C "$SRC" rev-parse HEAD)"
[ "$head" = "$ESPEAK_NG_COMMIT" ] || { echo "espeak-ng is at $head, not $ESPEAK_NG_COMMIT" >&2; exit 1; }

rm -rf "$WORK/build" "$PREFIX"
# espeakng-loader's options (build.sh), and its -pthread on Linux. Two more:
# libsonic speeds up synthesized audio, which the add-on never asks espeak for
# (it only takes phonemes), and espeak-ng's CMake compiles the copy it fetches
# without -fPIC, which the AlmaLinux toolchain refuses in a shared library; and
# position-independent code throughout, for the same reason.
cmake -S "$SRC" -B "$WORK/build" -DBUILD_SHARED_LIBS=ON -DENABLE_TESTS=OFF -DCOMPILE_INTONATIONS=OFF \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_C_FLAGS=-pthread -DCMAKE_EXE_LINKER_FLAGS=-pthread \
    -DUSE_LIBSONIC=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON >/dev/null
cmake --build "$WORK/build" --config Release -j "$(nproc)" >/dev/null
cmake --install "$WORK/build" >/dev/null

PYTHON="${PYTHON:-python3}"
"$PYTHON" "$ROOT/tools/stage_espeak.py" --prefix "$PREFIX" --commit "$ESPEAK_NG_COMMIT"
