
/**
 * Veil Privacy Companion Extension
 * Operates in coordination with the native Veil Linux daemon.
 * Conceals matching tabs and bookmarks through the encrypted local vault.
 */

const NATIVE_HOST_NAME = "com.veil.privacy";

const SENSITIVE_TLDS = [".xxx", ".porn", ".adult", ".sex", ".sexy", ".cam", ".casino", ".bet", ".poker"];

const SENSITIVE_PATTERNS = [
  /casino/i, /bet365/i, /stake\.com/i, /1xbet/i, /pokerstars/i, /roulette/i,
  /blackjack/i, /sportsbook/i, /csgoroll/i, /csgoempire/i, /online.*gambling/i,
  /bestgore/i, /kaotic/i, /goregrish/i, /seegore/i, /heavy-r/i, /snuff/i,
  /darknet.*market/i, /silkroad/i, /tor.*market/i
];

const ADULT_HOST_PATTERNS = [
  /porn/i, /fap/i, /hentai/i, /xxx/i, /babepedia/i, /leaked\.fans/i,
  /leakedzone/i, /onlyfans/i, /fansly/i, /chaturbate/i, /stripchat/i,
  /cam4/i, /camsoda/i, /erome/i, /spankbang/i, /xvideos/i, /xhamster/i,
  /youporn/i, /redtube/i, /brazzers/i, /eporner/i, /pornwex/i, /fapcat/i,
  /sexselector/i, /sexygirl/i, /cherrynude/i, /lobstertube/i, /vptvid/i,
  /noodlemagazine/i, /tube8/i, /beeg/i, /hqporner/i, /tnaflix/i, /rule34/i,
  /nhentai/i, /gelbooru/i, /danbooru/i, /e-hentai/i, /exhentai/i, /luscious/i,
  /literotica/i, /livejasmin/i, /adultfriendfinder/i, /coomer/i, /kemono/i,
  /motherless/i, /daftsex/i, /youjizz/i, /fuq/i, /nudevista/i, /sunporno/i,
  /fetlife/i, /hanime/i, /hentaihaven/i, /javlibrary/i, /javbus/i, /dmm\.co\.jp/i,
  /javhd/i, /javmost/i, /redgifs/i, /thumbzilla/i, /txxx/i, /cumlouder/i,
  /hitomi\.la/i, /pururin/i, /tsumino/i, /shemalez/i, /gaytube/i, /kink\.com/i,
  /ifsa/i, /123av/i, /aznude/i, /asmrleak/i, /dirtyship/i, /leakgallery/i,
  /fapodrop/i, /fapachi/i, /nudogram/i, /nudostar/i, /tokyokinky/i,
  /elitebabes/i, /mrskin/i, /sheeshfans/i, /ukdevilz/i, /joyreactor/i,
  /tsthots/i, /fapflix/i, /erothot/i, /internetchicks/i
];

const SAFE_DOMAINS = [
  "wikipedia.org", "wikimedia.org", "britannica.com", "stanford.edu",
  "mayoclinic.org", "webmd.com", "cdc.gov", "nih.gov", "who.int",
  "nhs.uk", "healthline.com", "github.com", "gitlab.com", "stackoverflow.com",
  "chatgpt.com", "dailyplaylists.com", "artist.tools", "tapusor.com",
  "bbc.com", "reuters.com", "nytimes.com"
];

const SAFE_TERMS = [
  "symptom", "treatment", "diagnosis", "disease", "cancer", "prevention",
  "medical", "clinic", "hospital", "doctor", "therapy", "health", "biology",
  "anatomy", "education", "textbook", "analytics", "analyzer", "analysis",
  "playlist", "platform", "analog", "law", "statute", "legislation", "police",
  "arrest", "court", "rights", "civil rights", "counseling", "support",
  "advocacy", "investigation", "journalism", "documentary", "anti-spycam",
  "防止", "撲滅", "法律", "条例", "警察", "逮捕", "裁判", "相談", "被害", "対策",
  "防范", "维权", "警方", "通报", "严打", "成人教育", "成人高考", "自拍杆", "自拍相机", "摄影教程", "防偷拍"
];

const UNAMBIGUOUS_ADULT_TERMS = [
  "動画", "エロ", "無修正", "ビデオ", "ポルノ", "中出し", "裏垢", "ハメ撮り", "パイズリ",
  "视频", "无码", "流出", "内射", "做爱", "操逼", "福利姬", "黑料", "门事件", "骚逼",
  "야동", "섹스", "자위", "노모", "유출",
  "porn", "xxx", "creampie", "blowjob", "hardcore", "leak", "leaked", "sex", "erome"
];

