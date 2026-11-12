// Run with `node tests/browser_extension_smoke.cjs`.
// Minimal browser API simulation verifies critical lifecycle behavior without
// installing an extension into a real browser profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { webcrypto } = require('node:crypto');

const snooze = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));

async function test(browser) {
  const src = fs.readFileSync(path.join(__dirname, `../browser-extension/${browser}/background.js`), 'utf8');
  const PROFILE = '11111111-1111-4111-8111-111111111111';
  const original = 'https://www.pornhub.com/view_video.php?viewkey=abc123';
  const storage = { isVeilActive: false, revealOnDemand: true, veilProfileID: PROFILE };
  const bookmarks = [{ id: '99', parentId: '1', index: 0, title: 'Video', url: original }];
  const tabs = [{ id: 1, windowId: 5, index: 0, active: true, url: original, title: 'Video' }];
  const vault = new Map();
  const vaultedBookmarks = [];
  const historyActions = [];
  const listeners = {};
  const operations = [];
  let currentActive = false;
  let pausedURL = null;
  let connectName = null;
  let removeBeforeAck = false;
  let createBarrier = null;
  let editDuringVaultAck = false;

  function event(name) {
    return { addListener(fn) { listeners[name] = fn; } };
  }
  const port = {
    onMessage: event('nativeMessage'),
    onDisconnect: event('nativeDisconnect'),
    postMessage(message) {
      operations.push(message.type);
      if (message.type === 'vault_tabs') {
        assert(currentActive);
        for (const item of message.tabs) vault.set(item.token, item.url);
        queueMicrotask(() => listeners.nativeMessage({type:'tabs_vault_ack',status:'ok',tokens:message.tabs.map(i=>i.token),request_id:message.request_id}));
      } else if (message.type === 'resolve_tabs') {
        assert(!currentActive);
        const tabs = Object.fromEntries(message.tokens.filter(k => vault.has(k)).map(k => [k,vault.get(k)]));
        queueMicrotask(() => listeners.nativeMessage({type:'tabs_resolve',status:'ok',tabs,request_id:message.request_id}));
      } else if (message.type === 'clear_tabs') {
        for (const token of message.tokens) vault.delete(token);
        queueMicrotask(() => listeners.nativeMessage({type:'tabs_clear_ack',status:'ok',request_id:message.request_id}));
      } else if (message.type === 'vault_tab') {
        assert(currentActive);
        vault.set(message.token, message.url);
        queueMicrotask(() => listeners.nativeMessage({ type: 'tab_vault_ack', status: 'ok', request_id: message.request_id }));
      } else if (message.type === 'vault_bookmark') {
        assert(currentActive);
        vaultedBookmarks.push({ id: 42, guid: message.item.id, parent_guid: message.item.parentId, original_index: message.item.index, url: message.item.url, title: message.item.title });
        if (editDuringVaultAck) {
          // Change the bookmark after encryption but before deletion.
          bookmarks[0].url = 'https://example.net/new';
          bookmarks[0].title = 'Edited safely';
        }
        queueMicrotask(() => listeners.nativeMessage({ type: 'vault_ack', status: 'ok', vault_id: 42, request_id: message.request_id }));
      } else if (message.type === 'unstage_bookmark') {
        vaultedBookmarks.splice(0);
        queueMicrotask(() => listeners.nativeMessage({ type: 'unstage_ack', status: 'ok', request_id: message.request_id }));
      } else if (message.type === 'list_live_bookmarks') {
        queueMicrotask(() => listeners.nativeMessage({ type: 'live_bookmarks', status: 'ok', bookmarks: [...vaultedBookmarks], request_id: message.request_id }));
      } else if (message.type === 'bookmark_restored') {
        vaultedBookmarks.splice(0);
        queueMicrotask(() => listeners.nativeMessage({ type: 'bookmark_restored_ack', status: 'ok', request_id: message.request_id }));
      } else if (message.type === 'resolve_tab') {
        queueMicrotask(() => listeners.nativeMessage({ type: 'tab_resolve', status: vault.has(message.token) ? 'ok' : 'error', url: vault.get(message.token) || null, request_id: message.request_id }));
      } else if (message.type === 'clear_tab') {
        vault.delete(message.token);
        queueMicrotask(() => listeners.nativeMessage({ type: 'tab_clear_ack', status: 'ok', request_id: message.request_id }));
      }
    }
  };
  const chrome = {
    runtime: {
      id: 'some-extension-id',
      getURL(rel) { return `${browser === "firefox" ? "moz-extension" : "chrome-extension"}://some-extension-id/${rel}`; },
      connectNative(name) { connectName = name; return port; },
      onMessage: event('runtimeMessage'), reload() {}
    },
    storage: {
      local: {
        async get(defaults) {
          if (Array.isArray(defaults)) return Object.fromEntries(defaults.map(k => [k, storage[k]]));
          return { ...defaults, ...storage };
        },
        async set(values) { Object.assign(storage, values); },
        remove() {}
      }
    },
    action: {
      onClicked: event('actionClick'),
      setBadgeText() {}, setBadgeBackgroundColor() {}, setTitle() {}, setIcon() {}
    },
    tabs: {
      onUpdated: event('tabUpdated'), onActivated: event('tabActivated'), onCreated: event('tabCreated'),
      async query() { return tabs.map(t => ({ ...t })); },
      async get(id) { const t = tabs.find(t => t.id === id); if (!t) throw Error('No tab'); return { ...t }; },
      async update(id, props) {
        const t = tabs.find(t => t.id === id);
        t.url = props.url || t.url;
        if (t.url.includes('paused.html')) pausedURL = t.url;
        return { ...t };
      },
      async reload() {}, async discard() {}
    },
    windows: { onCreated: event('windowCreated') },
    bookmarks: {
      async getTree() {
        return [{ id: '0', children: [{ id: '1', children: bookmarks.map(b => ({ ...b })) }] }];
      },
      async remove(id) {
        if (!vaultedBookmarks.length) removeBeforeAck = true;
        const index = bookmarks.findIndex(b => b.id === id);
        if (index === -1) throw Error('Missing bookmark');
        bookmarks.splice(index, 1);
      },
      async create(bm) {
        if (createBarrier) {
          const barrier = createBarrier;
          barrier.enter();
          await barrier.wait;
        }
        const item = { ...bm, id: String(100 + bookmarks.length), index: bm.index || 0 };
        bookmarks.push(item);
        return item;
      },
      async get(id) { const result = bookmarks.filter(b => b.id === id); if (!result.length) throw Error('Not found'); return result; },
      async getChildren(id) { return bookmarks.filter(b => b.parentId === id); }
    },
    history: {
      search() { historyActions.push('search'); },
      deleteUrl() { historyActions.push('delete'); },
      addUrl() { historyActions.push('add'); }
    }
  };
  const sandbox = vm.createContext({
    chrome: browser === 'chrome' ? chrome : undefined,
    browser: browser === 'firefox' ? chrome : undefined,
    URL, crypto: webcrypto, console, setTimeout, clearTimeout, queueMicrotask,
    globalThis: { VEIL_EXTENSION_REVISION: 'test' }
  });
  vm.runInContext(src, sandbox, { filename: `${browser}/background.js` });
  await snooze(10);
  assert.equal(connectName, 'com.veil.privacy');

  // Check custom list precedence and malformed percent escaping.
  listeners.nativeMessage({ type: 'state', active: false,
    rules: { whitelist: ['pornhub.com'], blacklist: ['*.example.com', 'pornhub.com'] } });
  assert.equal(vm.runInContext('isAdult("https://pornhub.com/%GG")', sandbox), false,
    'Explicit whitelist outranks sensitive host and blacklist');
  assert.equal(vm.runInContext('isAdult("https://abc.example.com/safe")', sandbox), true,
    'Custom wildcard blacklist must apply to otherwise clean sites');
  assert.equal(vm.runInContext('isAdult("https://totallyexample.com/safe")', sandbox), false,
    'Custom domain glob must not overmatch');
  listeners.nativeMessage({ type: 'state', active: false,
    rules: { whitelist: [], blacklist: [] } });
  assert.equal(vm.runInContext('isAdult("https://pornhub.com/%GG")', sandbox), true,
    'Bad URL encoding cannot bypass a sensitive host');

  currentActive = true;
  listeners.nativeMessage({ type: 'state', active: true, reveal_on_demand: true });
  await snooze(60);
  assert(!removeBeforeAck, 'Bookmark must stay until vault acknowledgement');
  assert.equal(bookmarks.length, 0);
  assert(pausedURL && /#token=[a-f0-9-]{36}$/.test(pausedURL));
  assert(!pausedURL.includes('pornhub.com'), 'Original URL must never appear in paused address bar');
  assert.equal(historyActions.length, 0, 'Live browser history must remain untouched');

  // Rapid OFF -> ON while an async bookmark creation is running.
  // Its newly-created bookmark must be rolled back, leaving the original
  // encrypted vault record intact rather than doubling the backup entries.
  let enterRestore, releaseRestore;
  const createStarted = new Promise(resolve => { enterRestore = resolve; });
  const mayCreate = new Promise(resolve => { releaseRestore = resolve; });
  createBarrier = { enter: enterRestore, wait: mayCreate };
  currentActive = false;
  listeners.nativeMessage({ type: 'state', active: false, reveal_on_demand: true });
  await createStarted;
  currentActive = true;
  listeners.nativeMessage({ type: 'state', active: true, reveal_on_demand: true });
  createBarrier = null;
  releaseRestore();
  await snooze(70);
  assert.equal(bookmarks.length, 0, 'Interrupted restore cannot leave exposed bookmarks');
  assert.equal(vaultedBookmarks.length, 1, 'Interrupted restore must preserve one vault copy');

  currentActive = false;
  listeners.nativeMessage({ type: 'state', active: false, reveal_on_demand: true });
  await snooze(60);
  assert.equal(bookmarks.length, 1, 'Bookmarks should be restored with original parent');
  assert.equal(bookmarks[0].parentId, '1');
  assert.equal(bookmarks[0].url, original);
  assert.equal(vaultedBookmarks.length, 0);
  assert.equal(tabs[0].url, pausedURL, 'Tabs stay masked until Reveal click');

  const result = await new Promise(resolve => {
    const sender = { id: chrome.runtime.id, frameId: 0, tab: { id: 1 }, url: pausedURL };
    listeners.runtimeMessage({ type: 'VEIL_REVEAL_TAB' }, sender, resolve);
  });
  assert.equal(result.ok, true);
  assert.equal(tabs[0].url, original);
  await snooze(60); // Cleanup batches can flush after navigation succeeds.
  assert.equal(vault.size, 0, 'Tab URL must be deleted from vault after confirmed restoration');

  // A concurrent bookmark edit must survive, and its stale staged snapshot
  // must not reappear as a phantom duplicate after Veil is switched off.
  tabs[0].url = 'https://example.net/safe';
  bookmarks.splice(0, bookmarks.length, { id: '77', parentId: '1', index: 0, title: 'Video', url: original });
  editDuringVaultAck = true;
  currentActive = true;
  listeners.nativeMessage({ type: 'state', active: true, reveal_on_demand: true });
  await snooze(100);
  assert.equal(bookmarks.length, 1, 'Stale bookmark edit must not be deleted');
  assert.equal(bookmarks[0].url, 'https://example.net/new', 'Concurrent edit should be retained');
  assert.equal(vaultedBookmarks.length, 0, 'Stale vault entry must be cancelled');
  currentActive = false;
  listeners.nativeMessage({ type: 'state', active: false, reveal_on_demand: true });
  await snooze(100);
  assert.equal(bookmarks.length, 1, 'Restoration must not recreate outdated bookmark');
  console.log(`${browser}: lifecycle, races, stale-edit recovery, vault and reveal PASS`);
}

(async () => {
  await test('chrome');
  await test('firefox');
})().catch(error => { console.error(error); process.exitCode = 1; });
