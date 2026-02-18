#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import pathlib
import sys

repo = pathlib.Path('.').resolve()

violations: list[str] = []

allow_write_text = {
    repo / 'governance' / 'infrastructure' / 'fs_atomic.py',
}
allow_legacy_write_text = {
    repo / 'diagnostics' / 'error_logs.py',
    repo / 'diagnostics' / 'workspace_lock.py',
    repo / 'governance' / 'packs' / 'pack_lock.py',
}

scan_roots = {
    repo / 'governance',
    repo / 'diagnostics',
}

for path in repo.rglob('*.py'):
    if '.venv' in path.parts or 'dist' in path.parts or '__pycache__' in path.parts:
        continue
    if not any(root in path.parents or path == root for root in scan_roots):
        continue
    text = path.read_text(encoding='utf-8', errors='replace')

    if 'Path.write_text(' in text or '.write_text(' in text:
        if path not in allow_write_text and path not in allow_legacy_write_text:
            for idx, line in enumerate(text.splitlines(), start=1):
                if '.write_text(' in line and 'tmp.write_text(' not in line:
                    violations.append(f"{path.relative_to(repo)}:{idx}: disallowed write_text usage")

    if 'render_command_profiles(shlex.split(' in text:
        violations.append(f"{path.relative_to(repo)}: disallowed render_command_profiles(shlex.split(...))")

    if 'subprocess.run([sys.executable' in text:
        violations.append(f"{path.relative_to(repo)}: disallowed subprocess.run([sys.executable, ...])")

# forbid resolve() in repo identity module except gitdir-follow helpers
repo_identity = repo / 'governance' / 'domain' / 'repo_identity.py'
if repo_identity.exists():
    text = repo_identity.read_text(encoding='utf-8', errors='replace')
    for idx, line in enumerate(text.splitlines(), start=1):
        if '.resolve(' in line and 'gitdir' not in line.lower():
            violations.append(f"{repo_identity.relative_to(repo)}:{idx}: resolve() not allowed in repo identity flow")

if violations:
    print('❌ Architecture guard violations:')
    for v in violations:
        print('-', v)
    sys.exit(1)

print('✅ grep guards passed')
PY
