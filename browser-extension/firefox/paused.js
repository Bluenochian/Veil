const veilApi = typeof browser !== "undefined" ? browser : chrome;

const scene = document.querySelector(".scene");
const hero = document.querySelector(".hero");
const revealArea = document.getElementById("reveal-area");
const revealButton = document.getElementById("reveal-button");
const feedback = document.getElementById("reveal-feedback");
const modeCopy = document.querySelectorAll(".copy-on, .copy-off");
const favicon = document.getElementById("veil-favicon");

let revealAttempt = 0;

function resetReveal() {
  revealAttempt++;
  scene.classList.remove("is-revealing");
  revealButton.disabled = false;
  feedback.textContent = "";
}

function renderState({ isVeilActive, revealOnDemand }) {
  const canReveal = isVeilActive === false && revealOnDemand !== false;
  const mode = canReveal ? "off" : "on";
  if (document.body.dataset.mode === mode) return;

  if (!canReveal && revealArea.contains(document.activeElement)) {
    document.activeElement.blur();
  }
  resetReveal();
  document.body.dataset.mode = mode;
  favicon.href = canReveal ? "icons/icon48-off.png" : "icons/icon48.png";
  revealArea.inert = !canReveal;
  revealArea.setAttribute("aria-hidden", String(!canReveal));
  for (const el of modeCopy) {
    el.setAttribute("aria-hidden", String(el.classList.contains("copy-on") === canReveal));
  }
}

let stateRead = 0;
async function refreshState() {
  const read = ++stateRead;
  try {
    const state = await veilApi.storage.local.get(["isVeilActive", "revealOnDemand"]);
    if (read === stateRead) renderState(state);
  } catch {
    // Keep the tab covered if the extension state is unavailable.
  }
}

veilApi.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && ("isVeilActive" in changes || "revealOnDemand" in changes)) {
    refreshState();
  }
});

window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    resetReveal();
    refreshState();
  }
});

revealButton.addEventListener("click", async () => {
  if (document.body.dataset.mode !== "off" || revealButton.disabled) return;

  const attempt = ++revealAttempt;
  revealButton.disabled = true;
  feedback.textContent = "";
  scene.classList.add("is-revealing");

  // Give the artwork a moment to fade; reduced-motion skips the wait.
  // That ambient animation never ends. Awaiting .finished is a trap.
  // Keep Reveal short and interruptable. Users shouldnt fight the animation.
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    await new Promise(resolve => setTimeout(resolve, 430));
  }
  if (attempt !== revealAttempt) return;

  try {
    const result = await veilApi.runtime.sendMessage({ type: "VEIL_REVEAL_TAB" });
    if (!result?.ok) throw new Error(result?.error || "Could not reveal this tab.");
  } catch (error) {
    if (attempt !== revealAttempt) return;
    resetReveal();
    feedback.textContent = error.message || "Could not reveal this tab.";
    revealButton.focus();
  }
});

const particleLayer = document.getElementById("particles");

function populateParticles() {
  let seed = 38402;
  function random() {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  }
  
  const particles = document.createDocumentFragment();
  for (let i = 0; i < 94; i++) {
    const dot = document.createElement("i");
    dot.className = "mote";
    dot.style.setProperty("--x", (5 + random() * 90).toFixed(2) + "%");
    dot.style.setProperty("--y", (53 + random() * 35).toFixed(2) + "%");
    dot.style.setProperty("--r", (0.8 + random() * 1.5).toFixed(2) + "px");
    dot.style.setProperty("--dx", (-30 + random() * 60).toFixed(1) + "px");
    dot.style.setProperty("--dur", (11 + random() * 13).toFixed(1) + "s");
    dot.style.setProperty("--delay", (-random() * 23).toFixed(1) + "s");
    dot.style.setProperty("--peak", (0.22 + random() * 0.3).toFixed(2));
    particles.appendChild(dot);
  }
  particleLayer.appendChild(particles);
}

function updateVisibility() {
  document.body.classList.toggle("is-background", document.hidden);
  if (document.hidden) {
    particleLayer.replaceChildren();
    return;
  }
  for (const image of document.querySelectorAll(".emblem[data-src]")) {
    if (!image.hasAttribute("src")) image.src = image.dataset.src;
  }
  if (!particleLayer.firstChild) populateParticles();
}

document.addEventListener("visibilitychange", updateVisibility);
updateVisibility();
refreshState();