const STRONG_PATTERNS = [
  /\bporn\w*/i, /\bporno\w*/i, /\bxxx\b/i, /\bhentai\w*/i, /\bblowjob\w*/i,
  /\bcreampie\w*/i, /\bcumshot\w*/i, /\bgangbang\w*/i, /\bdeepthroat\w*/i,
  /\bdildo\w*/i, /\bfleshlight\w*/i, /\bcuckold\w*/i, /\bshemale\w*/i,
  /\bbukkake\w*/i, /\berome\w*/i, /\bspankbang\w*/i, /\bfapello\w*/i,
  /\bcamgirl\w*/i, /\brule34\w*/i, /\bjav\b/i, /\bjavhd\w*/i, /\bhardcore\b/i,
  /\banal\b/i, /\bcock\b/i, /\bdick\b/i, /\bpussy\b/i, /\bfucking\b/i,
  /\bnude\w*/i, /\bnaked\b/i, /\bonlyfans\w*/i, /\bfansly\w*/i,
  /\bleak\w*/i, /\bmilf\b/i, /\bm1lf\b/i, /\bsex\b/i, /\bcum\b/i, /\bnsfw\b/i,
  /\bbabepedia\w*/i, /\bdoujin\w*/i, /\bbabe\b/i, /\bifsa\b/i, /\bhandjob\w*/i,
  /\bsexually\b/i, /\bgroped\b/i, /\bsee through\b/i, /\btits\b/i, /\bboobs\b/i,
  /\bsextape\w*/i, /\bthot\w*/i, /\bjoi\b/i, /\b18\+\b/i, /\bhorny\b/i,
  /\bincest\w*/i, /\bstepmom\w*/i, /\bstepsister\w*/i, /\bstepdaughter\w*/i,
  /\bstepmother\w*/i, /\bstepbrother\w*/i, /\bstepson\w*/i, /\bhotwife\w*/i,
  /\bnetorare\b/i, /\bntr\b/i,
  /\bspycam\w*/i, /\bhidden\s*cam\w*/i, /\bvoyeur\w*/i, /\bupskirt\w*/i,
  /\bdownblouse\w*/i, /\bcreepshot\w*/i, /\bpeeping\s*tom\b/i,
  /\bfemdom\w*/i, /\bpegging\b/i, /\bchastity\b/i, /\bbondage\w*/i, /\bbdsm\b/i,
  /\b(gay|trans|transgender|twink|bear|sissy|crossdresser)\s+(porn|xxx|tube|video|sex|bareback|hardcore|creampie|blowjob|anal|fuck|fucking)\b/i,
  /\b(shemale|ladyboy|futanari|tranny|sissy\s*maid)\w*\b/i,
  /無修正/i, /裏ビデオ/i, /中出し/i, /ハメ撮り/i, /パイズリ/i, /フェラ/i, /手コキ/i,
  /オナニー/i, /潮吹き/i, /アヘ顔/i, /近親相姦/i, /義母/i, /義妹/i, /人妻中出し/i,
  /盗撮(動画|エロ|写真|画像)/i, /のぞき(部屋|魔|動画)/i, /パンチラ(動画|写真|画像)/i, /スカート内/i,
  /調教/i, /緊縛/i, /奴隷/i, /痴女/i, /痴漢(動画|エロ)/i, /露出(動画|狂|オナニー)/i,
  /无码/i, /内射/i, /自慰/i, /自拍偷拍/i, /偷拍自拍/i, /乱伦/i, /做爱/i, /操逼/i,
  /插逼/i, /潮吹/i, /福利姬/i, /黑料不打烊/i, /门事件/i, /吃瓜黑料/i, /精液/i, /颜射/i,
  /母子(乱伦|相奸|中出)/i, /继母/i, /偷窥/i, /裙底/i, /偷拍/i, /调教/i, /捆绑/i, /性奴/i,
  /야동/i, /노모/i, /유출/i, /직캠/i, /도촬/i, /섹스/i, /자위/i, /몰카/i, /성人방송/i
];

let customRules = { whitelist: [], blacklist: [] };

function safeDecode(value) {
  try { return decodeURIComponent(value); } catch { return value; }
}

