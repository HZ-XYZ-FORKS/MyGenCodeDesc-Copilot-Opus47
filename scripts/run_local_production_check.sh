#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

if [[ $# -ge 1 ]]; then
  LOG_FILE="$1"
else
  TS="$(date +"%Y%m%d_%H%M%S")"
  LOG_FILE="$LOG_DIR/production_check_$TS.log"
fi

mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

TOTAL_STEPS=0
FAILED_STEPS=0

stamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

log() {
  echo "[$(stamp)] $*" | tee -a "$LOG_FILE"
}

run_step() {
  local name="$1"
  shift

  TOTAL_STEPS=$((TOTAL_STEPS + 1))
  log "START step=$TOTAL_STEPS name=\"$name\""
  log "CMD   $*"

  if "$@" >>"$LOG_FILE" 2>&1; then
    log "PASS  step=$TOTAL_STEPS name=\"$name\""
  else
    local rc=$?
    FAILED_STEPS=$((FAILED_STEPS + 1))
    log "FAIL  step=$TOTAL_STEPS name=\"$name\" rc=$rc"
  fi

  log "END   step=$TOTAL_STEPS name=\"$name\""
  echo >>"$LOG_FILE"
}

log "Local production check started"
log "Repository root: $ROOT"

cd "$ROOT" || exit 1

run_step "System E2E robust tests" python3 -m pytest tests/test_system_e2e_robust.py -q
run_step "Scale matrix git-local (AlgA/B/C)" python3 -m pytest tests/test_scale_matrix_git_local.py -q --durations=5
run_step "Scale matrix git-remote (AlgA/B/C)" python3 -m pytest tests/test_scale_matrix_git_remote.py -q --durations=5
run_step "Scale matrix svn-local (AlgA/B/C)" python3 -m pytest tests/test_scale_matrix_svn_local.py -q --durations=5
run_step "Scale matrix svn-remote (AlgA/B/C)" python3 -m pytest tests/test_scale_matrix_svn_remote.py -q --durations=5
if [[ "${SKIP_SCALE_MAGNITUDE:-0}" != "1" ]]; then
  run_step "Scale magnitude git-local (AlgA/B/C, 500x50x5 + determinism + RSS)" \
    env RUN_SCALE_MAGNITUDE=1 python3 -m pytest tests/test_scale_magnitude.py -q --durations=5
else
  log "SKIP  Scale magnitude (SKIP_SCALE_MAGNITUDE=1)"
fi
run_step "Full regression tests" python3 -m pytest tests/ -q
run_step "Rich system demo" "$ROOT/scripts/run_system_demo.sh"

PASSED_STEPS=$((TOTAL_STEPS - FAILED_STEPS))

if [[ $FAILED_STEPS -eq 0 ]]; then
  RESULT="PASS"
  EXIT_CODE=0
else
  RESULT="FAIL"
  EXIT_CODE=1
fi

log "FINAL RESULT=$RESULT total_steps=$TOTAL_STEPS passed_steps=$PASSED_STEPS failed_steps=$FAILED_STEPS"
log "Log file: $LOG_FILE"

exit $EXIT_CODE
