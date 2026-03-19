from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP timestamps
FIXED_MTIME = 0                       # deterministic TAR/GZ mtime


EXCLUDE_DIRS = {
    ".git",
    ".github",
    "dist",
    "tests",
    "__MACOSX",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}

GOVERNANCE_EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

FORBIDDEN_METADATA_SEGMENTS = ("__MACOSX",)
FORBIDDEN_METADATA_FILENAMES = {".DS_Store", "Icon\r"}

BASELINE_REQUIRED_PATHS = (
    "scripts/migrate_session_state.py",
    "governance/render/intent_router.py",
    "governance/render/delta_renderer.py",
    "governance/render/token_guard.py",
    "governance/render/render_contract.py",
    "governance/assets/catalogs/AUDIT_REASON_CANONICAL_MAP.json",
    "governance/assets/catalogs/QUICKFIX_TEMPLATES.json",
    "governance/assets/catalogs/UX_INTENT_GOLDENS.json",
    "governance/assets/catalogs/tool_requirements.json",
)

BASELINE_REQUIRED_REASON_CODES = (
    "NOT_VERIFIED_MISSING_EVIDENCE",
    "NOT_VERIFIED_EVIDENCE_STALE",
)

CUSTOMER_SCRIPT_CATALOG_PATH = Path("governance/assets/catalogs/CUSTOMER_SCRIPT_CATALOG.json")
CUSTOMER_SCRIPT_CATALOG_SCHEMA = "governance.customer-script-catalog.v1"
WORKFLOW_TEMPLATE_CATALOG_PATHS = (
    Path("governance_content/templates/github-actions/template_catalog.json"),
    Path("templates/github-actions/template_catalog.json"),
)
WORKFLOW_TEMPLATE_CATALOG_SCHEMA = "governance.workflow-template-catalog.v1"
MARKDOWN_EXCLUDE_POLICY_PATH = Path("governance/assets/catalogs/CUSTOMER_MARKDOWN_EXCLUDE.json")
MARKDOWN_EXCLUDE_POLICY_SCHEMA = "governance.customer-markdown-exclude.v1"

CUSTOMER_DOCS_ALLOWLIST = {
    "docs/phases.md",
    "docs/install-layout.md",
    "docs/releasing.md",
    "docs/benchmarks.md",
    "docs/security-gates.md",
    "docs/customer-install-bundle-v1.md",
    "docs/release-security-model.md",
    "docs/mode-aware-repo-rules.md",
    "docs/governance_invariants.md",
    "master.md",
    "rules.md",
    "BOOTSTRAP.md",
    "CHANGELOG.md",
    "governance/assets/catalogs/CUSTOMER_SCRIPT_CATALOG.json",
    "governance/assets/catalogs/AUDIT_REASON_CANONICAL_MAP.json",
    "governance/assets/catalogs/QUICKFIX_TEMPLATES.json",
    "governance/assets/catalogs/UX_INTENT_GOLDENS.json",
    "governance/assets/catalogs/tool_requirements.json",
    "templates/github-actions/template_catalog.json",
}


def _legacy_rel_alias(rel: str) -> str:
    """Map migrated paths back to legacy relpaths used by allowlists/catalogs."""

    norm = rel.replace("\\", "/")
    if norm == "governance_content/master.md":
        return "master.md"
    if norm == "governance_content/rules.md":
        return "rules.md"
    if norm == "governance_spec/phase_api.yaml":
        return "phase_api.yaml"
    if norm.startswith("governance_content/docs/"):
        return "docs/" + norm.split("governance_content/docs/", 1)[1]
    if norm.startswith("governance_content/profiles/"):
        return "profiles/" + norm.split("governance_content/profiles/", 1)[1]
    if norm.startswith("governance_content/templates/"):
        return "templates/" + norm.split("governance_content/templates/", 1)[1]
    if norm.startswith("governance_spec/rulesets/"):
        return "rulesets/" + norm.split("governance_spec/rulesets/", 1)[1]
    return norm


