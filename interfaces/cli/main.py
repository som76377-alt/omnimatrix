import argparse
import json
from pathlib import Path

from core.application import ChatApplication
from core.conversation import Conversation
from core.orchestrator.omnitrix import Omnitrix
from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


def run_cli(
    application: ChatApplication,
    conversation: Conversation,
    input_fn=input,
    output_fn=print,
) -> None:
    """Run an interactive Omnitrix chat session."""

    while True:
        user_message = input_fn("> ")

        if user_message.strip() == "/exit":
            return

        if not user_message.strip():
            continue

        response = application.send_message(
            conversation,
            user_message,
        )

        output_fn(response)


def main(argv: list[str] | None = None) -> None:
    """Run interactive chat or a non-interactive durable-recovery command."""

    parser = argparse.ArgumentParser(
        description="Start Omnitrix chat or inspect/recover a journaled run."
    )
    parser.add_argument(
        "--config",
        help="Path to the Omnitrix model configuration file (required for chat/restart).",
    )
    parser.add_argument(
        "--allow-workspace-read",
        action="store_true",
        help="Explicitly grant read-only access to a confined workspace (hidden/secret-like files remain denied).",
    )
    parser.add_argument(
        "--workspace-root",
        help="Workspace directory to expose; requires --allow-workspace-read. Defaults to the current directory.",
    )
    parser.add_argument(
        "--journal",
        help="SQLite journal path. Enables durable journaling for chat or recovery commands.",
    )
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument(
        "--run-objective",
        metavar="OBJECTIVE",
        help="Execute one non-interactive task and persist it to the required journal.",
    )
    recovery.add_argument(
        "--list-runs",
        action="store_true",
        help="List recent run IDs and statuses without showing stored objectives.",
    )
    recovery.add_argument(
        "--inspect-run",
        metavar="RUN_ID",
        help="Print integrity findings and the conservative recovery disposition for a run.",
    )
    recovery.add_argument(
        "--restart-run",
        metavar="RUN_ID",
        help="Restart an interrupted run from its original objective, if the guarded policy permits.",
    )
    parser.add_argument(
        "--confirm-restart-from-objective",
        action="store_true",
        help="Explicitly authorize objective-only restart (required with --restart-run).",
    )
    args = parser.parse_args(argv)

    def create_omnitrix(config_path: str, journal: SQLiteJournal | None = None) -> Omnitrix:
        if args.allow_workspace_read:
            workspace_root = Path(args.workspace_root).expanduser() if args.workspace_root else Path.cwd()
            try:
                tool_registry = build_tool_registry(workspace_root)
            except RuntimeError as exc:
                parser.error(str(exc))
            return Omnitrix.from_config(
                config_path,
                journal=journal,
                tool_registry=tool_registry,
                tool_permission=ToolPermission.from_capabilities({"workspace.read"}),
            )
        if journal is not None:
            return Omnitrix.from_config(config_path, journal=journal)
        return Omnitrix.from_config(config_path)

    has_recovery_command = (
        args.run_objective is not None
        or args.list_runs
        or args.inspect_run is not None
        or args.restart_run is not None
    )
    if args.workspace_root and not args.allow_workspace_read:
        parser.error("--workspace-root requires --allow-workspace-read.")
    if args.allow_workspace_read and (args.list_runs or args.inspect_run is not None or args.restart_run is not None):
        parser.error("--allow-workspace-read cannot be combined with recovery inspection or restart commands.")
    if args.confirm_restart_from_objective and args.restart_run is None:
        parser.error("--confirm-restart-from-objective is only valid with --restart-run.")
    if has_recovery_command and not args.journal:
        parser.error("Recovery commands require --journal PATH.")
    if args.run_objective is not None and not args.config:
        parser.error("--run-objective requires --config PATH.")
    if args.restart_run is not None:
        if not args.config:
            parser.error("--restart-run requires --config PATH.")
        if not args.confirm_restart_from_objective:
            parser.error(
                "--restart-run requires --confirm-restart-from-objective; no restart was attempted."
            )

    if has_recovery_command:
        with SQLiteJournal(args.journal) as journal:
            if args.run_objective is not None:
                existing_ids = {
                    item["run_id"] for item in journal.list_runs(limit=999)
                }
                omnitrix = create_omnitrix(args.config, journal=journal)
                result = omnitrix.run(args.run_objective)
                new_runs = [
                    item for item in journal.list_runs(limit=1000)
                    if item["run_id"] not in existing_ids
                ]
                if len(new_runs) == 1:
                    print(json.dumps(
                        {"run_id": new_runs[0]["run_id"], "result": result},
                        ensure_ascii=False,
                        indent=2,
                    ))
                else:
                    print(json.dumps(
                        {
                            "result": result,
                            "note": "Run completed; use --list-runs to identify its run ID if concurrent writers were active.",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ))
                return
            if args.list_runs:
                print(json.dumps(journal.list_runs(), ensure_ascii=False, indent=2))
                return
            if args.inspect_run is not None:
                inspection = RecoveryService(journal).inspect(args.inspect_run)
                print(json.dumps(inspection.to_dict(), ensure_ascii=False, indent=2))
                return
            if args.restart_run is not None:
                omnitrix = Omnitrix.from_config(args.config, journal=journal)
                result = omnitrix.resume_interrupted_run(
                    args.restart_run,
                    confirm_restart_from_objective=True,
                )
                print(result)
                return

    if not args.config:
        parser.error("Interactive chat requires --config PATH.")

    if args.journal:
        with SQLiteJournal(args.journal) as journal:
            omnitrix = Omnitrix.from_config(args.config, journal=journal)
            run_cli(
                application=ChatApplication(omnitrix),
                conversation=Conversation(),
            )
        return

    omnitrix = create_omnitrix(args.config)
    run_cli(
        application=ChatApplication(omnitrix),
        conversation=Conversation(),
    )


if __name__ == "__main__":
    main()