function matchesRule(url, hostname, rule) {
  if (typeof rule !== "string" || !rule || rule.length > 512) return false;
  // fnmatch-style patterns: *, ?, [abc], [a-z], and [!abc].
  // Escape regex punctuation or a rule can match more than you intened.
  const input = rule.toLowerCase();
  let pattern = "^";
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === "*") { pattern += ".*"; continue; }
    if (c === "?") { pattern += "."; continue; }
    if (c === "[") {
      let end = i + 1;
      if (input[end] === "!") end++;
      if (input[end] === "]") end++;
      while (end < input.length && input[end] !== "]") end++;
      if (end < input.length) {
        let chars = input.slice(i + 1, end).replace(/\\/g, "\\\\");
        if (chars.startsWith("!")) chars = "^" + chars.slice(1);
        else if (chars.startsWith("^")) chars = "\\" + chars;
        pattern += "[" + chars + "]";
        i = end;
        continue;
      }
    }
    pattern += c.replace(/[\\^$+?.()|{}\[\]]/g, "\\$&");
  }
  try {
    const re = new RegExp(pattern + "$", "i");
    return re.test(hostname) || re.test(url.toLowerCase());
  } catch { return false; }
}

function isAdult(url, title = "") {
  if (!url) return false;
  let parsed = null;
  try {
    parsed = new URL(url);
  } catch (e) {
    return false;
  }

  const hostname = parsed.hostname.toLowerCase();
  // Broken % escapes still show up in URLs. Dont let decoding errors skip rules.
  const pathname = safeDecode(parsed.pathname || "").toLowerCase();
  const search = safeDecode(parsed.search || "").toLowerCase();
  const titleLower = (title || "").toLowerCase();
  const combined = hostname + " " + pathname + " " + search + " " + titleLower;

  if (customRules.whitelist.some(rule => matchesRule(url, hostname, rule))) return false;
  if (customRules.blacklist.some(rule => matchesRule(url, hostname, rule))) return true;

  for (const safe of SAFE_DOMAINS) {
    if (hostname === safe || hostname.endsWith("." + safe)) {
      return false;
    }
  }

  for (const tld of SENSITIVE_TLDS) {
    if (hostname.endsWith(tld)) return true;
  }

  for (const pat of SENSITIVE_PATTERNS) {
    if (pat.test(combined)) return true;
  }

  for (const pat of ADULT_HOST_PATTERNS) {
    if (pat.test(hostname)) return true;
  }

  let hasSafe = false;
  for (const term of SAFE_TERMS) {
    if (combined.includes(term.toLowerCase())) {
      hasSafe = true;
      break;
    }
  }

  if (hasSafe) {
    for (const term of UNAMBIGUOUS_ADULT_TERMS) {
      if (combined.includes(term.toLowerCase())) {
        return true;
      }
    }
    return false;
  }

  for (const pat of STRONG_PATTERNS) {
    if (pat.test(combined)) return true;
  }

  return false;
}

// State
let isVeilActive = false;
let revealOnDemand = true;
let nativePort = null;
let reconnectTimer = null;
const pendingNativeRequests = new Map();
let nextNativeRequestId = 0;
let concealInFlight = false;
let restoreInFlight = false;

// Each profile has its own ID. Dont mix up Brave profiles (or browsers).
const profileReady = chrome.storage.local.get({ veilProfileID: "" }).then(async ({ veilProfileID }) => {
  if (/^[a-f0-9-]{36}$/.test(veilProfileID)) return veilProfileID;
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ veilProfileID: id });
  return id;
});