def _resolve_rel_candidates(repo_root: Path, rel: str) -> list[str]:
    """Return concrete existing relpaths for a canonical/legacy entry."""

    rel_norm = rel.replace("\\", "/")
    candidates = [rel_norm]
    if rel_norm == "master.md":
        candidates.append("governance_content/master.md")
    elif rel_norm == "rules.md":
        candidates.append("governance_content/rules.md")
    elif rel_norm == "phase_api.yaml":
        candidates.append("governance_spec/phase_api.yaml")
    elif rel_norm.startswith("docs/"):
        candidates.append("governance_content/" + rel_norm)
    elif rel_norm.startswith("profiles/"):
        candidates.append("governance_content/" + rel_norm)
    elif rel_norm.startswith("templates/"):
        candidates.append("governance_content/" + rel_norm)
    elif rel_norm.startswith("rulesets/"):
        candidates.append("governance_spec/" + rel_norm)

    existing = [cand for cand in candidates if (repo_root / cand).is_file()]
    return existing or candidates


def _resolve_workflow_catalog_path(repo_root: Path) -> Path:
    for rel in WORKFLOW_TEMPLATE_CATALOG_PATHS:
        if (repo_root / rel).is_file():
            return rel
    raise SystemExit(
        "Missing workflow template catalog: "
        + ", ".join(str(p) for p in WORKFLOW_TEMPLATE_CATALOG_PATHS)
    )


def is_forbidden_metadata_path(relpath: str) -> bool:
    """Return True for macOS metadata payload paths forbidden in artifacts."""

    normalized = relpath.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if any(part in FORBIDDEN_METADATA_SEGMENTS for part in parts):
        return True
    if any(part in FORBIDDEN_METADATA_FILENAMES for part in parts):
        return True
    if any(part.startswith("._") for part in parts):
        return True
    return False


def _enforce_metadata_hygiene_on_files(files: Iterable[Path], repo_root: Path) -> None:
    """Fail closed if selected release files contain forbidden metadata entries."""

    offenders = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        if is_forbidden_metadata_path(rel):
            offenders.append(rel)
    if offenders:
        raise SystemExit(
            "Release metadata hygiene violation: forbidden files selected: " + ", ".join(sorted(offenders))
        )


def _enforce_metadata_hygiene_on_archive(artifact: Path, *, format_name: str) -> None:
    """Fail closed if built archive still contains forbidden metadata paths."""

    names: list[str] = []
    if format_name == "zip":
        with zipfile.ZipFile(artifact, "r") as zf:
            names = [n for n in zf.namelist() if n and not n.endswith("/")]
    elif format_name == "tar.gz":
        with tarfile.open(artifact, "r:gz") as tf:
            names = [m.name for m in tf.getmembers() if m.name and not m.isdir()]
    else:
        raise ValueError(f"unsupported artifact format for hygiene check: {format_name}")

    offenders = [name for name in names if is_forbidden_metadata_path(name)]
    if offenders:
        raise SystemExit(
            f"Release metadata hygiene violation in {artifact.name}: " + ", ".join(sorted(offenders))
        )


def _enforce_readme_baseline_claims(repo_root: Path) -> None:
    """Fail closed when README baseline claims are not backed by repository artifacts."""

    missing_paths = [p for p in BASELINE_REQUIRED_PATHS if not (repo_root / p).exists()]
    if missing_paths:
        raise SystemExit(
            "README baseline claims verification failed: missing required artifacts: "
            + ", ".join(sorted(missing_paths))
        )

    reason_code_candidates = (
        repo_root / "governance_runtime" / "domain" / "reason_codes.py",
        repo_root / "governance" / "domain" / "reason_codes.py",
    )
    reason_codes_path = next((p for p in reason_code_candidates if p.exists()), None)
    if reason_codes_path is None:
        raise SystemExit(
            "README baseline claims verification failed: reason code module missing "
            "(expected governance_runtime/domain/reason_codes.py)"
        )
    reason_codes_src = reason_codes_path.read_text(encoding="utf-8")
    missing_codes = [c for c in BASELINE_REQUIRED_REASON_CODES if c not in reason_codes_src]
    if missing_codes:
        raise SystemExit(
            "README baseline claims verification failed: missing reason code constants: "
            + ", ".join(sorted(missing_codes))
        )


