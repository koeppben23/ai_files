"""Main orchestrator for Phase-6 internal review loop.

Coordinates the PolicyResolver, LLMCaller, and ResponseValidator to run
the Phase-6 review loop. This is the ONLY module that should be called
by entrypoints.

The orchestrator:
- Reads state_doc but NEVER mutates it
- Returns a structured ReviewResult
- Does NOT persist events (entrypoint handles persistence)
- Does NOT derive commands_home (it is injected)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from governance_runtime.application.services.phase6_review_orchestrator.policy_resolver import (
    BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
    PolicyResolver,
)
from governance_runtime.application.services.phase6_review_orchestrator.llm_caller import (
    LLMCaller,
    LLMResponse,
    SubprocessResult,
)
import subprocess as _subprocess


def _run_subprocess(cmd: str) -> SubprocessResult:
    """Execute a subprocess and return SubprocessResult."""
    result = _subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return SubprocessResult(
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        returncode=result.returncode,
    )
from governance_runtime.application.services.phase6_review_orchestrator.response_validator import (
    ResponseValidator,
    ValidationResult,
)
from governance_runtime.application.services.phase6_review_orchestrator.review_result import (
    CompletionStatus,
    ReviewIteration,
    ReviewLoopResult,
    ReviewOutcome,
    ReviewResult,
)
from governance_runtime.shared.number_utils import coerce_int as _coerce_int

# Import StateNormalizer for canonical state access
from governance_runtime.application.services.state_normalizer import normalize_to_canonical
from governance_runtime.application.services.plan_reader import read_plan_body
from governance_runtime.shared.hash_utils import sha256_text as _sha256_text


@dataclass
class ReviewDependencies:
    """Injectable dependencies for the review loop.

    Allows testing by injecting mock implementations.
    """

    policy_resolver: PolicyResolver
    llm_caller: LLMCaller
    response_validator: ResponseValidator

    @classmethod
    def default(cls) -> ReviewDependencies:
        """Create default dependencies."""
        import os
        return cls(
            policy_resolver=PolicyResolver(),
            llm_caller=LLMCaller(
                env_reader=lambda key: os.environ.get(key),
                subprocess_runner=lambda cmd: _run_subprocess(cmd),
            ),
            response_validator=ResponseValidator(),
        )

    @classmethod
    def from_module_hooks(cls) -> ReviewDependencies:
        """Create dependencies using module-level hooks.

        This allows tests to mock the module-level functions.
        """
        # Import at runtime to allow mocking
        from governance_runtime.application.services.phase6_review_orchestrator import (
            _get_policy_resolver,
            _get_llm_caller,
            _get_response_validator,
        )
        return cls(
            policy_resolver=_get_policy_resolver(),
            llm_caller=_get_llm_caller(),
            response_validator=_get_response_validator(),
        )


@dataclass(frozen=True)
class ReviewLoopConfig:
    """Configuration for the review loop."""

    commands_home: Path
    session_path: Path
    max_iterations: int = 3
    min_iterations: int = 1
    force_stable_digest: bool = False

    @classmethod
    def from_state(
        cls,
        *,
        state: Mapping[str, object],
        session_path: Path,
        commands_home: Path,
    ) -> ReviewLoopConfig:
        """Create config from state values.

        Args:
            state: The SESSION_STATE dict.
            session_path: Path to the session state file.
            commands_home: Path to the commands directory.
        """
        review_block_raw = state.get("ImplementationReview")
        review_block = dict(review_block_raw) if isinstance(review_block_raw, dict) else {}

        max_iterations = _coerce_int(
            review_block.get("max_iterations")
            or review_block.get("MaxIterations")
            or state.get("phase6_max_review_iterations")
            or state.get("phase6MaxReviewIterations")
            or 3
        )
        max_iterations = min(max(max_iterations, 1), 3)

        min_iterations = _coerce_int(
            review_block.get("min_self_review_iterations")
            or review_block.get("MinSelfReviewIterations")
            or state.get("phase6_min_self_review_iterations")
            or state.get("phase6MinSelfReviewIterations")
            or 1
        )
        min_iterations = max(1, min(min_iterations, max_iterations))

        force_stable = bool(state.get("phase6_force_stable_digest", False))

        return cls(
            commands_home=commands_home,
            session_path=session_path,
            max_iterations=max_iterations,
            min_iterations=min_iterations,
            force_stable_digest=force_stable,
        )


def run_review_loop(
    *,
    state_doc: dict,
    config: ReviewLoopConfig,
    dependencies: ReviewDependencies | None = None,
    json_loader: Callable[[Path], dict] | None = None,
    context_writer: Callable[[Path, dict], None] | None = None,
    clock: Callable[[], str] | None = None,
    schema_path_resolver: Callable[[Path], Path] | None = None,
) -> ReviewResult:
    """Run the Phase-6 internal review loop.

    This is the main entry point for the orchestrator. It:
    1. Reads state from state_doc (never mutates it)
    2. Runs the review loop with the configured components
    3. Returns a structured ReviewResult

    The entrypoint is responsible for:
    - Applying the result to state via result.to_state_updates()
    - Persisting audit events via result.to_audit_events()
    - Writing the modified state to disk

    Args:
        state_doc: The session state document (READ ONLY).
        config: Configuration for the review loop.
        dependencies: Injectable dependencies (for testing).
        json_loader: Injectable JSON loader for reading plan records.
        context_writer: Injectable context writer for LLM calls.
        clock: Injectable clock function for timestamps.
        schema_path_resolver: Injectable path resolver for schema path.

    Returns:
        ReviewResult with the outcome of the review loop.
    """
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    # Use canonical state for field access
    canonical = normalize_to_canonical(state)

    # Check phase using canonical field
    phase_text = str(canonical.get("phase") or "").strip()
    if not phase_text.startswith("6"):
        return ReviewResult(loop_result=None)

    # Initialize components (use injected or module hooks for testability)
    if dependencies is not None:
        policy_resolver = dependencies.policy_resolver
        llm_caller = dependencies.llm_caller
        response_validator = dependencies.response_validator
    else:
        # Use module hooks which can be mocked in tests
        deps = ReviewDependencies.from_module_hooks()
        policy_resolver = deps.policy_resolver
        llm_caller = deps.llm_caller
        response_validator = deps.response_validator

    if hasattr(llm_caller, "set_workspace_root"):
        llm_caller.set_workspace_root(config.session_path.parent)

    # Get initial state values using canonical fields
    review_block = canonical.get("implementation_review") or {}

    iteration = _coerce_int(
        review_block.get("iteration")
        or canonical.get("phase6_review_iterations")
    )
    iteration = min(max(iteration, 0), config.max_iterations)

    prev_digest = str(
        review_block.get("prev_impl_digest")
        or canonical.get("phase6_prev_impl_digest")
        or ""
    ).strip()
    curr_digest = str(
        review_block.get("curr_impl_digest")
        or canonical.get("phase6_curr_impl_digest")
        or ""
    ).strip()

    base_seed = str(
        canonical.get("phase5_plan_record_digest")
        or "phase6"
    )
    if not prev_digest:
        prev_digest = f"sha256:{_sha256_text(base_seed + ':initial')}"
    if not curr_digest:
        curr_digest = f"sha256:{_sha256_text(base_seed + ':0')}"

    # Load policy and mandate
    mandate_text = ""
    effective_review_policy = ""
    if llm_caller.is_configured:
        mandate_schema = policy_resolver.load_mandate_schema()
        if mandate_schema:
            mandate_text = mandate_schema.mandate_text

        _clock = clock
        _schema_resolver = schema_path_resolver
        if _clock is None:
            from datetime import datetime, timezone
            _clock = lambda: datetime.now(timezone.utc).isoformat()
        if _schema_resolver is None:
            _schema_resolver = lambda p: p

        policy_result = policy_resolver.load_effective_review_policy(
            state=state,
            commands_home=config.commands_home,
            clock=_clock,
            schema_path_resolver=_schema_resolver,
        )
        if not policy_result.is_available and llm_caller.is_configured:
            return ReviewResult(
                loop_result=ReviewLoopResult(
                    iterations=(),
                    final_iteration=iteration,
                    max_iterations=config.max_iterations,
                    min_iterations=config.min_iterations,
                    prev_digest=prev_digest,
                    curr_digest=curr_digest,
                    revision_delta="changed",
                    completion_status=CompletionStatus.PHASE6_IN_PROGRESS,
                    implementation_review_complete=False,
                    blocked=True,
                    block_reason="effective-review-policy-unavailable",
                    block_reason_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
                    recovery_action="Ensure rulebooks and addons are loadable and contain valid policy content.",
                )
            )
        effective_review_policy = policy_result.policy_text

    # Get implementation context
    ticket = str(state.get("Ticket") or state.get("ticket") or "").strip()
    task = str(state.get("Task") or state.get("task") or "").strip()
    plan_text = read_plan_body(config.session_path, json_loader=json_loader)
    impl_summary = _build_implementation_summary(state)

    # Get review output schema
    mandate_schema = policy_resolver.load_mandate_schema()
    output_schema_text = mandate_schema.review_output_schema_text if mandate_schema else ""

    # Run the loop
    iterations: list[ReviewIteration] = []
    initial_digest_stable = bool(prev_digest and curr_digest and prev_digest == curr_digest)
    revision_delta = "none" if initial_digest_stable else "changed"
    llm_approve = False
    complete = False

    while iteration < config.max_iterations and not complete:
        iteration += 1
        previous = curr_digest
        # Keep digest stable if force_stable_digest is set AND either:
        # - We're past iteration 1, OR
        # - The initial state had stable digests (prev == curr)
        if config.force_stable_digest and (iteration >= 2 or initial_digest_stable):
            curr_digest = previous
        else:
            curr_digest = f"sha256:{_sha256_text(base_seed + ':' + str(iteration))}"
        revision_delta = "none" if curr_digest == previous else "changed"

        # Call LLM if executor is configured
        llm_result: ValidationResult | None = None
        llm_response: LLMResponse | None = None
        if llm_caller.is_configured:
            context = llm_caller.build_context(
                ticket=ticket,
                task=task,
                plan_text=plan_text,
                implementation_summary=impl_summary,
                mandate=mandate_text,
                effective_review_policy=effective_review_policy,
                output_schema_text=output_schema_text,
            )
            context_file = Path.home() / ".governance" / "review" / "llm_impl_review_context.json"
            llm_response = llm_caller.invoke(context=context, context_file=context_file, context_writer=context_writer)
            llm_result = response_validator.validate(
                llm_response.stdout,
                mandates_schema=mandate_schema.raw_schema if mandate_schema else None,
            )

            if llm_result.is_approve:
                llm_approve = True
                if iteration >= config.max_iterations:
                    complete = True
                elif iteration >= config.min_iterations and revision_delta == "none":
                    complete = True

        # Complete if digest is stable and we've met minimum iterations (even without LLM)
        if not complete and iteration >= config.min_iterations and revision_delta == "none":
            complete = True

        # Create iteration result
        it = ReviewIteration(
            iteration=iteration,
            input_digest=previous,
            output_digest=curr_digest,
            revision_delta=revision_delta,
            outcome=ReviewOutcome.COMPLETED if complete else ReviewOutcome.REVISED,
            llm_invoked=llm_response.invoked if llm_response else False,
            llm_valid=llm_result.valid if llm_result else False,
            llm_verdict=llm_result.verdict if llm_result else "unknown",
            llm_findings=llm_result.findings if llm_result else [],
            llm_response_raw=llm_response.stdout[:1000] if llm_response else None,
        )
        iterations.append(it)

        prev_digest = previous
        if complete:
            break

    loop_result = ReviewLoopResult(
        iterations=tuple(iterations),
        final_iteration=iteration,
        max_iterations=config.max_iterations,
        min_iterations=config.min_iterations,
        prev_digest=prev_digest,
        curr_digest=curr_digest,
        revision_delta=revision_delta,
        completion_status=CompletionStatus.PHASE6_COMPLETED if complete else CompletionStatus.PHASE6_IN_PROGRESS,
        implementation_review_complete=complete,
    )

    return ReviewResult(loop_result=loop_result)


def _build_implementation_summary(state: dict) -> str:
    """Build a human-readable implementation summary from state."""
    changed_files = (
        state.get("implementation_changed_files")
        or state.get("implementation_package_changed_files")
        or []
    )
    domain_changed = (
        state.get("implementation_domain_changed_files")
        or state.get("implementation_package_domain_changed_files")
        or []
    )
    checks = state.get("implementation_checks_executed") or []
    checks_ok = bool(state.get("implementation_checks_ok", False))

    parts: list[str] = []
    if changed_files:
        parts.append(f"Changed files ({len(changed_files)}): " + ", ".join(str(f) for f in changed_files[:20]))
    if domain_changed:
        parts.append(f"Domain files changed ({len(domain_changed)}): " + ", ".join(str(f) for f in domain_changed[:20]))
    if checks:
        parts.append(f"Checks executed ({len(checks)}): " + ", ".join(str(c) for c in checks))
    if checks_ok:
        parts.append("Checks result: PASS")
    else:
        parts.append("Checks result: FAIL or not executed")

    return "\n".join(parts) if parts else "No implementation data available."
