"""Tests for MD Python lint script."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.mark.governance
class TestMdPythonLint:
    def test_allows_fenced_code_block_examples(self):
        from scripts.lint_md_python import lint_md_file, REPO_ROOT
        import scripts.lint_md_python as lint_module
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            md_file = tmpdir / "test.md"
            md_file.write_text("""
# Example

```yaml
run: python -m pip install something
```
""")
            
            original_root = lint_module.REPO_ROOT
            lint_module.REPO_ROOT = tmpdir
            
            violations = lint_md_file(md_file)
            
            lint_module.REPO_ROOT = original_root
            
            assert violations == []
    
    def test_forbids_inline_python_execution(self):
        from scripts.lint_md_python import lint_md_file
        import scripts.lint_md_python as lint_module
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            md_file = tmpdir / "test.md"
            md_file.write_text("""
# Bad

!`${PYTHON_COMMAND} -c "import runpy"
""")
            
            original_root = lint_module.REPO_ROOT
            lint_module.REPO_ROOT = tmpdir
            
            violations = lint_md_file(md_file)
            
            lint_module.REPO_ROOT = original_root
            
            assert len(violations) == 1
            assert "Dangerous" in violations[0][1]
    
    def test_forbids_runpy_even_in_code_blocks(self):
        from scripts.lint_md_python import lint_md_file
        import scripts.lint_md_python as lint_module
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            md_file = tmpdir / "test.md"
            md_file.write_text("""
# Bad

```python
import runpy
runpy.run_path("script.py")
```
""")
            
            original_root = lint_module.REPO_ROOT
            lint_module.REPO_ROOT = tmpdir
            
            violations = lint_md_file(md_file)
            
            lint_module.REPO_ROOT = original_root
            
            assert len(violations) == 1
    
    def test_is_dangerous_execution_detects_runpy(self):
        from scripts.lint_md_python import is_dangerous_execution
        
        assert is_dangerous_execution('python -c "import runpy"') is True
        assert is_dangerous_execution("import runpy") is True
        assert is_dangerous_execution("!`${PYTHON_COMMAND}") is True
        assert is_dangerous_execution("print('hello')") is False
    
    def test_is_in_fenced_code_block(self):
        from scripts.lint_md_python import is_in_fenced_code_block
        
        lines = [
            "Text",
            "```python",
            "code here",
            "```",
            "more text",
        ]
        
        assert is_in_fenced_code_block(lines, 0) is False  # Before block
        assert is_in_fenced_code_block(lines, 2) is True   # Inside block
        assert is_in_fenced_code_block(lines, 4) is False  # After block