def _enforce_readme_local_link_integrity(repo_root: Path) -> None:
    """Fail closed when root README markdown links point to missing local files."""

    readmes = ("README.md", "README-OPENCODE.md", "README-RULES.md")
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []

    for name in readmes:
        readme_path = repo_root / name
        if not readme_path.exists():
            broken.append(f"{name}:missing")
            continue
        content = readme_path.read_text(encoding="utf-8")
        for raw_target in pattern.findall(content):
            target = raw_target.strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            if target.startswith("/"):
                candidate = repo_root / target.lstrip("/")
            else:
                candidate = (readme_path.parent / target).resolve()
            if not candidate.exists():
                broken.append(f"{name}:{raw_target}")

    if broken:
        raise SystemExit(
            "README link integrity failed: unresolved local links: " + ", ".join(sorted(broken))
        )


def _load_customer_release_script_paths(repo_root: Path) -> set[str]:
    catalog_path = repo_root / CUSTOMER_SCRIPT_CATALOG_PATH
    if not catalog_path.exists():
        raise SystemExit(f"Missing customer script catalog: {CUSTOMER_SCRIPT_CATALOG_PATH}")

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {CUSTOMER_SCRIPT_CATALOG_PATH}: {exc}") from exc

    if payload.get("schema") != CUSTOMER_SCRIPT_CATALOG_SCHEMA:
        raise SystemExit(
            f"Invalid customer script catalog schema in {CUSTOMER_SCRIPT_CATALOG_PATH}: "
            f"expected {CUSTOMER_SCRIPT_CATALOG_SCHEMA}, got {payload.get('schema')!r}"
        )

    raw_scripts = payload.get("scripts")
    if not isinstance(raw_scripts, list) or not raw_scripts:
        raise SystemExit(f"{CUSTOMER_SCRIPT_CATALOG_PATH}: scripts must be a non-empty array")

    selected: set[str] = set()
    for idx, item in enumerate(raw_scripts, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"{CUSTOMER_SCRIPT_CATALOG_PATH}: scripts[{idx}] must be an object")

        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise SystemExit(f"{CUSTOMER_SCRIPT_CATALOG_PATH}: scripts[{idx}] missing non-empty path")
        rel = raw_path.replace("\\", "/")
        if not rel.startswith("scripts/"):
            raise SystemExit(f"{CUSTOMER_SCRIPT_CATALOG_PATH}: scripts[{idx}].path must be under scripts/: {rel}")

        if bool(item.get("ship_in_release")):
            selected.add(rel)

    if not selected:
        raise SystemExit(f"{CUSTOMER_SCRIPT_CATALOG_PATH}: no ship_in_release=true scripts defined")

    missing = sorted(rel for rel in selected if not (repo_root / rel).is_file())
    if missing:
        raise SystemExit(
            "Customer script catalog references missing script files: " + ", ".join(missing)
        )
    return selected


def _load_workflow_template_paths(repo_root: Path) -> set[str]:
    catalog_rel = _resolve_workflow_catalog_path(repo_root)
    catalog_path = repo_root / catalog_rel

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {catalog_rel}: {exc}") from exc

    if payload.get("schema") != WORKFLOW_TEMPLATE_CATALOG_SCHEMA:
            raise SystemExit(
            f"Invalid workflow template catalog schema in {catalog_rel}: "
            f"expected {WORKFLOW_TEMPLATE_CATALOG_SCHEMA}, got {payload.get('schema')!r}"
        )

    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        raise SystemExit(f"{catalog_rel}: templates must be a non-empty array")

    selected: set[str] = set()
    for idx, item in enumerate(raw_templates, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"{catalog_rel}: templates[{idx}] must be an object")
        raw_file = item.get("file")
        if not isinstance(raw_file, str) or not raw_file:
            raise SystemExit(f"{catalog_rel}: templates[{idx}] missing non-empty file")
        rel = raw_file.replace("\\", "/")
        legacy = rel.startswith("templates/github-actions/") and rel.endswith(".yml")
        migrated = rel.startswith("governance_content/templates/github-actions/") and rel.endswith(".yml")
        if not (legacy or migrated):
            raise SystemExit(
                f"{catalog_rel}: templates[{idx}].file must be templates/github-actions/*.yml: {rel}"
            )
        for cand in _resolve_rel_candidates(repo_root, rel):
            if (repo_root / cand).is_file():
                selected.add(cand)

    if not selected:
        raise SystemExit(f"{catalog_rel}: no valid workflow templates resolved")

    missing = sorted(rel for rel in selected if not (repo_root / rel).is_file())
    if missing:
        raise SystemExit(
            "Workflow template catalog references missing files: " + ", ".join(missing)
        )
    return selected


