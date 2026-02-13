def test_ci_kernel_guard_reference_kernel_only():
    # Hard guard: CI workflows must exist and reference the Kernel master.md
    from pathlib import Path
    import pytest
    wf_dir = Path('.github/workflows')
    if not wf_dir.exists() or not any(wf_dir.glob('*.yml')):
        pytest.fail("CI workflows missing: hard guard failure; Kernel must be guarded by real workflow templates")
    found = False
    for p in wf_dir.glob('*.yml'):
        try:
            content = p.read_text(encoding='utf-8').lower()
            if 'master.md' in content:
                found = True
                break
        except Exception:
            continue
    assert found, "No kernel (master.md) reference found in CI workflows; hard guard failed"
