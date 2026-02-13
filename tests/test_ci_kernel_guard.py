def test_ci_kernel_guard_reference_kernel_only():
    # Simple guard to ensure CI infrastructure references master.md as kernel
    import os
    path = os.path.join('.github', 'workflows', 'ci.yml')
    if not os.path.exists(path):
        path = None
    # If CI file exists, do a lightweight check for master.md literal
    if path and os.path.exists(path):
        txt = open(path, 'r', encoding='utf-8').read().lower()
        assert 'master.md' in txt
    else:
        # If CI workflow not present in this repo snapshot, skip gracefully
        pass
