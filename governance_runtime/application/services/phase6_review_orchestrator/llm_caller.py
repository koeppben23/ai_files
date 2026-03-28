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
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def _parse_json_events_to_text(response_text: str) -> str:
    """Parse OpenCode JSON events and extract assistant text response.

    When --format json is used, opencode run returns NDJSON events.
    We extract the text from 'text' type events.

    Args:
        response_text: Raw stdout from opencode run --format json

    Returns:
        Extracted text content from assistant response, or original text if parsing fails.
    """
    if not response_text.strip():
        return response_text

    try:
        lines = response_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                event_type = event.get("type")
                if event_type == "text":
                    part = event.get("part", {})
                    text_content = part.get("text", "")
                    if text_content:
                        return text_content
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    return response_text

from governance_runtime.infrastructure.governance_binding_resolver import (
    GovernanceBindingResolutionError,
    resolve_governance_binding,
)
from governance_runtime.infrastructure.opencode_model_binding import resolve_active_opencode_model


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
            import subprocess
            def _default_runner(cmd: str, env: dict[str, str] | None = None) -> SubprocessResult:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                return SubprocessResult(
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    returncode=result.returncode,
                )
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

    def _run_subprocess(self, cmd: str, env: dict[str, str] | None = None) -> SubprocessResult:
        try:
            return self._subprocess_runner(cmd, env)
        except TypeError:
            return self._subprocess_runner(cmd)

    def _build_bridge_env(self) -> dict[str, str] | None:
        if self._bridge_env_factory is None:
            return None
        return self._bridge_env_factory()

    def _resolve_desktop_bridge_cmd(self) -> str:
        if self._workspace_root is None:
            return ""
        candidate_env = str(self._env_reader("OPENCODE_CLI_BIN") or "").strip()
        candidate_paths: list[str] = []
        if candidate_env:
            candidate_paths.append(candidate_env)
        candidate_paths.append("/Applications/OpenCode.app/Contents/MacOS/opencode-cli")
        which_opencode = shutil.which("opencode")
        if which_opencode:
            candidate_paths.append(which_opencode)
        which_opencode_cli = shutil.which("opencode-cli")
        if which_opencode_cli:
            candidate_paths.append(which_opencode_cli)

        cli_bin = ""
        for token in candidate_paths:
            path = Path(token)
            if path.exists() and path.is_file() and (path.stat().st_mode & 0o111):
                cli_bin = str(path)
                break
        if not cli_bin:
            return ""

        model_info = resolve_active_opencode_model()
        model_token = ""
        if isinstance(model_info, dict):
            provider = str(model_info.get("provider") or "").strip()
            model_id = str(model_info.get("model_id") or "").strip()
            if provider and model_id:
                model_token = f"{provider}/{model_id}"

        message = (
            "Read the attached implementation review context JSON and produce only valid JSON conforming to the output schema."
        )
        cmd_parts = [
            shlex.quote(cli_bin),
            "run",
            "--continue",
            "--format",
            "json",
            "--file",
            "{context_file}",
        ]
        if model_token:
            cmd_parts.extend(["--model", shlex.quote(model_token)])
        cmd_parts.append(shlex.quote(message))
        return " ".join(cmd_parts)

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

        if not pipeline_mode:
            bridge_cmd = self._resolve_desktop_bridge_cmd()
            if not bridge_cmd:
                return LLMResponse(
                    invoked=False,
                    stdout="",
                    stderr="",
                    return_code=0,
                    error=(
                        "Direct mode review binding resolved to active chat binding, but no callable desktop bridge is available."
                    ),
                    pipeline_mode=False,
                    binding_role="review",
                    binding_source=binding_source,
                )
            if context_writer is None:
                raise ValueError("context_writer is required for invoke (inject write_json_atomic from infrastructure)")

            context_file.parent.mkdir(parents=True, exist_ok=True)
            context_writer(context_file, context)
            final_cmd = bridge_cmd.replace("{context_file}", shlex.quote(str(context_file)))
            try:
                result = self._run_subprocess(final_cmd, self._build_bridge_env())
                stdout = _parse_json_events_to_text(result.stdout or "")
                return LLMResponse(
                    invoked=True,
                    stdout=stdout,
                    stderr=result.stderr or "",
                    return_code=result.returncode,
                    pipeline_mode=False,
                    binding_role="review",
                    binding_source=binding_source,
                )
            except Exception as exc:
                return LLMResponse(
                    invoked=True,
                    stdout="",
                    stderr=str(exc),
                    return_code=-1,
                    error=f"LLM executor failed: {exc}",
                    pipeline_mode=False,
                    binding_role="review",
                    binding_source=binding_source,
                )

        if context_writer is None:
            raise ValueError("context_writer is required for invoke (inject write_json_atomic from infrastructure)")

        # Write context to file
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_writer(context_file, context)

        # Build the command
        final_cmd = binding_value
        if "{context_file}" in final_cmd:
            final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

        # Execute command
        try:
            result = self._run_subprocess(final_cmd)
            return LLMResponse(
                invoked=True,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                return_code=result.returncode,
                pipeline_mode=True,
                binding_role="review",
                binding_source=binding_source,
            )
        except Exception as exc:
            return LLMResponse(
                invoked=True,
                stdout="",
                stderr=str(exc),
                return_code=-1,
                error=f"LLM executor failed: {exc}",
                pipeline_mode=True,
                binding_role="review",
                binding_source=binding_source,
            )
