"""LLM caller for Phase-6 review.

Handles invocation of the LLM executor subprocess for implementation review.
This component is responsible for:
- Checking if an LLM executor is configured
- Building the LLM context and instructions
- Executing the subprocess and capturing output
- Returning the raw response text

The caller does NOT validate the response - that's the ResponseValidator's job.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def _invoke_llm_via_server(
    prompt_text: str,
    model_info: dict | None = None,
    output_schema: dict | None = None,
    required: bool = False,
) -> str:
    """Invoke LLM via direct server API.

    This replaces subprocess("opencode run --session ...") with direct HTTP calls.
    Session ID must be set via OPENCODE_SESSION_ID environment variable.

    Args:
        prompt_text: The prompt to send
        model_info: Optional model specification from resolve_active_opencode_model()
        output_schema: Optional JSON schema for structured output
        required: If True, fail-closed when server not available

    Returns:
        LLM response text

    Raises:
        ServerNotAvailableError: If server method fails
        APIError: If OPENCODE_SESSION_ID is not set
    """
    try:
        response = send_session_prompt(
            text=prompt_text,
            model=model_info,
            output_schema=output_schema,
            required=required,
        )
        return extract_session_response(response)
    except ServerNotAvailableError:
        raise
    except Exception as exc:
        raise ServerNotAvailableError(f"Server client failed: {exc}") from exc


from governance_runtime.infrastructure.governance_binding_resolver import (
    GovernanceBindingResolutionError,
    resolve_governance_binding,
)
from governance_runtime.infrastructure.opencode_model_binding import resolve_active_opencode_model
from governance_runtime.infrastructure.opencode_server_client import (
    send_session_prompt,
    extract_session_response,
    ServerNotAvailableError,
    resolve_opencode_server_base_url,
)


@dataclass(frozen=True)
class SubprocessResult:
    """Result of a subprocess execution."""
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class LLMResponse:
    """Raw response from the LLM executor."""

    invoked: bool
    stdout: str
    stderr: str
    return_code: int
    error: str | None = None
    pipeline_mode: bool | None = None
    binding_role: str = "review"
    binding_source: str = ""
    invoke_backend: str = ""
    invoke_backend_url: str = ""
    invoke_backend_error: str = ""

    @property
    def has_output(self) -> bool:
        """Check if the LLM returned any output."""
        return bool(self.stdout and self.stdout.strip())


class LLMCaller:
    """Invokes the LLM executor for implementation review.

    This component encapsulates all subprocess execution logic.
    It does NOT validate the response - it only executes and returns raw output.
    """

    def __init__(
        self,
        *,
        executor_cmd: str | None = None,
        env_reader: Callable[[str], str | None] | None = None,
        subprocess_runner: Callable[[str], SubprocessResult] | None = None,
        bridge_env_factory: Callable[[], dict[str, str] | None] | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        """Initialize the LLM caller.

        Args:
            executor_cmd: Explicit command override (testing/injection only).
            env_reader: Injectable env reader.
            subprocess_runner: Injectable subprocess runner (optional). Defaults to subprocess.run.
            workspace_root: Workspace directory for governance-config.json lookup.
        """
        if subprocess_runner is not None:
            self._subprocess_runner = subprocess_runner
        else:
            def _default_runner(cmd: str, env: dict[str, str] | None = None) -> SubprocessResult:
                raise RuntimeError("Legacy subprocess execution is disabled; use server client path")
            self._subprocess_runner = _default_runner

        if env_reader is not None:
            self._env_reader = env_reader
        else:
            self._env_reader = lambda key: None

        self._bridge_env_factory = bridge_env_factory
        self._workspace_root = workspace_root
        self._executor_cmd = str(executor_cmd or "").strip()

    def set_workspace_root(self, workspace_root: Path | None) -> None:
        """Set workspace root used for mode-aware binding resolution."""
        self._workspace_root = workspace_root

    def _resolve_review_binding(self) -> tuple[bool, str, str]:
        """Resolve the active review binding for current workspace mode."""
        if self._executor_cmd:
            return True, self._executor_cmd, "override:executor_cmd"

        resolution = resolve_governance_binding(
            role="review",
            workspace_root=self._workspace_root,
            env_reader=self._env_reader,
            has_active_chat_binding=self._has_active_desktop_llm_binding(),
        )
        return (
            resolution.pipeline_mode,
            str(resolution.binding_value or "").strip(),
            str(resolution.source or "").strip(),
        )

    def _has_active_desktop_llm_binding(self) -> bool:
        if str(self._env_reader("OPENCODE") or "").strip() == "1":
            return True
        binding_tokens = (
            "OPENCODE_MODEL",
            "OPENCODE_MODEL_ID",
            "OPENCODE_MODEL_PROVIDER",
            "OPENCODE_MODEL_CONTEXT_LIMIT",
            "OPENCODE_CLIENT_MODEL",
            "OPENCODE_CLIENT_PROVIDER",
        )
        return any(str(self._env_reader(key) or "").strip() for key in binding_tokens)

    @property
    def is_configured(self) -> bool:
        """Check if an LLM executor is configured."""
        try:
            _pipeline_mode, binding_value, _binding_source = self._resolve_review_binding()
            return bool(binding_value)
        except GovernanceBindingResolutionError:
            return False

    def build_context(
        self,
        *,
        ticket: str,
        task: str,
        plan_text: str,
        implementation_summary: str,
        mandate: str = "",
        effective_review_policy: str = "",
        output_schema_text: str = "",
    ) -> dict[str, Any]:
        """Build the LLM context payload.

        Args:
            ticket: The ticket identifier.
            task: The task description.
            plan_text: The approved plan body.
            implementation_summary: Summary of implementation changes.
            mandate: The review mandate text.
            effective_review_policy: The effective review policy text.
            output_schema_text: The JSON schema for the expected output.

        Returns:
            Context dict to be written to a JSON file for the LLM.
        """
        instruction_parts: list[str] = []
        if mandate:
            instruction_parts.append("Apply the review mandate below to review the implementation result.")
        if effective_review_policy:
            instruction_parts.append(
                "Apply the effective review policy below for active profile and addons."
            )
        if output_schema_text:
            instruction_parts.append(
                "You MUST respond with valid JSON that conforms to the output schema below.\n"
                "Do NOT include any text outside the JSON object.\n\n"
                "Output schema:\n" + output_schema_text
            )

        context: dict[str, Any] = {
            "schema": "opencode.impl-review.llm-context.v2",
            "ticket": ticket,
            "task": task,
            "approved_plan": plan_text,
            "implementation_summary": implementation_summary,
        }
        if mandate:
            context["review_mandate"] = mandate
        if effective_review_policy:
            context["effective_review_policy"] = effective_review_policy
            context["effective_policy_loaded"] = True
        if instruction_parts:
            context["instruction"] = "\n".join(instruction_parts)

        return context

    def invoke(
        self,
        *,
        context: dict[str, Any],
        context_file: Path,
        context_writer: Callable[[Path, dict], None] | None = None,
    ) -> LLMResponse:
        """Invoke the LLM executor.

        Args:
            context: The context payload (will be written to context_file).
            context_file: Path where context JSON will be written.
            context_writer: Injectable context writer (for testing). If None,
                           raises ValueError to enforce architecture rules.

        Returns:
            LLMResponse with the raw output.
        """
        try:
            pipeline_mode, binding_value, binding_source = self._resolve_review_binding()
        except GovernanceBindingResolutionError as exc:
            return LLMResponse(
                invoked=False,
                stdout="",
                stderr="",
                return_code=0,
                error=str(exc),
                pipeline_mode=None,
                binding_role="review",
                binding_source="",
            )

        session_id = str(self._env_reader("OPENCODE_SESSION_ID") or "").strip()
        model_info = resolve_active_opencode_model(env_reader=self._env_reader)
        if not session_id and isinstance(model_info, dict):
            session_id = str(model_info.get("session_id") or "").strip()

        model_dict = None
        if model_info and isinstance(model_info, dict):
            provider = model_info.get("provider", "")
            model_id = model_info.get("model_id", "")
            if provider and model_id:
                model_dict = {"providerID": provider, "modelID": model_id}

        if not session_id:
            return LLMResponse(
                invoked=False,
                stdout="",
                stderr="[server_client] missing session id",
                return_code=1,
                error="Server session id unavailable for review invocation",
                pipeline_mode=pipeline_mode,
                binding_role="review",
                binding_source=binding_source,
                invoke_backend="server_client",
                invoke_backend_error="missing-session-id",
            )

        try:
            context_json = json.dumps(context, ensure_ascii=True, indent=2)
            output_schema_text = context.get("output_schema_text", "")
            output_schema = json.loads(output_schema_text) if output_schema_text.strip() else None

            instruction = "Review the implementation and produce valid JSON conforming to the output schema."
            if output_schema:
                instruction += f"\n\nOutput schema:\n{json.dumps(output_schema, ensure_ascii=True)}"

            prompt_text = instruction + "\n\nContext:\n" + context_json
            response_text = _invoke_llm_via_server(
                prompt_text=prompt_text,
                model_info=model_dict,
                output_schema=output_schema,
                required=True,
            )

            validator = ResponseValidator()
            validation_result = validator.validate(response_text)
            if not validation_result.valid:
                return LLMResponse(
                    invoked=True,
                    stdout=response_text,
                    stderr="[server_client] invalid review response",
                    return_code=1,
                    error=f"Response validation failed: {validation_result.findings}",
                    pipeline_mode=pipeline_mode,
                    binding_role="review",
                    binding_source=binding_source,
                    invoke_backend="server_client",
                    invoke_backend_error="invalid-review-response",
                )

            server_url = ""
            try:
                server_url = resolve_opencode_server_base_url()
            except ServerNotAvailableError:
                pass
            return LLMResponse(
                invoked=True,
                stdout=response_text,
                stderr="[server_client] Phase6 review via direct HTTP",
                return_code=0,
                pipeline_mode=pipeline_mode,
                binding_role="review",
                binding_source=binding_source,
                invoke_backend="server_client",
                invoke_backend_url=server_url,
            )
        except ServerNotAvailableError as exc:
            server_error = f"ServerNotAvailableError: {exc}"
            return LLMResponse(
                invoked=True,
                stdout="",
                stderr=f"[server_required_fail_closed] {server_error}",
                return_code=1,
                error=f"Server required but failed: {server_error}",
                pipeline_mode=pipeline_mode,
                binding_role="review",
                binding_source=binding_source,
                invoke_backend="server_client",
                invoke_backend_error=server_error,
            )
        except Exception as exc:
            server_error = f"Server client exception: {exc}"
            return LLMResponse(
                invoked=True,
                stdout="",
                stderr=f"[server_required_fail_closed] {server_error}",
                return_code=1,
                error=f"Server required but failed: {server_error}",
                pipeline_mode=pipeline_mode,
                binding_role="review",
                binding_source=binding_source,
                invoke_backend="server_client",
                invoke_backend_error=server_error,
            )
