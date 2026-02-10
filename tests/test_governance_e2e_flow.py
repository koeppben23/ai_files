from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from dataclasses import dataclass
from pathlib import Path
import hashlib

import pytest

from .util import REPO_ROOT, read_text, run_install


@dataclass(frozen=True)
class AddonManifest:
    addon_key: str
    addon_class: str
    rulebook: str
    capabilities_any: tuple[str, ...]
    capabilities_all: tuple[str, ...]
    signals: tuple[tuple[str, str], ...]


def _commands_dir(config_root: Path) -> Path:
    return config_root / "commands"


def _parse_addon_manifest(path: Path) -> AddonManifest:
    text = read_text(path)

    def get_scalar(key: str) -> str:
        m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        assert m, f"Missing '{key}' in {path.name}"
        return m.group(1).strip().strip('"').strip("'")

    addon_key = get_scalar("addon_key")
    addon_class = get_scalar("addon_class")
    rulebook = get_scalar("rulebook")

    def get_list(key: str) -> tuple[str, ...]:
        m = re.search(rf"^{re.escape(key)}:\s*$", text, flags=re.MULTILINE)
        if not m:
            return tuple()
        vals: list[str] = []
        for line in text[m.end() :].splitlines():
            l = line.rstrip("\n")
            if not l.strip():
                continue
            mm = re.match(r"^\s{2}-\s*(.*?)\s*$", l)
            if mm:
                vals.append(mm.group(1).strip().strip('"').strip("'"))
                continue
            if l.startswith("  ") and not l.strip():
                continue
            if l.startswith(" "):
                continue
            break
        return tuple(v for v in vals if v)

    capabilities_any = get_list("capabilities_any")
    capabilities_all = get_list("capabilities_all")
    signals = tuple(
        (m.group(1).strip(), m.group(2).strip().strip('"').strip("'"))
        for m in re.finditer(r"^\s*-\s*([a-z_]+):\s*(.*?)\s*$", text, flags=re.MULTILINE)
    )
    return AddonManifest(
        addon_key=addon_key,
        addon_class=addon_class,
        rulebook=rulebook,
        capabilities_any=capabilities_any,
        capabilities_all=capabilities_all,
        signals=signals,
    )


def _repo_relpaths(repo_root: Path) -> list[str]:
    rels = []
    for p in repo_root.rglob("*"):
        if p.is_file():
            rels.append(p.relative_to(repo_root).as_posix())
    return rels


def _matches_file_glob(glob_pattern: str, repo_relpaths: list[str]) -> bool:
    for rel in repo_relpaths:
        candidates = [glob_pattern]
        if glob_pattern.startswith("**/"):
            # fnmatch treats this as requiring at least one segment;
            # allow root match too (e.g. **/nx.json -> nx.json)
            candidates.append(glob_pattern[3:])
        if any(fnmatch(rel, c) for c in candidates):
            return True
    return False


def _has_maven_dep(repo_root: Path, dep: str) -> bool:
    if ":" not in dep:
        return False
    group_id, artifact_id = dep.split(":", 1)
    target = f"{group_id}:{artifact_id}"
    for coord in _iter_maven_coords(repo_root):
        if coord == target:
            return True
    return False


def _has_maven_dep_prefix(repo_root: Path, dep_prefix: str) -> bool:
    for coord in _iter_maven_coords(repo_root):
        if coord.startswith(dep_prefix):
            return True
    return False


def _iter_maven_coords(repo_root: Path):
    pattern = re.compile(
        r"<dependency>.*?<groupId>\s*([^<\s]+)\s*</groupId>.*?<artifactId>\s*([^<\s]+)\s*</artifactId>.*?</dependency>",
        flags=re.DOTALL,
    )
    for pom in repo_root.rglob("pom.xml"):
        text = pom.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            yield f"{m.group(1)}:{m.group(2)}"


def _has_code_regex(repo_root: Path, pattern: str) -> bool:
    rx = re.compile(pattern)
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".jar", ".class"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if rx.search(text):
            return True
    return False


def _has_config_key_prefix(repo_root: Path, prefix: str) -> bool:
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".yml", ".yaml", ".properties", ".conf", ".toml"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if prefix in text:
            return True
    return False


def _signal_matches(signal_key: str, signal_value: str, repo_root: Path, repo_relpaths: list[str]) -> bool:
    if signal_key == "file_glob":
        return _matches_file_glob(signal_value, repo_relpaths)
    if signal_key == "workflow_file":
        return signal_value in repo_relpaths
    if signal_key == "maven_dep":
        return _has_maven_dep(repo_root, signal_value)
    if signal_key == "maven_dep_prefix":
        return _has_maven_dep_prefix(repo_root, signal_value)
    if signal_key == "code_regex":
        return _has_code_regex(repo_root, signal_value)
    if signal_key == "config_key_prefix":
        return _has_config_key_prefix(repo_root, signal_value)
    return False


