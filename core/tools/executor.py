import hashlib
import json
import uuid

from core.persistence.sqlite_journal import MAX_REPLAY_RESULT_BYTES, SQLiteJournal
from core.tools.base import ToolResult
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest
from core.tools.schema import validate_json_schema


class ToolExecutor:
    """Authorize, validate, and optionally journal tool executions."""

    def __init__(
        self, registry: ToolRegistry, journal: SQLiteJournal | None = None
    ) -> None:
        if journal is not None and not isinstance(journal, SQLiteJournal):
            raise TypeError("journal must be a SQLiteJournal or None.")
        self.registry = registry
        self.journal = journal

    def execute(
        self,
        request: ToolRequest,
        permission: ToolPermission,
    ) -> ToolResult:
        """Fail closed before execution and refuse previously claimed idempotency keys."""

        tool = self.registry.get(request.tool_name)

        if not permission.allows(tool.capabilities):
            return ToolResult(
                success=False,
                error=f"Permission denied for tool: {request.tool_name}",
            )

        try:
            errors = validate_json_schema(request.arguments, tool.parameters_schema)
        except (TypeError, ValueError) as exc:
            return ToolResult(
                success=False,
                error=f"Invalid tool schema for {request.tool_name}: {exc}",
            )

        if errors:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool {request.tool_name}: " + "; ".join(errors),
            )

        if self.journal is None:
            return tool.execute(**request.arguments)

        try:
            canonical_request = json.dumps(
                {"tool_name": request.tool_name, "arguments": request.arguments},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                error="Tool arguments cannot be represented safely for execution journaling.",
            )

        request_sha256 = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        execution_id = uuid.uuid4().hex
        idempotency_key = request.idempotency_key or execution_id

        try:
            record = self.journal.begin_tool_execution(
                execution_id,
                idempotency_key,
                request.tool_name,
                request_sha256,
                run_id=request.run_id,
                task_id=request.task_id,
                attempt_id=request.attempt_id,
                logical_action_id=request.logical_action_id,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=(
                    "A durable tool-execution record could not be established; "
                    f"the tool was not run ({type(exc).__name__})."
                ),
                metadata={"execution_outcome": "not_started"},
            )

        if not record["created"]:
            if record["request_sha256"] != request_sha256:
                return ToolResult(
                    success=False,
                    error="Idempotency key was already used for a different request; execution refused.",
                    metadata={
                        "idempotency_key": idempotency_key,
                        "prior_status": record["status"],
                        "execution_outcome": "not_started",
                    },
                )
            return ToolResult(
                success=False,
                error=(
                    "Duplicate tool request was not executed; a prior record exists "
                    f"with status '{record['status']}'. Reconciliation is required."
                ),
                metadata={
                    "idempotency_key": idempotency_key,
                    "prior_status": record["status"],
                    "execution_outcome": (
                        "unknown" if record["status"] in {"running", "unknown"}
                        else "already_recorded"
                    ),
                },
            )

        try:
            result = tool.execute(**request.arguments)
        except Exception as exc:
            try:
                self.journal.finish_tool_execution(
                    execution_id,
                    "unknown",
                    {"error_type": type(exc).__name__},
                )
            except Exception:
                # The durable "running" record still blocks a duplicate execution.
                pass
            raise

        terminal_status = "succeeded" if result.success else "returned_failure"
        outcome = {
            "success": result.success,
            "error_type": "ToolReturnedFailure" if not result.success else None,
        }
        replay_result = None
        replay_policy = getattr(tool, "replay_policy", "never")
        if result.success and replay_policy == "deterministic_json_v1":
            try:
                encoded_output = json.dumps(
                    result.output, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                )
                if len(encoded_output.encode("utf-8")) <= MAX_REPLAY_RESULT_BYTES:
                    replay_result = {
                        "policy": replay_policy,
                        "output": result.output,
                    }
            except (TypeError, ValueError):
                # Tool success remains recorded, but an unsafe/non-JSON output is not replayable.
                replay_result = None
        try:
            self.journal.finish_tool_execution(
                execution_id, terminal_status, outcome, replay_result=replay_result
            )
        except Exception as exc:
            # Never claim a durable success if the outcome could not be committed.
            return ToolResult(
                success=False,
                error=(
                    "The tool returned, but its outcome could not be durably recorded; "
                    "treat the result as unknown and do not repeat it automatically."
                ),
                metadata={
                    "execution_id": execution_id,
                    "execution_outcome": "unknown",
                    "journal_error_type": type(exc).__name__,
                },
            )
        metadata = dict(result.metadata or {})
        metadata.update(
            {
                "execution_id": execution_id,
                "idempotency_key": idempotency_key,
                "execution_outcome": terminal_status,
                "replayable_result_persisted": replay_result is not None,
            }
        )
        return ToolResult(
            success=result.success,
            output=result.output,
            error=result.error,
            metadata=metadata,
        )
