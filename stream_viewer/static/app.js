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
    selectedFavoriteKey: null,
    selectedMetaBits: [],
    hls: null,
    loading: false,
    theater: false,
    watchFirst: false,
    sidebarWidth: 340,
    playback: "idle",
    bufferPercent: null,
    streamErrors: 0,
    statusMessage: "Ready",
    statusIsError: false,
    favorites: new Set(),
    favoritesOnly: false,
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
    nowQuality: document.getElementById("nowQuality"),
    nowFavorite: document.getElementById("nowFavorite"),
    nowDetails: document.getElementById("nowDetails"),
    nowStars: document.getElementById("nowStars"),
    fullscreenBtn: document.getElementById("fullscreenBtn"),
    filtersToggleBtn: document.getElementById("filtersToggleBtn"),
    favoritesToggleBtn: document.getElementById("favoritesToggleBtn"),
    favoritesHint: document.getElementById("favoritesHint"),
    favoritesHintDismiss: document.getElementById("favoritesHintDismiss"),
    browseToggleBtn: document.getElementById("browseToggleBtn"),
    showSidebarBtn: document.getElementById("showSidebarBtn"),
    resetFiltersBtnCompact: document.getElementById("resetFiltersBtnCompact"),
    compactActions: document.getElementById("compactActions"),
    phoneMoreWrap: document.getElementById("phoneMoreWrap"),
    phoneMoreBtn: document.getElementById("phoneMoreBtn"),
    phoneMorePanel: document.getElementById("phoneMorePanel"),
    filtersBadge: document.getElementById("filtersBadge"),
    sheetBackdrop: document.getElementById("sheetBackdrop"),
    filterSheetPanel: document.getElementById("filterSheetPanel"),
    filterSheetBody: document.getElementById("filterSheetBody"),
    filterSheetDoneBtn: document.getElementById("filterSheetDoneBtn"),
    filterBar: document.getElementById("filterBar"),
    statusDetailsBtn: document.getElementById("statusDetailsBtn"),
    statusDetails: document.getElementById("statusDetails"),
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
    statusVersionItem: document.getElementById("statusVersionItem"),
    statusVersionValue: document.getElementById("statusVersionValue"),
    updateAvailable: document.getElementById("updateAvailable"),
    updateAvailableLink: document.getElementById("updateAvailableLink"),
    updateAvailableDismiss: document.getElementById("updateAvailableDismiss"),
    shareBtn: document.getElementById("shareBtn"),
    shareDialog: document.getElementById("shareDialog"),
    shareDialogCloseBtn: document.getElementById("shareDialogCloseBtn"),
  };

  /* Narrow / touch: overlay channel drawer. Slim chrome is always on. */
  const NARROW_MQ = window.matchMedia(
    "(max-width: 1100px), ((pointer: coarse) and (max-width: 1400px))"
  );
  /* Phone: portrait, or landscape handset (short coarse viewport). */
  const PHONE_MQ = window.matchMedia(
    "(max-width: 600px), ((pointer: coarse) and (max-height: 500px) and (max-width: 960px))"
  );

  let searchTimer = null;

  const PREFS_COOKIE = "svtv_filters";
  const PREFS_MAX_AGE = 60 * 60 * 24 * 180; // 180 days
  const FAVORITES_KEY = "svtv_favorites_v2";
  const FAVORITES_LEGACY_KEY = "svtv_favorites";
  const FAVORITES_HINT_KEY = "svtv_favorites_hint_seen";
  const UPDATE_INFO_HINT_KEY = "svtv_update_info_seen";
  const IS_ANDROID = document.body?.dataset?.platform === "android";
  const MAX_FAVORITES = 100;
  const FAVORITE_KEY_RE = /^[0-9a-f]{64}$/;
  const FAVORITES_TOGGLE_TITLE =
    "Favorites are saved in this browser only and may be cleared by the OS or browser.";

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

  function clearLayoutSidebarWidthVar() {
    if (els.layout) els.layout.style.removeProperty("--sidebar-width");
  }

  function setSidebarWidth(width, { persist = false } = {}) {
    const next = clampSidebarWidth(width);
    state.sidebarWidth = next;
    // Narrow/phone drawers use CSS width (86–100vw). An inline --sidebar-width from
    // desktop resize prefs would otherwise clamp the overlay to ~220px on phones.
    if (isNarrow()) {
      clearLayoutSidebarWidthVar();
    } else if (els.layout) {
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
    if (state.favoritesOnly) prefs.favoritesOnly = true;
    const existing = readPrefs();
    if (
      typeof existing.dismissedUpdateVersion === "string" &&
      existing.dismissedUpdateVersion
    ) {
      prefs.dismissedUpdateVersion = existing.dismissedUpdateVersion;
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
    state.favoritesOnly = Boolean(prefs.favoritesOnly);
    syncFavoritesToggle();
  }

  function loadFavorites() {
    try {
      localStorage.removeItem(FAVORITES_LEGACY_KEY);
    } catch {
      // ignore
    }
    try {
      const raw = localStorage.getItem(FAVORITES_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return new Set();
      const keys = parsed
        .map((value) => String(value || "").trim().toLowerCase())
        .filter((key) => FAVORITE_KEY_RE.test(key))
        .slice(0, MAX_FAVORITES);
      return new Set(keys);
    } catch {
      return new Set();
    }
  }

  function saveFavorites() {
    try {
      localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites]));
    } catch {
      // Private mode / quota — favorites stay in memory for this session.
    }
  }

  function isFavorite(key) {
    return Boolean(key) && state.favorites.has(String(key));
  }

  function favoritesHintSeen() {
    try {
      return localStorage.getItem(FAVORITES_HINT_KEY) === "1";
    } catch {
      return false;
    }
  }

  function markFavoritesHintSeen() {
    try {
      localStorage.setItem(FAVORITES_HINT_KEY, "1");
    } catch {
      // ignore
    }
  }

  function showFavoritesHint() {
    if (!els.favoritesHint || favoritesHintSeen()) return;
    els.favoritesHint.hidden = false;
  }

  function hideFavoritesHint({ persist = false } = {}) {
    if (els.favoritesHint) els.favoritesHint.hidden = true;
    if (persist) markFavoritesHintSeen();
  }

  function syncFavoritesToggle() {
    const btn = els.favoritesToggleBtn;
    if (!btn) return;
    btn.setAttribute("aria-pressed", state.favoritesOnly ? "true" : "false");
    btn.classList.toggle("is-pressed", state.favoritesOnly);
    btn.title = FAVORITES_TOGGLE_TITLE;
  }

  function syncFavoriteButton(button, key) {
    if (!button) return;
    const on = isFavorite(key);
    button.classList.toggle("is-favorite", on);
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.setAttribute("aria-label", on ? "Remove from favorites" : "Add to favorites");
    button.title = on ? "Remove from favorites" : "Add to favorites";
    button.innerHTML = favoriteGlyph(on);
  }

  function favoriteGlyph(filled) {
    // Outline vs filled heart — distinct from quality stars.
    if (filled) {
      return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.1 21.35l-1.1-1C5.14 15.24 2 12.39 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.89-3.14 6.74-8.9 11.86l-1 0.99z"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.1 21.35l-1.1-1C5.14 15.24 2 12.39 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.89-3.14 6.74-8.9 11.86l-1 0.99z"/></svg>`;
  }

  function toggleFavorite(key) {
    const favKey = String(key || "").trim().toLowerCase();
    if (!FAVORITE_KEY_RE.test(favKey)) return;
    const adding = !state.favorites.has(favKey);
    if (adding) {
      if (state.favorites.size >= MAX_FAVORITES) {
        state.statusMessage = `Favorites limit reached (${MAX_FAVORITES})`;
        state.statusIsError = true;
        updateStatusBar();
        return;
      }
      state.favorites.add(favKey);
    } else {
      state.favorites.delete(favKey);
    }
    saveFavorites();
    for (const button of els.streamList.querySelectorAll(
      `.favorite-btn[data-fav-key="${favKey}"]`
    )) {
      syncFavoriteButton(button, favKey);
    }
    syncNowFavoriteMark();
    if (adding) showFavoritesHint();
    if (state.favoritesOnly) {
      loadStreams({ reset: true });
    }
  }

  function hasNarrowingFilters() {
    if (els.searchInput.value.trim()) return true;
    for (const select of els.filterForm.querySelectorAll("select[name]")) {
      if (select.value) return true;
    }
    return false;
  }

  function maybePruneFavorites() {
    if (!state.favoritesOnly || hasNarrowingFilters()) return;
    if (state.items.length < state.total) return;
    const alive = new Set(
      state.items.map((item) => String(item.favorite_key || "").toLowerCase())
    );
    let changed = false;
    for (const key of [...state.favorites]) {
      if (!alive.has(key)) {
        state.favorites.delete(key);
        changed = true;
      }
    }
    if (changed) saveFavorites();
  }

  function isNarrow() {
    return NARROW_MQ.matches;
  }

  function isPhone() {
    return PHONE_MQ.matches;
  }

  function placeFilterForm() {
    if (!els.filterForm || !els.filterSheetBody) return;
    if (els.filterForm.parentElement !== els.filterSheetBody) {
      els.filterSheetBody.appendChild(els.filterForm);
    }
  }

  function phoneOverflowItems() {
    // Phone two-row chrome surfaces Reset/Favorites inline; only Fullscreen stays under More.
    return [els.fullscreenBtn].filter(Boolean);
  }

  function closePhoneMoreMenu() {
    document.body.classList.remove("phone-more-open");
    if (els.phoneMorePanel) els.phoneMorePanel.hidden = true;
    if (els.phoneMoreBtn) els.phoneMoreBtn.setAttribute("aria-expanded", "false");
  }

  function openPhoneMoreMenu() {
    if (!isPhone()) return;
    closeFilterSheet();
    closeShareDialog();
    if (els.phoneMorePanel) els.phoneMorePanel.hidden = false;
    document.body.classList.add("phone-more-open");
    if (els.phoneMoreBtn) els.phoneMoreBtn.setAttribute("aria-expanded", "true");
  }

  function togglePhoneMoreMenu() {
    if (document.body.classList.contains("phone-more-open")) closePhoneMoreMenu();
    else openPhoneMoreMenu();
  }

  function placePhoneOverflowItems() {
    if (!els.compactActions || !els.phoneMorePanel || !els.phoneMoreWrap) return;
    if (isPhone()) {
      for (const el of phoneOverflowItems()) {
        if (el.parentElement !== els.phoneMorePanel) {
          els.phoneMorePanel.appendChild(el);
        }
      }
      // Row order: Filters · Reset · Favorites · Hide · More
      const beforeMore = [
        els.filtersToggleBtn,
        els.resetFiltersBtnCompact,
        els.favoritesToggleBtn,
        els.browseToggleBtn,
      ];
      for (const el of beforeMore) {
        if (el) els.compactActions.insertBefore(el, els.phoneMoreWrap);
      }
      return;
    }
    closePhoneMoreMenu();
    if (els.resetFiltersBtnCompact && els.filtersToggleBtn) {
      els.compactActions.insertBefore(els.resetFiltersBtnCompact, els.filtersToggleBtn);
    }
    if (els.favoritesToggleBtn && els.browseToggleBtn) {
      els.compactActions.insertBefore(els.favoritesToggleBtn, els.browseToggleBtn);
    }
    if (els.fullscreenBtn && els.phoneMoreWrap) {
      els.compactActions.insertBefore(els.fullscreenBtn, els.phoneMoreWrap);
    }
  }

  function countActiveFilters() {
    let count = 0;
    for (const select of els.filterForm.querySelectorAll("select[name]")) {
      if (select.value) count += 1;
    }
    return count;
  }

  function updateFiltersBadge() {
    if (!els.filtersBadge || !els.filtersToggleBtn) return;
    const count = countActiveFilters();
    if (count > 0) {
      els.filtersBadge.hidden = false;
      els.filtersBadge.textContent = String(count);
      els.filtersToggleBtn.textContent = "Filters ";
      els.filtersToggleBtn.appendChild(els.filtersBadge);
    } else {
      els.filtersBadge.hidden = true;
      els.filtersToggleBtn.textContent = "Filters";
      els.filtersToggleBtn.appendChild(els.filtersBadge);
    }
  }

  // Android WebView keeps a hardware video surface above HTML overlays unless the
  // <video> is paused/hidden. Track whether we paused it so Done can resume.
  let videoResumeAfterOverlay = false;

  function overlayBlocksVideoSurface() {
    return (
      document.body.classList.contains("filter-sheet-open") ||
      document.body.classList.contains("share-dialog-open")
    );
  }

  function suspendVideoForOverlay() {
    if (!els.video) return;
    document.body.classList.add("overlay-suspend-video");
    if (!els.video.paused) {
      videoResumeAfterOverlay = true;
      els.video.pause();
    }
  }

  function resumeVideoAfterOverlay() {
    if (overlayBlocksVideoSurface()) return;
    document.body.classList.remove("overlay-suspend-video");
    if (videoResumeAfterOverlay && els.video) {
      videoResumeAfterOverlay = false;
      els.video.play().catch(() => {});
    } else {
      videoResumeAfterOverlay = false;
    }
  }

  function closeFilterSheet() {
    document.body.classList.remove("filter-sheet-open");
    if (els.filterSheetPanel) els.filterSheetPanel.hidden = true;
    if (
      els.sheetBackdrop &&
      !document.body.classList.contains("channels-open") &&
      !document.body.classList.contains("share-dialog-open")
    ) {
      els.sheetBackdrop.hidden = true;
    }
    if (els.filtersToggleBtn) els.filtersToggleBtn.setAttribute("aria-expanded", "false");
    resumeVideoAfterOverlay();
  }

  function closeShareDialog() {
    document.body.classList.remove("share-dialog-open");
    if (els.shareDialog) els.shareDialog.hidden = true;
    if (
      els.sheetBackdrop &&
      !document.body.classList.contains("channels-open") &&
      !document.body.classList.contains("filter-sheet-open")
    ) {
      els.sheetBackdrop.hidden = true;
    }
    if (els.shareBtn) els.shareBtn.setAttribute("aria-expanded", "false");
    resumeVideoAfterOverlay();
  }

  function openShareDialog() {
    closePhoneMoreMenu();
    if (els.shareDialog) els.shareDialog.hidden = false;
    if (els.sheetBackdrop) els.sheetBackdrop.hidden = false;
    // Mark open before closing Filters so resumeVideoAfterOverlay stays suspended.
    document.body.classList.add("share-dialog-open");
    closeFilterSheet();
    if (els.shareBtn) els.shareBtn.setAttribute("aria-expanded", "true");
    suspendVideoForOverlay();
  }

  function toggleShareDialog() {
    if (document.body.classList.contains("share-dialog-open")) closeShareDialog();
    else openShareDialog();
  }

  function openFilterSheet() {
    placeFilterForm();
    closePhoneMoreMenu();
    // Keep watch-first: exiting would hide #stage on phone while HLS keeps playing,
    // and Android's video surface then blocks the sheet + backdrop (BUG-026).
    if (isNarrow()) setChannelsOpen(false);
    document.body.classList.add("filter-sheet-open");
    // Mark open before closing Share so resumeVideoAfterOverlay stays suspended.
    closeShareDialog();
    if (els.filterSheetPanel) els.filterSheetPanel.hidden = false;
    if (els.sheetBackdrop) els.sheetBackdrop.hidden = false;
    if (els.filtersToggleBtn) els.filtersToggleBtn.setAttribute("aria-expanded", "true");
    suspendVideoForOverlay();
  }

  function toggleFilterSheet() {
    if (document.body.classList.contains("filter-sheet-open")) closeFilterSheet();
    else openFilterSheet();
  }

  function setChannelsOpen(open) {
    if (!isNarrow()) {
      document.body.classList.remove("channels-open");
      if (
        els.sheetBackdrop &&
        !document.body.classList.contains("filter-sheet-open") &&
        !document.body.classList.contains("share-dialog-open")
      ) {
        els.sheetBackdrop.hidden = true;
      }
      return;
    }
    document.body.classList.toggle("channels-open", Boolean(open));
    if (open) {
      closeFilterSheet();
      closeShareDialog();
      closePhoneMoreMenu();
      // Backdrop only when the drawer is a temporary overlay over watch-first.
      if (state.watchFirst && els.sheetBackdrop) els.sheetBackdrop.hidden = false;
    } else if (
      els.sheetBackdrop &&
      !document.body.classList.contains("filter-sheet-open") &&
      !document.body.classList.contains("share-dialog-open")
    ) {
      els.sheetBackdrop.hidden = true;
    }
  }

  function syncTheaterChrome() {
    state.theater = state.watchFirst;
    if (els.layout) els.layout.classList.toggle("theater", state.watchFirst && !isNarrow());
    document.body.classList.toggle("theater-mode", state.watchFirst && !isNarrow());
    if (els.browseToggleBtn) {
      if (isPhone()) {
        els.browseToggleBtn.textContent = state.watchFirst ? "Show" : "Hide";
      } else {
        els.browseToggleBtn.textContent = state.watchFirst ? "Show channels" : "Hide channels";
      }
    }
  }

  function enterWatchFirst() {
    state.watchFirst = true;
    document.body.classList.add("watch-first");
    if (isNarrow()) setChannelsOpen(false);
    else document.body.classList.remove("channels-open");
    closeFilterSheet();
    closeShareDialog();
    closePhoneMoreMenu();
    syncTheaterChrome();
  }

  function exitWatchFirst() {
    state.watchFirst = false;
    document.body.classList.remove("watch-first");
    syncTheaterChrome();
    if (isNarrow()) setChannelsOpen(true);
  }

  function syncUiMode() {
    document.body.classList.add("ui-chrome-compact");
    const narrow = isNarrow();
    const phone = isPhone();
    document.body.classList.toggle("is-narrow", narrow);
    document.body.classList.toggle("is-phone", phone);
    document.body.classList.remove("is-compact");
    placeFilterForm();
    placePhoneOverflowItems();

    if (narrow) {
      clearLayoutSidebarWidthVar();
    } else {
      document.body.classList.remove("channels-open");
      setSidebarWidth(state.sidebarWidth || SIDEBAR_DEFAULT);
    }
    if (!phone) closePhoneMoreMenu();

    if (state.watchFirst) {
      enterWatchFirst();
    } else {
      syncTheaterChrome();
      if (narrow) setChannelsOpen(true);
    }
    updateFiltersBadge();
  }

  function setupSidebarResize() {
    const splitter = els.splitter;
    if (!splitter || !els.layout) return;

    splitter.setAttribute("aria-valuemin", String(SIDEBAR_MIN));
    splitter.setAttribute("aria-valuemax", String(SIDEBAR_MAX));
    if (isNarrow()) clearLayoutSidebarWidthVar();
    else setSidebarWidth(state.sidebarWidth || SIDEBAR_DEFAULT);

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
      if (state.watchFirst || isNarrow()) return;
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
    if (state.favoritesOnly && state.favorites.size) {
      params.set("favorite_keys", [...state.favorites].join(","));
    }
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
    // Overlay: only show a real programme title — never "No data" / Fetching….
    if (pending || !(info && info.title)) {
      node.hidden = true;
      node.textContent = "";
      node.dataset.state = pending ? "pending" : "empty";
      node.removeAttribute("title");
      return;
    }
    node.hidden = false;
    node.textContent = info.title;
    node.dataset.state = "title";
    node.classList.add("has-title");
    node.title = info.title;
  }

  function setNowQuality(quality) {
    const node = els.nowQuality;
    if (!node) return;
    const label = String(quality || "").trim();
    if (!label) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.textContent = label;
    node.title = `Resolution: ${label}`;
  }

  function syncNowFavoriteMark() {
    const node = els.nowFavorite;
    if (!node) return;
    const on = Boolean(
      state.selectedFavoriteKey && isFavorite(state.selectedFavoriteKey)
    );
    node.hidden = !on;
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
    state.selectedFavoriteKey = String(stream.favorite_key || "")
      .trim()
      .toLowerCase();
    const hasNow = Boolean(stream.now_playing && stream.now_playing.title);
    setViewerProgramme(hasNow ? stream.now_playing : null, { pending: !hasNow });
    setNowQuality(stream.video_quality);
    syncNowFavoriteMark();
    els.nowDetails.textContent = formatNowDetails(bits);
    // If detail payload had no EPG yet, resolve in background.
    if (!hasNow) {
      refreshNowPlaying([stream.id]);
    }
    fillStars(els.nowStars, stream.stream_quality);

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
    for (const row of els.streamList.querySelectorAll(".stream-item")) {
      row.classList.toggle("active", Number(row.dataset.id) === state.selectedId);
    }
  }

  function renderStreams(items, append) {
    if (!append) els.streamList.innerHTML = "";
    const fragment = document.createDocumentFragment();

    for (const item of items) {
      const li = document.createElement("li");
      const row = document.createElement("div");
      row.className = "stream-item";
      row.dataset.id = String(item.id);

      const selectBtn = document.createElement("button");
      selectBtn.type = "button";
      selectBtn.className = "stream-select";

      if (item.tvg_logo) {
        const img = document.createElement("img");
        img.src = item.tvg_logo;
        img.alt = "";
        img.loading = "lazy";
        img.onerror = () => {
          img.replaceWith(fallbackLogo(item.name));
        };
        selectBtn.appendChild(img);
      } else {
        selectBtn.appendChild(fallbackLogo(item.name));
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
      selectBtn.appendChild(meta);
      selectBtn.addEventListener("click", () => selectStream(item.id));

      const favBtn = document.createElement("button");
      favBtn.type = "button";
      favBtn.className = "favorite-btn";
      favBtn.dataset.favKey = String(item.favorite_key || "");
      syncFavoriteButton(favBtn, item.favorite_key);
      favBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        toggleFavorite(item.favorite_key);
      });

      row.append(selectBtn, favBtn);
      li.appendChild(row);
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
    const existing = readPrefs();
    clearCookie(PREFS_COOKIE);
    // Keep source, sidebar width, and Favorites filter. Starred channels live in
    // localStorage and are only removed by tapping a channel's favorite button.
    const kept = {};
    if (state.source) kept.source = state.source;
    if (state.sidebarWidth && state.sidebarWidth !== SIDEBAR_DEFAULT) {
      kept.sidebarWidth = state.sidebarWidth;
    }
    if (state.favoritesOnly) kept.favoritesOnly = true;
    if (
      typeof existing.dismissedUpdateVersion === "string" &&
      existing.dismissedUpdateVersion
    ) {
      kept.dismissedUpdateVersion = existing.dismissedUpdateVersion;
    }
    if (Object.keys(kept).length) writePrefs(kept);
    updateFiltersBadge();
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

    if (reset && state.favoritesOnly && state.favorites.size === 0) {
      state.offset = 0;
      state.items = [];
      state.total = 0;
      if (els.streamListWrap) els.streamListWrap.scrollTop = 0;
      renderStreams([], false);
      if (els.listSentinel) els.listSentinel.hidden = true;
      if (state.playback === "idle") {
        state.statusMessage = "No favorites yet — mark channels in the list";
        state.statusIsError = false;
      }
      updateStatusBar();
      return;
    }

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
      maybePruneFavorites();
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
    if (state.watchFirst) exitWatchFirst();
    else enterWatchFirst();
  }

  function isDomFullscreen() {
    return Boolean(
      document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.msFullscreenElement
    );
  }

  function syncFullscreenUi() {
    const active = isDomFullscreen() || document.body.classList.contains("is-fullscreen");
    if (els.fullscreenBtn) {
      els.fullscreenBtn.textContent = active ? "Exit fullscreen" : "Fullscreen";
    }
  }

  function enterCssFullscreen() {
    document.body.dataset.cssFullscreen = "1";
    document.body.classList.add("is-fullscreen");
    syncFullscreenUi();
  }

  function exitCssFullscreen() {
    delete document.body.dataset.cssFullscreen;
    document.body.classList.remove("is-fullscreen");
    syncFullscreenUi();
  }

  async function exitDomFullscreen() {
    const exit =
      document.exitFullscreen ||
      document.webkitExitFullscreen ||
      document.msExitFullscreen;
    if (exit) await exit.call(document);
  }

  async function requestDomFullscreen(target) {
    if (!target) return false;
    const req =
      target.requestFullscreen ||
      target.webkitRequestFullscreen ||
      target.webkitRequestFullScreen ||
      target.msRequestFullscreen;
    if (!req) return false;
    await req.call(target);
    return true;
  }

  async function toggleFullscreen() {
    // Android WebView often rejects Element.requestFullscreen unless WebChromeClient
    // handles onShowCustomView. Prefer <video>, then player frame, then CSS immersive.
    if (isDomFullscreen()) {
      try {
        await exitDomFullscreen();
      } catch {
        // ignore
      }
      exitCssFullscreen();
      return;
    }
    if (document.body.dataset.cssFullscreen === "1") {
      exitCssFullscreen();
      return;
    }

    const video = els.video;
    const frame = els.playerFrame;
    try {
      if (video && typeof video.webkitEnterFullscreen === "function") {
        video.webkitEnterFullscreen();
        enterCssFullscreen();
        return;
      }
      if (await requestDomFullscreen(video)) {
        document.body.classList.add("is-fullscreen");
        syncFullscreenUi();
        return;
      }
      if (await requestDomFullscreen(frame)) {
        document.body.classList.add("is-fullscreen");
        syncFullscreenUi();
        return;
      }
      enterCssFullscreen();
    } catch {
      enterCssFullscreen();
    }
  }

  function onFullscreenChange() {
    if (isDomFullscreen()) {
      delete document.body.dataset.cssFullscreen;
      document.body.classList.add("is-fullscreen");
    } else if (document.body.dataset.cssFullscreen !== "1") {
      document.body.classList.remove("is-fullscreen");
    }
    syncFullscreenUi();
  }

  document.addEventListener("fullscreenchange", onFullscreenChange);
  document.addEventListener("webkitfullscreenchange", onFullscreenChange);

  els.searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      savePrefs();
      loadStreams({ reset: true });
    }, 220);
  });

  els.searchInput.addEventListener("focus", () => {
    // On narrow/Android the drawer is independent of search (search stays in the
    // top bar). Exiting watch-first here would force the sidebar open again.
    if (state.watchFirst && !isNarrow()) exitWatchFirst();
  });

  els.filterForm.addEventListener("change", () => {
    savePrefs();
    updateFiltersBadge();
    loadStreams({ reset: true });
  });
  els.resetFiltersBtn?.addEventListener("click", resetFilters);
  els.resetFiltersBtnCompact?.addEventListener("click", () => {
    resetFilters();
    updateFiltersBadge();
    closePhoneMoreMenu();
  });
  els.fullscreenBtn?.addEventListener("click", () => {
    closePhoneMoreMenu();
    toggleFullscreen();
  });

  els.filtersToggleBtn?.addEventListener("click", () => {
    toggleFilterSheet();
  });
  els.favoritesToggleBtn?.addEventListener("click", () => {
    if (state.watchFirst) exitWatchFirst();
    state.favoritesOnly = !state.favoritesOnly;
    syncFavoritesToggle();
    savePrefs();
    loadStreams({ reset: true });
    closePhoneMoreMenu();
  });
  els.favoritesHintDismiss?.addEventListener("click", () => {
    hideFavoritesHint({ persist: true });
  });
  els.filterSheetDoneBtn?.addEventListener("click", closeFilterSheet);
  els.shareBtn?.addEventListener("click", toggleShareDialog);
  els.shareDialogCloseBtn?.addEventListener("click", closeShareDialog);
  els.browseToggleBtn?.addEventListener("click", () => {
    closePhoneMoreMenu();
    toggleTheater();
  });
  els.phoneMoreBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePhoneMoreMenu();
  });
  els.phoneMorePanel?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  els.showSidebarBtn?.addEventListener("click", () => {
    exitWatchFirst();
  });
  els.statusDetailsBtn?.addEventListener("click", () => {
    const open = !document.body.classList.contains("status-details-open");
    document.body.classList.toggle("status-details-open", open);
    els.statusDetailsBtn.setAttribute("aria-expanded", open ? "true" : "false");
    els.statusDetailsBtn.textContent = open ? "Less" : "Details";
  });
  els.sheetBackdrop?.addEventListener("click", () => {
    closeFilterSheet();
    closeShareDialog();
    closePhoneMoreMenu();
    if (state.watchFirst) setChannelsOpen(false);
  });

  document.addEventListener("click", (event) => {
    if (!document.body.classList.contains("phone-more-open")) return;
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (els.phoneMoreWrap?.contains(target)) return;
    closePhoneMoreMenu();
  });

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
    if (event.key === "Escape") {
      closeFilterSheet();
      closeShareDialog();
      closePhoneMoreMenu();
      if (isNarrow() && state.watchFirst) setChannelsOpen(false);
    }
  });

  NARROW_MQ.addEventListener?.("change", syncUiMode);
  PHONE_MQ.addEventListener?.("change", syncUiMode);
  window.addEventListener("resize", () => {
    syncUiMode();
  });

  function hideUpdateNotice() {
    if (els.updateAvailable) els.updateAvailable.hidden = true;
  }

  function updateInfoHintSeen() {
    try {
      return localStorage.getItem(UPDATE_INFO_HINT_KEY) === "1";
    } catch {
      return false;
    }
  }

  function markUpdateInfoHintSeen() {
    try {
      localStorage.setItem(UPDATE_INFO_HINT_KEY, "1");
    } catch {
      // ignore
    }
  }

  function linkStatusVersion(releaseUrl) {
    if (IS_ANDROID) return;
    const valueEl = els.statusVersionValue;
    if (!valueEl || !releaseUrl) return;
    if (valueEl.tagName === "A") {
      valueEl.href = releaseUrl;
      return;
    }
    const link = document.createElement("a");
    link.id = "statusVersionValue";
    link.className = "status-version-link";
    link.href = releaseUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "Newer version available — open release page";
    link.textContent = valueEl.textContent;
    valueEl.replaceWith(link);
    els.statusVersionValue = link;
  }

  function showUpdateNotice(latest, releaseUrl) {
    if (!els.updateAvailable || !els.updateAvailableLink || !releaseUrl) return;
    els.updateAvailable.dataset.latest = latest;
    els.updateAvailableLink.href = releaseUrl;
    if (IS_ANDROID) {
      els.updateAvailableLink.textContent = "Newer release online";
      els.updateAvailableLink.title =
        "A newer release is on GitHub. Sideload the APK from Releases when you want it.";
    } else {
      els.updateAvailableLink.textContent = "Update available";
      els.updateAvailableLink.title = `Version ${latest} is available`;
    }
    els.updateAvailable.hidden = false;
    linkStatusVersion(releaseUrl);
  }

  function dismissUpdateNotice(latest) {
    if (IS_ANDROID) {
      markUpdateInfoHintSeen();
    } else {
      const prefs = collectPrefs();
      prefs.dismissedUpdateVersion = latest;
      writePrefs(prefs);
    }
    hideUpdateNotice();
  }

  async function checkForUpdate() {
    try {
      if (IS_ANDROID && updateInfoHintSeen()) return;
      const response = await fetch("/api/update");
      if (!response.ok) return;
      const data = await response.json();
      if (!data || !data.update_available || !data.latest || !data.release_url) {
        return;
      }
      if (!IS_ANDROID) {
        const prefs = readPrefs();
        if (prefs.dismissedUpdateVersion === data.latest) return;
      }
      showUpdateNotice(data.latest, data.release_url);
    } catch {
      // Fail-soft: offline / API errors never interrupt browsing.
    }
  }

  if (els.updateAvailableDismiss) {
    els.updateAvailableDismiss.addEventListener("click", () => {
      const version = els.updateAvailable?.dataset?.latest;
      if (version) dismissUpdateNotice(version);
      else {
        if (IS_ANDROID) markUpdateInfoHintSeen();
        hideUpdateNotice();
      }
    });
  }

  (async () => {
    try {
      state.favorites = loadFavorites();
      setupInfiniteScroll();
      setupSidebarResize();
      syncUiMode();
      updateStatusBar();
      const prefs = readPrefs();
      await loadMeta(prefs.source || null);
      applyPrefs(prefs);
      updateFiltersBadge();
      syncFavoritesToggle();
      syncUiMode();
      await loadStreams({ reset: true });
      checkForUpdate();
    } catch (error) {
      state.statusMessage = "No catalog data available";
      state.statusIsError = true;
      updateStatusBar();
      console.error(error);
    }
  })();
})();