def _infer_capabilities(repo_root: Path, repo_relpaths: list[str]) -> set[str]:
    caps: set[str] = set()

    if (repo_root / "pom.xml").exists() or (repo_root / "build.gradle").exists() or (repo_root / "src" / "main" / "java").exists():
        caps.add("java")

    if _has_maven_dep(repo_root, "org.springframework:spring-context") or _has_maven_dep(repo_root, "org.springframework.kafka:spring-kafka"):
        caps.add("spring")

    if _has_maven_dep(repo_root, "org.springframework.kafka:spring-kafka") or _has_code_regex(repo_root, r"@KafkaListener") or _has_config_key_prefix(repo_root, "spring.kafka."):
        caps.add("kafka")

    if _has_maven_dep(repo_root, "org.liquibase:liquibase-core") or _has_config_key_prefix(repo_root, "spring.liquibase."):
        caps.add("liquibase")

    if any(_matches_file_glob(p, repo_relpaths) for p in ["**/openapi*.yml", "**/openapi*.yaml", "**/openapi*.json", "**/swagger*.yml", "**/swagger*.yaml", "**/swagger*.json"]):
        caps.add("openapi")

    if any(_matches_file_glob("**/*.feature", repo_relpaths) for _ in [0]):
        caps.add("cucumber")

    if any(_matches_file_glob(p, repo_relpaths) for p in ["**/nx.json"]):
        caps.add("nx")

    if _has_code_regex(repo_root, r"@angular/core"):
        caps.add("angular")

    if any(_matches_file_glob(p, repo_relpaths) for p in ["**/cypress.config.ts", "**/cypress.config.js", "**/*.cy.ts", "**/*.cy.js"]):
        caps.add("cypress")

    if all((repo_root / p).exists() for p in ["master.md", "rules.md", "SESSION_STATE_SCHEMA.md"]):
        caps.add("governance_docs")

    return caps


def _evaluate_addons(commands_dir: Path, repo_root: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """Returns (status_by_addon, blocked_next_codes, warnings)."""
    manifests_dir = commands_dir / "profiles" / "addons"
    manifests = sorted(manifests_dir.glob("*.addon.yml"))
    assert manifests, f"No addon manifests found in {manifests_dir}"

    statuses: dict[str, str] = {}
    blocked: list[str] = []
    warnings: list[str] = []

    relpaths = _repo_relpaths(repo_root)
    capabilities = _infer_capabilities(repo_root, relpaths)

    for mf in manifests:
        addon = _parse_addon_manifest(mf)
        caps_all_ok = all(c in capabilities for c in addon.capabilities_all)
        caps_any_ok = (not addon.capabilities_any) or any(c in capabilities for c in addon.capabilities_any)
        required = caps_all_ok and caps_any_ok
        if not required:
            required = any(_signal_matches(k, v, repo_root, relpaths) for k, v in addon.signals)
        if not required:
            statuses[addon.addon_key] = "skipped"
            continue

        rb_path = commands_dir / "profiles" / addon.rulebook
        if rb_path.exists():
            statuses[addon.addon_key] = "loaded"
            continue

        statuses[addon.addon_key] = "missing-rulebook"
        if addon.addon_class == "required":
            blocked.append(f"BLOCKED-MISSING-ADDON:{addon.addon_key}")
        else:
            warnings.append(f"WARN-MISSING-ADDON:{addon.addon_key}")

    return statuses, blocked, warnings


def _activation_delta_hashes(commands_dir: Path, repo_root: Path) -> tuple[str, str]:
    manifests = sorted((commands_dir / "profiles" / "addons").glob("*.addon.yml"))
    relpaths = _repo_relpaths(repo_root)
    capabilities = sorted(_infer_capabilities(repo_root, relpaths))

    addon_scan = hashlib.sha256()
    for mf in manifests:
        addon_scan.update(mf.name.encode("utf-8"))
        addon_scan.update(b"\0")
        addon_scan.update(mf.read_bytes())
        addon_scan.update(b"\n")

    repo_facts = hashlib.sha256()
    for cap in capabilities:
        repo_facts.update(cap.encode("utf-8"))
        repo_facts.update(b"\n")

    return addon_scan.hexdigest(), repo_facts.hexdigest()


def _activation_delta_gate(previous: tuple[str, str, tuple], current: tuple[str, str, tuple]) -> str:
    prev_addon_hash, prev_repo_hash, prev_outcome = previous
    cur_addon_hash, cur_repo_hash, cur_outcome = current
    if prev_addon_hash == cur_addon_hash and prev_repo_hash == cur_repo_hash and prev_outcome != cur_outcome:
        return "BLOCKED-ACTIVATION-DELTA-MISMATCH"
    return "OK"


def _render_short_intent(intent: str, state: dict) -> list[str]:
    status = str(state.get("status", "NOT_VERIFIED"))
    if intent == "where_am_i":
        phase = str(state.get("phase", "unknown"))
        gate = str(state.get("active_gate", "none"))
        nxt = str(state.get("next", "none"))
        return [f"status: {status}", f"phase/gate: {phase} / {gate}", f"next: {nxt}"]
    if intent == "what_blocks_me":
        reason = str(state.get("reason_code", "none"))
        nxt = str(state.get("next_command", "none"))
        return [f"status: {status}", f"primary blocker: {reason}", f"next: {nxt}"]
    if intent == "what_now":
        nxt = str(state.get("next", "none"))
        return [f"status: {status}", f"next: {nxt}"]
    return [f"status: {status}", "next: none"]


@pytest.mark.e2e_governance
def test_e2e_capability_first_activation_with_hard_signal_fallback(tmp_path: Path):
    config_root = tmp_path / "opencode-config-e2e-capabilities"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "cap-repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Capability-first path: cypress capability from config file should activate addon
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / "cypress.config.ts").write_text("export default {}\n", encoding="utf-8")
    statuses, blocked, warnings = _evaluate_addons(commands, repo)
    assert statuses.get("frontendCypress") == "loaded"
    assert not blocked
    assert not any(w.endswith(":frontendCypress") for w in warnings)

    # Hard-signal fallback path: cucumber capability intentionally absent (no .feature),
    # but maven_dep_prefix signal should still activate addon
    (repo / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>io.cucumber</groupId>
      <artifactId>cucumber-java</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )
    statuses, blocked, warnings = _evaluate_addons(commands, repo)
    assert statuses.get("cucumber") == "loaded"
    assert not blocked
    assert not any(w.endswith(":cucumber") for w in warnings)


