(() => {
  "use strict";

  const OWNER = "som76377-alt";
  const REPO = "omnimatrix";
  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
  const REFRESH_MS = 10 * 60 * 1000;
  const state = { runs: [], pulls: [], snapshot: null, refreshedAt: null, apiError: null };
  const byId = (id) => document.getElementById(id);

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function setView(view) {
    const validViews = ["overview", "status", "capabilities", "workspace", "recovery"];
    const target = validViews.includes(view) ? view : "overview";
    document.querySelectorAll(".view").forEach((section) => {
      section.classList.toggle("active", section.id === `view-${target}`);
    });
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === target;
      button.classList.toggle("active", active);
      if (button.classList.contains("nav-item") || button.classList.contains("mobile-nav-item")) {
        button.setAttribute("aria-current", active ? "page" : "false");
      }
    });
    byId("crumb-view").textContent = target.replace("-", " ").toUpperCase();
    if (window.location.hash !== `#${target}`) history.replaceState(null, "", `#${target}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-goto]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.goto));
  });
  window.addEventListener("hashchange", () => setView(window.location.hash.slice(1)));
  setView(window.location.hash.slice(1) || "overview");

  function shortSha(sha) {
    return typeof sha === "string" && sha.length ? sha.slice(0, 7) : "—";
  }

  function dateLabel(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    }).format(date);
  }

  function relativeTime(value) {
    if (!value) return "time unavailable";
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (!Number.isFinite(seconds)) return "time unavailable";
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  function workflowState(run) {
    if (!run) return { label: "UNKNOWN", kind: "unknown" };
    if (run.status !== "completed") {
      const label = run.status === "in_progress" ? "RUNNING" : (run.status || "QUEUED").replaceAll("_", " ").toUpperCase();
      return { label, kind: "pending" };
    }
    if (run.conclusion === "success") return { label: "PASSED", kind: "success" };
    if (run.conclusion === "failure") return { label: "FAILED", kind: "failure" };
    if (run.conclusion === "cancelled") return { label: "CANCELLED", kind: "failure" };
    return { label: (run.conclusion || "COMPLETED").replaceAll("_", " ").toUpperCase(), kind: "unknown" };
  }

  async function fetchJson(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store",
    });
    if (!response.ok) {
      if (response.status === 403 || response.status === 429) {
        throw new Error("GitHub API rate limit reached. Try again later.");
      }
      throw new Error(`GitHub API request failed (${response.status}).`);
    }
    return response.json();
  }

  function latestCiRun() {
    const runs = state.runs.filter((run) => run.name === "CI");
    runs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    return runs[0] || null;
  }

  function addRunRow(parent, run, compact) {
    const result = workflowState(run);
    const row = element("div", "run-row");
    const dot = element("span", `run-status-dot ${result.kind}`);
    dot.setAttribute("aria-hidden", "true");
    const main = element("div", "run-row-main");
    const title = element("strong", "", run.name || "Workflow");
    const meta = element("span", "", `#${run.run_number ?? "—"} · ${shortSha(run.head_sha)}`);
    main.append(title, meta);
    const side = element("div", "run-row-side");
    const status = element("span", `run-result ${result.kind}`, result.label);
    const date = element("time", "", compact ? relativeTime(run.created_at) : dateLabel(run.created_at));
    side.append(status, date);
    row.append(dot, main, side);
    row.title = `${run.name || "Workflow"} · ${result.label} · ${run.head_sha || "commit unknown"}`;
    if (run.html_url) {
      row.tabIndex = 0;
      row.setAttribute("role", "link");
      row.addEventListener("click", () => window.open(run.html_url, "_blank", "noopener,noreferrer"));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          window.open(run.html_url, "_blank", "noopener,noreferrer");
        }
      });
    }
    parent.append(row);
  }

  function renderRuns() {
    const ci = latestCiRun();
    const navState = byId("nav-ci-state");
    const connection = byId("connection-label");
    const connectionWrap = document.querySelector(".connection");
    if (ci) {
      const ciResult = workflowState(ci);
      navState.textContent = ciResult.kind === "success" ? "PASS" : ciResult.kind === "failure" ? "FAIL" : "RUN";
      navState.className = `nav-count ${ciResult.kind}`;
      byId("overview-ci").textContent = ciResult.label;
      byId("overview-ci-detail").textContent = ci.name || "CI workflow";
      byId("overview-ci-date").textContent = relativeTime(ci.created_at).toUpperCase();
      byId("overview-ci-link").href = ci.html_url || `https://github.com/${OWNER}/${REPO}/actions`;
      connection.textContent = "GITHUB LIVE";
      connectionWrap.classList.add("is-connected");
      connectionWrap.classList.remove("is-error");
      const banner = byId("status-banner");
      banner.classList.remove("is-failed", "is-running");
      if (ciResult.kind === "failure") banner.classList.add("is-failed");
      if (ciResult.kind === "pending") banner.classList.add("is-running");
      banner.replaceChildren();
      const mark = element("span", "status-mark", ciResult.kind === "success" ? "✓" : ciResult.kind === "failure" ? "!" : "↻");
      const textGroup = element("div");
      const headline = element("strong", "", ciResult.kind === "success" ? "Latest CI workflow passed" : ciResult.kind === "failure" ? "Latest CI workflow failed" : "Latest CI workflow is still running");
      const detail = element("p", "", `Run #${ci.run_number ?? "—"} · commit ${shortSha(ci.head_sha)} · ${dateLabel(ci.created_at)}`);
      textGroup.append(headline, detail);
      banner.append(mark, textGroup, element("span", "status-banner-code", "GITHUB ACTIONS"));
    } else {
      navState.textContent = "—";
      byId("overview-ci").textContent = "NO RUN";
      byId("overview-ci-detail").textContent = "No CI run returned for main.";
      connection.textContent = state.apiError ? "GITHUB UNAVAILABLE" : "NO RUN DATA";
      connectionWrap.classList.add("is-error");
    }

    const compact = byId("overview-runs");
    const full = byId("status-runs");
    compact.replaceChildren();
    full.replaceChildren();
    if (!state.runs.length) {
      compact.append(element("div", "empty-state", "No recent workflow runs were returned."));
      full.append(element("div", "empty-state", "No recent workflow runs were returned."));
      byId("run-count").textContent = "0 RUNS";
      return;
    }
    state.runs.slice(0, 4).forEach((run) => addRunRow(compact, run, true));
    state.runs.slice(0, 10).forEach((run, index) => {
      const result = workflowState(run);
      const row = element("div", "workflow-row");
      row.append(element("span", "workflow-run-no", String(index + 1).padStart(2, "0")));
      const main = element("div", "workflow-main");
      const link = element("a", "", run.name || "Workflow");
      link.href = run.html_url || `https://github.com/${OWNER}/${REPO}/actions`;
      link.target = "_blank";
      link.rel = "noreferrer";
      const meta = element("p", "", `RUN #${run.run_number ?? "—"} · ${shortSha(run.head_sha)} · ${run.event || "event unknown"}`);
      main.append(link, meta);
      const side = element("div", "workflow-side");
      side.append(element("span", `run-result ${result.kind}`, result.label), element("time", "", relativeTime(run.created_at)));
      row.append(main, side);
      full.append(row);
    });
    byId("run-count").textContent = `${Math.min(state.runs.length, 10)} RUNS`;
    if (ci) {
      const result = workflowState(ci);
      const description = result.kind === "success" ? "Test/build workflow completed successfully." :
        result.kind === "failure" ? "The workflow failed. Open the run for step-level details." :
        "The workflow has not completed yet.";
      byId("status-banner").querySelector("p").textContent = description;
    }
  }

  function renderPulls() {
    byId("overview-prs").textContent = state.pulls.length ? String(state.pulls.length) : "0";
    const list = byId("open-pulls");
    list.replaceChildren();
    if (!state.pulls.length) {
      list.append(element("div", "empty-state", state.apiError ? "Pull requests could not be loaded." : "No open pull requests returned."));
      return;
    }
    state.pulls.slice(0, 5).forEach((pull) => {
      const row = element("div", "pull-row");
      const main = element("div");
      const link = element("a", "", pull.title || "Untitled pull request");
      link.href = pull.html_url;
      link.target = "_blank";
      link.rel = "noreferrer";
      const note = element("p", "", `#${pull.number} · ${pull.draft ? "DRAFT" : "OPEN"} · UPDATED ${relativeTime(pull.updated_at).toUpperCase()}`);
      main.append(link, note);
      row.append(main, element("span", "pull-no", `#${pull.number}`));
      list.append(row);
    });
  }

  function renderSnapshot() {
    const snapshot = state.snapshot;
    if (!snapshot || typeof snapshot !== "object" || !snapshot.test_count) {
      byId("overview-tests").textContent = "—";
      byId("overview-tests-detail").textContent = "No deployed test snapshot available yet.";
      byId("overview-tests-sha").textContent = "COMMIT —";
      byId("status-test-count").textContent = "—";
      byId("status-test-label").textContent = "No deployed test snapshot";
      byId("status-test-description").textContent = "A snapshot appears only after the dashboard build and test suite pass and the site deploys.";
      byId("status-test-outcome").textContent = "UNKNOWN";
      byId("status-test-sha").textContent = "—";
      byId("status-generated-at").textContent = "—";
      return;
    }
    const passed = snapshot.test_status === "passed";
    byId("overview-tests").textContent = String(snapshot.test_count);
    byId("overview-tests-detail").textContent = passed ? "Tests passed in the deployed build." : "The deployed snapshot did not report a passing suite.";
    byId("overview-tests-sha").textContent = `COMMIT ${shortSha(snapshot.commit_sha)}`;
    byId("status-test-count").textContent = String(snapshot.test_count);
    byId("status-test-label").textContent = passed ? "Automated tests passed" : "Test run did not pass";
    byId("status-test-description").textContent = "Python unittest count from the build that generated this deployed snapshot.";
    byId("status-test-outcome").textContent = (snapshot.test_status || "unknown").toUpperCase();
    byId("status-test-outcome").style.color = passed ? "var(--acid)" : "var(--red)";
    byId("status-test-sha").textContent = shortSha(snapshot.commit_sha);
    byId("status-test-sha").title = snapshot.commit_sha || "";
    byId("status-generated-at").textContent = dateLabel(snapshot.generated_at);
    if (snapshot.run_url) byId("snapshot-run-link").href = snapshot.run_url;
  }

  async function refreshStatus() {
    const refresh = byId("refresh-button");
    refresh.classList.add("spinning");
    refresh.disabled = true;
    state.apiError = null;
    try {
      const [runsResponse, pullsResponse, snapshotResponse] = await Promise.allSettled([
        fetchJson(`${API}/actions/runs?branch=main&per_page=10`),
        fetchJson(`${API}/pulls?state=open&per_page=5`),
        fetch(`./status.json?refresh=${Date.now()}`, { cache: "no-store" }).then((r) => r.ok ? r.json() : null),
      ]);
      if (runsResponse.status === "fulfilled") {
        state.runs = Array.isArray(runsResponse.value.workflow_runs) ? runsResponse.value.workflow_runs : [];
        state.runs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      } else {
        state.apiError = runsResponse.reason instanceof Error ? runsResponse.reason.message : "Workflow data is unavailable.";
      }
      if (pullsResponse.status === "fulfilled") {
        state.pulls = Array.isArray(pullsResponse.value) ? pullsResponse.value : [];
      } else {
        state.apiError = state.apiError || (pullsResponse.reason instanceof Error ? pullsResponse.reason.message : "Pull request data is unavailable.");
      }
      if (snapshotResponse.status === "fulfilled" && snapshotResponse.value) state.snapshot = snapshotResponse.value;
      state.refreshedAt = new Date();
      renderRuns();
      renderPulls();
      renderSnapshot();
      byId("last-updated").textContent = dateLabel(state.refreshedAt).toUpperCase();
      if (state.apiError) {
        byId("connection-label").textContent = "PARTIAL GITHUB DATA";
        document.querySelector(".connection").classList.add("is-error");
      }
    } catch (error) {
      state.apiError = error instanceof Error ? error.message : "Unknown refresh error.";
      byId("connection-label").textContent = "REFRESH FAILED";
      document.querySelector(".connection").classList.add("is-error");
      const emptyRuns = element("div", "empty-state", state.apiError);
      byId("overview-runs").replaceChildren(emptyRuns);
      byId("status-runs").replaceChildren(element("div", "empty-state", state.apiError));
      byId("open-pulls").replaceChildren(element("div", "empty-state", "Live pull-request data is unavailable."));
    } finally {
      refresh.classList.remove("spinning");
      refresh.disabled = false;
    }
  }

  byId("refresh-button").addEventListener("click", refreshStatus);

  function shellQuote(value) {
    return "'" + value.replace(/'/g, "'\\''") + "'";
  }

  function buildWorkspaceCommand() {
    const root = byId("workspace-root").value.trim() || ".";
    const paths = byId("workspace-allow").value.split(/\r?\n/).map((path) => path.trim()).filter(Boolean);
    const parts = [
      "python -m interfaces.cli.main",
      "--config config/demo.models.json",
      "--allow-workspace-read",
      `--workspace-root ${shellQuote(root)}`,
    ];
    paths.forEach((path) => parts.push(`--workspace-allow ${shellQuote(path)}`));
    byId("workspace-command").textContent = parts.join(" ");
    byId("command-feedback").textContent = paths.length ? `Restricted to ${paths.length} configured path prefix(es).` : "No path allowlist selected — root-scoped access remains enabled.";
  }

  byId("workspace-root").addEventListener("input", buildWorkspaceCommand);
  byId("workspace-allow").addEventListener("input", buildWorkspaceCommand);
  buildWorkspaceCommand();

  let toastTimer;
  function toast(message) {
    const node = byId("toast");
    node.textContent = message;
    node.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("visible"), 2200);
  }

  async function copyText(value) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
      } else {
        const textarea = element("textarea");
        textarea.value = value;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        const success = document.execCommand("copy");
        textarea.remove();
        if (!success) throw new Error("Clipboard unavailable");
      }
      toast("Copied to clipboard.");
      byId("command-feedback").textContent = "Command copied. Run it from the Omnitrix repository workspace.";
    } catch {
      toast("Copy failed — select the command and copy it manually.");
    }
  }

  byId("copy-command").addEventListener("click", () => copyText(byId("workspace-command").textContent));
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.copy));
  });

  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
    window.addEventListener("load", async () => {
      try {
        const registration = await navigator.serviceWorker.register("./sw.js", { scope: "./" });
        registration.update().catch(() => {});
        setInterval(() => registration.update().catch(() => {}), REFRESH_MS);
      } catch {
        // The console remains functional without install/offline support.
      }
    });
  }

  refreshStatus();
  setInterval(refreshStatus, REFRESH_MS);
})();