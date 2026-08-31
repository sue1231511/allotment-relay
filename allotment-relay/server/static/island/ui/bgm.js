const SRC = {
  island: "/static/island/assets/audio/island",
};

const MUTE_KEY = "island-bgm-mute";

let current = "";
let el = null;
let want = false;

export function bgmMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setBgmMuted(on) {
  try {
    localStorage.setItem(MUTE_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
  if (el) el.muted = Boolean(on);
}

function pickSrc(base) {
  const probe = document.createElement("audio");
  if (probe.canPlayType("audio/mpeg")) return `${base}.mp3`;
  if (probe.canPlayType('audio/ogg; codecs="vorbis"') || probe.canPlayType("audio/ogg")) {
    return `${base}.ogg`;
  }
  return `${base}.mp3`;
}

function halt() {
  if (!el) {
    current = "";
    return;
  }
  el.pause();
  el.removeAttribute("src");
  el.load();
  el = null;
  current = "";
}

export function playBgm(id) {
  const base = SRC[id];
  if (!base) return;
  if (current === id && el) {
    el.muted = bgmMuted();
    if (el.paused) el.play().catch(() => {});
    return;
  }
  halt();
  current = id;
  el = new Audio(pickSrc(base));
  el.loop = true;
  el.preload = "auto";
  el.volume = 0.38;
  el.muted = bgmMuted();
  el.play().catch(() => {});
}

export function startIslandBgm() {
  want = true;
  playBgm("island");
}

export function stopBgm() {
  want = false;
  halt();
}

function unlock() {
  if (want) playBgm("island");
}

if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", unlock, true);
}
