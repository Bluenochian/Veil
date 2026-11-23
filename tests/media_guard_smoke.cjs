// A real browser isn't required to check the media guard's ON/OFF behavior.
// Run with: node tests/media_guard_smoke.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function check(browserName) {
  const source = fs.readFileSync(
    path.join(__dirname, "../browser-extension", browserName, "media-guard.js"),
    "utf8"
  );
  const listeners = {};
  const media = [];
  let block = false;
  let observer;

  const api = {
    runtime: {
      async sendMessage(message) {
        assert.equal(message.type, "VEIL_MEDIA_POLICY");
        return { block };
      }
    },
    storage: { onChanged: { addListener(fn) { listeners.storageChange = fn; } } }
  };
  class HTMLMediaElement {
    constructor() {
      this.nodeType = 1;
      this.muted = false;
      this.autoplay = true;
      this.preload = "auto";
      this.pauses = 0;
    }
    pause() { this.pauses++; }
    matches() { return true; }
  }
  class MutationObserver {
    constructor(fn) { this.fn = fn; observer = this; this.disconnected = false; }
    observe() {}
    disconnect() { this.disconnected = true; }
  }
  const document = {
    documentElement: {
      nodeType: 1,
      matches() { return false; },
      querySelectorAll() { return media; }
    },
    addEventListener(name, fn) { listeners[name] = fn; }
  };
  const window = { addEventListener(name, fn) { listeners[name] = fn; } };
  vm.runInNewContext(source, {
    browser: browserName === "firefox" ? api : undefined,
    chrome: browserName === "chrome" ? api : undefined,
    document, window, MutationObserver, HTMLMediaElement
  }, { filename: browserName + "/media-guard.js" });

  const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
  await flush();
  const video = new HTMLMediaElement();
  media.push(video);
  listeners.play({ target: video });
  assert.equal(video.pauses, 0, "Inactive must leave media alone");

  block = true;
  listeners.storageChange({ isVeilActive: { newValue: true } }, "local");
  await flush();
  assert.equal(video.muted, true);
  assert.equal(video.autoplay, false);
  assert.equal(video.preload, "none");
  assert.equal(video.pauses, 1);

  const audio = new HTMLMediaElement();
  observer.fn([{ addedNodes: [audio] }]);
  assert.equal(audio.pauses, 1, "New audio should be stopped too");

  block = false;
  listeners.storageChange({ isVeilActive: { newValue: false } }, "local");
  await flush();
  assert.equal(video.muted, false, "Restore original mute state");
  assert.equal(video.autoplay, true, "Restore autoplay preference");
  assert.equal(audio.muted, false);
  assert.equal(observer.disconnected, true);
  listeners.play({ target: audio });
  assert.equal(audio.pauses, 1, "OFF must leave media alone");
  process.stdout.write(browserName + ": media guard PASS\n");
}

(async () => {
  await check("chrome");
  await check("firefox");
})().catch(error => { console.error(error); process.exitCode = 1; });
