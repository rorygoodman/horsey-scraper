#!/usr/bin/env bash
# Forward the first positional arg as the worker count (default 3).
# Examples:
#   ./run.sh        # 3 workers (default)
#   ./run.sh 1      # serial — exactly the pre-parallel behavior
#   ./run.sh 5      # 5 parallel workers (max 10)
WORKERS="${1:-3}"
exec ./gradlew run --quiet --args="$WORKERS"
