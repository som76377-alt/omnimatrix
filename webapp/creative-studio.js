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
    onlineAssetResults: [], onlineSearchBusy: false, onlineImportBusy: false,
    autoFinishBusy: false, lastAutoDraftClipIds: [], autoRenderOnAssembly: false,
    autoCriticRevisionPerformed: false
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

  async function createOriginalGraphicCards(brief) {
    const selector = $("preview-scale");
    const dimensions = String(selector && selector.value || "1280x720").split("x").map(Number);
    const width = dimensions[0] || 1280;
    const height = dimensions[1] || 720;
    const title = extractBriefTitle(brief).slice(0, 72) || "A closer look";
    const topic = deriveAssetQuery(brief).slice(0, 96) || title;
    const induction = /induction|magnetic field|coil|cooktop|stove|electromagnet/i.test(brief);
    const stages = [
      { kicker: "01 / THE QUESTION", heading: title, footer: "Start with the phenomenon." },
      { kicker: "02 / THE MECHANISM", heading: induction ? "FIELD → CURRENT → HEAT" : "FOLLOW THE PROCESS", footer: topic },
      { kicker: "03 / THE TAKEAWAY", heading: "CAUSE BECOMES EFFECT", footer: "A visual explainer · original vector graphics" }
    ];
    const files = [];
    const stamp = crypto.randomUUID().slice(0, 8);
    for (let index = 0; index < stages.length; index += 1) {
      const canvasNode = document.createElement("canvas");
      canvasNode.width = width;
      canvasNode.height = height;
      const g = canvasNode.getContext("2d", { alpha: false });
      if (!g) throw new Error("This browser cannot create original graphic scenes.");
      g.fillStyle = "#10120f"; g.fillRect(0, 0, width, height);
      g.strokeStyle = "#242a22"; g.lineWidth = 1;
      const step = Math.max(24, Math.round(width / 32));
      for (let x = 0; x < width; x += step) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, height); g.stroke(); }
      for (let y = 0; y < height; y += step) { g.beginPath(); g.moveTo(0, y); g.lineTo(width, y); g.stroke(); }
      const margin = Math.round(width * 0.075);
      g.fillStyle = "#d5fb63"; g.fillRect(margin, margin, Math.round(width * 0.065), Math.max(3, Math.round(width * 0.004)));
      g.fillStyle = "#d5fb63"; g.font = "600 " + Math.max(12, Math.round(width * 0.016)) + "px system-ui";
      g.fillText(stages[index].kicker, margin, margin + Math.round(height * 0.055));
      const headingSize = Math.max(22, Math.round(width * (index === 0 ? 0.055 : 0.043)));
      g.fillStyle = "#f1f3e8"; g.font = "700 " + headingSize + "px system-ui";
      const words = stages[index].heading.split(/\s+/);
      let line = "", lines = [];
      for (const word of words) {
        const next = line ? line + " " + word : word;
        if (g.measureText(next).width > width * 0.82 && line) { lines.push(line); line = word; } else line = next;
      }
      if (line) lines.push(line);
      lines.slice(0, 3).forEach((row, i) => g.fillText(row, margin, Math.round(height * 0.31) + i * Math.round(headingSize * 1.15)));
      const cx = Math.round(width * 0.69), cy = Math.round(height * 0.61), radius = Math.round(Math.min(width, height) * 0.12);
      g.strokeStyle = "#d5fb63"; g.lineWidth = Math.max(2, Math.round(width * 0.002));
      if (induction) {
        // A clean, original schematic: pan, coil and alternating field lines.
        g.beginPath(); g.ellipse(cx, cy - radius * 0.55, radius * 1.25, radius * 0.28, 0, 0, Math.PI * 2); g.stroke();
        g.beginPath(); g.moveTo(cx - radius * 1.25, cy - radius * 0.55); g.lineTo(cx - radius * 0.95, cy + radius * 0.12); g.quadraticCurveTo(cx, cy + radius * 0.48, cx + radius * 0.95, cy + radius * 0.12); g.lineTo(cx + radius * 1.25, cy - radius * 0.55); g.stroke();
        for (let j = 0; j < 4; j += 1) { g.beginPath(); g.ellipse(cx, cy + radius * (0.25 + j * 0.13), radius * (0.65 + j * 0.22), radius * (0.10 + j * 0.015), 0, 0, Math.PI * 2); g.stroke(); }
        g.fillStyle = "#d5fb63"; for (let j = 0; j < 9; j += 1) { const px = cx - radius * 0.85 + j * radius * 0.21; g.beginPath(); g.arc(px, cy + radius * 0.72, Math.max(2, radius * 0.035), 0, Math.PI * 2); g.fill(); }
      } else {
        const nodes = [{x:cx-radius*1.1,y:cy},{x:cx,y:cy-radius*0.72},{x:cx+radius*1.1,y:cy},{x:cx,y:cy+radius*0.72}];
        g.strokeStyle = "#d5fb63";
        [[0,1],[1,2],[2,3],[3,0],[0,2]].forEach(([a,b])=>{g.beginPath();g.moveTo(nodes[a].x,nodes[a].y);g.lineTo(nodes[b].x,nodes[b].y);g.stroke();});
        nodes.forEach((n,i)=>{g.fillStyle=i===1?"#d5fb63":"#10120f";g.beginPath();g.arc(n.x,n.y,Math.max(8,radius*0.18),0,Math.PI*2);g.fill();g.strokeStyle="#d5fb63";g.stroke();});
        for(let j=0;j<7;j++){g.fillStyle="#f1f3e8";g.beginPath();g.arc(cx-radius*0.75+j*radius*0.25,cy+radius*1.1+(j%2)*radius*0.12,Math.max(2,radius*0.025),0,Math.PI*2);g.fill();}
      }
      g.fillStyle = "#a7ad9c"; g.font = "500 " + Math.max(12, Math.round(width * 0.015)) + "px system-ui";
      g.fillText(stages[index].footer.slice(0, 100), margin, height - margin);
      g.fillStyle = "#d5fb63"; g.font = "600 " + Math.max(11, Math.round(width * 0.012)) + "px ui-monospace, monospace";
      g.fillText("OMNITRIX / MOTION GRAPHICS", margin, height - Math.round(margin * 0.42));
      const blob = await new Promise((resolve, reject) => canvasNode.toBlob((value) => value ? resolve(value) : reject(new Error("Original graphic export failed.")), "image/png"));
      files.push(new File([blob], "omnitrix-original-" + stamp + "-" + (index + 1) + ".png", { type: "image/png", lastModified: Date.now() }));
    }
    return files;
  }

  async function requestGeneratedImage(brief) {
    const nativeMode = isNativeMobileStudio();
    const token = aiRuntimeToken();
    if (!nativeMode && !token) throw new Error("The authenticated Studio runtime is not connected.");
    const width = canvas.width || 1280;
    const height = canvas.height || 720;
    const response = await fetch(
      nativeMode ? "./api/mobile/creative/generate-image" : "./api/creative/generate-image",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(nativeMode ? {} : { Authorization: "Bearer " + token })
        },
        body: JSON.stringify({
          consent: true,
          prompt: String(brief || "").slice(0, 1500) +
            "\\nCompose for a " + width + " by " + height + " video frame. Create a specific, accurate visual for the subject; no captions, no interface, no decorative particles."
        })
      }
    );
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The image-generation route returned unreadable JSON."); }
    if (!response.ok || !data || data.ok !== true || !data.image_base64) {
      throw new Error((data && data.error) || "The image provider did not return a usable image.");
    }
    const binary = atob(data.image_base64);
    if (binary.length < 1024 || binary.length > 6 * 1024 * 1024) {
      throw new Error("The generated image is empty or exceeds the local import limit.");
    }
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const mime = ["image/png", "image/jpeg", "image/webp"].includes(data.mime_type) ? data.mime_type : "image/png";
    const extension = mime === "image/jpeg" ? "jpg" : mime === "image/webp" ? "webp" : "png";
    return new File([bytes], "omnitrix-ai-generated-" + crypto.randomUUID().slice(0, 8) + "." + extension, {
      type: mime, lastModified: Date.now()
    });
  }

  async function assembleOriginalGraphicFallback(brief) {
    onlineStatus("No suitable source clips were found. The graphics engineer is creating an original three-scene vector explainer…", "");
    const files = await createOriginalGraphicCards(brief);
    let imageGenerated = false;
    if ($("auto-creative-consent").checked) {
      try {
        onlineStatus("No suitable source media. Asking the configured image model for one original scene…", "");
        files.unshift(await requestGeneratedImage(brief));
        imageGenerated = true;
      } catch (error) {
        onlineStatus("AI image generation unavailable (" + String(error.message || error) + "). Using original vector graphics instead.", "");
      }
    }
    const before = new Set(state.assets.map((asset) => asset.name));
    await importFiles(files);
    const generated = state.assets.filter((asset) => files.some((file) => file.name === asset.name) && !before.has(asset.name));
    if (generated.length !== files.length) throw new Error("Original graphics were created, but not all scenes could be added to the media library.");
    const secondsMatch = brief.match(/\b(\d{1,3})\s*(?:-| )?\s*(?:seconds?|secs?)\b/i);
    const targetSeconds = Math.min(45, Math.max(4, secondsMatch ? Number(secondsMatch[1]) : 12));
    const startIndex = state.project.timeline.length;
    generated.forEach((asset, index) => {
      const clip = createClip(asset);
      clip.duration = targetSeconds / generated.length;
      clip.fit = asset.name.startsWith("omnitrix-ai-generated-") ? "cover" : "contain";
      clip.motion = index === 0 ? "slow-zoom" : index === 1 ? "pan-left" : "none";
      clip.title = "";
      clip.subtitle = "";
      state.project.timeline.push(clip);
    });
    const added = state.project.timeline.slice(startIndex);
    state.selectedClipId = added[0] ? added[0].id : state.selectedClipId;
    state.currentClipId = state.selectedClipId;
    renderTimeline(); renderInspector(); renderGraphicLayers(); updateStats(); drawFrame();
    await saveProject(false);
    state.lastAutoDraftClipIds = added.map((clip) => clip.id);
    onlineStatus(imageGenerated
      ? "An original AI-generated image plus original vector graphics were assembled. Inspect factual details and composition before publishing."
      : "Original motion-graphics draft assembled from locally drawn vector scenes. A configured image model was unavailable or not authorised.", "success");
    if ($("auto-creative-consent").checked) {
      await finishDraftAutomatically(state.lastAutoDraftClipIds);
    } else if (state.autoRenderOnAssembly) {
      await renderVideo();
    }
  }

  function updatePreviewResolution() {
    const selector = $("preview-scale");
    if (!selector) return;
    const dimensions = String(selector.value || "1280x720").split("x").map(Number);
    const width = dimensions[0] || 1280;
    const height = dimensions[1] || 720;
    canvas.width = width;
    canvas.height = height;
    const ratio = width === height ? "1:1" : width > height ? "16:9" : "9:16";
    const ratioLabel = document.querySelector(".resolution-tag");
    if (ratioLabel) ratioLabel.textContent = ratio;
    const wrapper = document.querySelector(".canvas-wrap");
    if (wrapper) wrapper.style.aspectRatio = width + " / " + height;
    updateStats();
    drawFrame();
  }

  function setPreviewResolutionFromBrief(brief) {
    const selector = $("preview-scale");
    if (!selector) return;
    const text = String(brief || "");
    let target = "";
    if (/\b(?:vertical|portrait|9\s*[:x/]\s*16|9\s+by\s+16|tiktok|reels?|shorts?)\b/i.test(text)) {
      target = "720x1280";
    } else if (/\b(?:square|1\s*[:x/]\s*1|1\s+by\s+1)\b/i.test(text)) {
      target = "720x720";
    } else if (/\b(?:horizontal|landscape|wide|16\s*[:x/]\s*9|16\s+by\s+9)\b/i.test(text)) {
      target = "1280x720";
    }
    if (target && Array.from(selector.options).some((option) => option.value === target)) {
      selector.value = target;
      updatePreviewResolution();
    }
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
      // Commons-hosted media may be imported into a private draft even when
      // metadata is incomplete. That does not imply permission to publish it.
      (item.rights_verified === true || item.provider === "commons"));
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
      copy.textContent = "Omnitrix can broaden the search automatically. If no usable media exists, create an original motion-graphics scene instead.";
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
    const nativeMode = isNativeMobileStudio();
    const provider = nativeMode ? "commons" : ($("online-asset-provider").value || "commons");
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
    if (!nativeMode && !token) {
      onlineStatus("The authenticated Python-backed Studio runtime is not connected in this tab. Open the core Studio, connect its runtime, then return here.", "error");
      return null;
    }
    state.onlineSearchBusy = true;
    $("search-online-assets").disabled = true;
    onlineStatus("Searching " + (provider === "commons" ? "Wikimedia Commons" : "Pexels") + " for “" + query + "”…", "");
    try {
      const params = new URLSearchParams({ q: query, provider, kind: $("online-asset-kind").value || "any", limit: "12" });
      const endpoint = nativeMode ? "./api/mobile/creative/search?" : "./api/creative/search?";
      const response = await fetch(endpoint + params.toString(), {
        method: "GET", cache: "no-store",
        headers: nativeMode ? { Accept: "application/json" } : { Accept: "application/json", Authorization: "Bearer " + token }
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
      const nativeMode = isNativeMobileStudio();
      const token = aiRuntimeToken();
      if (!nativeMode && !token) throw new Error("The authenticated Studio runtime is not connected.");
      onlineStatus("Downloading a bounded copy of “" + (item.title || "asset") + "”…", "");
      const params = new URLSearchParams({ provider: nativeMode ? "commons" : item.provider, url: item.asset_url });
      const endpoint = nativeMode ? "./api/mobile/creative/assets/download?" : "./api/creative/assets/download?";
      const response = await fetch(endpoint + params.toString(), {
        method: "GET", cache: "no-store",
        headers: nativeMode ? {} : { Authorization: "Bearer " + token }
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

  async function finishDraftAutomatically(clipIds) {
    if (!$("auto-creative-consent").checked || state.autoFinishBusy) return;
    state.autoCriticRevisionPerformed = false;
    const selectedIds = Array.from(new Set((clipIds || []).filter((id) =>
      state.project.timeline.some((clip) => clip.id === id)
    ))).slice(0, 6);
    if (!selectedIds.length) {
      onlineStatus("No new draft shots remain to direct. Your library is untouched.", "error");
      return;
    }
    state.autoFinishBusy = true;
    const button = $("build-from-brief");
    button.disabled = true;
    try {
      $("ai-director-panel").hidden = false;
      renderAiSelectionList();
      const selected = new Set(selectedIds);
      $("ai-selection-list").querySelectorAll("input.ai-asset-check").forEach((checkbox) => {
        checkbox.checked = selected.has(checkbox.value);
      });
      $("ai-consent").checked = true;
      updateAiControls();
      await loadAiModelStatus();
      if (state.creativeStatus && state.creativeStatus.configured) {
        onlineStatus("The visual director is examining only the selected new shots' resized thumbnails…", "");
        await runAiDirection();
        if (state.creativePlan && Array.isArray(state.creativePlan.operations) && state.creativePlan.operations.length) {
          applyAiPlan();
        }
        if (state.creativePlanApplied) {
          onlineStatus("Validated visual edits and graphics were applied to the new draft. Starting local WebM export; inspect it before publishing.", "success");
        } else {
          onlineStatus("The initial timeline is ready, but the visual director did not apply a validated proposal. " +
            (String($("ai-status").textContent || "").trim() || "No supported changes were returned.") +
            " Exporting the supported basic edit.", "");
        }
      } else {
        onlineStatus("A basic asset-based cut is ready, but the visual model is not configured or reachable. No AI visual analysis was claimed. Exporting the basic draft.", "");
      }
      await saveProject(false);
      $("ai-director-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      renderVideo();
    } catch (error) {
      onlineStatus("Automatic visual direction could not finish: " + String(error.message || error) + ". The current local timeline is preserved; inspect it and export manually if useful.", "error");
    } finally {
      state.autoFinishBusy = false;
      button.disabled = false;
    }
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
    setPreviewResolutionFromBrief(brief);
    const provider = $("online-asset-provider").value || "commons";
    if (provider === "pinterest") {
      onlineStatus("Pinterest is a reference-only source. Creating an original graphics draft instead of scraping Pins.", "");
      await assembleOriginalGraphicFallback(brief);
      return;
    }
    if (state.project.timeline.length && !window.confirm("Append a new draft to your existing timeline? Existing shots will be kept.")) return;
    $("build-from-brief").disabled = true;
    try {
      if (!$("online-asset-query").value.trim()) $("online-asset-query").value = deriveAssetQuery(brief);
      let data = await searchOnlineAssets();
      if (!data || !Array.isArray(data.items)) {
        await assembleOriginalGraphicFallback(brief);
        return;
      }
      let eligible = data.items.filter(supportedOnlineAsset);
      if (!eligible.length) {
        if (provider === "pinterest") {
          onlineStatus("Pinterest is a reference source, not a direct import provider. Creating an original motion-graphics draft instead.", "");
        }
        await assembleOriginalGraphicFallback(brief);
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
      state.lastAutoDraftClipIds = draftClips.map((clip) => clip.id).slice(0, 6);
      const automaticDirection = $("auto-creative-consent").checked;
      $("ai-director-panel").hidden = false;
      renderAiSelectionList();
      // Select only the newly assembled clips, never earlier project shots.
      const draftIds = new Set(state.lastAutoDraftClipIds);
      $("ai-selection-list").querySelectorAll("input.ai-asset-check").forEach((checkbox) => {
        checkbox.checked = draftIds.has(checkbox.value);
      });
      updateAiControls();

      if (automaticDirection) {
        // This path requires the explicit per-run checkbox above.
        await finishDraftAutomatically(state.lastAutoDraftClipIds);
      } else {
        onlineStatus(
          "Draft assembled from " + selected.length + " web result(s), target " + targetSeconds + " seconds. Asset matching used titles, descriptions and licence metadata, not a model visually judging the source results.",
          "success"
        );
        await loadAiModelStatus();
        if (state.autoRenderOnAssembly) {
          onlineStatus("The main chat requested a video, so the local basic draft is being exported now. No thumbnails were shared with a model. For richer AI-directed edits on a future run, explicitly enable the visual-direction consent.", "success");
          renderVideo();
        }
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

  function waitForVideoEvent(video, eventName, timeoutMs, failureMessage) {
    return new Promise((resolve, reject) => {
      let timer = 0;
      const cleanup = () => {
        window.clearTimeout(timer);
        video.removeEventListener(eventName, onReady);
        video.removeEventListener("error", onError);
      };
      const onReady = () => { cleanup(); resolve(); };
      const onError = () => { cleanup(); reject(new Error(failureMessage || "The exported video could not be decoded.")); };
      video.addEventListener(eventName, onReady, { once: true });
      video.addEventListener("error", onError, { once: true });
      timer = window.setTimeout(() => {
        cleanup();
        reject(new Error("Timed out while checking the exported video."));
      }, timeoutMs);
      if (eventName === "loadedmetadata" && video.readyState >= 1) onReady();
      if (eventName === "loadeddata" && video.readyState >= 2) onReady();
    });
  }

  async function inspectRenderedVideo(blob, expectedDuration, reviewClipIds, renderTimelineSnapshot) {
    if (!(blob instanceof Blob) || !blob.size) throw new Error("The browser returned an empty video file.");
    if (blob.size < 2048) throw new Error("The exported video is unexpectedly tiny and may be incomplete.");
    const url = URL.createObjectURL(blob);
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.setAttribute("aria-hidden", "true");
    video.style.position = "fixed";
    video.style.left = "-10000px";
    video.style.width = "2px";
    video.style.height = "2px";
    document.body.append(video);
    const warnings = [];
    try {
      const metadata = waitForVideoEvent(video, "loadedmetadata", 12000, "The exported WebM could not be reopened for verification.");
      video.src = url;
      video.load();
      await metadata;
      const duration = Number(video.duration);
      const width = Number(video.videoWidth);
      const height = Number(video.videoHeight);
      if (!Number.isFinite(duration) || duration <= 0 || width <= 0 || height <= 0) {
        throw new Error("The exported file did not expose valid playable video metadata.");
      }
      if (Number.isFinite(expectedDuration) && expectedDuration > 0) {
        const tolerance = Math.max(1.25, expectedDuration * 0.12);
        if (Math.abs(duration - expectedDuration) > tolerance) {
          warnings.push("duration differs from the timeline (" + duration.toFixed(2) + "s vs " + expectedDuration.toFixed(2) + "s)");
        }
      }
      const probe = document.createElement("canvas");
      probe.width = 64;
      probe.height = 36;
      const probeContext = probe.getContext("2d", { willReadFrequently: true });
      if (!probeContext) throw new Error("The browser could not create the local frame-inspection canvas.");
      const times = Array.from(new Set([
        Math.min(duration * 0.02, 0.08),
        duration * 0.25,
        duration * 0.5,
        duration * 0.75,
        Math.max(0, duration - Math.min(duration * 0.02, 0.08))
      ].map((time) => Math.max(0, Math.min(duration - 0.01, time)).toFixed(3)))).map(Number);
      const frameStats = [];
      const reviewFrames = [];
      const seekTo = async (time) => {
        if (Math.abs(video.currentTime - time) <= 0.02) return;
        await new Promise((resolve, reject) => {
          let timer = 0;
          const cleanup = () => {
            window.clearTimeout(timer);
            video.removeEventListener("seeked", onSeeked);
            video.removeEventListener("error", onError);
          };
          const onSeeked = () => { cleanup(); resolve(); };
          const onError = () => { cleanup(); reject(new Error("A sampled frame could not be decoded.")); };
          timer = window.setTimeout(() => {
            cleanup();
            reject(new Error("Timed out seeking within the exported video."));
          }, 5000);
          video.addEventListener("seeked", onSeeked, { once: true });
          video.addEventListener("error", onError, { once: true });
          video.currentTime = time;
        });
      };
      await waitForVideoEvent(video, "loadeddata", 8000, "The exported video did not decode its first frame.");
      for (const time of times) {
        await seekTo(time);
        probeContext.drawImage(video, 0, 0, probe.width, probe.height);
        const pixels = probeContext.getImageData(0, 0, probe.width, probe.height).data;
        let sum = 0;
        let squared = 0;
        for (let i = 0; i < pixels.length; i += 4) {
          const luma = 0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
          sum += luma;
          squared += luma * luma;
        }
        const count = pixels.length / 4;
        const mean = sum / count;
        const variance = Math.max(0, squared / count - mean * mean);
        frameStats.push({ time, mean, variance });
      }

      const reviewSet = new Set(Array.isArray(reviewClipIds) ? reviewClipIds : []);
      const timeline = Array.isArray(renderTimelineSnapshot) ? renderTimelineSnapshot : [];
      let timelineStart = 0;
      const reviewCanvas = document.createElement("canvas");
      const reviewScale = Math.min(1, 360 / Math.max(1, width), 640 / Math.max(1, height));
      reviewCanvas.width = Math.max(1, Math.round(width * reviewScale));
      reviewCanvas.height = Math.max(1, Math.round(height * reviewScale));
      const reviewContext = reviewCanvas.getContext("2d", { alpha: false });
      if (reviewContext && reviewSet.size) {
        for (const clip of timeline) {
          const clipDuration = Math.max(0.5, Number(clip.duration) || 0);
          const targetTime = Math.min(duration - 0.01, Math.max(0, timelineStart + clipDuration / 2));
          timelineStart += clipDuration;
          if (!reviewSet.has(clip.id) || reviewFrames.length >= 4) continue;
          await seekTo(targetTime);
          reviewContext.fillStyle = "#10130f";
          reviewContext.fillRect(0, 0, reviewCanvas.width, reviewCanvas.height);
          reviewContext.drawImage(video, 0, 0, reviewCanvas.width, reviewCanvas.height);
          let dataUrl = reviewCanvas.toDataURL("image/jpeg", 0.7);
          // Keep every consented rendered sample under the existing 350 KB preview cap.
          if (dataUrl.length > 340000) dataUrl = reviewCanvas.toDataURL("image/jpeg", 0.5);
          if (dataUrl.length <= 350000) {
            reviewFrames.push({
              time: targetTime,
              clip_id: clip.id,
              asset_id: clip.assetId,
              preview_data_url: dataUrl
            });
          } else {
            warnings.push("could not create a small rendered review frame for clip " + String(clip.id).slice(0, 12));
          }
        }
      }
      const suspiciousDark = frameStats.filter((frame) => frame.mean < 5 && frame.variance < 3);
      if (suspiciousDark.length) {
        warnings.push("possible black/blank output near " + suspiciousDark.map((frame) => frame.time.toFixed(1) + "s").join(", "));
      }
      return {
        ok: true, decodable: true, duration, width, height,
        sampledFrames: frameStats.length,
        reviewFrames,
        warnings
      };
    } finally {
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
      URL.revokeObjectURL(url);
    }
  }

  async function critiqueRenderedDraft(inspection, renderSignature) {
    if (!$("auto-creative-consent").checked) {
      return { attempted: false, changed: false, message: "Post-render model critique consent was switched off before upload." };
    }
    const token = aiRuntimeToken();
    const nativeMode = isNativeMobileStudio();
    if (!token && !nativeMode) return { attempted: false, changed: false, message: "Runtime token unavailable; local render only." };
    if (aiTimelineSignature() !== renderSignature) {
      return { attempted: false, changed: false, message: "Timeline changed after rendering; the draft was not auto-modified." };
    }
    const allowed = new Set(state.lastAutoDraftClipIds.slice(0, 4));
    const frames = Array.isArray(inspection && inspection.reviewFrames)
      ? inspection.reviewFrames.filter((frame) => allowed.has(frame.clip_id)).slice(0, 4)
      : [];
    if (!frames.length) return { attempted: false, changed: false, message: "No safely mapped rendered-frame samples were available." };
    await loadAiModelStatus();
    if (!state.creativeStatus || state.creativeStatus.configured !== true) {
      return { attempted: false, changed: false, message: "Visual model not configured; no post-render AI critique was run." };
    }
    const ids = frames.map((frame) => frame.clip_id);
    const timelineById = new Map(state.project.timeline.map((clip) => [clip.id, clip]));
    const records = frames.map((frame) => {
      const clip = timelineById.get(frame.clip_id);
      const asset = clip ? assetById(clip.assetId) : null;
      if (!clip || !asset || clip.assetId !== frame.asset_id || typeof frame.preview_data_url !== "string") {
        throw new Error("A rendered sample no longer maps to its original shot. The automatic critique was cancelled.");
      }
      return {
        asset_id: clip.assetId,
        clip_id: clip.id,
        name: (asset.name || "shot") + " — rendered output at " + Number(frame.time).toFixed(2) + "s",
        preview_data_url: frame.preview_data_url,
        duration: Number(clip.duration) || 0,
        source_duration: Number(asset.duration) || 0,
        source_in: Number(clip.sourceIn) || 0,
        media_type: String(asset.type || ""),
        motion: String(clip.motion || "none"),
        fit: String(clip.fit || "cover")
      };
    });
    const critiqueBrief = [
      "POST-RENDER VISUAL CRITIC — THESE ARE SAMPLES FROM THE ACTUAL EXPORTED WEBM, not source thumbnails.",
      "Inspect only these sampled rendered frames. They include the composition, cropping, text and native graphics that were actually exported.",
      "Compare visible evidence with the user's brief. Report only concrete defects supported by these frames, such as a clearly irrelevant shot, title covering the subject, unreadable/overflowing text, bad crop or redundant graphic.",
      "Use only the exact supplied clip/asset IDs. If a shot is visibly off-topic, remove_clip with a specific reason is allowed. Return supported corrective operations only; do not add decorations to make the result busier.",
      "Do not claim to inspect sound, motion between frames, full clips, or unshown moments. If the frames are acceptable or uncertain, return an empty operations array.",
      "Original brief: " + String($("creative-brief").value || "").slice(0, 3500)
    ].join("\n\n");
    const response = await fetch((isNativeMobileStudio() ? "./api/mobile/creative/analyze" : "./api/creative/analyze"), {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify({
        consent: true,
        consent_clip_ids: ids,
        allow_reorder: false,
        brief: critiqueBrief.slice(0, 4000),
        assets: records
      })
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The rendered-frame critic returned unreadable JSON."); }
    if (!response.ok || !data || data.ok !== true) {
      throw new Error((data && data.error) || "Post-render visual critique could not start.");
    }
    if (data.status === "processing" && typeof data.job_id === "string") {
      aiSetStatus("The local render decoded. Waiting for the consented post-render critic to inspect sampled output frames…", "");
      data = await pollAiCreativeJob(data.job_id, token);
    }
    if (!data || data.ok !== true || data.status !== "complete" || !data.plan) {
      throw new Error((data && data.error) || "The post-render critic did not return a verified complete plan.");
    }
    if (aiTimelineSignature() !== renderSignature) {
      throw new Error("The timeline changed while the critic was running. Its proposed edits were discarded.");
    }
    state.creativePlan = data.plan;
    state.creativeSnapshot = renderSignature;
    state.creativeSelectedIds = ids.slice();
    state.creativeAllowReorder = false;
    state.creativePlanApplied = false;
    renderAiPlan(data);
    const count = Array.isArray(data.plan.operations) ? data.plan.operations.length : 0;
    if (!count) {
      return {
        attempted: true, changed: false,
        message: "Post-render critic (" + (data.worker || "worker unknown") + " / " + (data.model || "model unknown") + ") returned no supported corrections."
      };
    }
    applyAiPlan();
    if (!state.creativePlanApplied) {
      throw new Error("The critic proposed changes, but the local validator rejected them. No automatic correction was applied.");
    }
    state.autoCriticRevisionPerformed = true;
    return {
      attempted: true, changed: true,
      message: "Post-render critic (" + (data.worker || "worker unknown") + " / " + (data.model || "model unknown") + ") applied " + count + " validated correction operation(s). A single bounded re-render will follow."
    };
  }

  async function deliverRenderedVideo(blob, fileName) {
    if (isNativeMobileStudio()) {
      if (!(blob instanceof Blob) || !blob.size) throw new Error("The renderer returned an empty WebM.");
      if (blob.size > 24 * 1024 * 1024) {
        throw new Error("This render is over the 24 MB mobile-save limit. Choose a shorter duration or lower resolution, then render again.");
      }
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 32768) {
        binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + 32768)));
      }
      const response = window.OmnitrixNativeBridge.saveVideoBase64(fileName, blob.type || "video/webm", btoa(binary));
      if (response !== "saved") {
        const detail = String(response || "").startsWith("error:") ? String(response).slice(6) : "";
        throw new Error(detail || "Android did not confirm saving the generated video.");
      }
      return "saved to Movies/Omnitrix on this phone";
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return "downloaded to this device";
  }

  async function renderVideo(options) {
    if (state.exporting) return;
    const autoCritiqueRetry = Boolean(options && options.autoCritiqueRetry === true);
    const runPostRenderCritic = Boolean(!autoCritiqueRetry && state.autoFinishBusy && $("auto-creative-consent").checked);
    if (!state.project.timeline.length) { showMessage("Add at least one shot before rendering.", true); return; }
    if (!("MediaRecorder" in window) || !canvas.captureStream) {
      showMessage("This browser does not support canvas video recording. Try a current version of Chrome or Edge.", true);
      return;
    }
    pausePreview();
    const dimensions = $("preview-scale").value.split("x").map(Number);
    const original = { width: canvas.width, height: canvas.height };
    const expectedDuration = totalDuration();
    const renderTimelineSnapshot = state.project.timeline.map((clip) => ({
      id: clip.id, assetId: clip.assetId, duration: Number(clip.duration) || 0
    }));
    const reviewClipIds = runPostRenderCritic
      ? state.lastAutoDraftClipIds.slice(0, 4)
      : [];
    const renderSignature = aiTimelineSignature();
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
      recorder.onstop = async () => {
        const blob = new Blob(state.chunks, { type: recorder.mimeType || "video/webm" });
        outputStream.getTracks().forEach((track) => track.stop());
        canvas.width = original.width;
        canvas.height = original.height;
        state.recorder = null;
        state.isPlaying = false;
        sourceVideo.pause();
        drawFrame();
        if (blob.size) {
          let inspection = null;
          let inspectionFailure = "";
          showMessage("Checking the actual WebM file locally (decode, duration, size and sampled frames)…", false);
          try {
            inspection = await inspectRenderedVideo(blob, expectedDuration, reviewClipIds, renderTimelineSnapshot);
          } catch (error) {
            inspectionFailure = String(error.message || error);
          }
          let critique = { attempted: false, changed: false, message: "" };
          if (runPostRenderCritic && $("auto-creative-consent").checked &&
              inspection && inspection.ok && inspection.reviewFrames && inspection.reviewFrames.length) {
            try {
              critique = await critiqueRenderedDraft(inspection, renderSignature);
            } catch (error) {
              critique = { attempted: true, changed: false, message: "Post-render critic unavailable: " + String(error.message || error) };
            }
          }

          if (critique.changed && state.creativePlanApplied && !autoCritiqueRetry) {
            state.exporting = false;
            $("render-video").disabled = false;
            $("render-video-bottom").disabled = false;
            updateTransport();
            showMessage(critique.message + " Discarding the intermediate render and rendering the corrected timeline once.", false);
            await renderVideo({ autoCritiqueRetry: true });
            return;
          }

          // Deliver the actual encoded artifact. Native Android saves it to Movies/Omnitrix;
          // standard browsers receive a regular WebM download.
          let deliveryLabel = "";
          try {
            deliveryLabel = await deliverRenderedVideo(blob, slug(state.project.name) + "-draft.webm");
          } catch (error) {
            deliveryLabel = "not saved: " + String(error.message || error);
          }
          let criticSuffix = "";
          if (critique.attempted) criticSuffix = " · " + critique.message;
          else if (runPostRenderCritic && $("auto-creative-consent").checked) {
            criticSuffix = " · No verified post-render AI critique: " + (critique.message || "No rendered sample was inspected.");
          }
          if (inspection && inspection.ok) {
            const dimensionsLabel = inspection.width + "×" + inspection.height;
            if (inspection.warnings.length) {
              showMessage(
                "WebM exported and decoded · " + formatBytes(blob.size) + " · " + dimensionsLabel + " · " +
                inspection.duration.toFixed(2) + "s. QA warning: " + inspection.warnings.join("; ") +
                ". The file was " + deliveryLabel + "; inspect these points before publishing." + criticSuffix,
                true
              );
            } else {
              const correctionNote = state.autoCriticRevisionPerformed
                ? " One validated correction pass was applied after inspecting the first render; the final render received technical QA, not a second AI critique."
                : "";
              showMessage(
                "WebM exported, reopened and decoded locally · " + deliveryLabel + " · " + formatBytes(blob.size) + " · " +
                dimensionsLabel + " · " + inspection.duration.toFixed(2) + "s · " +
                inspection.sampledFrames + " sampled frames checked. This is technical QA, not a guarantee of artistic quality." +
                correctionNote + criticSuffix,
                false
              );
            }
          } else {
            showMessage(
              "A " + formatBytes(blob.size) + " WebM was generated and " + (deliveryLabel || "delivered") + ", but its playback could not be verified: " +
              (inspectionFailure || "unknown decode error") + ". Open the file and inspect it before publishing." + criticSuffix,
              true
            );
          }
        } else {
          showMessage("The browser returned an empty video file. Try a shorter sequence or lower resolution.", true);
        }
        state.exporting = false;
        $("render-video").disabled = false;
        $("render-video-bottom").disabled = false;
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

  function isNativeMobileStudio() {
    try {
      return Boolean(window.OmnitrixNativeBridge &&
        typeof window.OmnitrixNativeBridge.initialPrompt === "function" &&
        typeof window.OmnitrixNativeBridge.saveVideoBase64 === "function");
    } catch (_) { return false; }
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
    const nativeMode = isNativeMobileStudio();
    if (!token && !nativeMode) {
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
      const response = await fetch(nativeMode ? "./api/mobile/creative/status" : "./api/creative/status", {
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
      case "remove_clip": return name + " — remove this shot: " + op.reason + ".";
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
    const nativeMode = isNativeMobileStudio();
    const maxAttempts = 240;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      const response = await fetch((nativeMode ? "./api/mobile/creative/jobs/" : "./api/creative/jobs/") + encodeURIComponent(jobId), {
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
    const nativeMode = isNativeMobileStudio();
    if (!token && !nativeMode) {
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
      const response = await fetch((isNativeMobileStudio() ? "./api/mobile/creative/analyze" : "./api/creative/analyze"), {
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
    const removedClipIds = new Set();
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
          case "remove_clip":
            if (typeof op.reason !== "string" || op.reason.trim().length < 12 || op.reason.length > 180) {
              throw new Error("A removed shot requires a specific evidence-based reason; nothing was applied.");
            }
            removedClipIds.add(clip.id);
            break;
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
      if (removedClipIds.size) {
        const survivingSelected = working.filter((clip) =>
          state.creativeSelectedIds.includes(clip.id) && !removedClipIds.has(clip.id)
        );
        if (!survivingSelected.length) {
          throw new Error("At least one selected shot must remain in the edit; nothing was applied.");
        }
        const retained = working.filter((clip) => !removedClipIds.has(clip.id));
        working.splice(0, working.length, ...retained);
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
    const autoAuthorized = state.autoFinishBusy;
    aiSetStatus(
      (autoAuthorized ? "Validated plan applied under your explicit per-run consent." : "Reviewed plan applied to the local editable timeline.") +
      " The editable project was queued for autosave. Unsupported effects were not added.",
      "success"
    );
    $("agent-state").textContent = (autoAuthorized
      ? "The validated proposal was automatically applied under your per-run consent."
      : "AI-directed changes were applied after your review.") +
      " The exported result still needs a visual review.";
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
    $("build-from-brief").addEventListener("click", async () => {
      state.autoRenderOnAssembly = true;
      $("auto-creative-consent").checked = true;
      try { await buildDraftFromBrief(); }
      finally { state.autoRenderOnAssembly = false; }
    });
    $("auto-creative-consent").addEventListener("change", () => {
      if ($("auto-creative-consent").checked && state.lastAutoDraftClipIds.length) {
        finishDraftAutomatically(state.lastAutoDraftClipIds);
      }
    });
    $("save-project").addEventListener("click", () => saveProject(true));
    $("save-brief").addEventListener("click", () => { state.project.brief = $("creative-brief").value; scheduleSave(); toast("Director's brief saved with project."); });
    $("open-ai-director").addEventListener("click", openAiDirector);
    $("close-ai-director").addEventListener("click", () => { $("ai-director-panel").hidden = true; });
    $("ai-consent").addEventListener("change", updateAiControls);
    $("ai-analyze").addEventListener("click", runAiDirection);
    $("ai-apply-plan").addEventListener("click", applyAiPlan);
    $("ai-cancel-plan").addEventListener("click", clearAiProposal);
    $("project-name").addEventListener("input", scheduleSave);
    $("creative-brief").addEventListener("input", () => {
      const link = $("google-images-reference");
      if (link) {
        const query = deriveAssetQuery($("creative-brief").value);
        link.href = "https://www.google.com/search?tbm=isch&q=" + encodeURIComponent(query || "science motion graphics");
      }
      scheduleSave();
    });
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
    $("preview-scale").addEventListener("change", updatePreviewResolution);
    bindInspector();
    bindGraphicLayers();
  }

  async function init() {
    try {
      state.db = await openDatabase();
      bindUi();
      await loadProject();
      const launchParams = new URLSearchParams(window.location.search);
      const nativeMode = isNativeMobileStudio();
      if (nativeMode) {
        const provider = $("online-asset-provider");
        if (provider) { provider.value = "commons"; provider.disabled = true; }
        const referenceButton = $("pinterest-reference");
        if (referenceButton) referenceButton.hidden = true;
      }
      let inboundBrief = "";
      if (nativeMode) {
        try { inboundBrief = String(window.OmnitrixNativeBridge.initialPrompt() || "").slice(0, 4000).trim(); }
        catch (_) {}
      }
      if (!inboundBrief) {
        try {
          inboundBrief = String(sessionStorage.getItem("omnitrix-creative-brief-pending") || "").slice(0, 4000).trim();
          sessionStorage.removeItem("omnitrix-creative-brief-pending");
        } catch (_) {}
      }
      if (inboundBrief) {
        $("creative-brief").value = inboundBrief;
        state.project.brief = inboundBrief;
        const googleImagesLink = $("google-images-reference");
        if (googleImagesLink) googleImagesLink.href = "https://www.google.com/search?tbm=isch&q=" + encodeURIComponent(deriveAssetQuery(inboundBrief) || "visual references");
        $("online-asset-query").value = deriveAssetQuery(inboundBrief);
        setPreviewResolutionFromBrief(inboundBrief);
        await saveProject(false);
        if (launchParams.get("autoDraft") === "1") {
          // The full prompt is passed in same-tab session storage, not in a query string.
          window.history.replaceState(null, "", window.location.pathname);
          state.autoRenderOnAssembly = true;
          // A direct prompt-to-video request authorizes the bounded creative
          // workflow. Model preview analysis only runs when a provider is
          // actually configured and reachable; status remains explicit.
          $("auto-creative-consent").checked = true;
          await buildDraftFromBrief();
          state.autoRenderOnAssembly = false;
        }
      }
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
