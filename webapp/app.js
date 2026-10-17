(() => {
  "use strict";

  const OWNER = "som76377-alt";
  const REPO = "omnimatrix";
  const GITHUB_API = "https://api.github.com/repos/" + OWNER + "/" + REPO;
  const TOKEN_KEY = "omnitrix-studio-runtime-token";
  const SESSION_KEY = "omnitrix-studio-session-id";
  const SESSION_REFRESH_MS = 10 * 60 * 1000;
  const RUNTIME_REFRESH_MS = 60 * 1000;
  const SERVICE_WORKER_REFRESH_MS = 60 * 1000;
  const state = {
    token: sessionStorage.getItem(TOKEN_KEY) || "",
    runtime: null,
    connected: false,
    activeView: "workspace",
    workspacePath: "",
    workspaceEntries: [],
    selectedFile: null,
    workflows: [],
    workflowError: null,
    snapshot: null,
    localTest: null,
    activity: [],
    busyChat: false,
    busyTests: false,
  };
  const byId = (id) => document.getElementById(id);

  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined && text !== null) result.textContent = String(text);
    return result;
  }

  function getSessionId() {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = (window.crypto && typeof window.crypto.randomUUID === "function")
        ? window.crypto.randomUUID()
        : "session_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 18);
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }
  let sessionId = getSessionId();

  function toast(message) {
    const target = byId("toast");
    target.textContent = message;
    target.classList.add("visible");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => target.classList.remove("visible"), 2800);
  }

  function addActivity(category, message) {
    const safeCategory = String(category).slice(0, 12);
    const safeMessage = String(message).slice(0, 350);
    state.activity.unshift({ category: safeCategory, message: safeMessage, at: new Date() });
    state.activity = state.activity.slice(0, 35);
    const target = byId("activity-log");
    target.replaceChildren();
    state.activity.forEach((item) => {
      const p = node("p", "activity-line");
      p.append(node("span", "", item.category), document.createTextNode(" " + item.message));
      target.append(p);
    });
  }

  function shortSha(value) {
    return typeof value === "string" && value.length ? value.slice(0, 7) : "—";
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
    if (!value) return "time unknown";
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (!Number.isFinite(seconds)) return "time unknown";
    if (seconds < 60) return "just now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    return Math.floor(seconds / 86400) + "d ago";
  }

  function setView(view) {
    const valid = ["workspace", "chat", "status", "capabilities", "recovery"];
    const target = valid.includes(view) ? view : "workspace";
    state.activeView = target;
    document.querySelectorAll(".view").forEach((section) => {
      section.classList.toggle("active", section.id === "view-" + target);
    });
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === target;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    byId("breadcrumb-view").textContent = target === "capabilities"
      ? "TOOLS & MODELS"
      : target === "status"
        ? "TESTS & STATUS"
        : target === "recovery"
          ? "RECOVERY JOURNAL"
          : target.toUpperCase();
    if (window.location.hash !== "#" + target) history.replaceState(null, "", "#" + target);
    if (target === "status") {
      renderStatus();
      loadGitHubStatus();
    }
    if (target === "capabilities") renderCapabilities();
    if (target === "recovery") renderRecovery();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-goto]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.goto));
  });
  window.addEventListener("hashchange", () => setView(window.location.hash.slice(1)));
  setView(window.location.hash.slice(1) || "workspace");

  function baseHeaders() {
    const headers = { Accept: "application/json" };
    if (state.token) headers.Authorization = "Bearer " + state.token;
    return headers;
  }

  async function apiRequest(route, options) {
    const requestOptions = Object.assign({
      method: "GET",
      headers: baseHeaders(),
      cache: "no-store",
    }, options || {});
    requestOptions.headers = Object.assign(baseHeaders(), (options && options.headers) || {});
    const response = await fetch("./api" + route, requestOptions);
    let data;
    try {
      data = await response.json();
    } catch {
      data = { ok: false, error: "No Python API response was returned for this URL." };
    }
    if (!response.ok) {
      const error = new Error(data.error || ("API request failed (" + response.status + ")."));
      error.status = response.status;
      if (response.status === 401) {
        state.connected = false;
        updateConnectionUI();
        byId("connect-help").textContent = "The token is missing or no longer valid. Paste the current token from the Studio server terminal.";
      }
      throw error;
    }
    return data;
  }

  async function githubJson(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store",
    });
    if (!response.ok) {
      if (response.status === 403 || response.status === 429) {
        throw new Error("GitHub API rate limit reached. Try again later.");
      }
      throw new Error("GitHub returned HTTP " + response.status + ".");
    }
    return response.json();
  }

  function updateConnectionUI() {
    const light = byId("backend-light");
    const treeLight = byId("tree-light");
    const label = byId("backend-label");
    const detail = byId("backend-detail");
    const status = byId("runtime-state");
    const statusText = status.querySelector("span");
    const connected = state.connected && state.runtime;
    light.classList.toggle("connected", Boolean(connected));
    light.classList.toggle("error", !connected && Boolean(state.token));
    treeLight.classList.toggle("connected", Boolean(connected && state.runtime.workspace_read_enabled));
    treeLight.classList.toggle("error", !connected);
    label.textContent = connected ? "Python runtime connected" : "Runtime disconnected";
    detail.textContent = connected
      ? (state.runtime.provider_mode === "offline-demo" ? "Offline demo · simulated inference" : "Configured model adapter")
      : (isPagesHost() ? "Static Pages · connect Codespaces" : "Token required · Python API not connected");
    status.classList.toggle("connected", Boolean(connected));
    status.classList.toggle("failed", !connected && Boolean(state.token));
    statusText.textContent = connected
      ? (state.runtime.provider_mode === "offline-demo" ? "DEMO BACKEND" : "PYTHON BACKEND ONLINE")
      : "PYTHON BACKEND OFFLINE";
    byId("top-connect").textContent = connected ? "RUNTIME CONNECTED ✓" : "CONNECT RUNTIME ↗";
    byId("top-connect").classList.toggle("connected-button", Boolean(connected));
    byId("sidebar-workspace-mode").textContent = connected && state.runtime.workspace_read_enabled
      ? "Live Codespace working tree · read only"
      : "Public GitHub / main snapshot";
    byId("tree-source-label").textContent = connected && state.runtime.workspace_read_enabled
      ? "LIVE WORKSPACE" : "PUBLIC REPOSITORY";
    byId("source-mode").textContent = connected && state.runtime.workspace_read_enabled
      ? "CODESPACE / LIVE WORKTREE" : "GITHUB / MAIN SNAPSHOT";
    byId("sidebar-root-name").textContent = connected ? state.runtime.workspace_name : "main repository";
    byId("revision-chip").textContent = connected && state.runtime.revision
      ? state.runtime.revision : "main";
    byId("sidebar-revision").textContent = (connected && state.runtime.revision ? state.runtime.revision : "main") + " · read only";
    const syncChip = byId("sync-chip");
    if (!connected) {
      syncChip.textContent = "GITHUB / STATIC";
      syncChip.className = "state-pill sync-chip";
    } else if (!state.runtime.auto_sync_main_enabled) {
      syncChip.textContent = "AUTO-SYNC OFF";
      syncChip.className = "state-pill sync-chip amber-pill";
    } else {
      const syncLabels = {
        waiting: "SYNC CHECK STARTING",
        up_to_date: "SYNCED WITH MAIN",
        deferred_busy: "SYNC PAUSED / BUSY",
        deferred_dirty: "LOCAL CHANGES / PAUSED",
        deferred_not_main: "MAIN BRANCH ONLY",
        error: "SYNC ERROR",
        updated: "RESTARTING STUDIO",
      };
      syncChip.textContent = syncLabels[state.runtime.sync_status] || "AUTO-SYNC ACTIVE";
      syncChip.className = "state-pill sync-chip" +
        (["error", "deferred_dirty", "deferred_not_main"].includes(state.runtime.sync_status) ? " amber-pill" : "");
    }
    byId("workspace-footer-right").textContent = connected
      ? "Runtime revision " + (state.runtime.revision || "unknown") +
        (state.runtime.working_tree_dirty ? " · local changes present" : "") +
        (state.runtime.auto_sync_main_enabled ? " · GitHub sync " + (state.runtime.sync_status || "waiting") : " · auto-sync disabled")
      : "GitHub snapshot reads main; connect Python to browse the live workspace.";
    byId("chat-provider-chip").textContent = connected
      ? (state.runtime.provider_mode === "offline-demo" ? "OFFLINE DEMO / SIMULATED" : "CONFIGURED MODEL")
      : "BACKEND OFFLINE";
    byId("chat-thread-subtitle").textContent = connected
      ? ("Runtime " + (state.runtime.revision || "revision unknown"))
      : "Waiting for backend connection";
    byId("chat-mode").textContent = connected
      ? (state.runtime.provider_mode === "offline-demo" ? "SIMULATED RESPONSES" : "REAL MODEL ADAPTER")
      : "NO INFERENCE";
    byId("chat-input").disabled = !connected || state.busyChat;
    byId("send-message").disabled = !connected || state.busyChat;
    byId("chat-input").placeholder = connected
      ? "Ask Omnitrix to inspect, reason, or use an authorized tool…"
      : "Connect the private Python runtime to start chatting…";
    const tools = connected ? state.runtime.tools || [] : [];
    const calculator = tools.find((tool) => tool.name === "calculator");
    byId("composer-permissions").textContent = connected
      ? ("Calculator " + (calculator && calculator.permission_granted ? "allowed" : "denied") +
        " · workspace " + (state.runtime.workspace_read_enabled ? "read enabled" : "read disabled"))
      : "No backend permissions loaded";
    if (connected) {
      byId("context-model-mode").textContent = state.runtime.provider_mode === "offline-demo" ? "OFFLINE DEMO" : "CONFIGURED";
      byId("context-model-mode").className = state.runtime.provider_mode === "offline-demo" ? "amber-text" : "yes";
      byId("context-workspace").textContent = state.runtime.workspace_read_enabled ? "ENABLED" : "DISABLED";
      byId("context-workspace").className = state.runtime.workspace_read_enabled ? "yes" : "no";
      byId("context-calculator").textContent = calculator && calculator.permission_granted ? "ALLOWED" : "DENIED";
      byId("context-calculator").className = calculator && calculator.permission_granted ? "yes" : "no";
      byId("context-tests").textContent = state.runtime.tests_enabled ? "ENABLED" : "DISABLED";
      byId("context-tests").className = state.runtime.tests_enabled ? "yes" : "no";
      byId("runtime-summary-title").textContent = "Python runtime connected";
      byId("runtime-summary-subtitle").textContent = "Revision " + (state.runtime.revision || "unknown") + " · " + state.runtime.models.length + " enabled model(s) · " + tools.length + " registered tool(s).";
      byId("runtime-summary-mode").textContent = state.runtime.provider_mode === "offline-demo" ? "SIMULATED MODEL" : "MODEL CONFIGURED";
      byId("runtime-summary-mode").className = "state-pill" + (state.runtime.provider_mode === "offline-demo" ? " amber-pill" : "");
    } else {
      byId("context-model-mode").textContent = "DISCONNECTED";
      byId("context-model-mode").className = "no";
      byId("context-workspace").textContent = "UNKNOWN";
      byId("context-workspace").className = "no";
      byId("context-calculator").textContent = "UNKNOWN";
      byId("context-calculator").className = "no";
      byId("context-tests").textContent = "UNKNOWN";
      byId("context-tests").className = "no";
      byId("runtime-summary-title").textContent = "Not connected";
      byId("runtime-summary-subtitle").textContent = "Start the Studio server in your Codespace and paste its private runtime token above.";
      byId("runtime-summary-mode").textContent = "DISCONNECTED";
      byId("runtime-summary-mode").className = "state-pill amber-pill";
    }
    byId("run-tests").disabled = !connected || !state.runtime.tests_enabled || state.busyTests;
  }

  async function refreshBackend() {
    if (!state.token) {
      state.connected = false;
      state.runtime = null;
      updateConnectionUI();
      renderCapabilities();
      renderStatus();
      return;
    }
    try {
      const data = await apiRequest("/health");
      state.runtime = data;
      state.connected = true;
      state.localTest = state.localTest;
      updateConnectionUI();
      renderCapabilities();
      await loadLatestLocalTest();
      await loadDirectory(state.workspacePath, { silent: true });
      addActivity("API", "Connected to Python runtime at revision " + (data.revision || "unknown") + ".");
      byId("connect-help").textContent = "Runtime connected. The token is stored only for this browser tab and is not written to the repository.";
      byId("connect-panel").hidden = true;
    } catch (error) {
      state.connected = false;
      state.runtime = null;
      updateConnectionUI();
      renderCapabilities();
      if (error.status === 401) {
        byId("connect-panel").hidden = false;
        byId("connect-help").textContent = "Token rejected. Copy the current token printed by the running server and try again.";
      } else {
        byId("connect-help").textContent = "Python API unavailable at this origin. On GitHub Pages this is expected; open the forwarded Codespaces port for the full Studio. " + error.message;
      }
    }
  }

  function openConnect() {
    byId("connect-panel").hidden = false;
    byId("runtime-token").value = state.token;
    byId("runtime-token").focus();
  }
  byId("open-connect").addEventListener("click", openConnect);
  byId("top-connect").addEventListener("click", openConnect);
  byId("close-connect").addEventListener("click", () => { byId("connect-panel").hidden = true; });
  byId("connect-runtime").addEventListener("click", async () => {
    const token = byId("runtime-token").value.trim();
    if (!token) {
      toast("Paste the access token printed by the running Studio server.");
      return;
    }
    state.token = token;
    sessionStorage.setItem(TOKEN_KEY, token);
    await refreshBackend();
    if (state.connected) toast("Python runtime connected.");
  });
  byId("disconnect-runtime").addEventListener("click", async () => {
    state.token = "";
    sessionStorage.removeItem(TOKEN_KEY);
    state.runtime = null;
    state.connected = false;
    updateConnectionUI();
    byId("connect-panel").hidden = true;
    await loadDirectory(state.workspacePath, { silent: true });
    renderCapabilities();
    toast("Runtime disconnected. Only public GitHub source browsing remains.");
  });
  byId("refresh-status").addEventListener("click", async () => {
    await refreshBackend();
    await loadGitHubStatus();
    toast(state.connected ? "Runtime and status refreshed." : "GitHub status refreshed; Python backend is offline.");
  });

  function isPagesHost() {
    return window.location.hostname.endsWith("github.io");
  }

  function isSensitiveName(name) {
    const lower = String(name).toLowerCase();
    return lower.startsWith(".") ||
      lower.startsWith(".env") ||
      /(^|[._-])(secret|secrets|credential|credentials|token|tokens|api[_-]?key|private[_-]?key)([._-]|$)/.test(lower) ||
      /\.(pem|key|p12|pfx|sqlite|sqlite3|db)$/.test(lower) ||
      ["id_rsa", "id_ed25519", "authorized_keys"].includes(lower);
  }

  function formatSize(value) {
    if (!Number.isFinite(value)) return "";
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }

  function safeGitHubPath(path) {
    return String(path).split("/").filter(Boolean).map((part) => encodeURIComponent(part)).join("/");
  }

  async function loadDirectory(path, options) {
    const opts = options || {};
    const cleanPath = String(path || "").replace(/^\/+|\/+$/g, "");
    state.workspacePath = cleanPath;
    byId("explorer-location").textContent = "/" + cleanPath;
    byId("active-path-label").textContent = cleanPath ? cleanPath : "repository root";
    const target = byId("file-tree");
    target.replaceChildren(node("div", "tree-empty", "Loading directory…"));
    byId("tree-light").classList.toggle("connected", Boolean(state.connected && state.runtime.workspace_read_enabled));
    try {
      let entries;
      let source = "github";
      if (state.connected && state.runtime.workspace_read_enabled) {
        try {
          const response = await apiRequest("/workspace/list?path=" + encodeURIComponent(cleanPath || "."));
          if (!response.ok || !response.output || !Array.isArray(response.output.entries)) {
            throw new Error(response.error || "Workspace listing unavailable.");
          }
          entries = response.output.entries;
          source = "runtime";
        } catch (error) {
          if (error.status === 401) throw error;
          entries = await getGitHubDirectory(cleanPath);
        }
      } else {
        entries = await getGitHubDirectory(cleanPath);
      }
      state.workspaceEntries = entries;
      byId("tree-source-label").textContent = source === "runtime" ? "LIVE WORKSPACE" : "PUBLIC REPO";
      renderDirectory(entries, cleanPath);
      if (!opts.silent) addActivity("FS", "Listed " + (cleanPath || "repository root") + " from " + (source === "runtime" ? "live workspace" : "GitHub/main") + ".");
    } catch (error) {
      target.replaceChildren(node("div", "tree-empty", "Unable to read this directory: " + error.message));
      byId("tree-source-label").textContent = "UNAVAILABLE";
    }
  }

  async function getGitHubDirectory(path) {
    const suffix = path ? "/" + safeGitHubPath(path) : "";
    const url = GITHUB_API + "/contents" + suffix + "?ref=main";
    const data = await githubJson(url);
    if (!Array.isArray(data)) throw new Error("GitHub did not return a directory listing.");
    return data.filter((item) => !isSensitiveName(item.name) && ["file", "dir"].includes(item.type))
      .map((item) => ({
        name: item.name,
        type: item.type === "dir" ? "directory" : "file",
        size_bytes: item.size,
        path: item.path,
      }))
      .sort((a, b) => {
        if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      });
  }

  function renderDirectory(entries, path) {
    const target = byId("file-tree");
    target.replaceChildren();
    if (path) {
      const upPath = path.split("/").slice(0, -1).join("/");
      const up = node("button", "tree-entry folder", "");
      up.append(node("span", "tree-icon", "↰"), node("span", "tree-name", ".."));
      up.addEventListener("click", () => loadDirectory(upPath));
      target.append(up);
    }
    if (!entries.length) target.append(node("div", "tree-empty", "No eligible files in this directory."));
    entries.forEach((entry) => {
      const fullPath = entry.path || (path ? path + "/" : "") + entry.name;
      const isDirectory = entry.type === "directory" || entry.type === "dir";
      const button = node("button", "tree-entry" + (isDirectory ? " folder" : "") + (state.selectedFile === fullPath ? " selected" : ""), "");
      button.title = fullPath;
      button.append(node("span", "tree-icon", isDirectory ? "▸" : iconForFile(entry.name)));
      button.append(node("span", "tree-name", entry.name));
      if (!isDirectory && Number.isFinite(entry.size_bytes)) button.append(node("span", "tree-size", formatSize(entry.size_bytes)));
      button.addEventListener("click", () => {
        if (isDirectory) loadDirectory(fullPath);
        else loadFile(fullPath, entry.size_bytes);
      });
      target.append(button);
    });
  }

  function iconForFile(name) {
    const ext = String(name).split(".").pop().toLowerCase();
    const map = { py: "π", js: "JS", ts: "TS", css: "#", html: "H", json: "{ }", md: "M", yml: "Y", yaml: "Y", txt: "T", sh: "$", toml: "T" };
    return map[ext] || "·";
  }

  async function loadFile(path, knownSize) {
    state.selectedFile = path;
    byId("editor-filename").textContent = path.split("/").pop();
    byId("editor-path").textContent = path;
    byId("active-path-label").textContent = path;
    byId("file-type-icon").textContent = iconForFile(path.split("/").pop());
    byId("editor-status").textContent = "LOADING SOURCE…";
    byId("editor-size").textContent = Number.isFinite(knownSize) ? formatSize(knownSize) : "—";
    byId("editor-body").replaceChildren(node("div", "code-empty", "Loading file…"));
    if (Number.isFinite(knownSize) && knownSize > 64 * 1024) {
      showCode(path, "This file is larger than the 64 KiB read limit. Select a smaller source file.", true);
      return;
    }
    try {
      let content;
      let source = "GITHUB MAIN";
      if (state.connected && state.runtime.workspace_read_enabled) {
        try {
          const response = await apiRequest("/workspace/read?path=" + encodeURIComponent(path));
          if (!response.ok || !response.output) throw new Error(response.error || "The workspace read was refused.");
          content = response.output.content;
          source = "LIVE WORKSPACE";
        } catch (error) {
          if (error.status === 401) throw error;
          content = await getGitHubFile(path);
        }
      } else {
        content = await getGitHubFile(path);
      }
      showCode(path, content, false);
      byId("editor-status").textContent = source + " · NO MODIFICATIONS";
      byId("editor-size").textContent = formatSize(new TextEncoder().encode(content).length);
      document.querySelectorAll(".tree-entry").forEach((item) => {
        item.classList.toggle("selected", item.title === path);
      });
      addActivity("FILE", "Read " + path + " from " + source + ".");
    } catch (error) {
      showCode(path, "File could not be read: " + error.message, true);
      byId("editor-status").textContent = "READ FAILED";
      addActivity("FILE", "Read refused for " + path + ".");
    }
  }

  async function getGitHubFile(path) {
    const response = await githubJson(GITHUB_API + "/contents/" + safeGitHubPath(path) + "?ref=main");
    if (!response || response.type !== "file" || typeof response.content !== "string") {
      throw new Error("GitHub did not return a text file.");
    }
    if (response.size > 64 * 1024) throw new Error("File exceeds the 64 KiB read limit.");
    const raw = atob(response.content.replace(/\s/g, ""));
    const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
    if (bytes.length > 64 * 1024) throw new Error("File exceeds the 64 KiB read limit.");
    if (bytes.includes(0)) throw new Error("Binary files are not available.");
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  }

  function showCode(path, content, isNotice) {
    const editor = byId("editor-body");
    editor.replaceChildren();
    const frame = node("div", "code-frame");
    const lines = String(content).split("\n");
    const numbers = node("div", "line-numbers", lines.map((_, i) => String(i + 1)).join("\n"));
    const source = node("pre", "code-content");
    const code = node("code", "");
    lines.forEach((line) => code.append(node("span", "code-line", line === "" ? " " : line)));
    source.append(code);
    frame.append(numbers, source);
    editor.append(frame);
    if (isNotice) editor.classList.add("editor-notice");
    else editor.classList.remove("editor-notice");
    byId("editor-filename").textContent = path.split("/").pop();
    byId("editor-path").textContent = path;
    byId("active-path-label").textContent = path;
  }

  byId("root-button").addEventListener("click", () => loadDirectory(""));
  byId("refresh-tree").addEventListener("click", () => loadDirectory(state.workspacePath));
  byId("sidebar-refresh").addEventListener("click", () => loadDirectory(state.workspacePath));

  function appendMessage(role, content, sourceLabel) {
    const article = node("article", "message " + (role === "user" ? "user-message" : "assistant-message"));
    article.append(node("div", "message-avatar", role === "user" ? "YOU" : "O"));
    const body = node("div", "message-content");
    const meta = node("div", "message-meta");
    meta.append(node("span", "", role === "user" ? "YOU" : "OMNITRIX CORE"), node("time", "", dateLabel(new Date().toISOString())));
    const bubble = node("div", "message-bubble", content);
    body.append(meta, bubble, node("div", "message-source", sourceLabel || (role === "user" ? "USER MESSAGE" : "MODEL RESPONSE")));
    article.append(body);
    byId("chat-messages").append(article);
    byId("chat-messages").scrollTop = byId("chat-messages").scrollHeight;
  }

  function showInitialChat() {
    byId("chat-messages").replaceChildren();
    const content = state.connected
      ? "Runtime connected. Send a message to run a real turn through the configured Omnitrix core."
      : "The Studio interface is ready, but it has not run a model. Connect the Python runtime to begin a real session. GitHub Pages can show the interface and public source, but cannot execute the Python orchestrator.";
    appendMessage("assistant", content, "STUDIO STATUS · NOT MODEL GENERATED");
  }

  async function submitChat(event) {
    event.preventDefault();
    const input = byId("chat-input");
    const message = input.value.trim();
    if (!message || state.busyChat) return;
    if (!state.connected) {
      toast("Connect the Python runtime before sending a real message.");
      openConnect();
      return;
    }
    state.busyChat = true;
    input.value = "";
    byId("chat-char-count").textContent = "0 / 8000";
    appendMessage("user", message, "SENT TO PYTHON BACKEND");
    byId("send-message").disabled = true;
    byId("chat-thread-subtitle").textContent = "Omnitrix is processing the turn…";
    addActivity("CHAT", "Message submitted to the configured Omnitrix backend.");
    try {
      const result = await apiRequest("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message }),
      });
      const source = result.provider_mode === "offline-demo"
        ? "OFFLINE DEMO · SIMULATED RESPONSE · NOT REAL INFERENCE"
        : "PYTHON ORCHESTRATOR · " + result.elapsed_seconds + "s";
      appendMessage("assistant", result.reply, source);
      byId("chat-thread-subtitle").textContent = result.provider_mode === "offline-demo"
        ? "Simulated demo provider · no real inference" : "Real configured provider adapter";
      byId("chat-mode").textContent = result.provider_mode === "offline-demo" ? "SIMULATED RESPONSES" : "MODEL ADAPTER ACTIVE";
      addActivity("CHAT", "Turn completed in " + result.elapsed_seconds + "s via " + result.provider_mode + ".");
    } catch (error) {
      appendMessage("assistant", error.message, "SYSTEM ERROR · NO VERIFIED COMPLETION");
      byId("chat-thread-subtitle").textContent = "Turn did not complete";
      addActivity("ERROR", "Chat request failed: " + error.message);
      if (error.status === 401) openConnect();
    } finally {
      state.busyChat = false;
      input.disabled = !state.connected;
      byId("send-message").disabled = !state.connected;
      byId("chat-char-count").textContent = input.value.length + " / 8000";
      input.focus();
    }
  }

  byId("chat-form").addEventListener("submit", submitChat);
  byId("chat-input").addEventListener("input", () => {
    byId("chat-char-count").textContent = byId("chat-input").value.length + " / 8000";
  });
  byId("chat-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      byId("chat-form").requestSubmit();
    }
  });
  byId("new-chat").addEventListener("click", () => {
    sessionId = (window.crypto && typeof window.crypto.randomUUID === "function")
      ? window.crypto.randomUUID()
      : "session_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 18);
    sessionStorage.setItem(SESSION_KEY, sessionId);
    showInitialChat();
    addActivity("CHAT", "Started a new in-memory conversation session.");
  });

  async function runTests() {
    if (!state.connected) {
      toast("Connect the Python runtime first.");
      openConnect();
      return;
    }
    if (!state.runtime.tests_enabled) {
      toast("Local test runner is disabled. Restart Studio with --allow-test-run.");
      return;
    }
    if (state.busyTests) return;
    state.busyTests = true;
    byId("run-tests").disabled = true;
    byId("run-tests").textContent = "RUNNING…";
    byId("terminal-state").textContent = "RUNNING";
    byId("terminal-state").style.color = "var(--amber)";
    byId("terminal-tests").hidden = false;
    byId("terminal-activity").hidden = true;
    document.querySelectorAll("[data-terminal-tab]").forEach((button) => button.classList.toggle("active", button.dataset.terminalTab === "tests"));
    byId("test-output").hidden = false;
    byId("test-output").textContent = "$ python -m unittest discover -s tests -v\nRunning the repository's fixed test suite…\n";
    addActivity("TEST", "Started the fixed Python unittest suite in the active workspace.");
    try {
      const result = await apiRequest("/tests/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      state.localTest = result;
      renderLocalTest(result);
      byId("test-output").textContent = result.output || "(No test output.)";
      byId("terminal-state").textContent = result.status.toUpperCase();
      byId("terminal-state").style.color = result.status === "passed" ? "var(--acid)" : "var(--red)";
      addActivity("TEST", "Local suite " + result.status + " with " + (result.test_count ?? "unknown") + " tests.");
      toast(result.status === "passed" ? "Local test suite passed." : "Local test suite " + result.status + ".");
    } catch (error) {
      byId("test-output").textContent = "TEST RUN DID NOT COMPLETE\n" + error.message;
      byId("terminal-state").textContent = "ERROR";
      byId("terminal-state").style.color = "var(--red)";
      addActivity("TEST", "Local test command failed to run: " + error.message);
    } finally {
      state.busyTests = false;
      byId("run-tests").textContent = "▶ RUN FULL TEST SUITE";
      byId("run-tests").disabled = !state.connected || !state.runtime.tests_enabled;
    }
  }
  byId("run-tests").addEventListener("click", runTests);
  byId("clear-output").addEventListener("click", () => {
    byId("test-output").textContent = "";
    byId("test-output").hidden = true;
    byId("terminal-state").textContent = "IDLE";
  });
  document.querySelectorAll("[data-terminal-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const tests = button.dataset.terminalTab === "tests";
      document.querySelectorAll("[data-terminal-tab]").forEach((item) => item.classList.toggle("active", item === button));
      byId("terminal-tests").hidden = !tests;
      byId("terminal-activity").hidden = tests;
    });
  });

  async function loadLatestLocalTest() {
    if (!state.connected) return;
    try {
      const result = await apiRequest("/tests/latest");
      state.localTest = result.result;
      renderLocalTest(state.localTest);
    } catch {
      // The test evidence area remains explicitly empty if the runtime cannot report it.
    }
  }

  function renderLocalTest(result) {
    if (!result) {
      byId("local-test-result").textContent = "NOT RUN";
      byId("local-test-title").textContent = "Local test suite";
      byId("local-test-description").textContent = "No local result recorded in this runtime yet.";
      byId("local-revision").textContent = state.runtime ? shortSha(state.runtime.revision) : "—";
      byId("local-test-count").textContent = "—";
      byId("local-test-duration").textContent = "—";
      return;
    }
    byId("local-test-result").textContent = String(result.status || "unknown").toUpperCase().replaceAll("_", " ");
    byId("local-test-result").className = "status-number small-number " + (result.status === "passed" ? "success" : result.status === "failed" ? "failure" : "pending");
    byId("local-test-title").textContent = result.status === "passed" ? "Local tests passed" : "Local tests did not pass";
    byId("local-test-description").textContent = result.finished_at ? "Finished " + dateLabel(result.finished_at) : "Latest test result in this runtime.";
    byId("local-revision").textContent = shortSha(result.revision);
    byId("local-test-count").textContent = result.test_count === null || result.test_count === undefined ? "—" : String(result.test_count);
    byId("local-test-duration").textContent = Number.isFinite(result.duration_seconds) ? result.duration_seconds + "s" : "—";
  }

  async function loadGitHubStatus() {
    const workflowList = byId("workflow-list");
    workflowList.replaceChildren(node("div", "empty-state", "Querying public GitHub Actions…"));
    const [runsResult, snapshotResult] = await Promise.allSettled([
      githubJson(GITHUB_API + "/actions/runs?branch=main&per_page=10"),
      fetch("./status.json?refresh=" + Date.now(), { cache: "no-store" }).then(async (response) => {
        if (!response.ok) return null;
        return response.json();
      }),
    ]);
    if (runsResult.status === "fulfilled") {
      state.workflows = Array.isArray(runsResult.value.workflow_runs) ? runsResult.value.workflow_runs : [];
      state.workflows.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      state.workflowError = null;
    } else {
      state.workflows = [];
      state.workflowError = runsResult.reason instanceof Error ? runsResult.reason.message : "Workflow status unavailable.";
    }
    state.snapshot = snapshotResult.status === "fulfilled" ? snapshotResult.value : null;
    renderStatus();
  }

  function workflowState(run) {
    if (!run) return { label: "UNKNOWN", kind: "unknown" };
    if (run.status !== "completed") {
      return { label: run.status === "in_progress" ? "RUNNING" : String(run.status || "queued").toUpperCase(), kind: "pending" };
    }
    if (run.conclusion === "success") return { label: "PASSED", kind: "success" };
    if (run.conclusion === "failure") return { label: "FAILED", kind: "failure" };
    if (run.conclusion === "cancelled") return { label: "CANCELLED", kind: "failure" };
    return { label: String(run.conclusion || "completed").toUpperCase(), kind: "unknown" };
  }

  function renderStatus() {
    const ci = state.workflows.find((run) => run.name === "CI") || null;
    const stateResult = workflowState(ci);
    const banner = byId("ci-banner");
    banner.classList.toggle("failed", stateResult.kind === "failure");
    banner.classList.toggle("running", stateResult.kind === "pending");
    banner.replaceChildren();
    banner.append(node("span", "status-icon", stateResult.kind === "success" ? "✓" : stateResult.kind === "failure" ? "!" : "⌁"));
    const copy = node("div");
    const heading = node("strong", "", ci ? (stateResult.kind === "success" ? "Latest CI workflow passed" : stateResult.kind === "failure" ? "Latest CI workflow failed" : "Latest CI workflow is still running") : "GitHub CI status unavailable");
    const detail = node("p", "", ci
      ? "Run #" + (ci.run_number || "—") + " · commit " + shortSha(ci.head_sha) + " · " + dateLabel(ci.created_at)
      : (state.workflowError || "No recent CI run was returned."));
    copy.append(heading, detail);
    banner.append(copy, node("span", "status-badge", ci ? stateResult.label : "UNKNOWN"));
    byId("nav-ci-state").textContent = ci ? (stateResult.kind === "success" ? "PASS" : stateResult.kind === "failure" ? "FAIL" : "RUN") : "—";
    byId("nav-ci-state").className = "nav-count " + stateResult.kind;
    byId("ci-result").textContent = ci ? stateResult.label : "UNKNOWN";
    byId("ci-result").className = "status-number " + stateResult.kind;
    byId("ci-title").textContent = ci ? "CI workflow " + stateResult.label.toLowerCase() : "Workflow result unknown";
    byId("ci-description").textContent = ci ? "This result belongs to the commit shown below." : (state.workflowError || "No CI workflow information is available.");
    byId("ci-run-no").textContent = ci ? "#" + (ci.run_number || "—") : "—";
    byId("ci-sha").textContent = ci ? shortSha(ci.head_sha) : "—";
    byId("ci-sha").title = ci ? ci.head_sha : "";
    byId("ci-updated").textContent = ci ? dateLabel(ci.updated_at || ci.created_at) : "—";
    byId("ci-run-link").href = ci && ci.html_url ? ci.html_url : "https://github.com/" + OWNER + "/" + REPO + "/actions";
    renderSnapshot();
    renderWorkflowList();
    renderLocalTest(state.localTest);
  }

  function renderSnapshot() {
    const snapshot = state.snapshot;
    if (!snapshot || !snapshot.test_count) {
      byId("snapshot-count").textContent = "—";
      byId("snapshot-title").textContent = "Snapshot not available";
      byId("snapshot-description").textContent = "This page is deployed only after verification. If the URL is still 404, check the Pages deploy workflow.";
      byId("snapshot-result").textContent = "UNKNOWN";
      byId("snapshot-sha").textContent = "—";
      byId("snapshot-date").textContent = "—";
      byId("snapshot-link").href = "https://github.com/" + OWNER + "/" + REPO + "/actions";
      return;
    }
    const passed = snapshot.test_status === "passed";
    byId("snapshot-count").textContent = String(snapshot.test_count);
    byId("snapshot-count").className = "status-number " + (passed ? "success" : "failure");
    byId("snapshot-title").textContent = passed ? "Tests passed in deployed build" : "Deployed snapshot did not pass";
    byId("snapshot-description").textContent = "Evidence generated by the successful website build, not from a placeholder.";
    byId("snapshot-result").textContent = String(snapshot.test_status || "unknown").toUpperCase();
    byId("snapshot-sha").textContent = shortSha(snapshot.commit_sha);
    byId("snapshot-sha").title = snapshot.commit_sha || "";
    byId("snapshot-date").textContent = dateLabel(snapshot.generated_at);
    byId("snapshot-link").href = snapshot.run_url || "https://github.com/" + OWNER + "/" + REPO + "/actions";
  }

  function renderWorkflowList() {
    const list = byId("workflow-list");
    list.replaceChildren();
    if (!state.workflows.length) {
      list.append(node("div", "empty-state", state.workflowError || "No recent workflow runs returned."));
      return;
    }
    state.workflows.slice(0, 10).forEach((run, index) => {
      const result = workflowState(run);
      const row = node("div", "workflow-row");
      row.append(node("span", "workflow-number", String(index + 1).padStart(2, "0")));
      const main = node("div", "workflow-main");
      const link = node("a", "", run.name || "Workflow");
      link.href = run.html_url || "https://github.com/" + OWNER + "/" + REPO + "/actions";
      link.target = "_blank";
      link.rel = "noreferrer";
      const meta = node("p", "", "RUN #" + (run.run_number || "—") + " · " + shortSha(run.head_sha) + " · " + String(run.event || "event").toUpperCase());
      main.append(link, meta);
      const side = node("div", "workflow-side");
      side.append(node("span", "workflow-state " + result.kind, result.label), node("time", "", relativeTime(run.created_at)));
      row.append(main, side);
      list.append(row);
    });
  }

  byId("refresh-workflows").addEventListener("click", loadGitHubStatus);

  function renderCapabilities() {
    const modelList = byId("model-list");
    const toolList = byId("tool-list");
    modelList.replaceChildren();
    toolList.replaceChildren();
    if (!state.connected) {
      byId("model-count").textContent = "BACKEND OFFLINE";
      byId("tool-count").textContent = "BACKEND OFFLINE";
      modelList.append(node("div", "empty-state", "A Gemini provider adapter and an offline demo adapter exist in the repository. Connect the runtime to inspect configured profiles."));
      toolList.append(node("div", "empty-state", "The calculator and optional read-only workspace inspector are registered in the core. Live permission flags require a runtime connection."));
      return;
    }
    const models = state.runtime.models || [];
    const tools = state.runtime.tools || [];
    byId("model-count").textContent = models.length + " MODEL(S)";
    byId("tool-count").textContent = tools.length + " TOOL(S)";
    if (!models.length) modelList.append(node("div", "empty-state", "No enabled models are configured."));
    models.forEach((model) => {
      const row = node("div", "registry-item");
      row.append(node("span", "registry-icon", model.provider === "demo" ? "D" : "M"));
      const main = node("div", "registry-main");
      main.append(node("strong", "", model.name));
      main.append(node("p", "", "Provider: " + model.provider + " · Model ID: " + (model.model_id || "not specified")));
      main.append(node("div", "registry-meta", "Capabilities: " + ((model.capabilities || []).join(", ") || "none declared")));
      row.append(main, node("span", "registry-status " + (model.provider === "demo" ? "limited" : ""), model.provider === "demo" ? "SIMULATED" : "CONFIGURED"));
      modelList.append(row);
    });
    if (!tools.length) toolList.append(node("div", "empty-state", "No tools registered."));
    tools.forEach((tool) => {
      const row = node("div", "registry-item");
      row.append(node("span", "registry-icon", tool.name === "calculator" ? "÷" : "▤"));
      const main = node("div", "registry-main");
      main.append(node("strong", "", tool.name));
      main.append(node("p", "", tool.description));
      main.append(node("div", "registry-meta", "Required: " + ((tool.capabilities || []).join(", ") || "none")));
      row.append(main, node("span", "registry-status " + (!tool.permission_granted ? "limited" : ""), tool.permission_granted ? "ALLOWED" : "DENIED"));
      toolList.append(row);
    });
  }

  function renderRecovery() {
    // The current backend exposes journal commands, not a web journal API. Keep the page explicit about this boundary.
  }

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.copy));
  });

  async function copyText(value) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
      } else {
        const textarea = node("textarea");
        textarea.value = value;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) throw new Error("Clipboard unavailable");
      }
      toast("Copied command.");
    } catch {
      toast("Copy failed. Select and copy the command manually.");
    }
  }

  byId("clear-output").addEventListener("click", () => {
    byId("test-output").textContent = "";
    byId("test-output").hidden = true;
    byId("terminal-state").textContent = "IDLE";
  });

  // Keep the current workspace readable even without a server by using public GitHub contents.
  updateConnectionUI();
  renderCapabilities();
  renderLocalTest(null);
  showInitialChat();
  addActivity("SYS", "Studio shell loaded. No model request has been made yet.");
  loadDirectory("");
  loadGitHubStatus();
  refreshBackend();

  window.setInterval(loadGitHubStatus, SESSION_REFRESH_MS);
  window.setInterval(() => {
    if (state.token) refreshBackend();
  }, RUNTIME_REFRESH_MS);

  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    window.addEventListener("load", async () => {
      try {
        const registration = await navigator.serviceWorker.register("./sw.js", { scope: "./" });
        registration.update().catch(() => {});
        window.setInterval(() => registration.update().catch(() => {}), SERVICE_WORKER_REFRESH_MS);
      } catch {
        // The app remains usable online without service-worker support.
      }
    });
  }
})();