@pytest.mark.e2e_governance
def test_e2e_activation_delta_is_bit_identical_when_inputs_unchanged(tmp_path: Path):
    config_root = tmp_path / "opencode-config-e2e-delta"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "delta-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "nx.json").write_text("{}\n", encoding="utf-8")
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / "cypress.config.ts").write_text("export default {}\n", encoding="utf-8")

    first = _evaluate_addons(commands, repo)
    second = _evaluate_addons(commands, repo)

    assert first == second, "activation outcome must be bit-identical when manifests and repo facts are unchanged"


@pytest.mark.e2e_governance
def test_e2e_activation_delta_blocks_when_hashes_unchanged_but_outcome_drifts(tmp_path: Path):
    config_root = tmp_path / "opencode-config-e2e-delta-block"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "delta-repo-block"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "nx.json").write_text("{}\n", encoding="utf-8")

    statuses, blocked, warnings = _evaluate_addons(commands, repo)
    baseline_outcome = (tuple(sorted(statuses.items())), tuple(sorted(blocked)), tuple(sorted(warnings)))
    addon_hash, repo_hash = _activation_delta_hashes(commands, repo)

    drifted_outcome = (tuple(sorted(statuses.items())), tuple(sorted(blocked + ["BLOCKED-MISSING-ADDON:simulated"])), tuple(sorted(warnings)))

    gate = _activation_delta_gate(
        (addon_hash, repo_hash, baseline_outcome),
        (addon_hash, repo_hash, drifted_outcome),
    )
    assert gate == "BLOCKED-ACTIVATION-DELTA-MISMATCH"


@pytest.mark.e2e_governance
def test_e2e_short_intent_goldens_are_stable():
    fixture = REPO_ROOT / "diagnostics" / "UX_INTENT_GOLDENS.json"
    assert fixture.exists(), "Missing diagnostics/UX_INTENT_GOLDENS.json"
    payload = json.loads(read_text(fixture))

    assert payload.get("$schema") == "opencode.ux-intent-goldens.v1"
    assert payload.get("version") == "1"
    cases = payload.get("cases")
    assert isinstance(cases, list) and cases, "UX intent goldens must define at least one case"

    for case in cases:
        assert isinstance(case, dict)
        intent = str(case.get("intent", "")).strip()
        assert intent in {"where_am_i", "what_blocks_me", "what_now"}
        state = case.get("state")
        expected = case.get("expected")
        assert isinstance(state, dict)
        assert isinstance(expected, list) and expected
        rendered = _render_short_intent(intent, state)
        assert rendered == expected, f"Golden mismatch for case {case.get('id', 'unknown')}"
        assert 1 <= len(rendered) <= 3


