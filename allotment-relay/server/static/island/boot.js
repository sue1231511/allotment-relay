/** 门页不靠 ES module。模块没跑起来也能贴凭证、进地图、看见报错。 */
(function () {
  var toastEl = document.getElementById("island-toast");
  var keyForm = document.getElementById("island-key-form");
  var enrollForm = document.getElementById("island-enroll-form");
  var keyInput = document.getElementById("island-key");
  var nameInput = document.getElementById("island-enroll-name");
  var enterBtn = document.getElementById("island-enter");
  var enrollBtn = document.getElementById("island-enroll-btn");
  var hintEl = document.getElementById("island-gate-hint");

  function toast(text) {
    if (!toastEl || !text) return;
    toastEl.hidden = false;
    toastEl.removeAttribute("hidden");
    toastEl.textContent = text;
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function () {
      toastEl.hidden = true;
    }, 3200);
  }

  function hint(text) {
    if (hintEl) hintEl.textContent = text || "";
  }

  function showGate() {
    var gate = document.getElementById("island-gate");
    var stage = document.getElementById("island-stage");
    var dock = document.getElementById("island-dock");
    var root = document.getElementById("island-root");
    document.body.classList.remove("is-playing");
    document.body.classList.remove("is-yards");
    if (root) root.classList.remove("is-playing");
    if (gate) gate.classList.remove("island-hidden");
    if (stage) {
      stage.classList.add("island-hidden");
      stage.hidden = true;
    }
    if (dock) dock.hidden = true;
    var bag = document.getElementById("island-bag-chip");
    var back = document.getElementById("island-back-chip");
    if (bag) bag.hidden = true;
    if (back) back.hidden = true;
  }

  function showPlay() {
    var gate = document.getElementById("island-gate");
    var stage = document.getElementById("island-stage");
    var dock = document.getElementById("island-dock");
    var root = document.getElementById("island-root");
    document.body.classList.add("is-playing");
    if (root) root.classList.add("is-playing");
    if (gate) gate.classList.add("island-hidden");
    if (stage) {
      stage.classList.remove("island-hidden");
      stage.hidden = false;
      stage.removeAttribute("hidden");
    }
    if (dock) dock.hidden = true;
    var bag = document.getElementById("island-bag-chip");
    if (bag) {
      bag.hidden = false;
      bag.removeAttribute("hidden");
    }
  }

  function loadKey() {
    try {
      if (typeof loadSavedKey === "function") {
        var fromSite = loadSavedKey();
        if (fromSite) return fromSite;
      }
      var raw = localStorage.getItem("tidal_island_steward_api_key");
      return raw && raw.indexOf("ar_sk_") === 0 ? raw : "";
    } catch (err) {
      return "";
    }
  }

  function saveKey(key) {
    try {
      if (typeof saveSiteKey === "function") saveSiteKey(key);
      else localStorage.setItem("tidal_island_steward_api_key", key);
    } catch (err) {
      /* 无痕模式 */
    }
  }

  function setBusy(on, mode) {
    window.__islandBusy = !!on;
    if (enterBtn) {
      enterBtn.disabled = !!on;
      enterBtn.textContent = on && mode !== "enroll" ? "正在进入…" : "进入地图";
    }
    if (enrollBtn) {
      enrollBtn.disabled = !!on;
      enrollBtn.textContent = on && mode === "enroll" ? "正在登记…" : "登记登岛";
    }
    if (on) hint(mode === "enroll" ? "正在登记这个名字。" : "正在进入地图。");
  }

  function fallbackScene(reason) {
    var root = document.getElementById("island-scene");
    var bar = document.getElementById("island-actionbar");
    if (root) {
      root.innerHTML =
        '<div class="island-fallback">' +
        "<b>地图脚本还没就绪</b>" +
        "<p>" + (reason || "换系统浏览器再打开这一页。") + "</p>" +
        "</div>";
    }
    if (bar) {
      bar.innerHTML = "";
      bar.hidden = true;
    }
  }

  function handoff(data, scene) {
    if (typeof window.__islandStart === "function") {
      return Promise.resolve(window.__islandStart(data, scene || "map"));
    }
    window.__islandPending = { data: data, scene: scene || "map" };
    showPlay();
    fallbackScene("页面还在加载地点。等一两秒再进。");
    return Promise.resolve();
  }

  function postSession(key, name) {
    var headers = {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: "Bearer " + key,
    };
    try {
      headers["Idempotency-Key"] =
        crypto && crypto.randomUUID ? crypto.randomUUID() : "idem-" + Date.now();
    } catch (err) {
      headers["Idempotency-Key"] = "idem-" + Date.now();
    }
    return fetch("/api/v1/session", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ api_key: key, name: name || "" }),
    }).then(function (res) {
      return res.text().then(function (raw) {
        var data = {};
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch (err) {
          throw new Error("服务端没有返回可读结果。");
        }
        if (!res.ok || data.ok === false) {
          var err = (data && data.error) || {};
          throw new Error(err.message || "没能进入地图。");
        }
        return data;
      });
    });
  }

  function enterWithKey(key, name) {
    if (window.__islandBusy) return Promise.resolve();
    key = String(key || "").trim();
    name = String(name || "").trim();
    if (!key) {
      toast("先把凭证贴上。");
      hint("凭证是 ar_sk_ 开头的那一串。");
      return Promise.resolve();
    }
    if (key.indexOf("ar_sk_") !== 0) {
      toast("凭证应以 ar_sk_ 开头。");
      hint("先去领取，再整段贴进来。");
      return Promise.resolve();
    }
    if (name && (name.length < 2 || name.length > 24)) {
      toast("岛上的名字要 2～24 个字。");
      return Promise.resolve();
    }
    saveKey(key);
    setBusy(true, name ? "enroll" : "enter");
    return postSession(key, name)
      .then(function (data) {
        if (!data.enrolled) {
          if (enrollForm) enrollForm.classList.remove("island-hidden");
          toast("先起一个岛上的名字。");
          hint("下面写下岛上的名字，再点登记登岛。");
          return;
        }
        hint("");
        showPlay();
        return handoff(data, name ? "home" : "map");
      })
      .catch(function (err) {
        showGate();
        toast((err && err.message) || "没能进入地图。");
        hint((err && err.message) || "没能进入地图。");
      })
      .then(function () {
        setBusy(false);
      });
  }

  function onEnter(ev) {
    if (ev) ev.preventDefault();
    enterWithKey(keyInput && keyInput.value, "");
  }

  function onEnroll(ev) {
    if (ev) ev.preventDefault();
    enterWithKey(loadKey() || (keyInput && keyInput.value), nameInput && nameInput.value);
  }

  if (keyInput && !keyInput.value) {
    var saved = loadKey();
    if (saved) keyInput.value = saved;
  }
  if (keyForm) {
    keyForm.setAttribute("novalidate", "novalidate");
    keyForm.addEventListener("submit", onEnter);
  }
  if (enterBtn) enterBtn.addEventListener("click", onEnter);
  if (enrollForm) {
    enrollForm.setAttribute("novalidate", "novalidate");
    enrollForm.addEventListener("submit", onEnroll);
  }
  if (enrollBtn) enrollBtn.addEventListener("click", onEnroll);

  window.__islandBoot = {
    toast: toast,
    hint: hint,
    showGate: showGate,
    showPlay: showPlay,
    loadKey: loadKey,
    saveKey: saveKey,
    enterWithKey: enterWithKey,
    handoff: handoff,
    fallbackScene: fallbackScene,
  };

  setTimeout(function () {
    if (window.__islandApp) return;
    toast("地图脚本偏慢。先点进入地图，或换系统浏览器打开。");
    hint("若点了没反应，换 Safari / Chrome 打开，不要停在微信里。");
  }, 4000);
})();
