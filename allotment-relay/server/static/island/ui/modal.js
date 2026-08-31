import { popIn, popOut } from "./pop.js?v=island-lilistall1";

function paintModal(html) {
  const root = document.getElementById("island-modal");
  if (!root) return null;
  root.innerHTML = html;
  popIn(root);
  return root;
}

export function showEvent(event) {
  if (!event) return;
  const root = paintModal(cardMarkup(`
      <h3>${esc(event.title || "岛上")}</h3>
      <p>${esc(event.narrative || "")}</p>
      <button type="button" class="island-btn primary wide" data-close-modal>收下</button>
  `));
  if (!root) return;
  root.querySelector("[data-close-modal]").addEventListener("click", hideModal);
  root.addEventListener("click", (ev) => {
    if (ev.target === root) hideModal();
  }, { once: true });
}

export function careActs(plot) {
  const acts = [];
  if (!plot) return acts;
  if (plot.state === "growing" || plot.state === "tending") {
    if (!plot.tended) acts.push({ id: "tend", label: "打理" });
    if (!plot.watered) acts.push({ id: "water", label: "浇水" });
    if (!plot.fertilized) acts.push({ id: "fertilize", label: "施肥" });
  }
  if (plot.state === "ready") {
    acts.push({
      id: "harvest",
      label: (plot.orchard || plot.shake) ? "收果" : "收菜",
      primary: true,
    });
    if (plot.shake) acts.push({ id: "shake", label: "摇一摇" });
  }
  if (plot.state === "overripe") {
    acts.push({ id: "compost", label: "堆肥" });
    acts.push({ id: "harvest", label: "清果", primary: true });
  }
  return acts;
}

