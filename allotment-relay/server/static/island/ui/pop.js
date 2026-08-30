const POP_MS = 280;

export function popIn(el) {
  if (!el) return;
  if (el._popTimer) {
    window.clearTimeout(el._popTimer);
    el._popTimer = 0;
    el._popOut = false;
  }
  el.hidden = false;
  el.classList.remove("is-out");
  el.classList.remove("is-pop");
  void el.offsetWidth;
  el.classList.add("is-pop");
}

export function popOut(el, done) {
  if (!el || el.hidden) {
    if (done) done();
    return;
  }
  if (el._popOut) return;
  el._popOut = true;
  el.classList.remove("is-pop");
  el.classList.add("is-out");
  el._popTimer = window.setTimeout(() => {
    el._popTimer = 0;
    el._popOut = false;
    el.hidden = true;
    el.classList.remove("is-out", "is-pop");
    if (done) done();
  }, POP_MS);
}