def _load_markdown_release_exclusions(repo_root: Path) -> set[str]:
    policy_path = repo_root / MARKDOWN_EXCLUDE_POLICY_PATH
    if not policy_path.exists():
        raise SystemExit(f"Missing markdown exclusion policy: {MARKDOWN_EXCLUDE_POLICY_PATH}")

    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {MARKDOWN_EXCLUDE_POLICY_PATH}: {exc}") from exc

    if payload.get("schema") != MARKDOWN_EXCLUDE_POLICY_SCHEMA:
        raise SystemExit(
            f"Invalid markdown exclusion policy schema in {MARKDOWN_EXCLUDE_POLICY_PATH}: "
            f"expected {MARKDOWN_EXCLUDE_POLICY_SCHEMA}, got {payload.get('schema')!r}"
        )

    raw = payload.get("release_excluded_markdown")
    if not isinstance(raw, list):
        raise SystemExit(f"{MARKDOWN_EXCLUDE_POLICY_PATH}: release_excluded_markdown must be an array")

    excluded: set[str] = set()
    for idx, entry in enumerate(raw, start=1):
        if not isinstance(entry, str) or not entry.strip():
            raise SystemExit(
                f"{MARKDOWN_EXCLUDE_POLICY_PATH}: release_excluded_markdown[{idx}] must be a non-empty string"
            )
        rel = entry.replace("\\", "/")
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or rel_path.suffix.lower() != ".md":
            raise SystemExit(
                f"{MARKDOWN_EXCLUDE_POLICY_PATH}: invalid markdown path in release_excluded_markdown[{idx}]"
            )
        if not any((repo_root / cand).is_file() for cand in _resolve_rel_candidates(repo_root, rel)):
            raise SystemExit(
                f"{MARKDOWN_EXCLUDE_POLICY_PATH}: referenced markdown file does not exist: {rel}"
            )
        excluded.add(_legacy_rel_alias(rel))

    return excluded


@dataclass(frozen=True)
class BuildPaths:
    repo_root: Path
    dist_dir: Path


def _read_governance_version(repo_root: Path) -> str:
    version_file = repo_root / "governance" / "VERSION"
    if not version_file.exists():
        raise SystemExit("governance/VERSION not found (required for build)")

    version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("governance/VERSION is empty (expected semver)")

    if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+", version):
        raise SystemExit(f"Invalid governance version in VERSION: {version} (expected semver)")

    return version


