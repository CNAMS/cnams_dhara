#!/usr/bin/env bash
# One command from a failing seed to a rendered timeline.
#
# If diagnosis takes more than one command it will not happen at 11 PM, and the
# simulator's value halves. That is the whole design constraint of this script.
#
#   ./scripts/replay_seed.sh 4471            # full timeline
#   ./scripts/replay_seed.sh 4471 r0         # just record r0
#   ./scripts/replay_seed.sh 4471 r0 quiet   # and on a healthy network
#
# The third argument matters more than it looks: if a failure reproduces under
# `quiet` it is a merge bug, not a network one, and that halves the search space
# before any code is read.
set -euo pipefail

SEED="${1:?usage: replay_seed.sh <seed> [record-id] [preset]}"
RECORD="${2:-}"
PRESET="${3:-hostile}"

cd "$(dirname "$0")/../dhara-py"

ARGS=(--replay "$SEED" --preset "$PRESET")
[ -n "$RECORD" ] && ARGS+=(--record "$RECORD")

exec python -m sim.runner "${ARGS[@]}"
