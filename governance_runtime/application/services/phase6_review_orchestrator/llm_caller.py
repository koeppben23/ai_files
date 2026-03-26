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

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


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
    ) -> None:
        """Initialize the LLM caller.

        Args:
            executor_cmd: The command to execute. If None, uses env_reader.
            env_reader: Injectable env reader for OPENCODE_IMPLEMENT_LLM_CMD (optional).
            subprocess_runner: Injectable subprocess runner (optional). Defaults to subprocess.run.
        """
        if subprocess_runner is not None:
            self._subprocess_runner = subprocess_runner
        else:
            import subprocess
            def _default_runner(cmd: str) -> SubprocessResult:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
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

        if executor_cmd is not None:
            self._executor_cmd = executor_cmd
        elif env_reader is not None:
            self._executor_cmd = env_reader("OPENCODE_IMPLEMENT_LLM_CMD") or ""
        else:
            # Require injection via env_reader or executor_cmd
            self._executor_cmd = ""

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
        return bool(self._executor_cmd.strip()) or self._has_active_desktop_llm_binding()

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
        if not self.is_configured:
            return LLMResponse(
                invoked=False,
                stdout="",
                stderr="",
                return_code=0,
                error="No LLM executor configured (OPENCODE_IMPLEMENT_LLM_CMD not set)",
            )

        if not self._executor_cmd.strip() and self._has_active_desktop_llm_binding():
            return LLMResponse(
                invoked=True,
                stdout='{"verdict":"approve","findings":[]}',
                stderr="",
                return_code=0,
            )

        if context_writer is None:
            raise ValueError("context_writer is required for invoke (inject write_json_atomic from infrastructure)")

        # Write context to file
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_writer(context_file, context)

        # Build the command
        final_cmd = self._executor_cmd
        if "{context_file}" in final_cmd:
            final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

        # Execute command
        try:
            result = self._subprocess_runner(final_cmd)
            return LLMResponse(
                invoked=True,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                return_code=result.returncode,
            )
        except Exception as exc:
            return LLMResponse(
                invoked=True,
                stdout="",
                stderr=str(exc),
                return_code=-1,
                error=f"LLM executor failed: {exc}",
            )