function nativeRequest(payload, timeoutMs = 8000) {
  if (!nativePort) return Promise.reject(new Error("Veil daemon is disconnected"));
  const port = nativePort;
  const request_id = `ext-${++nextNativeRequestId}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingNativeRequests.delete(request_id);
      reject(new Error("Veil daemon did not acknowledge the operation"));
    }, timeoutMs);
    pendingNativeRequests.set(request_id, { resolve, reject, timer });
    try {
      port.postMessage({ ...payload, request_id });
    } catch (error) {
      clearTimeout(timer);
      pendingNativeRequests.delete(request_id);
      reject(error);
    }
  });
}


const pausedPage = new URL(chrome.runtime.getURL("paused.html"));
const pendingDiscardTabs = new Set();
const pendingVaultTabs = new Set();
const buildRevision = globalThis.VEIL_EXTENSION_REVISION || "";
let refreshPausedPages = false;
const pendingTabChanges = new Map();
const TAB_BATCH_SIZE = 16;
const TAB_BATCH_GAP_MS = 12;
let tabBatchTimer = null;

const stateReady = chrome.storage.local.get({
  isVeilActive: false, revealOnDemand: true, veilBuildRevision: ""
})
  .then((state) => {
    isVeilActive = state.isVeilActive;
    revealOnDemand = state.revealOnDemand;
    refreshPausedPages = !!buildRevision && state.veilBuildRevision !== buildRevision;
    updateExtensionBadge(isVeilActive);
  })
  .catch(() => {});

function connectNative() {
  if (nativePort) return;
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);

    nativePort.onMessage.addListener((msg) => {
      if (msg?.request_id && pendingNativeRequests.has(msg.request_id)) {
        const pending = pendingNativeRequests.get(msg.request_id);
        pendingNativeRequests.delete(msg.request_id);
        clearTimeout(pending.timer);
        pending.resolve(msg);
        return;
      }
      handleNativeMessage(msg);
    });

    nativePort.onDisconnect.addListener(() => {
      nativePort = null;
      for (const request of pendingNativeRequests.values()) {
        clearTimeout(request.timer);
        request.reject(new Error("Veil daemon disconnected"));
      }
      pendingNativeRequests.clear();
      scheduleReconnect();
    });

    // Ask the daemon for fresh state on every connection, even if we think we know it.
  } catch (err) {
    nativePort = null;
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectNative();
  }, 2000);
}

function updateExtensionBadge(isActive) {
  try {
    if (isActive) {
      chrome.action.setBadgeText({ text: "ON" });
      chrome.action.setBadgeBackgroundColor({ color: "#a855f7" });
      chrome.action.setTitle({ title: "Veil: Active" });
      chrome.action.setIcon({
        path: {
          16: "icons/icon16.png",
          48: "icons/icon48.png",
          128: "icons/icon128.png"
        }
      });
    } else {
      chrome.action.setBadgeText({ text: "" });
      chrome.action.setTitle({ title: "Veil: Inactive" });
      chrome.action.setIcon({
        path: {
          16: "icons/icon16-off.png",
          48: "icons/icon48-off.png",
          128: "icons/icon128-off.png"
        }
      });
    }
  } catch (e) {}
}

function getPausedURL(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === pausedPage.protocol && parsed.host === pausedPage.host &&
        parsed.pathname === pausedPage.pathname) {
      return parsed;
    }
  } catch {}
  return null;
}

function pausedToken(pausedURL) {
  const token = pausedURL?.hash?.startsWith("#token=") ? pausedURL.hash.slice(7) : null;
  return token && /^[a-f0-9-]{36}$/.test(token) ? token : null;
}

async function resolvePausedURL(pausedURL) {
  const token = pausedToken(getPausedURL(pausedURL));
  if (!token) return null;
  const profile = await profileReady;
  const answer = await nativeRequest({ type: "resolve_tab", profile, token });
  if (answer.status === "error" && answer.error) throw new Error(answer.error);
  return answer.status === "ok" && /^https?:\/\//i.test(answer.url || "")
    ? { url: answer.url, token, profile } : null;
}

// Clear a group of restored tokens with one small transaction, without
// blocking tab navigation. Failed clears remain queued for reconnection.
const pendingClearTokens = new Set();
let clearTabsTimer = null;
let clearTabsInFlight = false;
function scheduleTabCleanup() {
  if (!nativePort || clearTabsTimer !== null || clearTabsInFlight || !pendingClearTokens.size) return;
  clearTabsTimer = setTimeout(() => {
    clearTabsTimer = null;
    flushTabCleanup().catch(() => {});
  }, 20);
}
async function flushTabCleanup() {
  if (!nativePort || clearTabsInFlight || isVeilActive || !pendingClearTokens.size) return;
  clearTabsInFlight = true;
  const tokens = [...pendingClearTokens].slice(0, 128);
  try {
    const profile = await profileReady;
    const response = await nativeRequest({ type: "clear_tabs", profile, tokens });
    if (response.status === "ok") for (const token of tokens) pendingClearTokens.delete(token);
  } catch { /* Keep tokens encrypted until a later authoritative reconnect. */ }
  finally {
    clearTabsInFlight = false;
    if (pendingClearTokens.size && !isVeilActive && nativePort) {
      // Daemon said no? Dont hammer it; the next state sync can retry.
      if (tokens.some(token => !pendingClearTokens.has(token))) scheduleTabCleanup();
    }
  }
}
async function clearPausedToken({ token }) {
  pendingClearTokens.add(token);
  scheduleTabCleanup();
}

function queueTabChange(tab, expectedURL, targetURL, shouldRun, beforeNavigate) {
  const previous = pendingTabChanges.get(tab.id);
  pendingTabChanges.set(tab.id, {
    id: tab.id, active: tab.active, expectedURL, targetURL, shouldRun,
    beforeNavigate: beforeNavigate ||
      (previous?.targetURL === targetURL && previous?.expectedURL === expectedURL
        ? previous.beforeNavigate : undefined)
  });
  if (tabBatchTimer === null) tabBatchTimer = setTimeout(processTabBatch, 0);
}

async function processTabBatch() {
  const batch = [...pendingTabChanges.values()]
    .sort((a, b) => Number(!!b.active) - Number(!!a.active)).slice(0, TAB_BATCH_SIZE);
  for (const item of batch) pendingTabChanges.delete(item.id);
  await Promise.allSettled(batch.map(async (item) => {
    if (!item.shouldRun()) return;
    const tab = await chrome.tabs.get(item.id);
    if (!item.shouldRun() || (tab.pendingUrl || tab.url) !== item.expectedURL) return;
    item.beforeNavigate?.();
    if (item.targetURL) {
      await chrome.tabs.update(tab.id, { url: item.targetURL });
      if (getPausedURL(item.expectedURL) && !isVeilActive) {
        const token = pausedToken(getPausedURL(item.expectedURL));
        if (token) {
          const profile = await profileReady;
          await clearPausedToken({ token, profile });
        }
      }
    } else {
      await chrome.tabs.reload(tab.id);
    }
  }));
  tabBatchTimer = pendingTabChanges.size ? setTimeout(processTabBatch, TAB_BATCH_GAP_MS) : null;
}

async function pauseTab(tab, url) {
  if (!isVeilActive || !nativePort || pendingVaultTabs.has(tab.id) || pendingTabChanges.has(tab.id)) return;
  pendingVaultTabs.add(tab.id);
  try {
    const profile = await profileReady;
    const token = crypto.randomUUID();
    // Vault ACK comes BEFORE navigation. Seriously. Otherwise recovery isnt safe.
    const answer = await nativeRequest({ type: "vault_tab", profile, token, url });
    if (answer.status !== "ok" || !isVeilActive) return;
    const pausedURL = pausedPage.href + "#token=" + token;
    queueTabChange(tab, url, pausedURL, () => isVeilActive);
  } catch (error) {
    console.warn("Veil could not safely vault tab:", error.message);
  } finally {
    pendingVaultTabs.delete(tab.id);
  }
}

async function restorePausedTab(tab, pausedURL, explicit = false) {
  if (isVeilActive || (!explicit && revealOnDemand)) return;
  try {
    const resolved = await resolvePausedURL(pausedURL);
    if (!resolved || isVeilActive || (!explicit && revealOnDemand)) return;
    // Only navigate if this is still the same tab. Tabs have a habit of moving.
    queueTabChange(tab, pausedURL, resolved.url,
      () => !isVeilActive && (explicit || !revealOnDemand), undefined);
    // Keep the vault record until navigation finishes. Crashes dont ask permission.
  } catch { /* Recovery remains possible on a subsequent daemon reconnect */ }
}

async function restorePausedTabs(explicit = false) {
  if (isVeilActive || (!explicit && revealOnDemand) || !nativePort) return;
  const profile = await profileReady;
  const tabs = await chrome.tabs.query({});
  const paused = tabs.map(tab => ({tab, url: tab.pendingUrl || tab.url})).filter(item => {
    item.token = pausedToken(getPausedURL(item.url));
    return item.token && !pendingTabChanges.has(item.tab.id);
  });
  for (let offset = 0; offset < paused.length; offset += 128) {
    if (isVeilActive || (!explicit && revealOnDemand)) return;
    const items = paused.slice(offset, offset + 128);
    try {
      const answer = await nativeRequest({type: "resolve_tabs", profile, tokens: items.map(item => item.token)});
      if (answer.status !== "ok" || !answer.tabs || typeof answer.tabs !== "object") {
        // Older daemon still around? Dont break the handshake.
        for (const item of items) await restorePausedTab(item.tab, item.url, explicit);
        continue;
      }
      for (const item of items) {
        const resolved = answer.tabs[item.token];
        if (typeof resolved !== "string" || !/^https?:\/\//i.test(resolved)) continue;
        queueTabChange(item.tab, item.url, resolved,
          () => !isVeilActive && (explicit || !revealOnDemand));
      }
    } catch {
      // Paused pages need those tokens or Restore cant do its job.
    }
  }
}

async function reloadOpenPausePages() {
  for (const tab of await chrome.tabs.query({})) {
    const url = tab.pendingUrl || tab.url;
    if (getPausedURL(url) && (isVeilActive || revealOnDemand) && !pendingTabChanges.has(tab.id)) {
      queueTabChange(tab, url, null, () => isVeilActive || revealOnDemand);
    }
  }
}

function syncPauseState() {
  const storage = { isVeilActive, revealOnDemand };
  if (refreshPausedPages) storage.veilBuildRevision = buildRevision;
  const refresh = refreshPausedPages;
  refreshPausedPages = false;
  chrome.storage.local.set(storage).then(() => {
    if (refresh) return reloadOpenPausePages();
  }).catch(() => {});
  if (!isVeilActive && !revealOnDemand) {
    restorePausedTabs().catch(() => {});
  }
}

function handleNativeMessage(msg) {
  if (!msg?.type) return;
  switch (msg.type) {
    case "state":
    case "set_state":
    case "veil_active":
    case "veil_inactive":
    case "trigger_conceal":
    case "trigger_restore": {
      const active = msg.type === "trigger_conceal" || msg.type === "veil_active" ||
        (msg.type !== "trigger_restore" && msg.type !== "veil_inactive" && !!msg.active);
      isVeilActive = active;
      if (msg.reveal_on_demand !== undefined) {
        revealOnDemand = !!msg.reveal_on_demand;
      }
      if (msg.rules && Array.isArray(msg.rules.whitelist) && Array.isArray(msg.rules.blacklist)) {
        customRules = { whitelist: msg.rules.whitelist, blacklist: msg.rules.blacklist };
      }
      syncPauseState();
      updateExtensionBadge(active);
      if (!active) scheduleTabCleanup();
      // Retry pending vault work on reconnect. State can change mid-toggle.
      if (active) executeConceal().catch(console.warn);
      else executeRestore().catch(console.warn);
      break;
    }
    case "reveal_preference":
      revealOnDemand = msg.reveal_on_demand !== false;
      syncPauseState();
      break;
    case "reveal_all_tabs":
      restorePausedTabs(true).catch(() => {});
      break;
    case "reload":
      chrome.runtime.reload();
      break;
  }
}

// Single-click toolbar icon toggle
chrome.action.onClicked.addListener(() => {
  if (nativePort) {
    nativePort.postMessage({ type: "toggle" });
  }
});

async function revealTab(sender) {
  await stateReady;
  if (isVeilActive || !revealOnDemand) {
    return { ok: false, error: "Reveal is not available right now." };
  }
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0 || sender.tab?.id == null) {
    return { ok: false, error: "This is not a paused Veil tab." };
  }
  if (!getPausedURL(sender.url)) return { ok: false, error: "This is not a paused Veil page." };
  const resolved = await resolvePausedURL(sender.url);
  if (!resolved) return { ok: false, error: "The original page is unavailable. Reconnect the Veil daemon." };

  const tab = await chrome.tabs.get(sender.tab.id);
  if (isVeilActive || !revealOnDemand || (tab.pendingUrl || tab.url) !== sender.url) {
    return { ok: false, error: "This tab is no longer ready to reveal." };
  }
  await chrome.tabs.update(tab.id, { url: resolved.url });
  await clearPausedToken(resolved);
  return { ok: true };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type !== "VEIL_REVEAL_TAB") return;
  revealTab(sender).then(sendResponse, (error) => {
    sendResponse({ ok: false, error: error?.message || "Could not reopen the original page. Try again." });
  });
  return true;
});

// -------------------------------------------------------------
// LIVE CONCEAL / RESTORE
// -------------------------------------------------------------
async function concealOpenTabs() {
  const tabs = await chrome.tabs.query({});
  if (!isVeilActive || !nativePort) return;
  const profile = await profileReady;
  const candidates = tabs.filter(tab => {
    const url = tab.pendingUrl || tab.url;
    const title = tab.pendingUrl ? "" : tab.title;
    return url && !pendingVaultTabs.has(tab.id) && !pendingTabChanges.has(tab.id) && !getPausedURL(url) && isAdult(url, title);
  });
  // One SQLite transaction is nicer than up to 128 seperate native round trips.
  // Never navigate on a missing or failed acknowledgement.
  for (let offset = 0; offset < candidates.length && isVeilActive && nativePort; offset += 128) {
    const chunk = candidates.slice(offset, offset + 128);
    const items = chunk.map(tab => ({ tab, url: tab.pendingUrl || tab.url, token: crypto.randomUUID() }));
    for (const item of items) pendingVaultTabs.add(item.tab.id);
    let batchOK = false;
    try {
      const response = await nativeRequest({
        type: "vault_tabs", profile,
        tabs: items.map(({ token, url }) => ({ token, url }))
      });
      const confirmed = new Set(Array.isArray(response.tokens) ? response.tokens : []);
      batchOK = response.status === "ok" && items.every(item => confirmed.has(item.token));
      if (batchOK && isVeilActive) {
        for (const item of items) {
          queueTabChange(item.tab, item.url, pausedPage.href + "#token=" + item.token, () => isVeilActive);
        }
      }
    } catch (error) {
      console.warn("Veil tab batch was not confirmed:", error.message);
    } finally {
      for (const item of items) pendingVaultTabs.delete(item.tab.id);
    }
    if (!batchOK && isVeilActive && nativePort) {
      // Old daemon? Fine, fall back to one at a time.
      for (const item of items) pauseTab(item.tab, item.url).catch(console.warn);
    }
  }
}

function collectSensitiveBookmarks(nodes) {
  const found = [];
  function visit(node) {
    if (node.url && isAdult(node.url, node.title || "")) {
      found.push({
        id: node.id, parentId: node.parentId || "", index: node.index ?? 0,
        title: node.title || "", url: node.url, dateAdded: node.dateAdded || 0
      });
    }
    for (const child of node.children || []) visit(child);
  }
  for (const node of nodes) visit(node);
  return found;
}

async function executeConceal() {
  concealOpenTabs().catch(console.warn);
  if (concealInFlight || restoreInFlight || !nativePort || !isVeilActive) return;
  concealInFlight = true;
  try {
    const profile = await profileReady;
    const bookmarks = collectSensitiveBookmarks(await chrome.bookmarks.getTree());
    for (const item of bookmarks) {
      if (!isVeilActive || !nativePort) break;
      try {
        // Staging is AES-GCM-encrypted in the daemon and committed BEFORE deletion.
        const response = await nativeRequest({ type: "vault_bookmark", profile, item });
        if (response.status !== "ok" || !isVeilActive) continue;
        // Remove only the encrypted snapshot. If the bookmark changed,
        // moved or deleted it during IPC, cancel staging to avoid a phantom
        // bookmark being recreated on the next restoration.
        let unchanged = false;
        try {
          const current = await chrome.bookmarks.get(String(item.id));
          unchanged = !!current?.[0] && current[0].url === item.url &&
            (current[0].title || "") === item.title &&
            (current[0].parentId || "") === item.parentId &&
            (current[0].index ?? 0) === item.index;
        } catch { /* The original bookmark was removed or its profile closed. */ }
        if (!isVeilActive) continue;
        if (!unchanged) {
          await nativeRequest({ type: "unstage_bookmark", profile, vault_id: response.vault_id });
          continue;
        }
        try {
          await chrome.bookmarks.remove(item.id);
        } catch (error) {
          // Remove failed? Dont pretend that bookmark vanished.
          await nativeRequest({ type: "unstage_bookmark", profile, vault_id: response.vault_id });
          throw error;
        }
      } catch (error) {
        // Keep the original bookmark if there is no affirmative durable acknowledgement.
        console.warn("Veil retained bookmark; safe vaulting was not confirmed:", error.message);
      }
    }
    // History is intentionally not deleted by the extension: chrome.history.addUrl()
    // cannot reconstruct original timestamps, visit count, or transitions.
  } finally {
    concealInFlight = false;
    // If OFF arrived during a browser API call, restore after that call completes.
    if (!isVeilActive) executeRestore().catch(console.warn);
  }
}

async function hasBookmarkWithId(id) {
  try {
    const items = await chrome.bookmarks.get(String(id));
    return !!items?.[0];
  } catch { return false; }
}

async function existingRestoredBookmark(bm) {
  if (await hasBookmarkWithId(bm.guid)) return true;
  try {
    const children = await chrome.bookmarks.getChildren(bm.parent_guid);
    const atIndex = children.find(child => child.index === bm.original_index);
    return !!atIndex && atIndex.url === bm.url && atIndex.title === bm.title;
  } catch { return false; }
}

async function restoreBookmark(bm) {
  if (await existingRestoredBookmark(bm)) return { restored: true, createdId: null };
  const payload = {
    parentId: String(bm.parent_guid), index: Math.max(0, bm.original_index || 0),
    title: bm.title || "", url: bm.url
  };
  try {
    const created = await chrome.bookmarks.create(payload);
    return { restored: true, createdId: created.id };
  } catch {
    // Folder went missing? Use the first editable folder instead of loosing the bookmark.
    try {
      const tree = await chrome.bookmarks.getTree();
      const fallback = tree[0]?.children?.find(node => !node.url);
      if (!fallback) return { restored: false, createdId: null };
      const created = await chrome.bookmarks.create({ parentId: fallback.id, title: payload.title, url: payload.url });
      return { restored: true, createdId: created.id };
    } catch { return { restored: false, createdId: null }; }
  }
}

async function executeRestore() {
  if (restoreInFlight || concealInFlight || isVeilActive || !nativePort) return;
  restoreInFlight = true;
  try {
    const profile = await profileReady;
    const result = await nativeRequest({ type: "list_live_bookmarks", profile });
    if (result.status !== "ok" || !Array.isArray(result.bookmarks)) return;
    for (const bm of result.bookmarks) {
      if (isVeilActive || !nativePort) break;
      if (!bm.url) continue;
      const restored = await restoreBookmark(bm);
      if (isVeilActive) {
        // ON arrived while an async create was running. Remove only the newly
        // created bookmark and keep its original encrypted vault row intact.
        // This avoids creating a second vault record with the browser's new ID.
        if (restored.createdId != null) {
          try { await chrome.bookmarks.remove(String(restored.createdId)); }
          catch (error) { console.warn("Veil could not re-conceal an interrupted restore:", error); }
        }
        break;
      }
      if (restored.restored) {
        // Clear each vault row ONLY after a successful creation / confirmed existence.
        const response = await nativeRequest({ type: "bookmark_restored", profile, vault_id: bm.id });
        if (response.status !== "ok") console.warn("Veil kept unconfirmed vault entry", bm.id);
      }
    }
  } finally {
    restoreInFlight = false;
    // A new activation may have arrived while bookmark creation was in flight.
    if (isVeilActive) executeConceal().catch(console.warn);
  }
}

// -------------------------------------------------------------
// EVENT LISTENERS & BACKGROUND WORKER
// -------------------------------------------------------------
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  await stateReady;
  if (changeInfo.url) {
    const pausedURL = getPausedURL(changeInfo.url);
    if (pausedURL) {
      if (!isVeilActive && !revealOnDemand) {
        restorePausedTab(tab, changeInfo.url);
      }
      return;
    }
    if (isVeilActive) {
      let conceal = false;
      try {
        const url = new URL(changeInfo.url);
        const isSearch = url.hostname.includes("google.") || url.hostname.includes("brave.com") ||
                         url.hostname.includes("duckduckgo.com") || url.hostname.includes("bing.com");
        const query = isSearch && url.searchParams.get("q");
        conceal = !!query && isAdult("https://example.com/" + encodeURIComponent(query), query);
        conceal ||= isAdult(changeInfo.url, tab.title);
      } catch {}
      if (conceal) {
        pauseTab(tab, changeInfo.url);
        return;
      }
    }
  }

  if (pendingDiscardTabs.has(tabId)) {
    if (tab.active) {
      pendingDiscardTabs.delete(tabId);
    } else {
      if (changeInfo.audible) {
        chrome.tabs.update(tabId, { muted: true }).catch(() => {});
      }
      if (changeInfo.status === "complete") {
        setTimeout(() => {
          if (pendingDiscardTabs.has(tabId)) {
            pendingDiscardTabs.delete(tabId);
            chrome.tabs.discard(tabId).catch(() => {});
          }
        }, 300);
      }
    }
  }
});

chrome.tabs.onActivated.addListener((activeInfo) => {
  pendingDiscardTabs.delete(activeInfo.tabId);
  chrome.tabs.get(activeInfo.tabId, (tab) => {
    if (!chrome.runtime.lastError && tab && tab.mutedInfo && tab.mutedInfo.muted) {
      chrome.tabs.update(activeInfo.tabId, { muted: false }).catch(() => {});
    }
  });
});

// New tabs shouldnt sneak past while Veil is active.
chrome.tabs.onCreated.addListener(async (tab) => {
  await stateReady;
  if (!isVeilActive) return;
  const targetUrl = tab.pendingUrl || tab.url;
  if (targetUrl && isAdult(targetUrl, tab.title || "")) {
    pauseTab(tab, targetUrl);
  }
});

// Active auto-veiling for newly spawned browser windows
chrome.windows.onCreated.addListener(async (window) => {
  await stateReady;
  if (!isVeilActive) return;
  const tabs = await chrome.tabs.query({ windowId: window.id });
  for (const tab of tabs) {
    const targetUrl = tab.pendingUrl || tab.url;
    if (targetUrl && isAdult(targetUrl, tab.title || "")) {
      pauseTab(tab, targetUrl).catch(console.warn);
    }
  }
});

stateReady.then(connectNative);
