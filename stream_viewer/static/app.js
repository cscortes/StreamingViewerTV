(() => {
  const state = {
    source: null,
    catalogTotal: 0,
    tvgIdCount: 0,
    epgState: "idle",
    epgDetail: "Guide not loaded yet",
    filtersMeta: {},
    items: [],
    total: 0,
    offset: 0,
    limit: 80,
    selectedId: null,
    selectedMetaBits: [],
    hls: null,
    loading: false,
    theater: false,
    sidebarWidth: 340,
    playback: "idle",
    bufferPercent: null,
    streamErrors: 0,
    statusMessage: "Ready",
    statusIsError: false,
  };

  const els = {
    layout: document.getElementById("layout"),
    splitter: document.getElementById("splitter"),
    sidebar: document.getElementById("sidebar"),
    searchInput: document.getElementById("searchInput"),
    resetFiltersBtn: document.getElementById("resetFiltersBtn"),
    filterForm: document.getElementById("filterForm"),
    streamList: document.getElementById("streamList"),
    streamListWrap: document.getElementById("streamListWrap"),
    listSentinel: document.getElementById("listSentinel"),
    video: document.getElementById("video"),
    playerEmpty: document.getElementById("playerEmpty"),
    playerFrame: document.getElementById("playerFrame"),
    nowPlaying: document.getElementById("nowPlaying"),
    nowLogo: document.getElementById("nowLogo"),
    nowTitle: document.getElementById("nowTitle"),
    nowProgramme: document.getElementById("nowProgramme"),
    nowDetails: document.getElementById("nowDetails"),
    nowStars: document.getElementById("nowStars"),
    theaterBtn: document.getElementById("theaterBtn"),
    fullscreenBtn: document.getElementById("fullscreenBtn"),
    openRaw: document.getElementById("openRaw"),
    playerStatus: document.getElementById("playerStatus"),
    statusCatalog: document.getElementById("statusCatalog"),
    statusMatches: document.getElementById("statusMatches"),
    statusListed: document.getElementById("statusListed"),
    statusTvg: document.getElementById("statusTvg"),
    statusGuideDot: document.getElementById("statusGuideDot"),
    statusGuide: document.getElementById("statusGuide"),
    statusDot: document.getElementById("statusDot"),
    statusPlayback: document.getElementById("statusPlayback"),
    statusErrors: document.getElementById("statusErrors"),
    statusMessage: document.getElementById("statusMessage"),
  };

  let searchTimer = null;

  const PREFS_COOKIE = "svtv_filters";
  const PREFS_MAX_AGE = 60 * 60 * 24 * 180; // 180 days

  function getCookie(name) {
    const prefix = `${name}=`;
    for (const part of document.cookie.split(";")) {
      const piece = part.trim();
      if (piece.startsWith(prefix)) {
        return piece.slice(prefix.length);
      }
    }
    return "";
  }

  function setCookie(name, value, maxAge) {
    document.cookie = `${name}=${value}; path=/; max-age=${maxAge}; SameSite=Lax`;
  }

  function clearCookie(name) {
    document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
  }

  function readPrefs() {
    const raw = getCookie(PREFS_COOKIE);
    if (!raw) return {};
    try {
      const parsed = JSON.parse(decodeURIComponent(raw));
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function writePrefs(prefs) {
    const payload = encodeURIComponent(JSON.stringify(prefs));
    setCookie(PREFS_COOKIE, payload, PREFS_MAX_AGE);
  }

  const SIDEBAR_MIN = 220;
  const SIDEBAR_MAX = 720;
  const SIDEBAR_DEFAULT = 340;

  function clampSidebarWidth(width) {
    const layoutWidth = els.layout?.clientWidth || window.innerWidth;
    const maxForLayout = Math.max(SIDEBAR_MIN, layoutWidth - 320);
    return Math.round(
      Math.min(SIDEBAR_MAX, maxForLayout, Math.max(SIDEBAR_MIN, width))
    );
  }

  function setSidebarWidth(width, { persist = false } = {}) {
    const next = clampSidebarWidth(width);
    state.sidebarWidth = next;
    if (els.layout) {
      els.layout.style.setProperty("--sidebar-width", `${next}px`);
    }
    if (els.splitter) {
      els.splitter.setAttribute("aria-valuenow", String(next));
    }
    if (persist) savePrefs();
  }

  function collectPrefs() {
    const prefs = {};
    const formData = new FormData(els.filterForm);
    for (const [key, value] of formData.entries()) {
      if (value) prefs[key] = value;
    }
    const q = els.searchInput.value.trim();
    if (q) prefs.q = q;
    if (state.source) prefs.source = state.source;
    if (state.sidebarWidth && state.sidebarWidth !== SIDEBAR_DEFAULT) {
      prefs.sidebarWidth = state.sidebarWidth;
    }
    return prefs;
  }

  function savePrefs() {
    const prefs = collectPrefs();
    if (Object.keys(prefs).length) {
      writePrefs(prefs);
    } else {
      clearCookie(PREFS_COOKIE);
    }
  }

  function applyPrefs(prefs) {
    if (!prefs || typeof prefs !== "object") return;
    if (typeof prefs.q === "string") {
      els.searchInput.value = prefs.q;
    }
    for (const select of els.filterForm.querySelectorAll("select[name]")) {
      const saved = prefs[select.name];
      if (typeof saved !== "string" || !saved) continue;
      const exists = Array.from(select.options).some((option) => option.value === saved);
      if (exists) select.value = saved;
    }
    if (typeof prefs.sidebarWidth === "number" || typeof prefs.sidebarWidth === "string") {
      const width = Number(prefs.sidebarWidth);
      if (Number.isFinite(width)) setSidebarWidth(width);
    }
  }

  function setupSidebarResize() {
    const splitter = els.splitter;
    if (!splitter || !els.layout) return;

    splitter.setAttribute("aria-valuemin", String(SIDEBAR_MIN));
    splitter.setAttribute("aria-valuemax", String(SIDEBAR_MAX));
    setSidebarWidth(state.sidebarWidth || SIDEBAR_DEFAULT);

    let dragging = false;

    const onPointerMove = (event) => {
      if (!dragging) return;
      const bounds = els.layout.getBoundingClientRect();
      setSidebarWidth(event.clientX - bounds.left);
    };

    const stopDrag = () => {
      if (!dragging) return;
      dragging = false;
      els.layout.classList.remove("is-resizing");
      document.body.style.cursor = "";
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopDrag);
      savePrefs();
    };

    splitter.addEventListener("pointerdown", (event) => {
      if (state.theater || window.matchMedia("(max-width: 960px)").matches) return;
      event.preventDefault();
      dragging = true;
      els.layout.classList.add("is-resizing");
      document.body.style.cursor = "col-resize";
      splitter.setPointerCapture?.(event.pointerId);
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", stopDrag);
    });

    splitter.addEventListener("dblclick", () => {
      setSidebarWidth(SIDEBAR_DEFAULT, { persist: true });
    });

    splitter.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setSidebarWidth((state.sidebarWidth || SIDEBAR_DEFAULT) - 24, { persist: true });
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setSidebarWidth((state.sidebarWidth || SIDEBAR_DEFAULT) + 24, { persist: true });
      } else if (event.key === "Home") {
        event.preventDefault();
        setSidebarWidth(SIDEBAR_MIN, { persist: true });
      } else if (event.key === "End") {
        event.preventDefault();
        setSidebarWidth(SIDEBAR_MAX, { persist: true });
      }
    });

    window.addEventListener("resize", () => {
      if (state.sidebarWidth) setSidebarWidth(state.sidebarWidth);
    });
  }

  const STREAM_QUALITY_STARS = {
    poor: 1,
    okay: 2,
    excellent: 3,
  };

  function streamStarCount(quality) {
    return STREAM_QUALITY_STARS[(quality || "").trim().toLowerCase()] || 0;
  }

  function starGlyph() {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 2.6l2.7 6.1 6.6.6-5 4.4 1.5 6.4L12 16.8 6.2 20.1 7.7 13.7 2.7 9.3l6.6-.6L12 2.6z"/></svg>`;
  }

  function renderStars(count, { size = "sm" } = {}) {
    const wrap = document.createElement("span");
    wrap.className = `quality-stars quality-stars--${size}`;
    if (!count) {
      wrap.hidden = true;
      return wrap;
    }
    wrap.setAttribute("aria-label", `${count} star${count === 1 ? "" : "s"} stream quality`);
    wrap.title =
      count === 3 ? "Excellent" : count === 2 ? "Okay" : "Poor";
    wrap.innerHTML = Array.from({ length: count }, () => starGlyph()).join("");
    return wrap;
  }

  function fillStars(el, quality) {
    const count = streamStarCount(quality);
    el.innerHTML = "";
    if (!count) {
      el.hidden = true;
      el.removeAttribute("aria-label");
      el.removeAttribute("title");
      return;
    }
    el.hidden = false;
    el.className = "quality-stars quality-stars--md";
    el.setAttribute("aria-label", `${count} star${count === 1 ? "" : "s"} stream quality`);
    el.title = count === 3 ? "Excellent" : count === 2 ? "Okay" : "Poor";
    el.innerHTML = Array.from({ length: count }, () => starGlyph()).join("");
  }

  function qualityOptionLabel(value, fallback) {
    const count = streamStarCount(value);
    if (!count) return fallback || value;
    return `${"★".repeat(count)}${"☆".repeat(3 - count)} ${value}+`;
  }

  function selectedFilters() {
    const params = new URLSearchParams();
    const formData = new FormData(els.filterForm);
    for (const [key, value] of formData.entries()) {
      if (value) params.append(key, value);
    }
    const q = els.searchInput.value.trim();
    if (q) params.set("q", q);
    if (state.source) params.set("source", state.source);
    return params;
  }

  const PLAYBACK_LABELS = {
    idle: "Idle",
    connecting: "Connecting",
    buffering: "Buffering",
    playing: "Playing",
    paused: "Paused",
    error: "Error",
  };

  // Live HLS rarely has a finite duration; treat this many seconds ahead as ~100%.
  const BUFFER_TARGET_SEC = 30;

  function getBufferStats(video) {
    if (!video) return { ahead: 0, percent: null };
    const ranges = video.buffered;
    const t = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    let ahead = 0;
    for (let i = 0; i < ranges.length; i += 1) {
      const start = ranges.start(i);
      const end = ranges.end(i);
      if (start <= t && end >= t) {
        ahead = end - t;
        break;
      }
      if (start > t) {
        ahead = Math.max(0, end - start);
        break;
      }
    }

    const duration = video.duration;
    let percent = null;
    if (Number.isFinite(duration) && duration > 0) {
      let covered = 0;
      for (let i = 0; i < ranges.length; i += 1) {
        covered += ranges.end(i) - ranges.start(i);
      }
      percent = Math.max(0, Math.min(100, Math.round((covered / duration) * 100)));
    } else if (ranges.length > 0 || ahead > 0) {
      percent = Math.max(0, Math.min(100, Math.round((ahead / BUFFER_TARGET_SEC) * 100)));
    }
    return { ahead, percent };
  }

  function bufferingLabel(streamName) {
    const { percent, ahead } = getBufferStats(els.video);
    const who = streamName || els.nowTitle?.textContent || "stream";
    if (percent != null) {
      return `Buffering ${who}… ${percent}%`;
    }
    if (ahead > 0) {
      return `Buffering ${who}… ${ahead.toFixed(1)}s`;
    }
    return `Buffering ${who}…`;
  }

  function refreshBufferProgress() {
    if (state.playback !== "buffering" && state.playback !== "connecting") return;
    const { percent } = getBufferStats(els.video);
    state.bufferPercent = percent;
    const msg = bufferingLabel();
    if (state.statusMessage !== msg) {
      state.statusMessage = msg;
      state.statusIsError = false;
    }
    updateStatusBar();
  }

  const GUIDE_LABELS = {
    idle: "Idle",
    loading: "Loading",
    loaded: "Loaded",
    error: "Error",
  };

  function applyEpgStatus(epg) {
    if (!epg || typeof epg !== "object") return;
    state.epgState = epg.state || "idle";
    state.epgDetail = epg.detail || GUIDE_LABELS[state.epgState] || "Guide";
    updateStatusBar();
  }

  function updateStatusBar() {
    if (els.statusCatalog) {
      els.statusCatalog.textContent = Number(state.catalogTotal || 0).toLocaleString();
    }
    if (els.statusMatches) {
      els.statusMatches.textContent = Number(state.total || 0).toLocaleString();
    }
    if (els.statusListed) {
      els.statusListed.textContent = Number(state.items.length || 0).toLocaleString();
    }
    if (els.statusTvg) {
      const have = Number(state.tvgIdCount || 0);
      const total = Number(state.catalogTotal || 0);
      els.statusTvg.textContent = total
        ? `${have.toLocaleString()}/${total.toLocaleString()}`
        : String(have);
      els.statusTvg.title = `${have} streams have a tvg_id (EPG channel id)`;
    }
    if (els.statusGuide) {
      const label = GUIDE_LABELS[state.epgState] || state.epgState;
      els.statusGuide.textContent = label;
      els.statusGuide.title = state.epgDetail || label;
    }
    if (els.statusGuideDot) {
      els.statusGuideDot.dataset.state = state.epgState || "idle";
      els.statusGuideDot.title = state.epgDetail || "";
    }
    if (els.statusErrors) {
      els.statusErrors.textContent = String(state.streamErrors || 0);
    }
    if (els.statusPlayback) {
      let label = PLAYBACK_LABELS[state.playback] || state.playback;
      if (
        (state.playback === "buffering" || state.playback === "connecting") &&
        state.bufferPercent != null
      ) {
        label = `${PLAYBACK_LABELS.buffering} ${state.bufferPercent}%`;
      }
      els.statusPlayback.textContent = label;
    }
    if (els.statusDot) {
      els.statusDot.dataset.state = state.playback || "idle";
    }
    if (els.statusMessage) {
      els.statusMessage.textContent = state.statusMessage || "Ready";
      els.statusMessage.title = state.statusMessage || "Ready";
      els.statusMessage.classList.toggle("is-error", Boolean(state.statusIsError));
    }
  }

  function setPlayback(playback, message, isError = false) {
    state.playback = playback;
    if (playback !== "buffering" && playback !== "connecting") {
      state.bufferPercent = null;
    } else {
      const { percent } = getBufferStats(els.video);
      state.bufferPercent = percent;
    }
    if (message != null) {
      state.statusMessage = message;
      state.statusIsError = Boolean(isError);
    }
    updateStatusBar();
  }

  function setStatus(message, isError = true) {
    if (!message) {
      els.playerStatus.hidden = true;
      els.playerStatus.textContent = "";
      if (state.playback === "error") {
        setPlayback("idle", "Ready", false);
      } else {
        state.statusIsError = false;
        if (!state.statusMessage || state.statusMessage.startsWith("Playback error")) {
          state.statusMessage = PLAYBACK_LABELS[state.playback] || "Ready";
        }
        updateStatusBar();
      }
      return;
    }
    els.playerStatus.hidden = false;
    els.playerStatus.textContent = message;
    els.playerStatus.style.color = isError ? "var(--danger)" : "var(--signal)";
    state.statusMessage = message;
    state.statusIsError = Boolean(isError);
    if (isError) {
      state.playback = "error";
    }
    updateStatusBar();
  }

  function destroyPlayer() {
    if (state.hls) {
      state.hls.destroy();
      state.hls = null;
    }
    els.video.removeAttribute("src");
    els.video.load();
  }

  function metaBits(stream) {
    return [
      stream.group_title,
      stream.country_name,
      stream.language_name,
      stream.video_quality,
    ].filter(Boolean);
  }

  function formatNowDetails(bits) {
    return (bits && bits.length ? bits.join(" · ") : "") || "Live stream";
  }

  function setViewerProgramme(info, { pending = false } = {}) {
    const node = els.nowProgramme;
    if (!node) return;
    node.classList.remove("is-pending", "is-empty", "has-title");
    if (pending) {
      node.textContent = "Fetching…";
      node.dataset.state = "pending";
      node.classList.add("is-pending");
      node.title = "Loading programme guide…";
      return;
    }
    if (info && info.title) {
      node.textContent = info.title;
      node.dataset.state = "title";
      node.classList.add("has-title");
      node.title = info.title;
      return;
    }
    node.textContent = "No data";
    node.dataset.state = "empty";
    node.classList.add("is-empty");
    node.title = "No programme data for this channel";
  }

  function setStreamNowLine(node, info, { pending = false } = {}) {
    if (!node) return;
    node.hidden = false;
    node.classList.remove("is-pending", "is-empty", "has-title");
    if (pending) {
      node.textContent = "Now: Fetching…";
      node.classList.add("is-pending");
      node.title = "Loading programme guide…";
      return;
    }
    if (info && info.title) {
      node.textContent = `Now: ${info.title}`;
      node.classList.add("has-title");
      node.title = info.title;
      return;
    }
    node.textContent = "Now: No data";
    node.classList.add("is-empty");
    node.title = "No programme data for this channel";
  }

  function playStream(stream) {
    destroyPlayer();
    setStatus("");
    els.playerEmpty.hidden = true;
    els.nowPlaying.hidden = false;
    state.selectedId = stream.id;
    setPlayback("connecting", `Connecting to ${stream.name}…`);

    els.nowTitle.textContent = stream.name;
    const bits = metaBits(stream);
    state.selectedMetaBits = bits;
    const hasNow = Boolean(stream.now_playing && stream.now_playing.title);
    setViewerProgramme(hasNow ? stream.now_playing : null, { pending: !hasNow });
    els.nowDetails.textContent = formatNowDetails(bits);
    // If detail payload had no EPG yet, resolve in background.
    if (!hasNow) {
      refreshNowPlaying([stream.id]);
    }
    fillStars(els.nowStars, stream.stream_quality);
    els.openRaw.href = stream.url;

    if (stream.tvg_logo) {
      els.nowLogo.hidden = false;
      els.nowLogo.src = stream.tvg_logo;
      els.nowLogo.alt = stream.name;
    } else {
      els.nowLogo.hidden = true;
      els.nowLogo.removeAttribute("src");
    }

    highlightActive();

    const playUrl = stream.play_url;
    if (window.Hls && Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        maxBufferLength: 30,
        maxMaxBufferLength: 60,
        liveSyncDurationCount: 3,
        liveMaxLatencyDurationCount: 12,
        fragLoadingTimeOut: 120000,
        manifestLoadingTimeOut: 20000,
      });
      state.hls = hls;
      hls.loadSource(playUrl);
      hls.attachMedia(els.video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setPlayback("buffering", bufferingLabel(stream.name));
        els.video.play().catch(() => setStatus("Press play to start the stream.", false));
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) {
          setPlayback(
            state.playback === "playing" ? "buffering" : state.playback,
            state.playback === "playing" || state.playback === "buffering"
              ? bufferingLabel(stream.name)
              : `Stream warning: ${data.details}`,
            false
          );
          return;
        }
        state.streamErrors += 1;
        setStatus(`Playback error: ${data.type} / ${data.details}`);
      });
      hls.on(Hls.Events.FRAG_BUFFERED, () => {
        refreshBufferProgress();
        if (!els.video.paused && state.playback !== "error") {
          setPlayback("playing", `Playing ${stream.name}`);
        }
      });
      hls.on(Hls.Events.BUFFER_APPENDED, () => {
        refreshBufferProgress();
      });
    } else if (els.video.canPlayType("application/vnd.apple.mpegurl")) {
      els.video.src = playUrl;
      setPlayback("buffering", bufferingLabel(stream.name));
      els.video.play().catch(() => setStatus("Press play to start the stream.", false));
    } else {
      state.streamErrors += 1;
      setStatus("This browser cannot play HLS streams.");
    }
  }

  async function refreshNowPlaying(streamIds) {
    const ids = (streamIds || []).filter((id) => id != null);
    if (!ids.length) return;
    for (const id of ids) {
      const node = els.streamList.querySelector(`.stream-now[data-stream-id="${id}"]`);
      setStreamNowLine(node, null, { pending: true });
    }
    if (state.selectedId != null && ids.map(String).includes(String(state.selectedId))) {
      setViewerProgramme(null, { pending: true });
      els.nowDetails.textContent = formatNowDetails(state.selectedMetaBits);
    }
    const params = new URLSearchParams();
    params.set("stream_ids", ids.join(","));
    if (state.source) params.set("source", state.source);
    if (state.epgState === "idle" || state.epgState === "error") {
      applyEpgStatus({ state: "loading", detail: "Loading TV guide…" });
    }
    try {
      const response = await fetch(`/api/epg/now?${params}`);
      if (!response.ok) {
        applyEpgStatus({ state: "error", detail: "Guide lookup failed" });
        for (const id of ids) {
          const node = els.streamList.querySelector(`.stream-now[data-stream-id="${id}"]`);
          setStreamNowLine(node, null, { pending: false });
        }
        if (state.selectedId != null && ids.map(String).includes(String(state.selectedId))) {
          setViewerProgramme(null, { pending: false });
        }
        return;
      }
      const data = await response.json();
      if (data.epg) applyEpgStatus(data.epg);
      const items = data.items || {};
      for (const id of ids) {
        const key = String(id);
        const info = Object.prototype.hasOwnProperty.call(items, key) ? items[key] : null;
        const node = els.streamList.querySelector(`.stream-now[data-stream-id="${key}"]`);
        setStreamNowLine(node, info, { pending: false });
      }
      if (state.selectedId != null && ids.map(String).includes(String(state.selectedId))) {
        const info = items[String(state.selectedId)];
        setViewerProgramme(info, { pending: false });
        els.nowDetails.textContent = formatNowDetails(state.selectedMetaBits);
      }
    } catch (error) {
      console.warn("EPG lookup failed", error);
      applyEpgStatus({ state: "error", detail: "Guide lookup failed" });
      for (const id of ids) {
        const node = els.streamList.querySelector(`.stream-now[data-stream-id="${id}"]`);
        setStreamNowLine(node, null, { pending: false });
      }
      if (state.selectedId != null && ids.map(String).includes(String(state.selectedId))) {
        setViewerProgramme(null, { pending: false });
      }
    }
  }

  async function selectStream(id) {
    const params = new URLSearchParams();
    if (state.source) params.set("source", state.source);
    setPlayback("connecting", "Loading stream details…");
    const response = await fetch(`/api/streams/${id}?${params}`);
    if (!response.ok) {
      state.streamErrors += 1;
      setStatus("Could not load stream details.");
      return;
    }
    const stream = await response.json();
    playStream(stream);
  }

  function highlightActive() {
    for (const button of els.streamList.querySelectorAll(".stream-item")) {
      button.classList.toggle("active", Number(button.dataset.id) === state.selectedId);
    }
  }

  function renderStreams(items, append) {
    if (!append) els.streamList.innerHTML = "";
    const fragment = document.createDocumentFragment();

    for (const item of items) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "stream-item";
      button.dataset.id = String(item.id);

      if (item.tvg_logo) {
        const img = document.createElement("img");
        img.src = item.tvg_logo;
        img.alt = "";
        img.loading = "lazy";
        img.onerror = () => {
          img.replaceWith(fallbackLogo(item.name));
        };
        button.appendChild(img);
      } else {
        button.appendChild(fallbackLogo(item.name));
      }

      const meta = document.createElement("div");
      meta.className = "stream-meta";

      const titleRow = document.createElement("div");
      titleRow.className = "stream-title-row";
      const title = document.createElement("strong");
      title.textContent = item.name;
      titleRow.append(title, renderStars(streamStarCount(item.stream_quality)));

      const subtitle = document.createElement("span");
      subtitle.className = "stream-subtitle";
      subtitle.textContent = [item.group_title, item.country_name, item.video_quality]
        .filter(Boolean)
        .join(" · ");

      const nowLine = document.createElement("span");
      nowLine.className = "stream-now is-pending";
      nowLine.hidden = false;
      nowLine.dataset.streamId = String(item.id);
      nowLine.textContent = "Now: Fetching…";
      nowLine.title = "Loading programme guide…";

      meta.append(titleRow, subtitle, nowLine);
      button.appendChild(meta);

      button.addEventListener("click", () => selectStream(item.id));
      li.appendChild(button);
      fragment.appendChild(li);
    }

    els.streamList.appendChild(fragment);
    highlightActive();
  }

  function fallbackLogo(name) {
    const div = document.createElement("div");
    div.className = "logo-fallback";
    div.textContent = (name || "?").trim().charAt(0).toUpperCase();
    return div;
  }

  function renderFilters(filters) {
    els.filterForm.innerHTML = "";
    const keys = Object.keys(filters);
    if (!keys.length) return;

    for (const [field, meta] of Object.entries(filters)) {
      if (!meta.options || !meta.options.length) continue;
      const group = document.createElement("div");
      group.className = "filter-group";

      const label = document.createElement("label");
      label.htmlFor = `filter-${field}`;
      label.textContent = meta.hint ? `${meta.label} (${meta.hint})` : meta.label;

      const select = document.createElement("select");
      select.id = `filter-${field}`;
      select.name = field;

      const all = document.createElement("option");
      all.value = "";
      all.textContent = `Any ${meta.label.toLowerCase()}`;
      select.appendChild(all);

      for (const option of meta.options) {
        const opt = document.createElement("option");
        opt.value = option.value;
        const display =
          field === "stream_quality"
            ? qualityOptionLabel(option.value, option.label || option.value)
            : option.label || option.value;
        opt.textContent = `${display} (${option.count})`;
        select.appendChild(opt);
      }

      group.append(label, select);
      els.filterForm.appendChild(group);
    }
  }

  function resetFilters() {
    els.searchInput.value = "";
    els.filterForm.reset();
    clearCookie(PREFS_COOKIE);
    // Keep CSV source and sidebar width after reset.
    const kept = {};
    if (state.source) kept.source = state.source;
    if (state.sidebarWidth && state.sidebarWidth !== SIDEBAR_DEFAULT) {
      kept.sidebarWidth = state.sidebarWidth;
    }
    if (Object.keys(kept).length) writePrefs(kept);
    loadStreams({ reset: true });
  }

  async function loadMeta(source) {
    const params = new URLSearchParams();
    if (source) params.set("source", source);
    const response = await fetch(`/api/meta?${params}`);
    if (!response.ok) throw new Error("Failed to load metadata");
    const data = await response.json();
    state.source = data.source;
    state.catalogTotal = data.total;
    state.tvgIdCount = Number(data.tvg_id_count || 0);
    state.filtersMeta = data.filters || {};
    if (data.epg) applyEpgStatus(data.epg);
    // Drop stale cookie sources (e.g. streams_probed.csv after switching to viewer.db).
    if (source && data.source && source !== data.source) {
      savePrefs();
    }
    renderFilters(state.filtersMeta);
    updateStatusBar();
  }

  async function loadStreams({ reset = false } = {}) {
    if (state.loading) return;
    if (!reset && state.items.length >= state.total && state.total > 0) return;

    state.loading = true;
    if (reset) {
      state.offset = 0;
      state.items = [];
      state.total = 0;
      // Filter/search/reset reloads the catalog page — jump back to the top of the list.
      if (els.streamListWrap) {
        els.streamListWrap.scrollTop = 0;
      }
    }

    const params = selectedFilters();
    params.set("offset", String(state.offset));
    params.set("limit", String(state.limit));

    if (reset) {
      state.statusMessage = "Loading streams…";
      state.statusIsError = false;
      updateStatusBar();
    }
    try {
      const response = await fetch(`/api/streams?${params}`);
      if (!response.ok) throw new Error("Failed to load streams");
      const data = await response.json();
      state.total = data.total;
      state.items = reset ? data.items : state.items.concat(data.items);
      state.offset = state.items.length;
      renderStreams(data.items, !reset);
      if (els.listSentinel) {
        els.listSentinel.hidden = state.items.length >= data.total;
      }
      if (state.playback === "idle") {
        state.statusMessage = `${data.total.toLocaleString()} match${data.total === 1 ? "" : "es"} · ${state.items.length.toLocaleString()} listed`;
        state.statusIsError = false;
      }
      updateStatusBar();
      refreshNowPlaying(data.items.map((item) => item.id));
    } catch (error) {
      state.statusMessage = "Could not load streams";
      state.statusIsError = true;
      updateStatusBar();
      console.error(error);
    } finally {
      state.loading = false;
      updateStatusBar();
      // If the list is still short enough that the sentinel stays visible, keep loading.
      maybeLoadMore();
    }
  }

  function maybeLoadMore() {
    if (state.loading) return;
    if (!els.listSentinel || els.listSentinel.hidden) return;
    if (state.items.length >= state.total && state.total > 0) return;
    const wrap = els.streamListWrap;
    if (!wrap) return;
    const sentinelTop = els.listSentinel.getBoundingClientRect().top;
    const wrapBottom = wrap.getBoundingClientRect().bottom;
    if (sentinelTop <= wrapBottom + 80) {
      loadStreams({ reset: false });
    }
  }

  function setupInfiniteScroll() {
    if (!els.listSentinel || !els.streamListWrap) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadStreams({ reset: false });
        }
      },
      {
        root: els.streamListWrap,
        rootMargin: "120px 0px",
        threshold: 0,
      }
    );
    observer.observe(els.listSentinel);
  }

  function toggleTheater() {
    state.theater = !state.theater;
    els.layout.classList.toggle("theater", state.theater);
    document.body.classList.toggle("theater-mode", state.theater);
    els.theaterBtn.textContent = state.theater ? "Exit theater" : "Theater";
  }

  async function toggleFullscreen() {
    const target = els.playerFrame;
    if (!document.fullscreenElement) {
      await target.requestFullscreen?.();
    } else {
      await document.exitFullscreen?.();
    }
  }

  document.addEventListener("fullscreenchange", () => {
    document.body.classList.toggle("is-fullscreen", Boolean(document.fullscreenElement));
    els.fullscreenBtn.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
  });

  els.searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      savePrefs();
      loadStreams({ reset: true });
    }, 220);
  });

  els.filterForm.addEventListener("change", () => {
    savePrefs();
    loadStreams({ reset: true });
  });
  els.resetFiltersBtn?.addEventListener("click", resetFilters);
  els.theaterBtn.addEventListener("click", toggleTheater);
  els.fullscreenBtn.addEventListener("click", toggleFullscreen);

  els.video.addEventListener("waiting", () => {
    if (state.selectedId == null || state.playback === "error") return;
    setPlayback("buffering", bufferingLabel());
  });
  els.video.addEventListener("stalled", () => {
    if (state.selectedId == null || state.playback === "error") return;
    setPlayback("buffering", bufferingLabel());
  });
  els.video.addEventListener("progress", () => {
    refreshBufferProgress();
  });
  els.video.addEventListener("playing", () => {
    if (state.playback === "error") return;
    const name = els.nowTitle?.textContent || "stream";
    const programme = els.nowProgramme?.classList.contains("has-title")
      ? els.nowProgramme.textContent
      : "";
    setPlayback("playing", programme ? `Playing ${name} — ${programme}` : `Playing ${name}`);
  });
  els.video.addEventListener("pause", () => {
    if (state.playback === "error" || !state.selectedId) return;
    if (els.video.ended) return;
    setPlayback("paused", "Paused");
  });
  els.video.addEventListener("error", () => {
    state.streamErrors += 1;
    setStatus("Video element error while playing stream.");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "t" && !event.metaKey && !event.ctrlKey && event.target.tagName !== "INPUT") {
      toggleTheater();
    }
    if (event.key === "f" && !event.metaKey && !event.ctrlKey && event.target.tagName !== "INPUT") {
      toggleFullscreen();
    }
  });

  (async () => {
    try {
      setupInfiniteScroll();
      setupSidebarResize();
      updateStatusBar();
      const prefs = readPrefs();
      await loadMeta(prefs.source || null);
      applyPrefs(prefs);
      await loadStreams({ reset: true });
    } catch (error) {
      state.statusMessage = "No catalog data available";
      state.statusIsError = true;
      updateStatusBar();
      console.error(error);
    }
  })();
})();
