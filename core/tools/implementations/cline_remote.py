"""Dispatch and collect Cline work on an ephemeral GitHub-hosted Actions runner.

The hosted Omnitrix process never starts the Cline CLI locally. It sends bounded,
non-secret task context to a repository workflow and returns the worker's artifact.
Implementation work is delivered as a reviewable PR; it is never auto-merged.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

_REPO = "som76377-alt/omnimatrix"
_WORKFLOW = "cline-remote-worker.yml"
_API = "https://api.github.com"
_MAX_INPUT = 60_000


class RemoteClineError(RuntimeError):
    """A safe, user-facing remote Cline bridge failure."""


def _api(token: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
         accept: str = "application/vnd.github+json", timeout: int = 20) -> tuple[dict[str, Any] | bytes, str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        _API + path, data=body, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Omnitrix-Cline-Worker/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise RemoteClineError("Remote Cline response exceeded the safe size limit.")
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type or not data:
                return (json.loads(data.decode("utf-8")) if data else {}), response.headers.get("Content-Type", "")
            return data, content_type
    except urllib.error.HTTPError as exc:
        # Do not include request headers or token material in errors.
        if exc.code in (401, 403):
            raise RemoteClineError("GitHub rejected the worker credential or its Actions permissions. Check the Render secret and repository access.") from None
        if exc.code == 404:
            raise RemoteClineError("The remote Cline workflow or requested run/artifact was not found.") from None
        if exc.code == 422:
            raise RemoteClineError("GitHub rejected the worker request. Check the workflow inputs and base branch.") from None
        raise RemoteClineError(f"GitHub worker API returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RemoteClineError(f"Could not reach the remote Cline worker ({type(exc).__name__}).") from None


def execute_remote(*, task: str, mode: str, context: str = "",
                   related_agent_findings: list[str] | None = None,
                   acceptance_criteria: list[str] | None = None,
                   files_in_scope: list[str] | None = None,
                   timeout_seconds: int = 300) -> Any:
    """Run a bounded coding request on GitHub Actions and collect its result artifact."""
    from core.tools.base import ToolResult

    token = os.environ.get("OMNITRIX_GITHUB_ACTIONS_TOKEN", "").strip()
    if not token:
        return ToolResult(success=False, error="Remote Cline is not configured: add OMNITRIX_GITHUB_ACTIONS_TOKEN to the private Render environment. The local Cline process remains disabled to protect the small web instance.", metadata={"tool": "cline.coding", "backend": "github_actions", "changes_applied": False})
    if mode not in {"plan", "implement"}:
        return ToolResult(success=False, error="mode must be plan or implement.")
    request_id = time.strftime("%Y%m%d%H%M%S") + "-" + __import__("secrets").token_hex(4)
    inputs = {
        "request_id": request_id,
        "task": task,
        "context": context[:12000],
        "findings_json": json.dumps((related_agent_findings or [])[:12], ensure_ascii=False),
        "criteria_json": json.dumps((acceptance_criteria or [])[:20], ensure_ascii=False),
        "scope_json": json.dumps((files_in_scope or [])[:50], ensure_ascii=False),
        "mode": mode,
        "base_ref": os.environ.get("CLINE_REMOTE_BASE_REF", "main").strip() or "main",
        "timeout_seconds": str(min(max(int(timeout_seconds), 30), 900)),
    }
    if sum(len(str(v)) for v in inputs.values()) > _MAX_INPUT:
        return ToolResult(success=False, error="Remote Cline handoff is too large; reduce context/findings and retry.", metadata={"tool": "cline.coding", "backend": "github_actions"})
    body = {"ref": "main", "inputs": inputs}
    _api(token, f"/repos/{_REPO}/actions/workflows/{_WORKFLOW}/dispatches?return_run_details=true", method="POST", payload=body, timeout=20)

    # GitHub may respond before the new run appears in list results. Correlate using
    # the workflow run-name, not simply the newest run, to avoid cross-request races.
    deadline = time.monotonic() + min(max(int(timeout_seconds), 30), 900) + 360
    run_data = None
    while time.monotonic() < deadline:
        data, _ = _api(token, f"/repos/{_REPO}/actions/workflows/{_WORKFLOW}/runs?event=workflow_dispatch&per_page=30", timeout=20)
        if isinstance(data, dict):
            for candidate in data.get("workflow_runs", []):
                title = str(candidate.get("display_title") or candidate.get("name") or "")
                if request_id in title:
                    run_data = candidate
                    break
        if run_data and run_data.get("status") == "completed":
            break
        time.sleep(3)
    if not run_data:
        return ToolResult(success=False, error="Cline worker was dispatched but GitHub did not expose its run before the deadline.", metadata={"tool":"cline.coding","backend":"github_actions","request_id":request_id,"changes_applied":False})
    run_id = int(run_data["id"])
    run_url = str(run_data.get("html_url", ""))
    if run_data.get("status") != "completed":
        return ToolResult(success=False, error="Remote Cline worker exceeded the waiting deadline. Check the linked Actions run.", metadata={"tool":"cline.coding","backend":"github_actions","request_id":request_id,"run_url":run_url,"changes_applied":False})
    artifacts, _ = _api(token, f"/repos/{_REPO}/actions/runs/{run_id}/artifacts", timeout=20)
    artifact = next((a for a in artifacts.get("artifacts", []) if a.get("name") == f"cline-result-{request_id}" and not a.get("expired")), None) if isinstance(artifacts, dict) else None
    result: dict[str, Any] = {}
    if artifact:
        archive, _ = _api(token, f"/repos/{_REPO}/actions/artifacts/{int(artifact['id'])}/zip", accept="application/vnd.github+json", timeout=45)
        if isinstance(archive, bytes):
            try:
                with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                    member = next((n for n in zf.namelist() if n.endswith("cline-result.json") and not n.startswith("/") and ".." not in n.split("/")), None)
                    if member:
                        raw = zf.read(member)
                        if len(raw) <= 512 * 1024:
                            result = json.loads(raw.decode("utf-8"))
            except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError):
                result = {}
    if not result:
        conclusion = str(run_data.get("conclusion") or "unknown")
        return ToolResult(success=False, error=f"Remote Cline run finished with status '{conclusion}', but its result artifact was unavailable.", output=run_url, metadata={"tool":"cline.coding","backend":"github_actions","request_id":request_id,"run_url":run_url,"changes_applied":False})
    result["run_url"] = run_url
    result["backend"] = "github_actions"

    # Repository settings may block GITHUB_TOKEN from opening pull requests.
    # The Render-side worker credential is already authorized to dispatch and
    # retrieve this run; use it for the PR only after Cline's scoped changes and
    # full tests have passed. Never auto-merge and never expose the credential.
    if (
        mode == "implement"
        and result.get("status") == "passed"
        and result.get("tests_passed") is True
        and result.get("changed_files")
        and not result.get("pull_request_url")
    ):
        safe_request_id = request_id
        branch = f"cline/omnitrix-{safe_request_id}"
        base = inputs["base_ref"]
        payload = {
            "title": f"Cline implementation: {safe_request_id}",
            "head": branch,
            "base": base,
            "body": (
                "Automated implementation proposal from Omnitrix's remote Cline worker. "
                "The worker reported passing repository tests. Please inspect the diff and CI. "
                "This pull request was not auto-merged."
            ),
            "maintainer_can_modify": True,
        }
        try:
            pr, _ = _api(token, f"/repos/{_REPO}/pulls", method="POST", payload=payload, timeout=30)
            pr_url = pr.get("html_url") if isinstance(pr, dict) else None
            if isinstance(pr_url, str) and pr_url.startswith("https://github.com/"):
                result["pull_request_url"] = pr_url
                result["pull_request_created_by"] = "render_runtime_credential"
            else:
                result["pull_request_creation_error"] = "GitHub did not return a valid pull-request URL."
        except RemoteClineError as exc:
            # Retain the worker's real status, but don't call delivery successful
            # until a reviewable PR exists.
            result["pull_request_creation_error"] = str(exc)

    success = result.get("status") == "passed"
    if mode == "implement":
        success = success and bool(result.get("tests_passed")) and bool(result.get("pull_request_url"))
    output = str(result.get("cline_output") or result.get("note") or "Remote Cline worker completed.")[-24000:]
    if result.get("pull_request_url"):
        output += "\nReviewable pull request: " + str(result["pull_request_url"])
    elif mode == "implement" and result.get("tests_passed"):
        output += (
            "\nCline's implementation and tests passed, but GitHub did not permit creation of the review PR. "
            "No merge occurred. Check the Render GitHub token's repository pull-request write permission."
        )
    elif mode == "implement":
        output += "\nValidation did not pass; no pull request was created. Review the Actions run for the test report."
    return ToolResult(
        success=success,
        output=output,
        error=None if success else (
            "Cline completed, but a validated reviewable pull request could not be delivered; inspect the worker report."
            if result.get("tests_passed") else
            "Remote Cline did not produce a fully validated result; inspect the worker report before retrying."
        ),
        metadata={k:v for k,v in result.items() if k not in {"cline_output","test_output"}},
    )
