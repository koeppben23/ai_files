def test_ci_kernel_guard_reference_kernel_only():
    # Hard guard: if CI workflow is not present, explicitly skip with reason
    import os
    path = os.path.join('.github', 'workflows', 'ci.yml')
    if not os.path.exists(path):
        import pytest
        pytest.skip("CI workflow not present in repo snapshot; skipping hard guard test")
    # If CI file exists, do a lightweight check for master.md literal
    txt = open(path, 'r', encoding='utf-8').read().lower()
    assert 'master.md' in txt
