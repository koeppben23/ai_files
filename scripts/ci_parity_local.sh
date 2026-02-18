#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PR_TITLE_VALUE="${PR_TITLE:-}"
SKIP_PR_TITLE=0
ALLOW_DIRTY=0
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${TMPDIR:-/tmp}/governance-ci-parity-venv}"
CONFIG_ROOT="${CONFIG_ROOT:-/tmp/opencode-ci-parity}"

usage() {
  cat <<'EOF'
Usage: scripts/ci_parity_local.sh [options]

Runs a local CI parity check aligned with .github/workflows/ci.yml.

Options:
  --pr-title "<title>"    PR title to validate against Conventional Commits regex.
                           You can also set PR_TITLE in the environment.
  --skip-pr-title          Skip PR title validation.
  --allow-dirty            Do not fail when git working tree is dirty at the end.
  --python <bin>           Python binary to use (default: python3 or PYTHON_BIN).
  --venv-dir <path>        Virtualenv path (default: /tmp/governance-ci-parity-venv).
  --config-root <path>     Installer smoke-test config root (default: /tmp/opencode-ci-parity).
  -h, --help               Show this help.

Examples:
  scripts/ci_parity_local.sh --pr-title "feat(governance): add principal factory flow for profiles and addons"
  PR_TITLE="fix(governance): normalize profile calibration and consistency checks" scripts/ci_parity_local.sh
  scripts/ci_parity_local.sh --skip-pr-title --allow-dirty
EOF
}

run_step() {
  local label="$1"
  shift
  echo
  echo "==> ${label}"
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-title)
      PR_TITLE_VALUE="$2"
      shift 2
      ;;
    --skip-pr-title)
      SKIP_PR_TITLE=1
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --venv-dir)
      VENV_DIR="$2"
      shift 2
      ;;
    --config-root)
      CONFIG_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ ! -d "${VENV_DIR}" ]]; then
  run_step "Creating virtual environment (${VENV_DIR})" "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
PYTEST="${VENV_DIR}/bin/pytest"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: Python virtual environment is missing at ${VENV_DIR}."
  exit 2
fi

if ! "${PY}" -m pytest --version >/dev/null 2>&1; then
  run_step "Installing local test dependencies (pip, pytest)" "${PY}" -m pip install --upgrade pip
  run_step "Installing pytest" "${PIP}" install pytest
fi

if [[ "${SKIP_PR_TITLE}" -eq 0 ]]; then
  if [[ -z "${PR_TITLE_VALUE}" ]]; then
    echo "ERROR: PR title check is enabled but no title was provided."
    echo "Provide --pr-title \"<title>\" or set PR_TITLE, or use --skip-pr-title."
    exit 2
  fi

  run_step "Validating PR title (Conventional Commits)" env PR_TITLE="${PR_TITLE_VALUE}" "${PY}" - <<'PY'
import os
import re
import sys

title = os.environ.get("PR_TITLE") or ""
pattern = r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: .+'
if not re.match(pattern, title):
    print("ERROR: PR title is not Conventional Commits compliant.")
    print("Title:", title)
    print("Expected pattern:", pattern)
    print("Examples: feat(installer): add manifest gate | fix: handle unicode paths | chore: cleanup")
    sys.exit(1)

print("OK: PR title is Conventional Commits compliant:", title)
PY
fi

cd "${REPO_ROOT}"

run_step "Running spec guards" "${PYTEST}" -q -m spec
run_step "Running build tests" "${PYTEST}" -q -m build
run_step "Building release artifacts" "${PY}" scripts/build.py
run_step "Validating addon manifests" "${PY}" scripts/validate_addons.py --repo-root .
run_step "Running installer tests" "${PYTEST}" -q -m installer
run_step "Running governance validation tests" "${PYTEST}" -q -m governance
run_step "Running governance end-to-end tests" "${PYTEST}" -q -m e2e_governance
run_step "Running release readiness tests" "${PYTEST}" -q -m release

run_step "Installer smoke test (dry-run)" "${PY}" install.py --dry-run --force --config-root "${CONFIG_ROOT}"
run_step "Installer smoke test (install)" "${PY}" install.py --force --no-backup --config-root "${CONFIG_ROOT}"
run_step "Installer smoke test (uninstall)" "${PY}" install.py --uninstall --force --config-root "${CONFIG_ROOT}"

echo
echo "==> Checking working tree cleanliness"
STATUS="$(git -C "${REPO_ROOT}" status --short)"
if [[ -n "${STATUS}" ]]; then
  echo "Working tree is not clean:"
  echo "${STATUS}"
  if [[ "${ALLOW_DIRTY}" -eq 0 ]]; then
    echo "ERROR: working tree must be clean for strict CI parity."
    echo "Use --allow-dirty to downgrade this to a warning."
    exit 1
  fi
  echo "WARNING: continuing because --allow-dirty is enabled."
else
  echo "Working tree is clean."
fi

echo
echo "OK: local CI parity check completed successfully."
