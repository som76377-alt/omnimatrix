(function () {
  "use strict";

  const DB_NAME = "omnitrix-creative-studio";
  const DB_VERSION = 1;
  const PROJECT_ID = "active";
  const MAX_FILES_PER_IMPORT = 500;
  const $ = (id) => document.getElementById(id);
  const state = {
    db: null, assets: [], project: null, selectedAssetId: null, selectedClipId: null, selectedGraphicLayerId: null,
    loadedMedia: null, mediaLoadToken: 0, objectUrls: new Map(), thumbUrls: new Map(),
    isPlaying: false, exporting: false, recorder: null, chunks: [], raf: 0,
    playhead: 0, playStartedAt: 0, saveTimer: 0, audioContext: null,
    audioSource: null, audioOutput: null, audioMonitor: null, lastFrameUi: 0,
    currentClipId: null, error: null,
    creativeStatus: null, creativePlan: null, creativeSnapshot: null,
    creativeSelectedIds: [], creativeAllowReorder: false, creativeBusy: false, creativePlanApplied: false,
    onlineAssetResults: [], onlineSearchBusy: false, onlineImportBusy: false
  };
  const canvas = $("preview-canvas");
  const ctx = canvas.getContext("2d", { alpha: false });
  const sourceVideo = $("source-video");

  function toast(message) {
    const target = $("toast");
    target.textContent = message;
    target.classList.add("visible");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => target.classList.remove("visible"), 2800);
  }

  function formatTime(seconds) {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const secs = value % 60;
    return hours ? String(hours).padStart(2, "0") + ":" + String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0")
      : String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0");
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  }

  function slug(value) {
    return String(value || "omnitrix-cut").normalize("NFKD").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 70) || "omnitrix-cut";
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!("indexedDB" in window)) {
        reject(new Error("This browser does not support local IndexedDB storage."));
        return;
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("assets")) db.createObjectStore("assets", { keyPath: "id" });
        if (!db.objectStoreNames.contains("projects")) db.createObjectStore("projects", { keyPath: "id" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("Could not open local project storage."));
    });
  }

  function requestResult(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("Local storage operation failed."));
    });
  }

  async function dbGet(store, key) {
    const tx = state.db.transaction(store, "readonly");
    return requestResult(tx.objectStore(store).get(key));
  }

  async function dbPut(store, value) {
    const tx = state.db.transaction(store, "readwrite");
    const done = new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error("Could not save to local storage."));
      tx.onabort = () => reject(tx.error || new Error("Local save was cancelled."));
    });
    tx.objectStore(store).put(value);
    await done;
  }

  async function dbDelete(store, key) {
    const tx = state.db.transaction(store, "readwrite");
    const done = new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error("Could not delete from local storage."));
      tx.onabort = () => reject(tx.error || new Error("Local deletion was cancelled."));
    });
    tx.objectStore(store).delete(key);
    await done;
  }

  async function readAssetRows() {
    const all = await dbGetAll("assets");
    state.assets = all.map((row) => ({
      id: row.id, name: row.name, type: row.type, size: row.size,
      lastModified: row.lastModified, duration: row.duration || 0,
      width: row.width || 0, height: row.height || 0, thumb: row.thumb || null,
      importedAt: row.importedAt, sourceProvider: row.sourceProvider || "",
      sourcePage: row.sourcePage || "", attribution: row.attribution || "",
      license: row.license || "", licenseUrl: row.licenseUrl || "",
      rightsVerified: row.rightsVerified === true
    }));
    updateStorageLabel();
    renderAssets();
    updateStats();
  }

  function dbGetAll(storeName) {
    return new Promise((resolve, reject) => {
      const tx = state.db.transaction(storeName, "readonly");
      const request = tx.objectStore(storeName).getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error || new Error("Could not list local assets."));
    });
  }

  function thumbUrl(asset) {
    if (!asset || !asset.thumb) return "";
    if (!state.thumbUrls.has(asset.id)) state.thumbUrls.set(asset.id, URL.createObjectURL(asset.thumb));
    return state.thumbUrls.get(asset.id);
  }

  function assetById(id) {
    return state.assets.find((item) => item.id === id) || null;
  }

  function selectedClip() {
    return state.project.timeline.find((clip) => clip.id === state.selectedClipId) || null;
  }

  function totalDuration() {
    return state.project.timeline.reduce((sum, clip) => sum + Math.max(0, Number(clip.duration) || 0), 0);
  }

  function clipAtTime(time) {
    let cursor = 0;
    for (let index = 0; index < state.project.timeline.length; index += 1) {
      const clip = state.project.timeline[index];
      const end = cursor + Math.max(0.1, Number(clip.duration) || 0.1);
      if (time < end || index === state.project.timeline.length - 1) {
        return { clip: clip, index: index, localTime: Math.max(0, time - cursor), start: cursor, end: end };
      }
      cursor = end;
    }
    return null;
  }

  function createClip(asset) {
    return {
      id: crypto.randomUUID(), assetId: asset.id, name: asset.name,
      sourceIn: 0, duration: asset.type.startsWith("video/") ? Math.max(0.5, Math.min(asset.duration || 5, 600)) : 4,
      fit: "cover", motion: "none", title: "", subtitle: "",
      titlePosition: "bottom", titleColor: "#d6fa62", titleSize: 44, titleFont: "sans", layers: []
    };
  }

  function defaultProject() {
    return { id: PROJECT_ID, name: "Untitled film", brief: "", timeline: [], updatedAt: new Date().toISOString() };
  }

  async function loadProject() {
    state.project = (await dbGet("projects", PROJECT_ID)) || defaultProject();
    if (!Array.isArray(state.project.timeline)) state.project.timeline = [];
    $("project-name").value = state.project.name || "Untitled film";
    $("creative-brief").value = state.project.brief || "";
    await readAssetRows();
    state.selectedClipId = state.project.selectedClipId || (state.project.timeline[0] && state.project.timeline[0].id) || null;
    renderTimeline();
    renderInspector();
    updateStats();
    drawFrame();
    $("autosave-state").textContent = state.project.updatedAt ? "Saved " + formatTime((Date.now() - new Date(state.project.updatedAt).getTime()) / 1000) + " ago" : "Not saved yet";
  }

  async function saveProject(showToast) {
    if (!state.project) return;
    state.project.name = $("project-name").value.trim().slice(0, 100) || "Untitled film";
    state.project.brief = $("creative-brief").value.slice(0, 4000);
    state.project.selectedClipId = state.selectedClipId;
    state.project.updatedAt = new Date().toISOString();
    try {
      await dbPut("projects", state.project);
      $("autosave-state").textContent = "Saved just now";
      if (showToast) toast("Project saved on this device.");
    } catch (error) {
      $("autosave-state").textContent = "Save failed";
      showMessage("Could not save project: " + error.message, true);
    }
  }

  function scheduleSave() {
    $("autosave-state").textContent = "Saving…";
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(() => saveProject(false), 350);
  }

  async function updateStorageLabel() {
    const label = $("storage-state");
    if (!navigator.storage || !navigator.storage.estimate) {
      label.textContent = "LOCAL WORKSPACE";
      return;
    }
    try {
      const usage = await navigator.storage.estimate();
      const used = usage.usage || 0;
      const quota = usage.quota || 0;
      label.textContent = "LOCAL STORAGE · " + formatBytes(used) + (quota ? " / " + formatBytes(quota) : "");
    } catch {
      label.textContent = "LOCAL WORKSPACE";
    }
  }

  function makeThumbnailFromCanvas(source, width, height) {
    const maxW = 360;
    const maxH = 220;
    const scale = Math.min(maxW / Math.max(1, width), maxH / Math.max(1, height), 1);
    const w = Math.max(1, Math.round(width * scale));
    const h = Math.max(1, Math.round(height * scale));
    const thumbCanvas = document.createElement("canvas");
    thumbCanvas.width = w;
    thumbCanvas.height = h;
    const tctx = thumbCanvas.getContext("2d", { alpha: false });
    tctx.fillStyle = "#10130f";
    tctx.fillRect(0, 0, w, h);
    const cover = Math.max(w / Math.max(1, width), h / Math.max(1, height));
    const dw = width * cover;
    const dh = height * cover;
    tctx.drawImage(source, (w - dw) / 2, (h - dh) / 2, dw, dh);
    return new Promise((resolve) => thumbCanvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.76));
  }

  async function inspectFile(file) {
    if (file.type.startsWith("image/")) {
      const bitmap = await createImageBitmap(file);
      const width = bitmap.width;
      const height = bitmap.height;
      const thumb = await makeThumbnailFromCanvas(bitmap, width, height);
      if (bitmap.close) bitmap.close();
      return { type: file.type, width: width, height: height, duration: 0, thumb: thumb };
    }
    if (file.type.startsWith("video/")) {
      const url = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      try {
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("Timed out reading video metadata.")), 15000);
          video.onloadedmetadata = () => { clearTimeout(timeout); resolve(); };
          video.onerror = () => { clearTimeout(timeout); reject(new Error("Browser could not read this video format.")); };
          video.src = url;
        });
        const duration = Number.isFinite(video.duration) ? video.duration : 0;
        let thumb = null;
        if (video.videoWidth && video.videoHeight) {
          await new Promise((resolve) => {
            const timeout = setTimeout(resolve, 1800);
            video.onseeked = () => { clearTimeout(timeout); resolve(); };
            try { video.currentTime = Math.min(0.12, Math.max(0, duration * 0.03)); } catch { clearTimeout(timeout); resolve(); }
          });
          if (video.readyState >= 2 && video.videoWidth) {
            thumb = await makeThumbnailFromCanvas(video, video.videoWidth, video.videoHeight);
          }
        }
        return { type: file.type, width: video.videoWidth || 0, height: video.videoHeight || 0, duration: duration, thumb: thumb };
      } finally {
        video.removeAttribute("src");
        video.load();
        URL.revokeObjectURL(url);
      }
    }
    throw new Error("Unsupported file type. Import images and video clips for this build.");
  }

  async function importFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    if (files.length > MAX_FILES_PER_IMPORT) {
      showMessage("Please import up to " + MAX_FILES_PER_IMPORT + " files per batch. Your files are not modified.", true);
      return;
    }
    const accepted = files.filter((file) => file.type.startsWith("image/") || file.type.startsWith("video/"));
    if (accepted.length !== files.length) toast("Some files were skipped. Import image and video files in this build.");
    if (!accepted.length) return;
    $("upload-progress").hidden = false;
    $("media-input").disabled = true;
    let imported = 0;
    let failed = 0;
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
    for (let i = 0; i < accepted.length; i += 1) {
      const file = accepted[i];
      $("upload-progress-bar").style.width = Math.round((i / accepted.length) * 100) + "%";
      $("upload-progress-text").textContent = "Preparing " + (i + 1) + " of " + accepted.length + " · " + file.name;
      try {
        const metadata = await inspectFile(file);
        const row = {
          id: crypto.randomUUID(), name: file.name, type: metadata.type, size: file.size,
          lastModified: file.lastModified, duration: metadata.duration || 0,
          width: metadata.width || 0, height: metadata.height || 0, thumb: metadata.thumb || null,
          blob: file, importedAt: new Date().toISOString()
        };
        await dbPut("assets", row);
        imported += 1;
      } catch (error) {
        failed += 1;
        console.warn("Creative Studio import failed for " + file.name, error);
      }
    }
    $("upload-progress-bar").style.width = "100%";
    $("upload-progress-text").textContent = imported + " imported" + (failed ? " · " + failed + " failed" : "");
    await readAssetRows();
    renderAssets();
    $("media-input").disabled = false;
    window.setTimeout(() => { $("upload-progress").hidden = true; }, 1300);
    toast(imported ? "Imported " + imported + " media asset" + (imported === 1 ? "" : "s") + "." : "No media assets were imported.");
    if (failed) showMessage(failed + " file(s) could not be imported. Try a browser-supported image or video format.", true);
  }

  function onlineStatus(message, kind) {
    const target = $("online-asset-status");
    if (!target) return;
    target.textContent = message || "";
    target.className = "online-asset-status" + (kind ? " " + kind : "");
  }

  function deriveAssetQuery(brief) {
    let value = String(brief || "").trim();
    value = value.replace(/\b(?:create|make|produce|generate|build|a|an|the|video|film|clip|short|vertical|horizontal|cinematic|premium|realistic|documentary|reel|shorts|explaining|explain|showing|show|about|for|with|please|use|style|duration|seconds?|secs?|\d{1,3}|9:16|16:9)\b/gi, " ");
    value = value.replace(/[^\p{L}\p{N}\s-]/gu, " ").replace(/\s+/g, " ").trim();
    return value.slice(0, 180) || String(brief || "").trim().slice(0, 180);
  }

  function safeExternalHttps(value) {
    try {
      const parsed = new URL(String(value || ""));
      return parsed.protocol === "https:" && !parsed.username && !parsed.password ? parsed.href : "";
    } catch { return ""; }
  }

  function safePreviewUrl(item) {
    try {
      const parsed = new URL(String(item.preview_url || ""));
      const allowed = item.provider === "commons"
        ? new Set(["upload.wikimedia.org"])
        : item.provider === "pexels" ? new Set(["images.pexels.com"]) : new Set();
      return parsed.protocol === "https:" && allowed.has(parsed.hostname.toLowerCase()) ? parsed.href : "";
    } catch { return ""; }
  }

  function supportedOnlineAsset(item) {
    const mime = String(item.mime_type || "").toLowerCase();
    return Boolean(item && ["commons", "pexels"].includes(item.provider) &&
      (["image/jpeg", "image/png", "image/webp", "image/avif", "video/mp4", "video/webm"].includes(mime)) &&
      /^https:\/\//i.test(String(item.asset_url || "")) &&
      (item.rights_verified === true));
  }

  function renderOnlineResults(response) {
    const target = $("online-asset-results");
    target.replaceChildren();
    const items = response && Array.isArray(response.items) ? response.items : [];
    if (response && response.provider === "pinterest" && response.search_url) {
      const note = document.createElement("div");
      note.className = "empty-state";
      const heading = document.createElement("strong");
      heading.textContent = "Pinterest reference search";
      const copy = document.createElement("span");
      copy.textContent = "Open Pinterest to browse inspiration. Pins are not copied automatically because source rights and platform permissions must be respected.";
      const link = document.createElement("a");
      link.href = safeExternalHttps(response.search_url) || "https://www.pinterest.com/";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "OPEN PINTEREST RESULTS ↗";
      note.append(heading, copy, link);
      target.append(note);
      return;
    }
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const heading = document.createElement("strong");
      heading.textContent = "No importable matches";
      const copy = document.createElement("span");
      copy.textContent = "Try a broader search or switch source. Only results with supported media formats and licence metadata can be imported automatically.";
      empty.append(heading, copy);
      target.append(empty);
      return;
    }
    for (const item of items) {
      const card = document.createElement("article");
      card.className = "online-asset-card";
      const preview = safePreviewUrl(item);
      if (preview) {
        const image = document.createElement("img");
        image.loading = "lazy";
        image.referrerPolicy = "no-referrer";
        image.src = preview;
        image.alt = "";
        image.addEventListener("error", () => { image.hidden = true; }, { once: true });
        card.append(image);
      }
      const body = document.createElement("div");
      body.className = "online-asset-card-body";
      const title = document.createElement("div");
      title.className = "online-asset-title";
      title.textContent = item.title || "Untitled asset";
      const meta = document.createElement("div");
      meta.className = "online-asset-meta";
      meta.textContent = [String(item.kind || "media").toUpperCase(), item.attribution ? "By " + item.attribution : item.provider].filter(Boolean).join(" · ");
      const licence = document.createElement("div");
      licence.className = "online-asset-license";
      licence.textContent = item.license || "Licence not identified — verify before reuse";
      body.append(title, meta, licence);
      if (item.description) {
        const description = document.createElement("div");
        description.className = "online-asset-meta";
        description.textContent = String(item.description).slice(0, 220);
        body.append(description);
      }
      const actions = document.createElement("div");
      actions.className = "online-asset-card-actions";
      const source = document.createElement("a");
      source.className = "button quiet small";
      source.href = safeExternalHttps(item.source_page) || "https://commons.wikimedia.org/";
      source.target = "_blank";
      source.rel = "noopener noreferrer";
      source.textContent = "SOURCE ↗";
      actions.append(source);
      const add = document.createElement("button");
      add.type = "button";
      add.className = "button primary small";
      add.textContent = "IMPORT + ADD";
      add.disabled = !supportedOnlineAsset(item);
      add.title = add.disabled ? "Supported media and identifiable licence metadata are required for automatic import." : "Download a bounded copy and add it to your local timeline";
      add.addEventListener("click", async () => {
        add.disabled = true;
        add.textContent = "IMPORTING…";
        try {
          const id = await importOnlineAsset(item, true);
          onlineStatus("Imported " + item.title + " and added it to the local timeline. Original source and licence metadata are saved with the asset.", "success");
          add.textContent = "ADDED";
          add.disabled = true;
          return id;
        } catch (error) {
          add.textContent = "RETRY IMPORT";
          add.disabled = false;
          onlineStatus(String(error.message || error), "error");
        }
      });
      actions.append(add);
      body.append(actions);
      card.append(body);
      target.append(card);
    }
  }

  async function searchOnlineAssets(options) {
    const provider = $("online-asset-provider").value || "commons";
    const queryInput = $("online-asset-query");
    let query = String(queryInput.value || "").trim();
    if (!query) query = deriveAssetQuery($("creative-brief").value);
    if (!query) {
      onlineStatus("Enter a search phrase or describe the video in the Director's Brief.", "error");
      return null;
    }
    queryInput.value = query;
    if (state.onlineSearchBusy) return null;
    if (provider === "pinterest") {
      const link = "https://www.pinterest.com/search/pins/?" + new URLSearchParams({ q: query }).toString();
      renderOnlineResults({ provider: "pinterest", search_url: link, items: [] });
      onlineStatus("Pinterest is available as a reference search. Omnitrix does not scrape or auto-import Pins.", "");
      return { provider, query, items: [], search_url: link, manual_reference_only: true };
    }
    const token = aiRuntimeToken();
    if (!token) {
      onlineStatus("The authenticated Python-backed Studio runtime is not connected in this tab. Open the core Studio, connect its runtime, then return here.", "error");
      return null;
    }
    state.onlineSearchBusy = true;
    $("search-online-assets").disabled = true;
    onlineStatus("Searching " + (provider === "commons" ? "Wikimedia Commons" : "Pexels") + " for “" + query + "”…", "");
    try {
      const params = new URLSearchParams({ q: query, provider, kind: $("online-asset-kind").value || "any", limit: "12" });
      const response = await fetch("./api/creative/search?" + params.toString(), {
        method: "GET", cache: "no-store",
        headers: { Accept: "application/json", Authorization: "Bearer " + token }
      });
      let data;
      try { data = await response.json(); }
      catch { throw new Error("Asset search returned unreadable JSON."); }
      if (!response.ok || !data || data.ok !== true) throw new Error((data && data.error) || "Online asset search failed.");
      state.onlineAssetResults = data.items || [];
      renderOnlineResults(data);
      onlineStatus(
        (data.count || state.onlineAssetResults.length) + " result(s) from " + provider + ". " +
        (data.note || "Review each source and licence before publishing."),
        "success"
      );
      return data;
    } catch (error) {
      onlineStatus(String(error.message || error), "error");
      return null;
    } finally {
      state.onlineSearchBusy = false;
      $("search-online-assets").disabled = false;
    }
  }

  async function importOnlineAsset(item, addToTimeline) {
    if (!supportedOnlineAsset(item)) throw new Error("This result has no supported media format or identifiable licence metadata; it was not imported.");
    if (state.onlineImportBusy) throw new Error("Another online asset is still importing. Retry after it finishes.");
    state.onlineImportBusy = true;
    try {
      const token = aiRuntimeToken();
      if (!token) throw new Error("The authenticated Studio runtime is not connected.");
      onlineStatus("Downloading a bounded copy of “" + (item.title || "asset") + "”…", "");
      const params = new URLSearchParams({ provider: item.provider, url: item.asset_url });
      const response = await fetch("./api/creative/assets/download?" + params.toString(), {
        method: "GET", cache: "no-store",
        headers: { Authorization: "Bearer " + token }
      });
      if (!response.ok) {
        let failure = {};
        try { failure = await response.json(); } catch {}
        throw new Error(failure.error || "The source could not provide this media file.");
      }
      const blob = await response.blob();
      if (!blob.size || blob.size > 24 * 1024 * 1024) throw new Error("The downloaded asset is empty or exceeds the 24 MB import limit.");
      const mime = (blob.type || item.mime_type || "").split(";")[0].toLowerCase();
      if (!["image/jpeg", "image/png", "image/webp", "image/avif", "video/mp4", "video/webm"].includes(mime)) {
        throw new Error("The downloaded file has an unsupported media type: " + (mime || "unknown") + ".");
      }
      const extension = ({ "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/avif": ".avif", "video/mp4": ".mp4", "video/webm": ".webm" })[mime];
      const base = slug(String(item.title || "online-asset")).slice(0, 75);
      const file = new File([blob], base + extension, { type: mime, lastModified: Date.now() });
      const metadata = await inspectFile(file);
      if (file.type.startsWith("video/") && (!metadata.duration || !metadata.thumb)) {
        throw new Error("The browser could not inspect this video or create its preview thumbnail. It was not added.");
      }
      const existing = state.assets.find((asset) => asset.sourcePage && asset.sourcePage === item.source_page && asset.sourceProvider === item.provider);
      if (existing) {
        if (addToTimeline) addAssetToTimeline(existing.id);
        return existing.id;
      }
      const row = {
        id: crypto.randomUUID(), name: file.name, type: metadata.type, size: file.size,
        lastModified: file.lastModified, duration: metadata.duration || 0,
        width: metadata.width || 0, height: metadata.height || 0, thumb: metadata.thumb || null,
        blob: file, importedAt: new Date().toISOString(),
        sourceProvider: item.provider, sourcePage: String(item.source_page || ""),
        attribution: String(item.attribution || "").slice(0, 180),
        license: String(item.license || "").slice(0, 180),
        licenseUrl: String(item.license_url || "").slice(0, 500),
        rightsVerified: item.rights_verified === true
      };
      await dbPut("assets", row);
      state.assets.unshift({
        id: row.id, name: row.name, type: row.type, size: row.size,
        lastModified: row.lastModified, duration: row.duration, width: row.width, height: row.height,
        thumb: row.thumb, importedAt: row.importedAt,
        sourceProvider: row.sourceProvider, sourcePage: row.sourcePage, attribution: row.attribution,
        license: row.license, licenseUrl: row.licenseUrl, rightsVerified: row.rightsVerified
      });
      renderAssets();
      updateStats();
      if (addToTimeline) addAssetToTimeline(row.id);
      else scheduleSave();
      return row.id;
    } finally {
      state.onlineImportBusy = false;
    }
  }

  function extractBriefTitle(brief) {
    let text = String(brief || "").trim();
    const markers = [/(?:explaining|about|covering|showing|on the topic of)\s+(.+?)(?:[.!?]|$)/i, /(?:video|film|clip)\s+(?:about|on)\s+(.+?)(?:[.!?]|$)/i];
    for (const pattern of markers) {
      const match = text.match(pattern);
      if (match && match[1]) { text = match[1]; break; }
    }
    text = text.replace(/^how\s+/i, "").replace(/\b(?:in|for)\s+\d+\s*(?:seconds?|secs?)\b/gi, "");
    text = text.replace(/\b(?:vertical|horizontal|cinematic|realistic|premium|science|documentary|style|video)\b/gi, " ");
    text = text.replace(/\s+/g, " ").trim().replace(/[.!?]+$/, "");
    return text ? text.slice(0, 76).toLocaleUpperCase() : "A CLOSER LOOK";
  }

  async function buildDraftFromBrief() {
    if (state.onlineImportBusy || state.onlineSearchBusy) {
      onlineStatus("Another asset task is running. Wait for it to finish before starting a second one.", "error");
      return;
    }
    const brief = String($("creative-brief").value || "").trim();
    if (!brief) {
      onlineStatus("Write your desired video in Director's Brief first, then press Auto-assemble Draft.", "error");
      $("creative-brief").focus();
      return;
    }
    const provider = $("online-asset-provider").value || "commons";
    if (provider === "pinterest") {
      onlineStatus("Pinterest is for inspiration links here, not reusable source media. Switch to Wikimedia Commons or configured Pexels for importable assets.", "error");
      await searchOnlineAssets();
      return;
    }
    if (state.project.timeline.length && !window.confirm("Append a new draft to your existing timeline? Existing shots will be kept.")) return;
    $("build-from-brief").disabled = true;
    try {
      if (!$("online-asset-query").value.trim()) $("online-asset-query").value = deriveAssetQuery(brief);
      let data = await searchOnlineAssets();
      if (!data || !Array.isArray(data.items)) return;
      let eligible = data.items.filter(supportedOnlineAsset);
      if (!eligible.length && provider === "pexels") {
        onlineStatus("No importable Pexels results. Check its server-side key or switch to Wikimedia Commons.", "error");
        return;
      }
      if (!eligible.length && provider === "commons") {
        onlineStatus("No results with supported formats and identifiable licences were found. Try a broader phrase; nothing was imported.", "error");
        return;
      }
      const terms = deriveAssetQuery(brief).toLowerCase().split(/\s+/).filter((word) => word.length > 2);
      const ranked = eligible.map((item, index) => {
        const haystack = (item.title + " " + item.description).toLowerCase();
        const score = terms.reduce((sum, word) => sum + (haystack.includes(word) ? 1 : 0), 0);
        return { item, index, score };
      }).sort((a, b) => b.score - a.score || a.index - b.index);
      const selected = [];
      const seen = new Set();
      for (const row of ranked) {
        const key = String(row.item.title || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
        if (!key || seen.has(key)) continue;
        seen.add(key);
        selected.push(row.item);
        if (selected.length >= 4) break;
      }
      if (!selected.length) throw new Error("No licence-identified assets passed the format and rights checks. Nothing was imported.");
      const secondsMatch = brief.match(/\b(\d{1,3})\s*(?:-| )?\s*(?:seconds?|secs?)\b/i);
      const targetSeconds = Math.min(45, Math.max(4, secondsMatch ? Number(secondsMatch[1]) : 12));
      const importedIds = [];
      for (let i = 0; i < selected.length; i += 1) {
        onlineStatus("Building draft: importing selected asset " + (i + 1) + " of " + selected.length + "…", "");
        const id = await importOnlineAsset(selected[i], false);
        importedIds.push(id);
      }
      // Add the selected assets as one batch after all downloads/metadata checks succeed.
      const startIndex = state.project.timeline.length;
      importedIds.forEach((id) => addAssetToTimeline(id));
      const draftClips = state.project.timeline.slice(startIndex);
      const baseDuration = targetSeconds / Math.max(1, draftClips.length);
      const title = extractBriefTitle(brief);
      draftClips.forEach((clip, index) => {
        const asset = assetById(clip.assetId);
        let duration = Math.min(6, Math.max(2, baseDuration));
        if (asset && asset.type.startsWith("video/") && Number(asset.duration) > 0) {
          duration = Math.min(duration, Number(asset.duration));
          clip.motion = "none";
        } else {
          clip.motion = index === 0 ? "slow-zoom" : "none";
        }
        clip.duration = Math.max(0.5, duration);
        clip.fit = "cover";
        clip.title = index === 0 ? title : "";
        clip.subtitle = "";
        clip.titlePosition = "bottom";
        clip.titleColor = "#f1f3e8";
        clip.titleSize = 44;
        clip.titleFont = "sans";
        clip.layers = Array.isArray(clip.layers) ? clip.layers : [];
      });
      state.selectedClipId = draftClips[0] ? draftClips[0].id : state.selectedClipId;
      state.currentClipId = state.selectedClipId;
      state.playhead = Math.max(0, startIndex >= 0 ? state.project.timeline.slice(0, startIndex).reduce((sum, clip) => sum + clip.duration, 0) : 0);
      renderTimeline();
      renderInspector();
      renderGraphicLayers();
      updateStats();
      drawFrame();
      await saveProject(false);
      const automaticDirection = $("auto-creative-consent").checked;
      $("ai-director-panel").hidden = false;
      renderAiSelectionList();
      // Select only the newly assembled clips, never earlier project shots.
      const draftIds = new Set(draftClips.map((clip) => clip.id));
      $("ai-selection-list").querySelectorAll("input.ai-asset-check").forEach((checkbox) => {
        checkbox.checked = draftIds.has(checkbox.value);
      });
      updateAiControls();

      if (automaticDirection) {
        // The separate checkbox explicitly authorizes this one model call and local auto-apply.
        $("ai-consent").checked = true;
        await loadAiModelStatus();
        if (state.creativeStatus && state.creativeStatus.configured) {
          onlineStatus("Asset draft assembled. The visual director is now examining only the new shots' resized thumbnails…", "");
          await runAiDirection();
          if (state.creativePlan && Array.isArray(state.creativePlan.operations) && state.creativePlan.operations.length) {
            applyAiPlan();
          }
          if (state.creativePlanApplied) {
            onlineStatus("The visual director's validated edits were applied to this draft. Starting a local WebM export; inspect it before publishing.", "success");
          } else {
            onlineStatus("The basic timeline is ready, but no validated visual-director edits were applied. " +
              (String($("ai-status").textContent || "").trim() || "Check the Director status and review the timeline.") +
              " Starting a local WebM export of the supported draft.", "");
          }
        } else {
          onlineStatus("A basic draft was assembled, but the visual model is not configured or reachable. No AI visual analysis was claimed. Starting a local WebM export of the basic draft.", "");
        }
        await saveProject(false);
        $("ai-director-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        renderVideo();
      } else {
        onlineStatus(
          "Draft assembled from " + selected.length + " web result(s), target " + targetSeconds + " seconds. Asset matching used titles, descriptions and licence metadata, not a model visually judging the source results. Preview the sequence; tick the optional automatic-direction consent to have the configured vision model inspect resized thumbnails, apply supported graphic/edit suggestions and export a draft.",
          "success"
        );
        await loadAiModelStatus();
        $("ai-director-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      onlineStatus(String(error.message || error), "error");
    } finally {
      state.onlineImportBusy = false;
      $("build-from-brief").disabled = false;
    }
  }

  function renderAssets() {
    const target = $("asset-grid");
    const search = $("asset-search").value.trim().toLowerCase();
    target.replaceChildren();
    const items = state.assets.filter((asset) => asset.name.toLowerCase().includes(search));
    $("library-count").textContent = String(state.assets.length);
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const strong = document.createElement("strong");
      strong.textContent = search ? "No matching files." : "Your visual library starts here.";
      const note = document.createElement("span");
      note.textContent = search ? "Try a different filename." : "Upload multiple images or clips at once. Originals stay in this browser profile.";
      empty.append(strong, note);
      target.append(empty);
      return;
    }
    for (const asset of items) {
      const card = document.createElement("article");
      card.className = "asset-card" + (state.selectedAssetId === asset.id ? " selected" : "");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", "Select " + asset.name);
      const thumb = document.createElement("div");
      thumb.className = "asset-thumb";
      if (asset.thumb) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = "";
        img.src = thumbUrl(asset);
        thumb.append(img);
      } else {
        const icon = document.createElement("span");
        icon.textContent = "VIDEO";
        icon.style.font = "10px var(--mono)";
        icon.style.color = "var(--green)";
        thumb.append(icon);
      }
      if (asset.type.startsWith("video/")) {
        const badge = document.createElement("span");
        badge.className = "video-badge";
        badge.textContent = "▶ " + formatTime(asset.duration);
        thumb.append(badge);
      }
      const info = document.createElement("div");
      info.className = "asset-info";
      const name = document.createElement("span");
      name.className = "asset-name";
      name.textContent = asset.name;
      const meta = document.createElement("div");
      meta.className = "asset-meta";
      const kind = document.createElement("span");
      kind.textContent = asset.type.startsWith("video/") ? "VIDEO" : "IMAGE";
      const size = document.createElement("span");
      size.textContent = formatBytes(asset.size);
      meta.append(kind, size);
      info.append(name, meta);
      if (asset.sourceProvider && asset.sourcePage) {
        const sourceNote = document.createElement("div");
        sourceNote.className = "asset-source-note";
        sourceNote.textContent = (asset.sourceProvider.toUpperCase() + " · " + (asset.license || "licence unknown")).slice(0, 220);
        if (asset.licenseUrl) {
          const licenceLink = document.createElement("a");
          licenceLink.href = safeExternalHttps(asset.licenseUrl) || "https://commons.wikimedia.org/";
          licenceLink.target = "_blank";
          licenceLink.rel = "noopener noreferrer";
          licenceLink.textContent = " Licence ↗";
          sourceNote.append(licenceLink);
        }
        const sourceLink = document.createElement("a");
        sourceLink.href = safeExternalHttps(asset.sourcePage) || "https://commons.wikimedia.org/";
        sourceLink.target = "_blank";
        sourceLink.rel = "noopener noreferrer";
        sourceLink.textContent = " Source ↗";
        sourceNote.append(sourceLink);
        info.append(sourceNote);
      }
      const remove = document.createElement("button");
      remove.className = "asset-delete";
      remove.type = "button";
      remove.textContent = "×";
      remove.title = "Remove from local media library";
      remove.setAttribute("aria-label", "Remove " + asset.name + " from library");
      remove.addEventListener("click", (event) => { event.stopPropagation(); deleteAsset(asset.id); });
      const add = document.createElement("button");
      add.className = "asset-quick-add";
      add.type = "button";
      add.textContent = "+ ADD TO TIMELINE";
      add.addEventListener("click", (event) => { event.stopPropagation(); addAssetToTimeline(asset.id); });
      card.append(thumb, info, add, remove);
      card.addEventListener("click", () => selectAsset(asset.id));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectAsset(asset.id); }
      });
      target.append(card);
    }
  }

  function selectAsset(id) {
    state.selectedAssetId = id;
    const clip = state.project.timeline.find((item) => item.assetId === id);
    if (clip && !state.selectedClipId) state.selectedClipId = clip.id;
    renderAssets();
    if (!state.project.timeline.length) {
      renderInspector();
      loadMediaForPreview(id, null);
      drawFrame();
    }
  }

  function addAssetToTimeline(id) {
    const asset = assetById(id);
    if (!asset) return;
    const clip = createClip(asset);
    state.project.timeline.push(clip);
    state.selectedAssetId = id;
    state.selectedClipId = clip.id;
    renderTimeline();
    renderInspector();
    updateStats();
    scheduleSave();
    drawFrame();
    toast("Added shot to timeline.");
  }

  function addAllAssets() {
    const used = new Set(state.project.timeline.map((clip) => clip.assetId));
    const missing = state.assets.filter((asset) => !used.has(asset.id));
    if (!missing.length) { toast("Every library asset is already on the timeline."); return; }
    missing.forEach((asset) => state.project.timeline.push(createClip(asset)));
    if (!state.selectedClipId && state.project.timeline.length) state.selectedClipId = state.project.timeline[0].id;
    renderTimeline();
    renderInspector();
    updateStats();
    scheduleSave();
    drawFrame();
    toast("Added " + missing.length + " shot(s) to the timeline.");
  }

  function renderTimeline() {
    const target = $("timeline-list");
    target.replaceChildren();
    const clips = state.project.timeline;
    $("timeline-count").textContent = clips.length + " SHOT" + (clips.length === 1 ? "" : "S");
    if (!clips.length) {
      const empty = document.createElement("div");
      empty.className = "timeline-empty";
      empty.textContent = "Add assets from the library to build your first sequence.";
      target.append(empty);
      return;
    }
    clips.forEach((clip, index) => {
      const asset = assetById(clip.assetId);
      const card = document.createElement("div");
      card.className = "timeline-clip" + (clip.id === state.selectedClipId ? " selected" : "");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", "Edit shot " + (index + 1) + " " + clip.name);
      const thumb = document.createElement("div");
      thumb.className = "timeline-clip-thumb";
      if (asset && asset.thumb) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.src = thumbUrl(asset);
        img.alt = "";
        thumb.append(img);
      } else {
        thumb.textContent = "SHOT " + String(index + 1).padStart(2, "0");
      }
      const details = document.createElement("div");
      details.className = "timeline-clip-details";
      const name = document.createElement("div");
      name.className = "timeline-clip-name";
      name.textContent = (index + 1).toString().padStart(2, "0") + " · " + (clip.title || clip.name);
      const sub = document.createElement("div");
      sub.className = "timeline-clip-sub";
      sub.textContent = formatTime(clip.duration) + " · " + (clip.motion === "none" ? "STATIC" : clip.motion.toUpperCase());
      details.append(name, sub);
      const controls = document.createElement("div");
      controls.className = "timeline-controls";
      const up = document.createElement("button");
      up.type = "button"; up.textContent = "↑"; up.title = "Move shot earlier"; up.setAttribute("aria-label", "Move shot earlier");
      up.disabled = index === 0;
      up.addEventListener("click", (event) => { event.stopPropagation(); moveClip(index, -1); });
      const down = document.createElement("button");
      down.type = "button"; down.textContent = "↓"; down.title = "Move shot later"; down.setAttribute("aria-label", "Move shot later");
      down.disabled = index === clips.length - 1;
      down.addEventListener("click", (event) => { event.stopPropagation(); moveClip(index, 1); });
      const remove = document.createElement("button");
      remove.type = "button"; remove.textContent = "×"; remove.title = "Remove from timeline"; remove.setAttribute("aria-label", "Remove shot");
      remove.addEventListener("click", (event) => { event.stopPropagation(); removeClip(clip.id); });
      controls.append(up, down, remove);
      card.append(thumb, details, controls);
      card.addEventListener("click", () => selectClip(clip.id));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectClip(clip.id); }
      });
      target.append(card);
    });
    target.scrollTop = target.scrollHeight;
  }

  function selectClip(id) {
    pausePreview();
    state.selectedClipId = id;
    const clip = selectedClip();
    if (clip) {
      state.selectedAssetId = clip.assetId;
      const data = clipAtTime(clipStart(id));
      state.playhead = data ? data.start : 0;
      loadMediaForPreview(clip.assetId, clip);
    }
    renderAssets();
    renderTimeline();
    renderInspector();
    updateStats();
    drawFrame();
    scheduleSave();
  }

  function clipStart(id) {
    let cursor = 0;
    for (const clip of state.project.timeline) {
      if (clip.id === id) return cursor;
      cursor += Number(clip.duration) || 0;
    }
    return 0;
  }

  function moveClip(index, direction) {
    const next = index + direction;
    if (next < 0 || next >= state.project.timeline.length) return;
    const clips = state.project.timeline;
    const item = clips.splice(index, 1)[0];
    clips.splice(next, 0, item);
    renderTimeline();
    updateStats();
    scheduleSave();
    drawFrame();
  }

  function removeClip(id) {
    state.project.timeline = state.project.timeline.filter((clip) => clip.id !== id);
    if (state.selectedClipId === id) state.selectedClipId = state.project.timeline[0] ? state.project.timeline[0].id : null;
    state.playhead = Math.min(state.playhead, Math.max(0, totalDuration() - 0.01));
    renderTimeline();
    renderInspector();
    updateStats();
    scheduleSave();
    drawFrame();
  }

  function renderInspector() {
    const clip = selectedClip();
    $("inspector-empty").hidden = Boolean(clip);
    $("inspector-form").hidden = !clip;
    $("selected-shot-label").textContent = clip ? String(state.project.timeline.indexOf(clip) + 1).padStart(2, "0") : "—";
    if (!clip) return;
    $("shot-name").value = clip.name || "";
    $("shot-start").value = Number(clip.sourceIn || 0);
    $("shot-duration").value = Number(clip.duration || 4);
    $("shot-fit").value = clip.fit || "cover";
    $("shot-motion").value = clip.motion || "none";
    $("shot-title").value = clip.title || "";
    $("shot-subtitle").value = clip.subtitle || "";
    $("shot-position").value = clip.titlePosition || "bottom";
    $("shot-colour").value = clip.titleColor || "#d6fa62";
    $("shot-font-size").value = clip.titleSize || 44;
    $("shot-font-value").textContent = (clip.titleSize || 44) + " px";
    $("shot-font").value = clip.titleFont || "sans";
    if (!Array.isArray(clip.layers)) clip.layers = [];
    if (!clip.layers.some((layer) => layer.id === state.selectedGraphicLayerId)) {
      state.selectedGraphicLayerId = clip.layers[0] ? clip.layers[0].id : null;
    }
    renderGraphicLayers();
  }

  function selectedGraphicLayer() {
    const clip = selectedClip();
    if (!clip) return null;
    if (!Array.isArray(clip.layers)) clip.layers = [];
    return clip.layers.find((layer) => layer.id === state.selectedGraphicLayerId) || null;
  }

  function newGraphicLayer(type) {
    const count = (selectedClip() && selectedClip().layers || []).length + 1;
    return {
      id: crypto.randomUUID(),
      type: type,
      name: (type === "text" ? "Text" : type === "rect" ? "Rectangle" : type === "circle" ? "Circle" : type === "line" ? "Line" : "Arrow") + " " + count,
      text: type === "text" ? "New graphic" : "",
      x: 50, y: type === "text" ? 76 : 50,
      width: type === "text" ? 70 : (type === "line" || type === "arrow" ? 32 : 22),
      height: type === "text" ? 12 : (type === "line" || type === "arrow" ? 1 : 16),
      fontSize: 44,
      color: "#d6fa62", opacity: 1, font: "sans", animation: "fade-in"
    };
  }

  function renderGraphicLayers() {
    const clip = selectedClip();
    const target = $("graphic-layer-list");
    target.replaceChildren();
    const layers = clip && Array.isArray(clip.layers) ? clip.layers : [];
    $("graphic-layer-count").textContent = String(layers.length);
    if (!layers.length) {
      const empty = document.createElement("div");
      empty.className = "layer-empty";
      empty.textContent = "Add text and shapes to build the composition.";
      target.append(empty);
    }
    layers.forEach((layer, index) => {
      const row = document.createElement("div");
      row.className = "graphic-layer-row" + (layer.id === state.selectedGraphicLayerId ? " selected" : "");
      const select = document.createElement("button");
      select.type = "button";
      select.className = "graphic-layer-select";
      select.textContent = (layer.type === "text" ? "T" : layer.type === "rect" ? "▰" : layer.type === "circle" ? "●" : layer.type === "line" ? "／" : "→") + "  " + (layer.name || "Graphic layer");
      select.addEventListener("click", () => {
        state.selectedGraphicLayerId = layer.id;
        renderGraphicLayers();
      });
      const up = document.createElement("button");
      up.type = "button"; up.className = "layer-order-button"; up.textContent = "↑"; up.title = "Move layer up"; up.disabled = index === 0;
      up.addEventListener("click", () => {
        if (index < 1) return;
        const item = layers.splice(index, 1)[0];
        layers.splice(index - 1, 0, item);
        renderGraphicLayers(); scheduleSave(); drawFrame();
      });
      const down = document.createElement("button");
      down.type = "button"; down.className = "layer-order-button"; down.textContent = "↓"; down.title = "Move layer down"; down.disabled = index === layers.length - 1;
      down.addEventListener("click", () => {
        if (index >= layers.length - 1) return;
        const item = layers.splice(index, 1)[0];
        layers.splice(index + 1, 0, item);
        renderGraphicLayers(); scheduleSave(); drawFrame();
      });
      row.append(select, up, down);
      target.append(row);
    });
    const layer = selectedGraphicLayer();
    $("graphic-layer-controls").hidden = !layer;
    if (!layer) return;
    $("graphic-layer-name").value = layer.name || "";
    $("graphic-layer-text").value = layer.text || "";
    $("graphic-layer-x").value = Number(layer.x ?? 50);
    $("graphic-layer-y").value = Number(layer.y ?? 50);
    $("graphic-layer-width").value = Number(layer.width ?? 22);
    $("graphic-layer-height").value = Number(layer.height ?? 16);
    $("graphic-layer-colour").value = /^#[0-9a-f]{6}$/i.test(layer.color || "") ? layer.color : "#d6fa62";
    $("graphic-layer-opacity").value = Number(layer.opacity ?? 1);
    $("graphic-layer-font").value = layer.font || "sans";
    $("graphic-layer-font-size").value = Number(layer.fontSize) || 44;
    $("graphic-layer-animation").value = layer.animation || "none";
    const isText = layer.type === "text";
    $("graphic-text-wrap").hidden = !isText;
    $("graphic-font-wrap").hidden = !isText;
    $("graphic-font-size-wrap").hidden = !isText;
  }

  function addGraphicLayer(type) {
    const clip = selectedClip();
    if (!clip) { toast("Select a shot before adding graphic layers."); return; }
    if (!Array.isArray(clip.layers)) clip.layers = [];
    const layer = newGraphicLayer(type);
    clip.layers.push(layer);
    state.selectedGraphicLayerId = layer.id;
    renderGraphicLayers();
    scheduleSave();
    drawFrame();
  }

  function bindGraphicLayers() {
    $("add-text-layer").addEventListener("click", () => addGraphicLayer("text"));
    $("add-rect-layer").addEventListener("click", () => addGraphicLayer("rect"));
    $("add-circle-layer").addEventListener("click", () => addGraphicLayer("circle"));
    $("add-line-layer").addEventListener("click", () => addGraphicLayer("line"));
    $("add-arrow-layer").addEventListener("click", () => addGraphicLayer("arrow"));
    const fields = {
      "graphic-layer-name": ["name", (v) => v.slice(0, 100)],
      "graphic-layer-text": ["text", (v) => v.slice(0, 300)],
      "graphic-layer-x": ["x", (v) => Math.min(100, Math.max(0, Number(v) || 0))],
      "graphic-layer-y": ["y", (v) => Math.min(100, Math.max(0, Number(v) || 0))],
      "graphic-layer-width": ["width", (v) => Math.min(100, Math.max(1, Number(v) || 1))],
      "graphic-layer-height": ["height", (v) => Math.min(100, Math.max(1, Number(v) || 1))],
      "graphic-layer-colour": ["color", (v) => /^#[0-9a-f]{6}$/i.test(v) ? v : "#d6fa62"],
      "graphic-layer-opacity": ["opacity", (v) => Math.min(1, Math.max(0, Number(v) || 0))],
      "graphic-layer-font": ["font", (v) => v],
      "graphic-layer-font-size": ["fontSize", (v) => Math.min(180, Math.max(10, Number(v) || 44))],
      "graphic-layer-animation": ["animation", (v) => v]
    };
    Object.entries(fields).forEach(([id, field]) => {
      $(id).addEventListener("input", () => {
        const layer = selectedGraphicLayer();
        if (!layer) return;
        layer[field[0]] = field[1]($(id).value);
        if (id === "graphic-layer-name") renderGraphicLayers();
        scheduleSave();
        drawFrame();
      });
    });
    $("delete-graphic-layer").addEventListener("click", () => {
      const clip = selectedClip();
      const layer = selectedGraphicLayer();
      if (!clip || !layer) return;
      clip.layers = clip.layers.filter((item) => item.id !== layer.id);
      state.selectedGraphicLayerId = clip.layers.length ? clip.layers[0].id : null;
      renderGraphicLayers(); scheduleSave(); drawFrame();
    });
  }

  function bindInspector() {
    const fieldMap = {
      "shot-name": ["name", (v) => v.slice(0, 120)],
      "shot-fit": ["fit", (v) => v],
      "shot-motion": ["motion", (v) => v],
      "shot-title": ["title", (v) => v.slice(0, 240)],
      "shot-subtitle": ["subtitle", (v) => v.slice(0, 300)],
      "shot-position": ["titlePosition", (v) => v],
      "shot-colour": ["titleColor", (v) => /^#[0-9a-f]{6}$/i.test(v) ? v : "#d6fa62"],
      "shot-font": ["titleFont", (v) => v]
    };
    Object.keys(fieldMap).forEach((id) => {
      $(id).addEventListener("input", () => {
        const clip = selectedClip();
        if (!clip) return;
        const setting = fieldMap[id];
        clip[setting[0]] = setting[1]($(id).value);
        if (id === "shot-name") clip.name = clip.name || "Shot";
        renderTimeline();
        scheduleSave();
        drawFrame();
      });
    });
    $("shot-font-size").addEventListener("input", () => {
      const clip = selectedClip();
      if (!clip) return;
      clip.titleSize = Number($("shot-font-size").value);
      $("shot-font-value").textContent = clip.titleSize + " px";
      scheduleSave(); drawFrame();
    });
    $("shot-start").addEventListener("change", () => {
      const clip = selectedClip();
      if (!clip) return;
      const asset = assetById(clip.assetId);
      const maxIn = asset && asset.duration ? Math.max(0, asset.duration - 0.1) : 0;
      clip.sourceIn = Math.min(maxIn, Math.max(0, Number($("shot-start").value) || 0));
      $("shot-start").value = clip.sourceIn;
      const remain = asset && asset.duration ? Math.max(0.1, asset.duration - clip.sourceIn) : 600;
      clip.duration = Math.min(Math.max(0.5, Number(clip.duration) || 4), remain);
      $("shot-duration").value = clip.duration;
      scheduleSave(); drawFrame();
    });
    $("shot-duration").addEventListener("change", () => {
      const clip = selectedClip();
      if (!clip) return;
      const asset = assetById(clip.assetId);
      const maxDuration = asset && asset.duration ? Math.max(0.5, asset.duration - Number(clip.sourceIn || 0)) : 600;
      clip.duration = Math.min(maxDuration, Math.max(0.5, Number($("shot-duration").value) || 4));
      $("shot-duration").value = clip.duration;
      renderTimeline(); updateStats(); scheduleSave(); drawFrame();
    });
    $("reset-shot").addEventListener("click", () => {
      const clip = selectedClip();
      const asset = clip && assetById(clip.assetId);
      if (!clip || !asset) return;
      const fresh = createClip(asset);
      fresh.id = clip.id;
      Object.assign(clip, fresh);
      renderInspector(); renderTimeline(); scheduleSave(); drawFrame();
      toast("Shot design reset.");
    });
  }

  function drawTextBlock(text, centerX, baseY, maxWidth, font, color, align, lineHeight) {
    if (!text) return;
    ctx.save();
    ctx.font = font;
    ctx.textAlign = align || "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = color || "#ffffff";
    ctx.shadowColor = "rgba(0,0,0,.8)";
    ctx.shadowBlur = Math.max(4, canvas.width * 0.008);
    ctx.shadowOffsetY = 2;
    const words = String(text).split(/\s+/);
    const lines = [];
    let line = "";
    words.forEach((word) => {
      const candidate = line ? line + " " + word : word;
      if (line && ctx.measureText(candidate).width > maxWidth) { lines.push(line); line = word; }
      else line = candidate;
    });
    if (line) lines.push(line);
    const lh = lineHeight || 1.15;
    lines.forEach((row, i) => ctx.fillText(row, centerX, baseY + (i - (lines.length - 1) / 2) * parseFloat(ctx.font) * lh, maxWidth));
    ctx.restore();
  }

  function drawFrame() {
    if (!ctx || !state.project) return;
    const width = canvas.width;
    const height = canvas.height;
    ctx.save();
    ctx.fillStyle = "#090b09";
    ctx.fillRect(0, 0, width, height);
    let entry = state.project.timeline.length ? clipAtTime(state.playhead) : null;
    let clip = entry && entry.clip;
    let localTime = entry ? entry.localTime : 0;
    if (!clip && !state.project.timeline.length && state.selectedAssetId) {
      const asset = assetById(state.selectedAssetId);
      if (asset) {
        clip = { id: "library-preview", assetId: asset.id, duration: asset.duration || 4, sourceIn: 0, fit: "cover", motion: "none", title: "", subtitle: "", titlePosition: "bottom", titleColor: "#d6fa62", titleSize: 44, titleFont: "sans" };
      }
    }
    if (!clip) {
      ctx.fillStyle = "#181d14";
      ctx.fillRect(0, 0, width, height);
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#d6fa62"; ctx.font = "600 " + Math.round(width * 0.023) + "px ui-monospace, monospace";
      ctx.fillText("OMNITRIX / CREATIVE STUDIO", width / 2, height / 2 - 10);
      ctx.fillStyle = "#a7ad9c"; ctx.font = Math.round(width * 0.012) + "px ui-monospace, monospace";
      ctx.fillText("IMPORT REFERENCES  ·  BUILD TIMELINE  ·  RENDER", width / 2, height / 2 + 24);
      ctx.restore();
      updateTransport();
      return;
    }
    if (state.loadedMedia && state.loadedMedia.assetId === clip.assetId) {
      const media = state.loadedMedia;
      if (media.type.startsWith("video/")) {
        const asset = assetById(clip.assetId);
        const expected = Math.max(0, Number(clip.sourceIn || 0) + localTime);
        if (Number.isFinite(sourceVideo.duration) && expected < sourceVideo.duration - 0.08 && (!state.isPlaying || Math.abs(sourceVideo.currentTime - expected) > 0.45)) {
          try { sourceVideo.currentTime = expected; } catch {}
        }
        if (state.isPlaying && sourceVideo.paused) sourceVideo.play().catch(() => {});
        if (!state.isPlaying && !sourceVideo.paused) sourceVideo.pause();
        if (sourceVideo.readyState >= 2 && sourceVideo.videoWidth) {
          drawMedia(sourceVideo, clip, localTime);
        }
        if (asset && localTime >= clip.duration) state.playhead = Math.min(totalDuration(), state.playhead);
      } else if (media.image && media.image.complete && media.image.naturalWidth) {
        drawMedia(media.image, clip, localTime);
      }
    } else {
      ctx.fillStyle = "#151a12";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#d6fa62";
      ctx.font = "500 " + Math.round(width * 0.016) + "px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText("LOADING SOURCE…", width / 2, height / 2);
      if (state.currentClipId !== (clip.id || clip.assetId)) {
        state.currentClipId = clip.id || clip.assetId;
        loadMediaForPreview(clip.assetId, clip);
      }
    }
    const progress = Math.min(1, localTime / Math.max(0.1, Number(clip.duration) || 4));
    if (clip.title || clip.subtitle) drawGraphicOverlay(clip);
    drawGraphicLayers(clip, localTime);
    ctx.restore();
    updateTransport();
  }

  function drawMedia(media, clip, localTime) {
    const W = canvas.width;
    const H = canvas.height;
    const sw = media.videoWidth || media.naturalWidth || media.width;
    const sh = media.videoHeight || media.naturalHeight || media.height;
    if (!sw || !sh) return;
    if (clip.fit === "contain") {
      ctx.fillStyle = "#080a08"; ctx.fillRect(0, 0, W, H);
    }
    const scale = clip.fit === "contain" ? Math.min(W / sw, H / sh) : Math.max(W / sw, H / sh);
    let motion = 1;
    let px = 0;
    let py = 0;
    const progress = Math.min(1, Math.max(0, localTime / Math.max(0.1, Number(clip.duration) || 4)));
    if (clip.motion === "slow-zoom") motion = 1 + 0.12 * progress;
    else if (clip.motion === "zoom-out") motion = 1.12 - 0.12 * progress;
    else if (clip.motion === "pan-left") px = (0.10 - 0.20 * progress) * W;
    else if (clip.motion === "pan-right") px = (-0.10 + 0.20 * progress) * W;
    const dw = sw * scale * motion;
    const dh = sh * scale * motion;
    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
    ctx.drawImage(media, (W - dw) / 2 + px, (H - dh) / 2 + py, dw, dh);
    ctx.restore();
  }

  function drawGraphicOverlay(clip) {
    const W = canvas.width;
    const H = canvas.height;
    const titleSize = Math.round((Number(clip.titleSize) || 44) * W / 960);
    const fontFace = clip.titleFont === "serif" ? 'Georgia, "Times New Roman", serif'
      : clip.titleFont === "mono" ? 'ui-monospace, SFMono-Regular, Menlo, monospace'
      : 'Inter, "DM Sans", system-ui, sans-serif';
    const titleFont = (clip.titleFont === "serif" ? "600 " : "750 ") + titleSize + "px " + fontFace;
    let y = clip.titlePosition === "top" ? H * 0.19 : clip.titlePosition === "center" ? H * 0.49 : H * 0.77;
    if (clip.title) drawTextBlock(clip.title, W / 2, y, W * 0.84, titleFont, clip.titleColor || "#d6fa62", "center", 1.1);
    if (clip.subtitle) {
      const subtitleY = y + (clip.title ? titleSize * 1.65 : 0);
      drawTextBlock(clip.subtitle, W / 2, subtitleY, W * 0.78, "500 " + Math.round(titleSize * 0.43) + "px " + fontFace, "#f1f3e8", "center", 1.2);
    }
    ctx.save();
    const lineY = y + (clip.title ? titleSize * 0.86 : 0);
    if (clip.title) {
      ctx.globalAlpha = 0.86;
      ctx.fillStyle = clip.titleColor || "#d6fa62";
      ctx.fillRect(W * 0.46, lineY + titleSize * 0.57, W * 0.08, Math.max(1, W * 0.0015));
    }
    ctx.restore();
  }

  function drawGraphicLayers(clip, localTime) {
    const layers = Array.isArray(clip.layers) ? clip.layers : [];
    const W = canvas.width;
    const H = canvas.height;
    layers.forEach((layer) => {
      const animationProgress = Math.min(1, Math.max(0, (Number(localTime) || 0) / 0.65));
      const eased = 1 - Math.pow(1 - animationProgress, 3);
      let alpha = Number.isFinite(Number(layer.opacity)) ? Math.min(1, Math.max(0, Number(layer.opacity))) : 1;
      let dx = 0;
      let dy = 0;
      let scale = 1;
      if (layer.animation === "fade-in") alpha *= eased;
      else if (layer.animation === "slide-up") { alpha *= eased; dy = (1 - eased) * H * 0.08; }
      else if (layer.animation === "slide-left") { alpha *= eased; dx = (1 - eased) * W * 0.12; }
      else if (layer.animation === "scale-in") { alpha *= eased; scale = 0.78 + 0.22 * eased; }
      const x = (Math.min(100, Math.max(0, Number(layer.x ?? 50))) / 100) * W + dx;
      const y = (Math.min(100, Math.max(0, Number(layer.y ?? 50))) / 100) * H + dy;
      const width = (Math.min(100, Math.max(1, Number(layer.width ?? 22))) / 100) * W * scale;
      const height = (Math.min(100, Math.max(1, Number(layer.height ?? 16))) / 100) * H * scale;
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.fillStyle = /^#[0-9a-f]{6}$/i.test(layer.color || "") ? layer.color : "#d6fa62";
      if (layer.type === "rect") {
        ctx.fillRect(x - width / 2, y - height / 2, width, height);
      } else if (layer.type === "circle") {
        ctx.beginPath();
        ctx.ellipse(x, y, width / 2, height / 2, 0, 0, Math.PI * 2);
        ctx.fill();
      } else if (layer.type === "line" || layer.type === "arrow") {
        const x1 = x - width / 2;
        const y1 = y - height / 2;
        const x2 = x + width / 2;
        const y2 = y + height / 2;
        const angle = Math.atan2(y2 - y1, x2 - x1);
        ctx.strokeStyle = ctx.fillStyle;
        ctx.lineWidth = Math.max(2, W * 0.0025);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        if (layer.type === "arrow") {
          const head = Math.max(8, Math.min(W, H) * 0.022);
          ctx.beginPath();
          ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - head * Math.cos(angle - Math.PI / 6), y2 - head * Math.sin(angle - Math.PI / 6));
          ctx.lineTo(x2 - head * Math.cos(angle + Math.PI / 6), y2 - head * Math.sin(angle + Math.PI / 6));
          ctx.closePath();
          ctx.fill();
        }
      } else if (layer.type === "text" && layer.text) {
        const fontSize = Math.max(10, Math.round((Number(layer.fontSize) || 44) * W / 960));
        const family = layer.font === "serif" ? 'Georgia, "Times New Roman", serif'
          : layer.font === "mono" ? 'ui-monospace, SFMono-Regular, Menlo, monospace'
          : 'Inter, "DM Sans", system-ui, sans-serif';
        const weight = layer.fontWeight === "regular" ? "500" : "750";
        drawTextBlock(layer.text, x, y, width, weight + " " + fontSize + "px " + family, ctx.fillStyle, "center", 1.12);
      }
      ctx.restore();
    });
  }

  async function loadMediaForPreview(assetId, clip) {
    if (!assetId) return;
    if (state.loadedMedia && state.loadedMedia.assetId === assetId) {
      if (clip && sourceVideo.readyState >= 1 && state.loadedMedia.type.startsWith("video/")) {
        try { sourceVideo.currentTime = Math.max(0, Number(clip.sourceIn) || 0); } catch {}
        if (state.isPlaying) sourceVideo.play().catch(() => {});
      }
      return;
    }
    const token = ++state.mediaLoadToken;
    const previousMedia = state.loadedMedia;
    try {
      const row = await dbGet("assets", assetId);
      if (!row || token !== state.mediaLoadToken) return;
      const url = URL.createObjectURL(row.blob);
      state.objectUrls.set(assetId, url);
      if (row.type.startsWith("video/")) {
        sourceVideo.pause();
        sourceVideo.src = url;
        sourceVideo.muted = false;
        sourceVideo.load();
        state.loadedMedia = { assetId: assetId, type: row.type, url: url, image: null };
        await new Promise((resolve) => {
          if (sourceVideo.readyState >= 1) return resolve();
          const timeout = setTimeout(resolve, 8000);
          sourceVideo.addEventListener("loadedmetadata", () => { clearTimeout(timeout); resolve(); }, { once: true });
          sourceVideo.addEventListener("error", () => { clearTimeout(timeout); resolve(); }, { once: true });
        });
        if (clip && Number.isFinite(sourceVideo.duration)) sourceVideo.currentTime = Math.min(Math.max(0, Number(clip.sourceIn) || 0), Math.max(0, sourceVideo.duration - 0.05));
        if (state.isPlaying) sourceVideo.play().catch(() => {});
      } else {
        sourceVideo.pause();
        const image = new Image();
        image.decoding = "async";
        state.loadedMedia = { assetId: assetId, type: row.type, url: url, image: image };
        await new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = () => reject(new Error("Could not decode image."));
          image.src = url;
        });
      }
      if (previousMedia && previousMedia.assetId !== assetId && state.objectUrls.has(previousMedia.assetId)) {
        URL.revokeObjectURL(state.objectUrls.get(previousMedia.assetId));
        state.objectUrls.delete(previousMedia.assetId);
      }
    } catch (error) {
      console.warn("Could not load preview source", error);
    } finally {
      drawFrame();
    }
  }

  function currentDuration() {
    return totalDuration();
  }

  function updateTransport() {
    const total = currentDuration();
    $("playhead").max = String(Math.max(0.1, total));
    $("playhead").value = String(Math.min(state.playhead, total || 0));
    $("playhead-current").textContent = formatTime(state.playhead);
    $("playhead-total").textContent = formatTime(total);
    $("timeline-duration").textContent = formatTime(total);
    $("export-length").textContent = formatTime(total);
    $("export-target").textContent = "WEBM · " + canvas.width + " × " + canvas.height;
    $("toggle-play").textContent = state.isPlaying ? "Ⅱ" : "▶";
    $("toggle-play").setAttribute("aria-label", state.isPlaying ? "Pause preview" : "Play preview");
    $("preview-state").textContent = state.exporting ? "RENDERING" : state.isPlaying ? "PLAYING" : "READY";
  }

  function updateStats() {
    $("asset-count").textContent = state.assets.length + " media asset" + (state.assets.length === 1 ? "" : "s");
    $("library-count").textContent = String(state.assets.length);
    $("timeline-count").textContent = state.project.timeline.length + " SHOT" + (state.project.timeline.length === 1 ? "" : "S");
    updateTransport();
  }

  async function ensureAudioGraph() {
    if (state.audioContext) {
      if (state.audioContext.state === "suspended") await state.audioContext.resume();
      return;
    }
    if (!window.AudioContext || !sourceVideo.captureStream && !window.MediaStream) return;
    state.audioContext = new AudioContext();
    state.audioSource = state.audioContext.createMediaElementSource(sourceVideo);
    state.audioOutput = state.audioContext.createMediaStreamDestination();
    state.audioMonitor = state.audioContext.createGain();
    state.audioMonitor.gain.value = 0;
    state.audioSource.connect(state.audioOutput);
    state.audioSource.connect(state.audioMonitor);
    state.audioMonitor.connect(state.audioContext.destination);
    await state.audioContext.resume();
  }

  function startPreview() {
    if (state.exporting || !state.project.timeline.length) {
      if (!state.project.timeline.length) toast("Add at least one shot to preview the sequence.");
      return;
    }
    if (state.playhead >= totalDuration()) state.playhead = 0;
    state.isPlaying = true;
    state.playStartedAt = performance.now() - state.playhead * 1000;
    ensureAudioGraph().catch(() => {});
    const entry = clipAtTime(state.playhead);
    if (entry) loadMediaForPreview(entry.clip.assetId, entry.clip);
    sourceVideo.play().catch(() => {});
    $("preview-state").textContent = "PLAYING";
    state.raf = requestAnimationFrame(playbackTick);
  }

  function pausePreview() {
    state.isPlaying = false;
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = 0;
    sourceVideo.pause();
    updateTransport();
  }

  function playbackTick(now) {
    if (!state.isPlaying) return;
    state.playhead = Math.max(0, (now - state.playStartedAt) / 1000);
    if (state.playhead >= totalDuration()) {
      state.playhead = totalDuration();
      state.isPlaying = false;
      sourceVideo.pause();
      state.raf = 0;
      drawFrame();
      if (state.exporting && state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
      else updateTransport();
      return;
    }
    drawFrame();
    if (now - state.lastFrameUi > 100) {
      updateTransport();
      state.lastFrameUi = now;
    }
    state.raf = requestAnimationFrame(playbackTick);
  }

  function togglePreview() {
    if (state.isPlaying) pausePreview();
    else startPreview();
  }

  function showMessage(message, isError) {
    const target = $("render-message");
    target.textContent = message;
    target.className = "render-message" + (isError ? " error" : " success");
  }

  async function renderVideo() {
    if (state.exporting) return;
    if (!state.project.timeline.length) { showMessage("Add at least one shot before rendering.", true); return; }
    if (!("MediaRecorder" in window) || !canvas.captureStream) {
      showMessage("This browser does not support canvas video recording. Try a current version of Chrome or Edge.", true);
      return;
    }
    pausePreview();
    const dimensions = $("preview-scale").value.split("x").map(Number);
    const original = { width: canvas.width, height: canvas.height };
    canvas.width = dimensions[0] || 1280;
    canvas.height = dimensions[1] || 720;
    state.playhead = 0;
    state.exporting = true;
    state.chunks = [];
    $("render-video").disabled = true;
    $("render-video-bottom").disabled = true;
    showMessage("Rendering locally in this browser. Keep this tab open until the download starts.", false);
    try {
      await ensureAudioGraph();
      const videoStream = canvas.captureStream(30);
      const outputStream = new MediaStream(videoStream.getVideoTracks());
      if (state.audioOutput) state.audioOutput.stream.getAudioTracks().forEach((track) => outputStream.addTrack(track));
      const candidates = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
      const mimeType = candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
      const recorder = new MediaRecorder(outputStream, {
        ...(mimeType ? { mimeType: mimeType } : {}),
        videoBitsPerSecond: dimensions[0] >= 1280 ? 5500000 : 2800000
      });
      state.recorder = recorder;
      recorder.ondataavailable = (event) => { if (event.data && event.data.size) state.chunks.push(event.data); };
      recorder.onerror = (event) => showMessage("Recorder error: " + ((event.error && event.error.message) || "unknown browser recording error"), true);
      recorder.onstop = () => {
        const blob = new Blob(state.chunks, { type: recorder.mimeType || "video/webm" });
        outputStream.getTracks().forEach((track) => track.stop());
        canvas.width = original.width;
        canvas.height = original.height;
        state.exporting = false;
        state.recorder = null;
        state.isPlaying = false;
        sourceVideo.pause();
        $("render-video").disabled = false;
        $("render-video-bottom").disabled = false;
        drawFrame();
        if (blob.size) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = slug(state.project.name) + "-draft.webm";
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 60000);
          showMessage("Render complete · " + formatBytes(blob.size) + " · downloaded as WebM. Keep original source media for future edits.", false);
        } else {
          showMessage("The browser returned an empty video file. Try a shorter sequence or lower resolution.", true);
        }
        updateTransport();
      };
      recorder.start(500);
      state.isPlaying = true;
      await ensureCurrentPreviewSource();
      state.playStartedAt = performance.now();
      state.raf = requestAnimationFrame(playbackTick);
      updateTransport();
    } catch (error) {
      state.exporting = false;
      state.isPlaying = false;
      canvas.width = original.width;
      canvas.height = original.height;
      $("render-video").disabled = false;
      $("render-video-bottom").disabled = false;
      drawFrame();
      showMessage("Could not start render: " + error.message, true);
    }
  }

  async function ensureCurrentPreviewSource() {
    const entry = clipAtTime(0);
    if (entry) {
      state.currentClipId = entry.clip.id;
      await loadMediaForPreview(entry.clip.assetId, entry.clip);
      try {
        if (entry.clip.sourceIn > 0 && sourceVideo.readyState >= 1) sourceVideo.currentTime = entry.clip.sourceIn;
        if (sourceVideo.readyState >= 2) await sourceVideo.play();
      } catch {}
    }
    drawFrame();
  }

  function downloadManifest() {
    const manifest = {
      schemaVersion: 1,
      app: "Omnitrix Creative Studio",
      exportedAt: new Date().toISOString(),
      project: {
        name: state.project.name,
        brief: state.project.brief,
        timeline: state.project.timeline.map((clip) => ({
          id: clip.id, assetId: clip.assetId, name: clip.name,
          sourceIn: clip.sourceIn, duration: clip.duration, fit: clip.fit, motion: clip.motion,
          title: clip.title, subtitle: clip.subtitle, titlePosition: clip.titlePosition,
          titleColor: clip.titleColor, titleSize: clip.titleSize, titleFont: clip.titleFont,
          layers: Array.isArray(clip.layers) ? clip.layers.map((layer) => Object.assign({}, layer)) : []
        }))
      },
      media: state.assets.map((asset) => ({
        id: asset.id, name: asset.name, type: asset.type, size: asset.size,
        duration: asset.duration, width: asset.width, height: asset.height,
        sourceProvider: asset.sourceProvider || "", sourcePage: asset.sourcePage || "",
        attribution: asset.attribution || "", license: asset.license || "",
        licenseUrl: asset.licenseUrl || "", rightsVerified: asset.rightsVerified === true
      })),
      notes: [
        "This is an editable decision manifest, not a media archive.",
        "Original media remains in the browser's local IndexedDB store. Back up originals separately.",
        "Online asset source, licence and attribution metadata are included where available; verify rights before publication.",
        "This render path uses browser MediaRecorder. Independent music/narration tracks, true transitions, masks, post-render model critique and generated raster imagery remain unsupported."
      ]
    };
    const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = slug(state.project.name) + "-edit-manifest.json";
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    showMessage("Edit manifest exported. It contains shot decisions and asset references, not the original media files.", false);
  }

  function renderProjectJson() {
    downloadManifest();
  }

  async function deleteAsset(id) {
    const asset = assetById(id);
    if (!asset || !window.confirm("Delete " + asset.name + " from this browser's media library and remove its shots from the timeline?")) return;
    state.project.timeline = state.project.timeline.filter((clip) => clip.assetId !== id);
    await dbDelete("assets", id);
    if (state.selectedAssetId === id) state.selectedAssetId = null;
    if (!state.project.timeline.some((clip) => clip.id === state.selectedClipId)) {
      state.selectedClipId = state.project.timeline[0] ? state.project.timeline[0].id : null;
    }
    if (state.objectUrls.has(id)) URL.revokeObjectURL(state.objectUrls.get(id));
    if (state.thumbUrls.has(id)) URL.revokeObjectURL(state.thumbUrls.get(id));
    state.objectUrls.delete(id); state.thumbUrls.delete(id);
    if (state.loadedMedia && state.loadedMedia.assetId === id) state.loadedMedia = null;
    await readAssetRows();
    renderTimeline(); renderInspector(); updateStats(); scheduleSave(); drawFrame();
  }

  function downloadProjectJson() {
    const used = new Set(state.project.timeline.map((clip) => clip.assetId));
    const missing = Array.from(used).filter((id) => !assetById(id));
    if (missing.length) showMessage("Some timeline references are missing from the local library. Re-import original media before continuing.", true);
    renderProjectJson();
  }


  function aiSetStatus(message, kind) {
    const target = $("ai-status");
    if (!target) return;
    target.textContent = message || "";
    target.className = "ai-status" + (kind ? " " + kind : "");
  }

  function aiRuntimeToken() {
    try { return sessionStorage.getItem("omnitrix-studio-runtime-token") || ""; }
    catch { return ""; }
  }

  function aiSetBadge(indicatorId, statusId, detailId, status, detail, successful) {
    const indicator = $(indicatorId);
    const label = $(statusId);
    const explanation = $(detailId);
    if (indicator) {
      indicator.classList.toggle("live", Boolean(successful));
      indicator.classList.toggle("pending", !successful);
    }
    if (label) {
      label.textContent = status;
      label.classList.toggle("pending-text", !successful);
    }
    if (explanation) explanation.textContent = detail;
  }

  async function loadAiModelStatus() {
    const label = $("ai-provider-label");
    const token = aiRuntimeToken();
    if (!token) {
      state.creativeStatus = null;
      if (label) label.textContent = "Connect to the Python-backed Studio runtime first. Open the core Studio in this browser tab and connect its runtime token.";
      aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
        "NOT CONNECTED", "Requires a connected Python runtime and configured multimodal provider", false);
      aiSetBadge("director-indicator", "director-status", "director-detail",
        "NOT CONNECTED", "Local editing remains available without model access", false);
      updateAiControls();
      return;
    }
    if (label) label.textContent = "Checking the configured visual-analysis route…";
    try {
      const response = await fetch("./api/creative/status", {
        method: "GET", cache: "no-store",
        headers: { Accept: "application/json", Authorization: "Bearer " + token }
      });
      const data = await response.json();
      if (!response.ok || !data || data.ok !== true) {
        throw new Error((data && data.error) || "The creative status route is unavailable.");
      }
      state.creativeStatus = data;
      if (data.configured) {
        if (label) label.textContent = "Configured route: " + data.provider + " · " + data.model +
          ". Configuration is not a live health check. A real model call happens only after explicit consent; provider quota or charges may apply.";
        aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
          "CONFIGURED", "Selected resized previews only; no live provider check was performed", false);
        aiSetBadge("director-indicator", "director-status", "director-detail",
          "READY TO PROPOSE", "A schema-checked proposal is available after an explicit model call; not a post-render critic", false);
      } else {
        if (label) label.textContent = "No Gemini API key is configured on this server. Local editing still works; AI direction is unavailable until the provider is configured.";
        aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
          "UNAVAILABLE", "GEMINI_API_KEY is not configured server-side", false);
        aiSetBadge("director-indicator", "director-status", "director-detail",
          "UNAVAILABLE", "No model proposal can be made without the configured provider", false);
      }
    } catch (error) {
      state.creativeStatus = null;
      if (label) label.textContent = "Cannot verify the provider route: " + String(error.message || error) +
        ". Open Creative Studio through the Python-backed runtime, not a static GitHub Pages preview.";
      aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
        "NOT CONNECTED", "The creative API could not be reached", false);
      aiSetBadge("director-indicator", "director-status", "director-detail",
        "NOT CONNECTED", "Local editing remains available", false);
    }
    updateAiControls();
  }

  function aiSelectedClipIds() {
    return Array.from($("ai-selection-list").querySelectorAll("input.ai-asset-check:checked"))
      .map((item) => item.value);
  }

  function updateAiControls() {
    const count = $("ai-selection-list")
      ? $("ai-selection-list").querySelectorAll("input.ai-asset-check:checked").length : 0;
    const consent = $("ai-consent") && $("ai-consent").checked;
    const configured = Boolean(state.creativeStatus && state.creativeStatus.configured);
    const button = $("ai-analyze");
    if (button) {
      button.disabled = state.creativeBusy || !configured || !consent || count < 1 || count > 6;
      button.textContent = state.creativeBusy ? "ANALYZING SELECTED PREVIEWS…" :
        "ANALYZE " + Math.max(0, count) + " SELECTED PREVIEW" + (count === 1 ? "" : "S");
    }
    const counter = $("ai-selection-count");
    if (counter) counter.textContent = count + " of up to 6 shots selected";
  }

  function renderAiSelectionList() {
    const target = $("ai-selection-list");
    if (!target) return;
    target.replaceChildren();
    if (!state.project || !state.project.timeline.length) {
      const note = document.createElement("p");
      note.className = "ai-muted";
      note.textContent = "Add shots to your timeline first. Only timeline shots can be selected for this model call.";
      target.append(note);
      updateAiControls();
      return;
    }
    for (const clip of state.project.timeline) {
      const asset = assetById(clip.assetId);
      const label = document.createElement("label");
      label.className = "ai-selection-row";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "ai-asset-check";
      checkbox.value = clip.id;
      checkbox.setAttribute("aria-label", "Include " + (asset ? asset.name : clip.name) + " in preview analysis");
      checkbox.addEventListener("change", () => {
        const selected = aiSelectedClipIds();
        if (selected.length > 6) {
          checkbox.checked = false;
          aiSetStatus("Choose no more than 6 shots per analysis. You can make another pass for additional shots.", "error");
        } else {
          aiSetStatus("", "");
        }
        state.creativePlan = null;
        state.creativeSnapshot = null;
        $("ai-plan-preview").hidden = true;
        $("ai-apply-plan").disabled = true;
        updateAiControls();
      });
      const image = document.createElement("img");
      image.className = "ai-selection-thumb";
      image.alt = "";
      image.loading = "lazy";
      if (asset && asset.thumb) image.src = thumbUrl(asset);
      else image.hidden = true;
      const details = document.createElement("span");
      details.className = "ai-selection-text";
      const name = document.createElement("span");
      name.className = "ai-selection-name";
      name.textContent = asset ? asset.name : (clip.name || "Missing media asset");
      const meta = document.createElement("span");
      meta.className = "ai-selection-meta";
      meta.textContent = (asset && asset.type.startsWith("video/") ? "Video · one thumbnail frame" : "Image · resized thumbnail") +
        " · current shot " + formatTime(Number(clip.duration) || 0) +
        (clip.motion && clip.motion !== "none" ? " · motion: " + clip.motion : "");
      details.append(name, meta);
      label.append(checkbox, image, details);
      target.append(label);
    }
    updateAiControls();
  }

  function aiTimelineSignature() {
    return JSON.stringify(state.project.timeline);
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      if (!(blob instanceof Blob)) {
        reject(new Error("A resized preview thumbnail is missing. Re-import the affected asset and try again."));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Could not read a local preview thumbnail."));
      reader.readAsDataURL(blob);
    });
  }

  function describeAiOperation(op) {
    const clip = state.project.timeline.find((item) => item.id === op.clip_id);
    const name = clip ? (assetById(clip.assetId)?.name || clip.name || "Shot") : "Shot";
    switch (op.type) {
      case "set_duration": return name + " — set duration to " + op.duration_seconds + " seconds.";
      case "set_motion": return name + " — use " + op.preset + " motion.";
      case "set_fit": return name + " — frame fit: " + op.fit + ".";
      case "set_title": return name + " — title: " + (op.text || "(clear title)");
      case "set_subtitle": return name + " — subtitle: " + (op.text || "(clear subtitle)");
      case "set_title_style": return name + " — title style: " + op.position + ", " + op.font + ", " + op.size + " px, " + op.color + ".";
      case "add_graphic_layer": return name + " — add purposeful " + op.layer_type + " layer “" + (op.name || "Graphic") + (op.text ? " / " + op.text : "") + "” with " + op.animation + " motion.";
      case "reorder_timeline": return "Reorder the complete timeline: " + op.clip_ids.map((id) => {
        const row = state.project.timeline.find((item) => item.id === id);
        return row ? (assetById(row.assetId)?.name || row.name || id) : id;
      }).join(" → ") + ".";
      default: return "Unsupported operation will not be applied.";
    }
  }

  function renderAiPlan(data) {
    const plan = data.plan;
    $("ai-plan-summary").textContent = plan.summary;
    $("ai-plan-identity").textContent =
      (data.worker || "worker unknown") + " · " + (data.model || "model unknown") +
      " · " + (Number(data.elapsed_ms || 0) / 1000).toFixed(1) + " s";
    const observationList = $("ai-plan-observations");
    observationList.replaceChildren();
    for (const item of plan.observations || []) {
      const li = document.createElement("li");
      const asset = state.assets.find((row) => row.id === item.asset_id);
      const clip = state.project.timeline.find((row) => row.id === item.clip_id);
      li.textContent = (asset ? asset.name : (clip ? clip.name : "Selected shot")) + ": " + item.observation;
      observationList.append(li);
    }
    if (!observationList.children.length) {
      const li = document.createElement("li");
      li.textContent = "No specific visual observations were returned.";
      observationList.append(li);
    }
    const operationList = $("ai-plan-operations");
    operationList.replaceChildren();
    for (const op of plan.operations || []) {
      const li = document.createElement("li");
      li.textContent = describeAiOperation(op);
      operationList.append(li);
    }
    if (!operationList.children.length) {
      const li = document.createElement("li");
      li.textContent = "No supported edits were proposed. There is nothing to apply.";
      operationList.append(li);
    }
    $("ai-plan-preview").hidden = false;
    $("ai-apply-plan").disabled = !(plan.operations && plan.operations.length) || state.creativePlanApplied;
  }

  function openAiDirector() {
    $("ai-director-panel").hidden = false;
    state.creativePlan = null;
    state.creativeSnapshot = null;
    state.creativePlanApplied = false;
    $("ai-consent").checked = false;
    $("ai-plan-preview").hidden = true;
    $("ai-apply-plan").disabled = true;
    aiSetStatus("", "");
    renderAiSelectionList();
    loadAiModelStatus();
    $("ai-director-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function pollAiCreativeJob(jobId, token) {
    const maxAttempts = 240;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      const response = await fetch("./api/creative/jobs/" + encodeURIComponent(jobId), {
        method: "GET",
        cache: "no-store",
        headers: { Accept: "application/json", Authorization: "Bearer " + token }
      });
      let data;
      try { data = await response.json(); }
      catch { throw new Error("The creative-job status route returned unreadable JSON."); }
      if (!response.ok || !data || data.ok !== true) {
        throw new Error((data && data.error) || "Could not read the creative analysis job status.");
      }
      if (data.status === "processing") {
        if (attempt % 5 === 0) {
          aiSetStatus("Visual analysis is still running. The job is kept server-side so a long provider call does not block the initial request; no edits are being applied.", "");
        }
        continue;
      }
      if (data.result && typeof data.result === "object") return data.result;
      throw new Error("The creative analysis job ended without a structured result. No edits were applied.");
    }
    throw new Error("Visual analysis exceeded the 6-minute polling window. Re-check provider status; no edits were applied automatically.");
  }

  async function runAiDirection() {
    if (state.creativeBusy) return;
    const token = aiRuntimeToken();
    if (!token) {
      aiSetStatus("Connect the Python-backed Studio runtime before requesting model analysis.", "error");
      return;
    }
    if (!$("ai-consent").checked) {
      aiSetStatus("Check the consent box before any preview is sent.", "error");
      return;
    }
    const ids = aiSelectedClipIds();
    if (!ids.length || ids.length > 6) {
      aiSetStatus("Select between 1 and 6 timeline shots.", "error");
      return;
    }
    if (!state.creativeStatus || !state.creativeStatus.configured) {
      aiSetStatus("The provider is not configured. Local editing still works; no preview was sent.", "error");
      return;
    }
    state.creativeBusy = true;
    state.creativePlan = null;
    state.creativeSnapshot = null;
    state.creativePlanApplied = false;
    $("ai-plan-preview").hidden = true;
    $("ai-apply-plan").disabled = true;
    updateAiControls();
    aiSetStatus("Preparing selected resized thumbnails locally. No original media will be sent…", "");
    const signature = aiTimelineSignature();
    try {
      const selectedClips = ids.map((id) => state.project.timeline.find((clip) => clip.id === id));
      if (selectedClips.some((clip) => !clip || !assetById(clip.assetId))) {
        throw new Error("The timeline changed or a selected asset is missing. Reopen the selection and try again.");
      }
      const records = [];
      for (const clip of selectedClips) {
        const stored = await dbGet("assets", clip.assetId);
        if (!stored || !stored.thumb) {
          throw new Error("A selected asset has no resized thumbnail. Re-import that asset and try again.");
        }
        const preview = await blobToDataUrl(stored.thumb);
        if (preview.length > 350000) {
          throw new Error("A resized preview is unusually large. Re-import that asset to create a smaller thumbnail.");
        }
        records.push({
          asset_id: clip.assetId,
          clip_id: clip.id,
          name: String(stored.name || clip.name || "Selected shot").slice(0, 160),
          preview_data_url: preview,
          duration: Number(clip.duration) || 0,
          source_duration: Number(stored.duration) || 0,
          source_in: Number(clip.sourceIn) || 0,
          media_type: String(stored.type || ""),
          motion: String(clip.motion || "none"),
          fit: String(clip.fit || "cover")
        });
      }
      const allTimelineIds = state.project.timeline.map((clip) => clip.id);
      const allowReorder = ids.length === allTimelineIds.length &&
        ids.every((id) => allTimelineIds.includes(id));
      aiSetStatus("Sending only " + records.length + " resized preview(s) to the configured provider…", "");
      const response = await fetch("./api/creative/analyze", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({
          consent: true,
          consent_clip_ids: ids,
          allow_reorder: allowReorder,
          brief: String($("creative-brief").value || "").slice(0, 4000),
          assets: records
        })
      });
      let data;
      try { data = await response.json(); }
      catch { throw new Error("The visual-analysis endpoint did not return readable JSON."); }
      if (!response.ok || !data || data.ok !== true) {
        throw new Error((data && data.error) || "Visual analysis did not start. No edits were applied.");
      }
      if (data.status === "processing" && typeof data.job_id === "string") {
        aiSetStatus("The server accepted the job. Waiting for the completed worker/model result…", "");
        data = await pollAiCreativeJob(data.job_id, token);
      }
      if (!data || data.ok !== true || data.status !== "complete" || !data.plan) {
        const message = data && data.error ? data.error : "Visual analysis did not complete. No edits were applied.";
        const identity = data && (data.model || data.worker) ? " [" + [data.worker, data.model].filter(Boolean).join(" · ") + "]" : "";
        throw new Error(message + identity);
      }
      if (aiTimelineSignature() !== signature) {
        throw new Error("The timeline changed during analysis. The proposal was discarded; run the analysis again.");
      }
      state.creativePlan = data.plan;
      state.creativeSnapshot = signature;
      state.creativeSelectedIds = ids.slice();
      state.creativeAllowReorder = allowReorder;
      state.creativePlanApplied = false;
      renderAiPlan(data);
      aiSetStatus("Analysis completed using " + (data.worker || "unknown worker") + " · " +
        (data.model || "unknown model") + ". This is a proposal from selected thumbnails, not a review of a rendered video. Nothing has been edited yet.", "success");
      aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
        "ANALYSIS COMPLETED", "Selected resized thumbnails were processed; full clips and rendered output were not inspected", true);
      aiSetBadge("director-indicator", "director-status", "director-detail",
        "PLAN READY", "Structured operations passed server-side allowlist validation; waiting for your approval", true);
      $("agent-state").textContent = "Visual analysis completed with " + (data.worker || "unknown worker") + " · " +
        (data.model || "unknown model") + ". A structured plan is ready for review. It has not changed your timeline.";
    } catch (error) {
      state.creativePlan = null;
      state.creativeSnapshot = null;
      $("ai-plan-preview").hidden = true;
      $("ai-apply-plan").disabled = true;
      aiSetStatus(String(error.message || error), "error");
      aiSetBadge("visual-analyst-indicator", "visual-analyst-status", "visual-analyst-detail",
        "CALL FAILED", "No verified complete analysis was returned", false);
    } finally {
      state.creativeBusy = false;
      updateAiControls();
    }
  }

  function applyAiPlan() {
    const plan = state.creativePlan;
    if (!plan || !Array.isArray(plan.operations) || !plan.operations.length) return;
    if (aiTimelineSignature() !== state.creativeSnapshot) {
      aiSetStatus("The timeline changed after the proposal. No edits were applied; analyze again to refresh the plan.", "error");
      $("ai-apply-plan").disabled = true;
      return;
    }
    const working = state.project.timeline.map((clip) => Object.assign({}, clip, {
      layers: Array.isArray(clip.layers) ? clip.layers.map((layer) => Object.assign({}, layer)) : []
    }));
    const byId = new Map(working.map((clip) => [clip.id, clip]));
    const allowedMotion = new Set(["none", "slow-zoom", "zoom-out", "pan-left", "pan-right"]);
    const allowedFit = new Set(["cover", "contain"]);
    const allowedPosition = new Set(["bottom", "center", "top"]);
    const allowedFont = new Set(["sans", "serif", "mono"]);
    const allowedColor = /^#[0-9a-fA-F]{6}$/;
    try {
      for (const op of plan.operations) {
        if (!op || typeof op !== "object") throw new Error("The proposed plan contains an invalid operation.");
        if (op.type === "reorder_timeline") {
          const order = op.clip_ids;
          const expected = working.map((clip) => clip.id);
          if (!state.creativeAllowReorder || !Array.isArray(order) ||
              order.length !== expected.length || new Set(order).size !== order.length ||
              order.some((id) => !expected.includes(id))) {
            throw new Error("Timeline reorder did not match every current shot; nothing was applied.");
          }
          const reordered = order.map((id) => byId.get(id));
          working.splice(0, working.length, ...reordered);
          continue;
        }
        const clip = byId.get(op.clip_id);
        if (!clip || clip.assetId !== op.asset_id || !state.creativeSelectedIds.includes(op.clip_id)) {
          throw new Error("An operation no longer matches the reviewed asset selection; nothing was applied.");
        }
        switch (op.type) {
          case "set_duration":
            if (typeof op.duration_seconds !== "number" || !Number.isFinite(op.duration_seconds) ||
                op.duration_seconds < 0.5 || op.duration_seconds > 600) throw new Error("Invalid shot duration; nothing was applied.");
            const sourceAsset = assetById(clip.assetId);
            if (sourceAsset && sourceAsset.type.startsWith("video/") && Number(sourceAsset.duration) > 0 &&
                op.duration_seconds > Math.max(0, Number(sourceAsset.duration) - (Number(clip.sourceIn) || 0))) {
              throw new Error("The proposed shot duration exceeds the remaining video source; nothing was applied.");
            }
            clip.duration = op.duration_seconds;
            break;
          case "set_motion":
            if (!allowedMotion.has(op.preset)) throw new Error("Unsupported motion preset; nothing was applied.");
            clip.motion = op.preset;
            break;
          case "set_fit":
            if (!allowedFit.has(op.fit)) throw new Error("Unsupported image fit; nothing was applied.");
            clip.fit = op.fit;
            break;
          case "set_title":
            if (typeof op.text !== "string" || op.text.length > 240) throw new Error("Invalid title text; nothing was applied.");
            clip.title = op.text;
            break;
          case "set_subtitle":
            if (typeof op.text !== "string" || op.text.length > 300) throw new Error("Invalid subtitle text; nothing was applied.");
            clip.subtitle = op.text;
            break;
          case "set_title_style":
            if (!allowedPosition.has(op.position) || !allowedFont.has(op.font) ||
                !Number.isInteger(op.size) || op.size < 22 || op.size > 88 ||
                typeof op.color !== "string" || !allowedColor.test(op.color)) {
              throw new Error("Unsupported title style; nothing was applied.");
            }
            clip.titlePosition = op.position;
            clip.titleFont = op.font;
            clip.titleSize = op.size;
            clip.titleColor = op.color;
            break;
          case "add_graphic_layer": {
            const allowedLayerTypes = new Set(["text", "rect", "circle", "line", "arrow"]);
            const allowedAnimations = new Set(["none", "fade-in", "slide-up", "slide-left", "scale-in"]);
            const numberInRange = (value, low, high) => typeof value === "number" && Number.isFinite(value) && value >= low && value <= high;
            if (!allowedLayerTypes.has(op.layer_type) || !allowedAnimations.has(op.animation) ||
                !allowedFont.has(op.font) || typeof op.name !== "string" || op.name.length > 100 ||
                typeof op.text !== "string" || op.text.length > 200 ||
                (op.layer_type === "text" && !op.text.trim()) ||
                !numberInRange(op.x, 0, 100) || !numberInRange(op.y, 0, 100) ||
                !numberInRange(op.width, 1, 100) || !numberInRange(op.height, 1, 100) ||
                !numberInRange(op.opacity, 0, 1) ||
                !Number.isInteger(op.font_size) || op.font_size < 10 || op.font_size > 180 ||
                typeof op.color !== "string" || !allowedColor.test(op.color)) {
              throw new Error("The graphics engineer proposed an invalid native layer; nothing was applied.");
            }
            if (!Array.isArray(clip.layers)) clip.layers = [];
            if (clip.layers.length >= 3) throw new Error("A shot may have no more than three added graphic layers.");
            clip.layers.push({
              id: crypto.randomUUID(), type: op.layer_type, name: op.name, text: op.text,
              x: op.x, y: op.y, width: op.width, height: op.height,
              fontSize: op.font_size, color: op.color, font: op.font,
              opacity: op.opacity, animation: op.animation
            });
            break;
          }
          default:
            throw new Error("This build cannot apply the proposed operation '" + String(op.type) + "'. Nothing was changed.");
        }
      }
    } catch (error) {
      aiSetStatus(String(error.message || error), "error");
      return;
    }
    pausePreview();
    state.project.timeline = working;
    if (!state.project.timeline.some((clip) => clip.id === state.selectedClipId)) {
      state.selectedClipId = state.project.timeline[0] ? state.project.timeline[0].id : null;
    }
    state.currentClipId = state.selectedClipId;
    state.creativePlanApplied = true;
    renderTimeline();
    renderInspector();
    updateStats();
    scheduleSave();
    drawFrame();
    $("ai-apply-plan").disabled = true;
    aiSetStatus("Reviewed plan applied to the local editable timeline and queued for autosave. No transition, audio track, mask, or generated asset was added.", "success");
    $("agent-state").textContent = "AI-directed changes were applied only after your approval. The rendered result still needs a visual review.";
  }

  function clearAiProposal() {
    state.creativePlan = null;
    state.creativeSnapshot = null;
    state.creativeSelectedIds = [];
    state.creativeAllowReorder = false;
    state.creativePlanApplied = false;
    $("ai-plan-preview").hidden = true;
    $("ai-apply-plan").disabled = true;
    aiSetStatus("Proposal cleared. Your timeline was not changed.", "");
  }

  function bindUi() {
    $("media-input").addEventListener("change", async (event) => {
      await importFiles(event.target.files);
      event.target.value = "";
    });
    const dropzone = $("dropzone");
    ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault(); dropzone.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault(); dropzone.classList.remove("drag-over");
    }));
    dropzone.addEventListener("drop", (event) => importFiles(event.dataTransfer && event.dataTransfer.files));
    $("asset-search").addEventListener("input", renderAssets);
    $("add-all-assets").addEventListener("click", addAllAssets);
    $("search-online-assets").addEventListener("click", () => searchOnlineAssets());
    $("online-asset-query").addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); searchOnlineAssets(); }
    });
    $("pinterest-reference").addEventListener("click", () => {
      const query = String($("online-asset-query").value || "").trim() || deriveAssetQuery($("creative-brief").value);
      if (!query) { onlineStatus("Enter a search phrase or write a Director's Brief first.", "error"); return; }
      const url = "https://www.pinterest.com/search/pins/?" + new URLSearchParams({ q: query }).toString();
      window.open(url, "_blank", "noopener,noreferrer");
    });
    $("build-from-brief").addEventListener("click", buildDraftFromBrief);
    $("save-project").addEventListener("click", () => saveProject(true));
    $("save-brief").addEventListener("click", () => { state.project.brief = $("creative-brief").value; scheduleSave(); toast("Director's brief saved with project."); });
    $("open-ai-director").addEventListener("click", openAiDirector);
    $("close-ai-director").addEventListener("click", () => { $("ai-director-panel").hidden = true; });
    $("ai-consent").addEventListener("change", updateAiControls);
    $("ai-analyze").addEventListener("click", runAiDirection);
    $("ai-apply-plan").addEventListener("click", applyAiPlan);
    $("ai-cancel-plan").addEventListener("click", clearAiProposal);
    $("project-name").addEventListener("input", scheduleSave);
    $("creative-brief").addEventListener("input", scheduleSave);
    $("toggle-play").addEventListener("click", togglePreview);
    $("render-video").addEventListener("click", renderVideo);
    $("render-video-bottom").addEventListener("click", renderVideo);
    $("export-project").addEventListener("click", downloadProjectJson);
    $("download-manifest").addEventListener("click", downloadManifest);
    $("clear-timeline").addEventListener("click", () => {
      if (!state.project.timeline.length) return;
      if (!window.confirm("Remove every shot from the timeline? Your media library stays intact.")) return;
      pausePreview();
      state.project.timeline = []; state.selectedClipId = null; state.playhead = 0;
      renderTimeline(); renderInspector(); updateStats(); scheduleSave(); drawFrame();
    });
    $("playhead").addEventListener("input", () => {
      pausePreview();
      state.playhead = Math.min(totalDuration(), Math.max(0, Number($("playhead").value) || 0));
      const entry = clipAtTime(state.playhead);
      if (entry) {
        state.currentClipId = entry.clip.id;
        loadMediaForPreview(entry.clip.assetId, entry.clip);
      }
      drawFrame();
    });
    $("previous-frame").addEventListener("click", () => {
      pausePreview();
      const entry = clipAtTime(state.playhead);
      const index = entry ? entry.index - 1 : state.project.timeline.length - 1;
      if (index >= 0 && state.project.timeline[index]) selectClip(state.project.timeline[index].id);
      else { state.playhead = 0; drawFrame(); }
    });
    $("next-frame").addEventListener("click", () => {
      pausePreview();
      const entry = clipAtTime(state.playhead);
      const index = entry ? Math.min(state.project.timeline.length - 1, entry.index + 1) : 0;
      if (state.project.timeline[index]) selectClip(state.project.timeline[index].id);
    });
    $("preview-scale").addEventListener("change", () => {
      const dims = $("preview-scale").value.split("x").map(Number);
      canvas.width = dims[0] || 1280; canvas.height = dims[1] || 720;
      updateStats(); drawFrame();
    });
    bindInspector();
    bindGraphicLayers();
  }

  async function init() {
    try {
      state.db = await openDatabase();
      bindUi();
      await loadProject();
      const storedCount = state.assets.length;
      $("agent-state").textContent = "Local editing is active. AI direction uses a configured provider only after explicit consent for selected resized previews. No media is sent until you request analysis.";
      updateStorageLabel();
      loadAiModelStatus();
      drawFrame();
      if (storedCount) toast("Restored " + storedCount + " local media asset(s).");
    } catch (error) {
      $("storage-state").textContent = "LOCAL STORAGE ERROR";
      showMessage("Studio could not initialise browser storage: " + error.message + ". Try the current Chrome browser over HTTPS.", true);
      $("media-input").disabled = true;
    }
  }

  window.addEventListener("pagehide", () => {
    pausePreview();
    state.objectUrls.forEach((url) => URL.revokeObjectURL(url));
    state.thumbUrls.forEach((url) => URL.revokeObjectURL(url));
    if (state.audioContext && state.audioContext.state !== "closed") state.audioContext.close().catch(() => {});
  });

  init();
})();