export function showCareSheet(plot, { onAct, onClose } = {}) {
  const acts = careActs(plot);
  const title = plot.token && /[园棚]/.test(String(plot.token))
    ? String(plot.token)
    : `#${plot.slot}`;
  const crop = plot.name || "作物";
  const root = paintModal(cardMarkup(`
      <h3>${esc(title)} · ${esc(crop)}</h3>
      <p>${esc(plot.detail || "选一项。")}</p>
      <div class="island-care-acts">
        ${acts.map((a) => `<button type="button" class="island-btn ${a.primary ? "primary" : ""} wide" data-care="${esc(a.id)}">${esc(a.label)}</button>`).join("")}
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelectorAll("[data-care]").forEach((btn) => {
    btn.addEventListener("click", () => {
      hideModal();
      if (onAct) onAct(btn.getAttribute("data-care"));
    });
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showExpandSheet(snap, { onConfirm, onClose } = {}) {
  const offer = (snap && snap.offer) || {};
  const token = offer.token || "";
  const word = (snap && snap.next_word) || "下一块";
  const root = paintModal(cardMarkup(`
      <h3>开垦草地</h3>
      <p>${esc(word)} ${esc(token)} · ${esc(offer.cost)} 票 · 开垦 ${esc(offer.clear_eta || "一会儿")}</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认开垦</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showVendSheet(item, { onConfirm, onClose } = {}) {
  const label = (item && (item.label || item.name || item.item)) || "这件";
  const price = item && item.vend_price != null ? item.vend_price : "—";
  const root = paintModal(cardMarkup(`
      <h3>卖掉</h3>
      <p>${esc(label)} · 回收 ${esc(price)} 票</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认卖</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showHintSheet({ title, body, onClose } = {}) {
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "岸工坊")}</h3>
      <p>${esc(body || "")}</p>
      <button type="button" class="island-btn primary wide" data-close-modal>知道了</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showCheerSheet({ title, body, presets = [], onConfirm, onClose } = {}) {
  const chips = (presets || []).map((line) => (
    `<button type="button" class="island-btn wide" data-cheer="${esc(line)}">${esc(line)}</button>`
  )).join("");
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "哄荔栀")}</h3>
      <p>${esc(body || "说句好话。不是潮下猫猫，也不是小橘应援。")}</p>
      <label class="island-field">
        <span>好话</span>
        <input id="island-cheer-input" type="text" maxlength="100" placeholder="今晚生意好" autocomplete="off">
      </label>
      <div class="island-care-acts">
        ${chips}
        <button type="button" class="island-btn primary wide" data-act="confirm">说出去</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  const send = (text) => {
    const line = String(text || "").trim();
    if (!line) {
      toast("说点什么。荔栀不接受沉默的讨好。");
      return;
    }
    hideModal();
    if (onConfirm) onConfirm(line);
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    const input = root.querySelector("#island-cheer-input");
    send(input && input.value);
  });
  root.querySelectorAll("[data-cheer]").forEach((btn) => {
    btn.addEventListener("click", () => send(btn.getAttribute("data-cheer")));
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showPitchSheet({ title, body, titleMin = 2, bodyMin = 40, onConfirm, onClose } = {}) {
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "投稿")}</h3>
      <p>${esc(body || "标题和正文分开写。不是接现有潮闻，稿费也不是领薪。")}</p>
      <label class="island-field">
        <span>建议做成</span>
        <span class="island-care-acts">
          <button type="button" class="island-btn" data-pitch="">不指定</button>
          <button type="button" class="island-btn" data-pitch="潮闻">潮闻</button>
          <button type="button" class="island-btn" data-pitch="故事">故事</button>
        </span>
      </label>
      <label class="island-field">
        <span>标题</span>
        <input id="island-pitch-title" type="text" maxlength="48" placeholder="岸上旧收音机" autocomplete="off">
      </label>
      <label class="island-field">
        <span>正文</span>
        <textarea id="island-pitch-body" rows="5" maxlength="12000" placeholder="至少 ${bodyMin} 字。第一幕……"></textarea>
      </label>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">投出去</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  let pitch = "";
  const markPitch = () => {
    root.querySelectorAll("[data-pitch]").forEach((btn) => {
      btn.classList.toggle("is-on", (btn.getAttribute("data-pitch") || "") === pitch);
    });
  };
  markPitch();
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelectorAll("[data-pitch]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pitch = btn.getAttribute("data-pitch") || "";
      markPitch();
    });
  });
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    const head = String(root.querySelector("#island-pitch-title")?.value || "").trim();
    const text = String(root.querySelector("#island-pitch-body")?.value || "").trim();
    if (head.length < titleMin) {
      toast(`标题至少 ${titleMin} 个字。`);
      return;
    }
    if (text.length < bodyMin) {
      toast(`正文太短（至少 ${bodyMin} 字）。编剧社收稿，不是扔一张便签。`);
      return;
    }
    const line = pitch ? `${pitch} ${head} | ${text}` : `${head} | ${text}`;
    hideModal();
    if (onConfirm) onConfirm(line);
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showFormSheet({ title, body, fields = [], confirm, onConfirm, onClose } = {}) {
  const inputs = (fields || []).map((field, idx) => {
    const id = esc(field.id || idx);
    const max = esc(field.max || 48);
    const ph = esc(field.placeholder || "");
    if (field.type === "textarea") {
      return `<label class="island-field">
        <span>${esc(field.label || "")}</span>
        <textarea id="island-form-${id}" rows="${esc(field.rows || 4)}" maxlength="${max}" placeholder="${ph}"></textarea>
      </label>`;
    }
    return `<label class="island-field">
      <span>${esc(field.label || "")}</span>
      <input id="island-form-${id}" type="text" maxlength="${max}" placeholder="${ph}" autocomplete="off">
    </label>`;
  }).join("");
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "写下")}</h3>
      <p>${esc(body || "")}</p>
      ${inputs}
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">${esc(confirm || "确认")}</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    const vals = {};
    for (const field of fields) {
      const el = root.querySelector(`#island-form-${field.id}`);
      const text = String(el && el.value || "").trim();
      if (!text) {
        toast(field.empty || `先写下${field.label || "这一栏"}。`);
        return;
      }
      if (field.min && text.length < field.min) {
        toast(field.empty || `${field.label || "这一栏"}至少 ${field.min} 个字。`);
        return;
      }
      vals[field.id] = text;
    }
    hideModal();
    if (onConfirm) onConfirm(vals);
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showPickSheet({ title, body, options = [], onConfirm, onClose } = {}) {
  const rows = (options || []).map((row) => (
    `<button type="button" class="island-btn wide" data-pick="${esc(row.id)}">${esc(row.label)}</button>`
  )).join("");
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "选一个")}</h3>
      <p>${esc(body || "")}</p>
      <div class="island-care-acts">
        ${rows || `<p class="island-fine">这会儿没有可选的。</p>`}
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      hideModal();
      if (onConfirm) onConfirm(btn.getAttribute("data-pick"));
    });
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showActSheet({ title, body, confirm, onConfirm, onClose } = {}) {
  const root = paintModal(cardMarkup(`
      <h3>${esc(title || "确认")}</h3>
      <p>${esc(body || "做这一下？")}</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">${esc(confirm || "确认")}</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showBuySheet(item, { onConfirm, onClose } = {}) {
  const label = (item && (item.label || item.name)) || "这件";
  const price = item && item.price != null ? item.price : "—";
  const root = paintModal(cardMarkup(`
      <h3>买下来</h3>
      <p>${esc(label)} · ${esc(price)} 票</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认买</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care"));
  if (!root) return;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

function cardMarkup(inner, extraClass) {
  const cls = extraClass ? `island-card ${extraClass}` : "island-card";
  return `<article class="${cls}" role="dialog" style="background-image:url('/static/island/assets/prompt-frame.png')">
    <div class="island-card-inner">${inner}</div>
  </article>`;
}

export function hideModal() {
  const root = document.getElementById("island-modal");
  if (!root) return;
  popOut(root, () => {
    root.innerHTML = "";
  });
}

export function toast(text) {
  if (window.__islandBoot && typeof window.__islandBoot.toast === "function") {
    window.__islandBoot.toast(text);
    return;
  }
  const el = document.getElementById("island-toast");
  if (!el) return;
  el.hidden = false;
  el.removeAttribute("hidden");
  el.classList.remove("is-pop");
  void el.offsetWidth;
  el.classList.add("is-pop");
  el.textContent = text;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 3200);
}

export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
