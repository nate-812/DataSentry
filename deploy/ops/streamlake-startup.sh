#!/usr/bin/env bash
set -euo pipefail

# StreamLake 人工维护窗口启动/停止编排脚本。
# 边界：不进入 DataSentry 自动执行白名单，不打印真实 secret，不自动 cancel Flink Job。
#
# 默认云端路径：
#   /root/bin/kafka.sh start
#   /root/bin/doris.sh start
#   /root/bin/flink.sh start
#   /root/bin/spring.sh start
#   /root/bin/ai.sh start
#   cd /opt/datasentry-monitoring && docker compose start
#   /root/bin/job.sh all
#   cd /opt/datasentry-monitoring && docker compose stop
#   /root/bin/spring.sh stop
#   /root/bin/ai.sh stop
#   /root/bin/flink.sh stop
#   /root/bin/doris.sh stop
#   /root/bin/kafka.sh stop

ROOT_BIN="${STREAMLAKE_ROOT_BIN:-/root/bin}"
MONITORING_DIR="${STREAMLAKE_MONITORING_DIR:-/opt/datasentry-monitoring}"
FLINK_BIN="${STREAMLAKE_FLINK_BIN:-/opt/flink/bin/flink}"

EXPECTED_JOBS=(
  "streamlake-kline-aggregation"
  "streamlake-whale-cep"
  "streamlake-risk-control"
)

usage() {
  cat <<'USAGE'
Usage:
  streamlake-startup plan start
  streamlake-startup plan stop
  streamlake-startup status
  streamlake-startup start
  streamlake-startup stop
  streamlake-startup restart

Environment overrides:
  STREAMLAKE_ROOT_BIN=/root/bin
  STREAMLAKE_MONITORING_DIR=/opt/datasentry-monitoring
  STREAMLAKE_FLINK_BIN=/opt/flink/bin/flink
USAGE
}

require_executable() {
  local path="$1"
  if [[ ! -x "$path" ]]; then
    echo "missing executable: $path" >&2
    return 1
  fi
}

run_step() {
  local label="$1"
  shift
  echo "==> $label"
  "$@"
}

run_script_step() {
  local label="$1"
  local script="$2"
  local action="$3"

  require_executable "$script"
  run_step "$label" "$script" "$action"
}

run_monitoring() {
  local action="$1"
  if [[ ! -d "$MONITORING_DIR" ]]; then
    echo "missing monitoring directory: $MONITORING_DIR" >&2
    return 1
  fi

  run_step "monitoring docker compose $action" bash -c \
    'cd "$1" && docker compose "$2"' _ "$MONITORING_DIR" "$action"
}

flink_jobs_output() {
  if [[ ! -x "$FLINK_BIN" ]]; then
    return 1
  fi
  "$FLINK_BIN" list -r 2>/dev/null || true
}

expected_job_count() {
  local output="$1"
  local count=0
  local job

  for job in "${EXPECTED_JOBS[@]}"; do
    if grep -Fq "$job" <<<"$output"; then
      count=$((count + 1))
    fi
  done

  echo "$count"
}

submit_jobs_if_needed() {
  require_executable "$ROOT_BIN/job.sh"

  local output
  if ! output="$(flink_jobs_output)"; then
    echo "cannot inspect Flink jobs with $FLINK_BIN; refuse to run job.sh all" >&2
    return 1
  fi

  local count
  count="$(expected_job_count "$output")"

  if [[ "$count" == "${#EXPECTED_JOBS[@]}" ]]; then
    echo "all expected Flink jobs already running; skip /root/bin/job.sh all"
    return 0
  fi

  if [[ "$count" != "0" ]]; then
    echo "only $count/${#EXPECTED_JOBS[@]} expected Flink jobs are running; refuse partial duplicate submit" >&2
    echo "check Flink jobs manually before running /root/bin/job.sh all" >&2
    return 1
  fi

  run_step "submit Flink jobs" "$ROOT_BIN/job.sh" all
}

print_start_plan() {
  cat <<'PLAN'
Start plan:
  1. /root/bin/kafka.sh start
  2. /root/bin/doris.sh start
  3. /root/bin/flink.sh start
  4. /root/bin/spring.sh start
  5. /root/bin/ai.sh start
  6. cd /opt/datasentry-monitoring && docker compose start
  7. inspect Flink jobs; run /root/bin/job.sh all only when none of the fixed jobs are running

Boundary:
  人工维护窗口使用；不进入 DataSentry 自动执行白名单；不打印真实 secret；不自动 cancel Flink Job。
PLAN
}

print_stop_plan() {
  cat <<'PLAN'
Stop plan:
  1. cd /opt/datasentry-monitoring && docker compose stop
  2. /root/bin/spring.sh stop
  3. /root/bin/ai.sh stop
  4. /root/bin/flink.sh stop
  5. /root/bin/doris.sh stop
  6. /root/bin/kafka.sh stop

Boundary:
  人工维护窗口使用；不进入 DataSentry 自动执行白名单；不打印真实 secret；不自动 cancel Flink Job。
PLAN
}

start_sequence() {
  run_script_step "start Kafka" "$ROOT_BIN/kafka.sh" start
  run_script_step "start Doris" "$ROOT_BIN/doris.sh" start
  run_script_step "start Flink cluster" "$ROOT_BIN/flink.sh" start
  run_script_step "start Spring API" "$ROOT_BIN/spring.sh" start
  run_script_step "start AI Engine" "$ROOT_BIN/ai.sh" start
  run_monitoring start
  submit_jobs_if_needed
}

stop_sequence() {
  run_monitoring stop
  run_script_step "stop Spring API" "$ROOT_BIN/spring.sh" stop
  run_script_step "stop AI Engine" "$ROOT_BIN/ai.sh" stop
  run_script_step "stop Flink cluster" "$ROOT_BIN/flink.sh" stop
  run_script_step "stop Doris" "$ROOT_BIN/doris.sh" stop
  run_script_step "stop Kafka" "$ROOT_BIN/kafka.sh" stop
}

status_step() {
  local label="$1"
  local script="$2"

  echo "==> $label"
  if [[ ! -x "$script" ]]; then
    echo "missing executable: $script"
    return 0
  fi
  "$script" status || true
}

status_sequence() {
  status_step "Kafka" "$ROOT_BIN/kafka.sh"
  status_step "Doris" "$ROOT_BIN/doris.sh"
  status_step "Flink cluster" "$ROOT_BIN/flink.sh"
  status_step "Spring API" "$ROOT_BIN/spring.sh"
  status_step "AI Engine" "$ROOT_BIN/ai.sh"

  echo "==> DataSentry monitoring stack"
  if [[ -d "$MONITORING_DIR" ]]; then
    (cd "$MONITORING_DIR" && docker compose ps) || true
  else
    echo "missing monitoring directory: $MONITORING_DIR"
  fi

  echo "==> Flink jobs"
  if [[ -x "$FLINK_BIN" ]]; then
    "$FLINK_BIN" list -r || true
  else
    echo "missing executable: $FLINK_BIN"
  fi
}

main() {
  local command="${1:-}"
  local target="${2:-}"

  case "$command" in
    plan)
      case "$target" in
        start) print_start_plan ;;
        stop) print_stop_plan ;;
        *) usage; return 1 ;;
      esac
      ;;
    status)
      status_sequence
      ;;
    start)
      start_sequence
      ;;
    stop)
      stop_sequence
      ;;
    restart)
      stop_sequence
      start_sequence
      ;;
    help|-h|--help|"")
      usage
      ;;
    *)
      usage
      return 1
      ;;
  esac
}

main "$@"
