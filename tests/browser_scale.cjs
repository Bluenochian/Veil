// Deterministic 100-sensitive-tab workload in a simulated browser profile.
// Run: node tests/browser_scale.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, limit = 10000) {
  const end = performance.now() + limit;
  while (!check()) {
    if (performance.now() > end) throw Error('100-tab lifecycle timed out');
    await sleep(5);
  }
}
async function run(browser, count = 100) {
  const code = fs.readFileSync(path.join(__dirname, '..', 'browser-extension', browser, 'background.js'), 'utf8');
  const profile = '11111111-1111-4111-8111-111111111111';
  const original = (id) => `https://pornhub.com/view_video.php?viewkey=sample-${id}`;
  const tabs = Array.from({length: count}, (_, i) => ({
    id: i + 1, active: i === 0, url: original(i), title: `Video ${i}`, index: i
  }));
  // Untargeted tabs must be left alone under load.
  for (let i = 0; i < 50; i++) tabs.push({id: 1000+i, active:false, url:`https://github.com/safe/repo${i}`, title:'Safe'});
  const tokenVault = new Map();
  const listeners = {};
  const storage = { veilProfileID: profile, isVeilActive:false, revealOnDemand:false };
  const counts = { update:0, store:0, storeBatch:0, resolve:0, resolveBatch:0, clear:0, clearBatch:0 };
  const event = key => ({addListener(fn) { listeners[key] = fn; }});
  let nativeSeq = 0;
  const send = (message) => {
    nativeSeq++;
    const resp = { request_id: message.request_id, type:'ack', status:'ok' };
    if (message.type === 'vault_tab') { counts.store++; tokenVault.set(message.token, message.url); }
    if (message.type === 'vault_tabs') { counts.storeBatch++; for (const item of message.tabs) tokenVault.set(item.token, item.url); resp.tokens = message.tabs.map(t=>t.token); }
    if (message.type === 'resolve_tab') { counts.resolve++; resp.url = tokenVault.get(message.token); resp.status = resp.url ? 'ok' : 'error'; }
    if (message.type === 'resolve_tabs') { counts.resolveBatch++; resp.tabs = Object.fromEntries(message.tokens.filter(k=>tokenVault.has(k)).map(k => [k,tokenVault.get(k)])); }
    if (message.type === 'clear_tab') { counts.clear++; tokenVault.delete(message.token); }
    if (message.type === 'clear_tabs') { counts.clearBatch++; for (const t of message.tokens) tokenVault.delete(t); }
    if (message.type === 'list_live_bookmarks') resp.bookmarks=[];
    setTimeout(() => listeners.message(resp), 1);
  };
  const mock = {
    runtime: { id:'simulated', getURL: rel => `${browser === 'firefox' ? 'moz-extension' : 'chrome-extension'}://simulated/${rel}`, connectNative:()=>({postMessage:send,onMessage:event('message'),onDisconnect:event('disconnect')}), onMessage:event('runtimeMessage'), reload(){} },
    storage: {local:{async get(keys){ return {...keys,...storage}; },async set(values){ Object.assign(storage,values); }}},
    action: {onClicked:event('click'), setBadgeText(){},setBadgeBackgroundColor(){},setTitle(){},setIcon(){}},
    tabs:{
      onUpdated:event('updated'),onActivated:event('activated'),onCreated:event('created'),
      async query() {return tabs.map(t=>({...t}));},
      async get(id) {const t=tabs.find(t=>t.id===id);if(!t)throw Error('not found');return {...t};},
      async update(id, {url}) {await sleep(2);const t=tabs.find(t=>t.id===id);t.url=url;counts.update++;return {...t};},
      async reload() {}, async discard(){}
    },
    windows:{onCreated:event('windowCreated')},
    bookmarks:{async getTree(){return [];}, async get(){return [];}, async getChildren(){return [];}, async create(x){return x;}, async remove(){}},
    history:{search(){throw Error('unexpected history access');}, deleteUrl(){throw Error('history deletion');}}
  };
  vm.runInNewContext(code, {chrome: browser === 'chrome' ? mock : undefined, browser: browser === 'firefox' ? mock : undefined, URL, crypto:webcrypto, console,setTimeout,clearTimeout,queueMicrotask,globalThis:{VEIL_EXTENSION_REVISION:'scale-test'}}, {filename: browser+'/background.js'});
  await sleep(20);
  const startConceal = performance.now();
  listeners.message({type:'state',active:true,reveal_on_demand:false,rules:{whitelist:[],blacklist:[]}});
  await until(()=>tabs.slice(0,count).every(t=>t.url.includes('/paused.html#token=')));
  const concealMs=performance.now()-startConceal;
  assert(tabs.slice(count).every(t=>t.url.startsWith('https://github.com/')));
  assert.equal(tokenVault.size,count);
  const startRestore = performance.now();
  listeners.message({type:'state',active:false,reveal_on_demand:false,rules:{whitelist:[],blacklist:[]}});
  await until(()=>tabs.slice(0,count).every((t,i)=>t.url===original(i)));
  const restoreMs=performance.now()-startRestore;
  await sleep(50);
  assert.equal(tokenVault.size,0,'all restored tokens should be cleared');
  assert.equal(counts.update,count*2,'no redundant navigation');
  return { browser, count, concealMs: Math.round(concealMs), restoreMs: Math.round(restoreMs), nativeMessages:nativeSeq, ...counts };
}
(async()=>{
  for(const browser of ['chrome','firefox']) console.log(JSON.stringify(await run(browser, Number(process.env.VEIL_SCALE_TABS || '100'))));
})().catch(e=>{console.error(e);process.exitCode=1;});