def _is_excluded(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    if any(part.startswith(".tmp_dist") for part in rel.parts):
        return True
    if any(part.startswith("tp_") for part in rel.parts):
        return True
    # Exclude AppleDouble sidecar files (resource-fork metadata).
    if any(part.startswith("._") for part in rel.parts):
        return True
    # Exclude macOS Finder metadata files.
    if any(part == "Icon\r" for part in rel.parts):
        return True
    return False


def _should_include_file(
    p: Path,
    rel: str,
    *,
    customer_release_scripts: set[str],
    shipped_workflow_templates: set[str],
    release_excluded_markdown: set[str],
) -> bool:
    rel_legacy = _legacy_rel_alias(rel)

    def _is_governance_runtime_excluded(rel_path: str) -> bool:
        if not (rel_path.startswith("governance/") or rel_path.startswith("governance_runtime/")):
            return False
        parts = rel_path.split("/")
        if any(part in GOVERNANCE_EXCLUDE_DIRS for part in parts):
            return True
        if "/tests/" in rel_path:
            return True
        name = Path(rel_path).name
        if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
            return True
        return False

    if rel in customer_release_scripts or rel_legacy in customer_release_scripts:
        return True
    if rel in shipped_workflow_templates or rel_legacy in shipped_workflow_templates:
        return True
    if rel in release_excluded_markdown or rel_legacy in release_excluded_markdown:
        return False
    name = p.name
    if name == "install.py":
        return True
    if name.upper().startswith("LICENSE") or name.upper().startswith("LICENCE"):
        return True
    if rel in {"phase_api.yaml", "governance_spec/phase_api.yaml"} or rel_legacy == "phase_api.yaml":
        return True
    # Canonical rail command templates required for strict command-surface install.
    if rel.startswith("opencode/commands/") and p.suffix.lower() == ".md":
        return True
    # Addon manifests are required at runtime for deterministic addon activation/reload.
    if (rel.startswith("profiles/addons/") or rel.startswith("governance_content/profiles/addons/") or rel_legacy.startswith("profiles/addons/")) and name.endswith(".addon.yml"):
        return True
    # Governance runtime should ship as a coherent tree, excluding only non-runtime artifacts.
    if rel.startswith("governance/"):
        return not _is_governance_runtime_excluded(rel)
    if rel.startswith("governance_runtime/"):
        if _is_governance_runtime_excluded(rel):
            return False
        if rel == "governance_runtime/VERSION":
            return True
        return p.suffix.lower() in {".py", ".json", ".yaml", ".yml", ".md"}
    # Bootstrap runtime modules required by governance entrypoints.
    if rel.startswith("bootstrap/") and p.suffix.lower() == ".py":
        return True
    # Local bootstrap runtime package.
    if rel.startswith("cli/") and p.suffix.lower() == ".py":
        return True
    if rel.startswith("governance/artifacts/opencode-plugins/") and p.suffix.lower() in {".mjs", ".js"}:
        return True
    if rel == "governance/VERSION":
        return True
    if rel.startswith("docs/") or rel.startswith("governance_content/docs/") or rel_legacy.startswith("docs/"):
        return rel in CUSTOMER_DOCS_ALLOWLIST or rel_legacy in CUSTOMER_DOCS_ALLOWLIST
    if p.suffix.lower() in {".md", ".json"}:
        return rel in CUSTOMER_DOCS_ALLOWLIST or rel_legacy in CUSTOMER_DOCS_ALLOWLIST
    return False


def _is_under(path: Path, root: Path) -> bool:
    """Return True when path is located under root."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def collect_release_files(
    repo_root: Path,
    *,
    excluded_roots: tuple[Path, ...] = (),
    customer_release_scripts: set[str],
    shipped_workflow_templates: set[str],
    release_excluded_markdown: set[str],
) -> list[Path]:
    """
    Allowlist strategy:
      - include: install.py, LICENSE*, LICENCE*, *.md, *.json,
        profiles/addons/*.addon.yml, governance/** (runtime),
        governance/artifacts/opencode-plugins/*.{mjs,js},
        scripts listed in governance/assets/catalogs/CUSTOMER_SCRIPT_CATALOG.json with ship_in_release=true,
        workflow template .yml files listed in templates/github-actions/template_catalog.json
      - exclude: .git, .github, dist, tests, caches
    Deterministic ordering (sorted by posix relpath).
    """
    out: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(_is_under(p, ex) for ex in excluded_roots):
            continue
        if _is_excluded(p, repo_root):
            continue
        rel = p.relative_to(repo_root).as_posix()
        if _should_include_file(
            p,
            rel,
            customer_release_scripts=customer_release_scripts,
            shipped_workflow_templates=shipped_workflow_templates,
            release_excluded_markdown=release_excluded_markdown,
        ):
            out.append(p)

    def key(x: Path) -> str:
        return x.relative_to(repo_root).as_posix()

    out = sorted(out, key=key)
    if not out:
        raise SystemExit("No files selected for release artifact (check include/exclude rules).")
    _enforce_runtime_imports(out, repo_root)
    _enforce_metadata_hygiene_on_files(out, repo_root)
    return out


def _enforce_runtime_imports(files: Iterable[Path], repo_root: Path) -> None:
    """Fail closed if governance entrypoints import modules outside the release payload."""

    relset = {p.relative_to(repo_root).as_posix() for p in files}
    stdlib_modules = set(getattr(sys, "stdlib_module_names", set()))
    entrypoints_root = repo_root / "governance" / "entrypoints"
    if not entrypoints_root.exists():
        raise SystemExit("Release build failed: governance/entrypoints missing")

    import_re = re.compile(r"^\s*(?:from\s+([\w\.]+)|import\s+([\w\.]+))")
    allow_prefixes = (
        "governance.",
        "governance_runtime.",
        "bootstrap.",
        "cli.",
        "yaml.",
        "artifacts.",
    )
    optional_runtime_prefixes = (
        "artifacts.",
    )
    allow_modules = {
        "yaml",
    }

    violations: list[str] = []
    for path in sorted(entrypoints_root.rglob("*.py")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if rel not in relset:
            violations.append(f"entrypoint not shipped: {rel}")
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        in_docstring = False
        for line in lines:
            token = line.lstrip()
            if token.startswith(('"""', "'''")):
                in_docstring = not in_docstring
                continue
            if in_docstring or token.startswith("#"):
                continue
            m = import_re.match(line)
            if not m:
                continue
            module = m.group(1) or m.group(2) or ""
            if not module:
                continue
            if module.startswith("."):
                continue
            root_module = module.split(".", 1)[0]
            if root_module in stdlib_modules:
                continue
            if module in allow_modules:
                continue
            if module.startswith(allow_prefixes):
                mod_path = module.replace(".", "/") + ".py"
                pkg_init = module.replace(".", "/") + "/__init__.py"
                if mod_path in relset or pkg_init in relset:
                    continue
                if module.startswith(optional_runtime_prefixes):
                    continue

            mod_path = module.replace(".", "/") + ".py"
            pkg_init = module.replace(".", "/") + "/__init__.py"
            module_file = repo_root / mod_path
            module_pkg = repo_root / pkg_init

            if mod_path in relset or pkg_init in relset:
                continue

            if module_file.exists() or module_pkg.exists():
                violations.append(f"{rel}: missing dependency {module}")
                continue

            if "." not in module:
                local_entrypoint = entrypoints_root / f"{module}.py"
                if local_entrypoint.exists():
                    if local_entrypoint.relative_to(repo_root).as_posix() not in relset:
                        violations.append(f"{rel}: missing dependency {module}")
                continue

    if violations:
        raise SystemExit(
            "Release build failed: runtime import dependencies missing from artifact: "
            + ", ".join(sorted(violations))
        )


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_zip(out_zip: Path, prefix: str, repo_root: Path, files: list[Path]) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in files:
            rel = src.relative_to(repo_root).as_posix()
            arc = f"{prefix}/{rel}"

            zi = zipfile.ZipInfo(arc)
            zi.date_time = FIXED_ZIP_DT
            zi.compress_type = zipfile.ZIP_DEFLATED

            # Deterministic, minimal permission model:
            # - install.py executable
            # - everything else 0644
            mode = 0o755 if src.name == "install.py" else 0o644
            zi.external_attr = (mode & 0xFFFF) << 16

            with src.open("rb") as fsrc, zf.open(zi, "w") as fdst:
                shutil.copyfileobj(fsrc, fdst)


def write_tar_gz(out_tgz: Path, prefix: str, repo_root: Path, files: list[Path]) -> None:
    out_tgz.parent.mkdir(parents=True, exist_ok=True)
    with out_tgz.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=FIXED_MTIME) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
                for src in files:
                    rel = src.relative_to(repo_root).as_posix()
                    arc = f"{prefix}/{rel}"

                    ti = tf.gettarinfo(str(src), arcname=arc)
                    ti.mtime = FIXED_MTIME
                    ti.uid = 0
                    ti.gid = 0
                    ti.uname = ""
                    ti.gname = ""
                    ti.mode = 0o755 if src.name == "install.py" else 0o644

                    with src.open("rb") as f:
                        tf.addfile(ti, fileobj=f)


def write_sha256sums(dist_dir: Path, artifacts: list[Path]) -> Path:
    out = dist_dir / "SHA256SUMS.txt"
    lines = []
    for a in artifacts:
        h = sha256_file(a)
        lines.append(f"{h}  {a.name}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_verification_report(dist_dir: Path, artifacts: list[Path]) -> Path:
    """Write machine-readable verification report sidecar for release artifacts."""

    artifact_hashes = {a.name: sha256_file(a) for a in artifacts}
    report = {
        "schema": "governance-verification-report.v1",
        "pytest_summary": os.environ.get("OPENCODE_PYTEST_SUMMARY", "not_provided"),
        "golden_summary": os.environ.get("OPENCODE_GOLDEN_SUMMARY", "not_provided"),
        "e2e_summary": os.environ.get("OPENCODE_E2E_SUMMARY", "not_provided"),
        "governance_lint": os.environ.get("OPENCODE_GOVERNANCE_LINT", "not_provided"),
        "readme_baseline_claims": "verified",
        "readme_link_integrity": "verified",
        "artifact_hashes": artifact_hashes,
    }
    out = dist_dir / "verification-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build deterministic release artifacts (zip + tar.gz).")
    p.add_argument("--out-dir", default="dist", help="Output directory (default: dist)")
    p.add_argument("--formats", default="zip,tar.gz", help="Comma-separated: zip, tar.gz (default: zip,tar.gz)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = (repo_root / args.out_dir).resolve()
    bp = BuildPaths(repo_root=repo_root, dist_dir=dist_dir)

    version = _read_governance_version(bp.repo_root)
    prefix = f"governance-{version}"

    _enforce_readme_baseline_claims(bp.repo_root)
    _enforce_readme_local_link_integrity(bp.repo_root)

    customer_release_scripts = _load_customer_release_script_paths(bp.repo_root)
    shipped_workflow_templates = _load_workflow_template_paths(bp.repo_root)
    release_excluded_markdown = _load_markdown_release_exclusions(bp.repo_root)

    files = collect_release_files(
        bp.repo_root,
        excluded_roots=(bp.dist_dir,),
        customer_release_scripts=customer_release_scripts,
        shipped_workflow_templates=shipped_workflow_templates,
        release_excluded_markdown=release_excluded_markdown,
    )

    formats = [s.strip().lower() for s in str(args.formats).split(",") if s.strip()]
    artifacts: list[Path] = []

    if "zip" in formats:
        out_zip = bp.dist_dir / f"{prefix}.zip"
        write_zip(out_zip, prefix=prefix, repo_root=bp.repo_root, files=files)
        _enforce_metadata_hygiene_on_archive(out_zip, format_name="zip")
        artifacts.append(out_zip)

    if "tar.gz" in formats or "tgz" in formats:
        out_tgz = bp.dist_dir / f"{prefix}.tar.gz"
        write_tar_gz(out_tgz, prefix=prefix, repo_root=bp.repo_root, files=files)
        _enforce_metadata_hygiene_on_archive(out_tgz, format_name="tar.gz")
        artifacts.append(out_tgz)

    sums = write_sha256sums(bp.dist_dir, artifacts)
    verification = write_verification_report(bp.dist_dir, artifacts)
    
    def _pretty(p: Path) -> str:
        """Pretty-print artifact paths without assuming they live under repo_root."""
        try:
            return str(p.relative_to(bp.repo_root))
        except ValueError:
            return str(p)

    print("Built artifacts:")
    for a in artifacts:
        print(f"  - {_pretty(a)}")
    print(f"  - {_pretty(sums)}")
    print(f"  - {_pretty(verification)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
