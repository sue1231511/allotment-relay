const TRACKS = [
  { id: "island", base: "/static/island/assets/audio/island", ogg: true },
  { id: "enchanted-garden", base: "/static/island/assets/audio/vadim_makes_sound-fantasy-worlds-enchanted-garden-570007", ogg: false },
];
const BUST = "island-two-track-bgm1";

const MUTE_KEY = "island-bgm-mute";

let current = "";
let el = null;
let want = false;
let trackIndex = 0;

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

function pickSrc(track) {
  const probe = document.createElement("audio");
  let file = `${track.base}.mp3`;
  if (track.ogg && !probe.canPlayType("audio/mpeg") && (probe.canPlayType('audio/ogg; codecs="vorbis"') || probe.canPlayType("audio/ogg"))) {
    file = `${track.base}.ogg`;
  }
  return `${file}?v=${BUST}`;
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
  const nextIndex = TRACKS.findIndex((track) => track.id === id);
  if (nextIndex < 0) return;
  if (current === id && el) {
    el.muted = bgmMuted();
    if (el.paused) el.play().catch(() => {});
    return;
  }
  halt();
  trackIndex = nextIndex;
  const track = TRACKS[trackIndex];
  current = id;
  el = new Audio(pickSrc(track));
  el.loop = false;
  el.preload = "auto";
  el.volume = 0.38;
  el.muted = bgmMuted();
  el.addEventListener("ended", () => {
    const next = TRACKS[(trackIndex + 1) % TRACKS.length];
    playBgm(next.id);
  });
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
