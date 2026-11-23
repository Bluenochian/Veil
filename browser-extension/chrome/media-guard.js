// Veil only quiets pages the extension has actually marked for concealment.
// Normal pages and user-allowed sites are left alone.
(() => {
  const api = typeof browser !== "undefined" ? browser : chrome;
  const original = new Map();
  let enabled = false;
  let observer = null;
  let revision = 0;

  function quiet(media) {
    if (!enabled || !(media instanceof HTMLMediaElement)) return;
    if (!original.has(media)) {
      original.set(media, {
        muted: media.muted, autoplay: media.autoplay, preload: media.preload
      });
    }
    media.autoplay = false;
    media.preload = "none";
    media.muted = true;
    try { media.pause(); } catch {}
  }

  function scan(node) {
    if (node.nodeType !== 1) return;
    if (node.matches?.("audio,video")) quiet(node);
    node.querySelectorAll?.("audio,video").forEach(quiet);
  }

  function startObserver() {
    if (!enabled || observer || !document.documentElement) return;
    scan(document.documentElement);
    observer = new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) scan(node);
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  function setEnabled(next) {
    if (enabled === next) return;
    enabled = next;
    if (enabled) {
      startObserver();
    } else {
      observer?.disconnect();
      observer = null;
      for (const [media, state] of original) {
        media.muted = state.muted;
        media.autoplay = state.autoplay;
        media.preload = state.preload;
      }
      original.clear();
    }
  }

  // A 'play' event can slip past a DOM observer on some dynamic players.
  window.addEventListener("play", event => quiet(event.target), true);
  window.addEventListener("playing", event => quiet(event.target), true);
  document.addEventListener("DOMContentLoaded", startObserver, { once: true });

  async function refresh() {
    const current = ++revision;
    try {
      const result = await api.runtime.sendMessage({ type: "VEIL_MEDIA_POLICY" });
      if (current === revision) setEnabled(result?.block === true);
    } catch {
      if (current === revision) setEnabled(false);
    }
  }

  api.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && Object.hasOwn(changes, "isVeilActive")) refresh();
  });
  refresh();
})();