@pytest.mark.e2e_governance
def test_e2e_governance_flow_required_block_then_reload_and_advisory_warn(tmp_path: Path):
    """
    End-to-end governance flow simulation:
    1) required addon missing -> BLOCKED
    2) rulebook re-added (nachladen) -> loaded and unblocked
    3) advisory addon missing -> WARN and non-blocking
    """
    config_root = tmp_path / "opencode-config-e2e"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "fake-repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Signals: Angular/Nx + Cypress
    (repo / "nx.json").write_text("{}\n", encoding="utf-8")
    (repo / "master.md").write_text("# Governance entrypoint\n", encoding="utf-8")
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / "cypress.config.ts").write_text("export default {}\n", encoding="utf-8")

    required_rb = commands / "profiles" / "rules.frontend-angular-nx-templates.md"
    advisory_rb = commands / "profiles" / "rules.frontend-cypress-testing.md"
    assert required_rb.exists(), f"Missing installed required rulebook: {required_rb}"
    assert advisory_rb.exists(), f"Missing installed advisory rulebook: {advisory_rb}"

    # Step 1: required missing -> BLOCKED
    required_backup = required_rb.with_suffix(required_rb.suffix + ".bak")
    required_rb.rename(required_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("angularNxTemplates") == "missing-rulebook"
        assert "BLOCKED-MISSING-ADDON:angularNxTemplates" in blocked
        assert not any(w.endswith(":angularNxTemplates") for w in warnings)
    finally:
        required_backup.rename(required_rb)

    # Step 2: re-evaluation after reload -> loaded + no required-block
    statuses, blocked, _warnings = _evaluate_addons(commands, repo)
    assert statuses.get("angularNxTemplates") == "loaded"
    assert "BLOCKED-MISSING-ADDON:angularNxTemplates" not in blocked
    assert statuses.get("principalExcellence") == "loaded"
    assert statuses.get("riskTiering") == "loaded"
    assert statuses.get("scorecardCalibration") == "loaded"

    # Step 3: advisory missing -> WARN (non-blocking)
    advisory_backup = advisory_rb.with_suffix(advisory_rb.suffix + ".bak")
    advisory_rb.rename(advisory_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("frontendCypress") == "missing-rulebook"
        assert "WARN-MISSING-ADDON:frontendCypress" in warnings
        assert "BLOCKED-MISSING-ADDON:frontendCypress" not in blocked
    finally:
        advisory_backup.rename(advisory_rb)

    # Step 3b: shared advisory contract missing -> WARN (non-blocking)
    shared_rb = commands / "profiles" / "rules.principal-excellence.md"
    assert shared_rb.exists(), f"Missing installed shared rulebook: {shared_rb}"
    shared_backup = shared_rb.with_suffix(shared_rb.suffix + ".bak")
    shared_rb.rename(shared_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("principalExcellence") == "missing-rulebook"
        assert "WARN-MISSING-ADDON:principalExcellence" in warnings
        assert "BLOCKED-MISSING-ADDON:principalExcellence" not in blocked
    finally:
        shared_backup.rename(shared_rb)

    # Step 4: maven_dep signal (kafka) -> required missing rulebook must BLOCK
    (repo / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )
    kafka_rb = commands / "profiles" / "rules.backend-java-kafka-templates.md"
    assert kafka_rb.exists(), f"Missing installed kafka rulebook: {kafka_rb}"
    kafka_backup = kafka_rb.with_suffix(kafka_rb.suffix + ".bak")
    kafka_rb.rename(kafka_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("kafka") == "missing-rulebook"
        assert "BLOCKED-MISSING-ADDON:kafka" in blocked
        assert not any(w.endswith(":kafka") for w in warnings)
    finally:
        kafka_backup.rename(kafka_rb)


@pytest.mark.e2e_governance
def test_e2e_kafka_addon_not_activated_for_java_or_spring_without_kafka_signals(tmp_path: Path):
    config_root = tmp_path / "opencode-config-e2e-kafka-scope"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "java-spring-no-kafka"
    repo.mkdir(parents=True, exist_ok=True)

    (repo / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )

    statuses, blocked, warnings = _evaluate_addons(commands, repo)
    assert statuses.get("kafka") == "skipped"
    assert "BLOCKED-MISSING-ADDON:kafka" not in blocked
    assert not any(w.endswith(":kafka") for w in warnings)
