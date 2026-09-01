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
    toastEl.classList.remove("is-pop");
    void toastEl.offsetWidth;
    toastEl.classList.add("is-pop");
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
    var bgm = document.getElementById("island-bgm-chip");
    if (bag) bag.hidden = true;
    if (back) back.hidden = true;
    if (bgm) bgm.hidden = true;
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
    var back = document.getElementById("island-back-chip");
    if (bag) bag.hidden = true;
    if (back) back.hidden = true;
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

  var MAP_PICS = ["/static/island/assets/scenes/island-map.jpg"];
  var SCENE_PICS = [
    "atelier", "bar", "beach", "clinic", "eatery", "hall", "hui", "hut-1", "hut-2", "hut-3", "hut-4",
    "island-map", "lianli", "lighthouse", "lili", "market", "plaza", "port", "quarry", "shop", "shore",
    "theater", "ting", "workshop", "writers", "yards"
  ].map(function (id) { return "/static/island/assets/scenes/" + id + ".webp"; });
  var VEIL_MS = 30000;
  var PIC_MS = 25000;
  var veilTimer = 0;
  var allScenesPromise = null;

  function showVeil(text, withProgress) {
    var el = document.getElementById("island-boot-veil");
    if (!el) return;
    var line = el.querySelector("p");
    var progress = el.querySelector("progress");
    var count = el.querySelector("small");
    if (line) line.textContent = text || "正在进入…";
    if (progress) {
      progress.hidden = !withProgress;
      if (withProgress) {
        progress.max = SCENE_PICS.length;
        progress.value = 0;
      }
    }
    if (count) {
      count.hidden = !withProgress;
      if (withProgress) count.textContent = "0 / " + SCENE_PICS.length + " 个地点";
    }
    el.hidden = false;
    el.removeAttribute("hidden");
    document.body.classList.add("is-entering");
    clearTimeout(veilTimer);
    veilTimer = setTimeout(hideVeil, VEIL_MS);
  }

  function hideVeil() {
    clearTimeout(veilTimer);
    veilTimer = 0;
    var el = document.getElementById("island-boot-veil");
    if (el) el.hidden = true;
    document.body.classList.remove("is-entering");
  }

  function withTimeout(promise, ms, message) {
    return new Promise(function (resolve, reject) {
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        reject(new Error(message || "等太久了。再点一次进入地图。"));
      }, ms);
      promise.then(
        function (value) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve(value);
        },
        function (err) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          reject(err);
        }
      );
    });
  }

  function preload(urls, timeoutMs, onProgress) {
    urls = urls || MAP_PICS;
    timeoutMs = timeoutMs || 8000;
    return Promise.all(
      urls.map(function (src) {
        return new Promise(function (resolve) {
          var done = false;
          var finish = function () {
            if (done) return;
            done = true;
            if (onProgress) onProgress();
            resolve();
          };
          var img = new Image();
          img.onload = finish;
          img.onerror = finish;
          img.src = src;
          setTimeout(finish, timeoutMs);
        });
      })
    );
  }

  function preloadAllScenes() {
    if (allScenesPromise) return allScenesPromise;
    clearTimeout(veilTimer);
    veilTimer = 0;
    var veil = document.getElementById("island-boot-veil");
    var progress = veil && veil.querySelector("progress");
    var count = veil && veil.querySelector("small");
    var completed = 0;
    var total = SCENE_PICS.length;
    if (progress) {
      progress.hidden = false;
      progress.max = total;
      progress.value = 0;
    }
    if (count) {
      count.hidden = false;
      count.textContent = "0 / " + total + " 个地点";
    }
    allScenesPromise = preload(SCENE_PICS, PIC_MS, function () {
      completed += 1;
      if (progress) progress.value = completed;
      if (count) count.textContent = completed + " / " + total + " 个地点";
    });
    return allScenesPromise;
  }

  function afterPaint() {
    return new Promise(function (resolve) {
      if (typeof requestAnimationFrame !== "function") {
        resolve();
        return;
      }
      requestAnimationFrame(function () {
        requestAnimationFrame(resolve);
      });
    });
  }

  function picHasPixels(img) {
    return !!(img && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0);
  }

  function waitOnePic(img, timeoutMs) {
    return new Promise(function (resolve) {
      var settled = false;
      function finish() {
        if (settled) return;
        settled = true;
        resolve();
      }
      var timer = setTimeout(finish, timeoutMs);

      function painted() {
        if (settled) return;
        clearTimeout(timer);
        afterPaint().then(finish);
      }

      function decodeThen() {
        if (settled) return;
        if (picHasPixels(img) && typeof img.decode === "function") {
          img.decode().then(painted, painted);
        } else {
          painted();
        }
      }

      function onDomLoad() {
        img.removeEventListener("load", onDomLoad);
        img.removeEventListener("error", onDomErr);
        decodeThen();
      }
      function onDomErr() {
        img.removeEventListener("load", onDomLoad);
        img.removeEventListener("error", onDomErr);
        painted();
      }

      img.addEventListener("load", onDomLoad);
      img.addEventListener("error", onDomErr);

      if (picHasPixels(img)) {
        decodeThen();
        return;
      }

      var src = img.currentSrc || img.src;
      if (!src) {
        painted();
        return;
      }

      var probe = new Image();
      probe.onload = function () {
        if (settled) return;
        if (picHasPixels(img)) {
          decodeThen();
          return;
        }
        img.addEventListener("load", onDomLoad);
      };
      probe.onerror = onDomErr;
      probe.src = src;
    });
  }

  function waitPics(root, timeoutMs) {
    root = root || document.getElementById("island-scene");
    timeoutMs = timeoutMs || PIC_MS;
    if (!root) return Promise.resolve();
    var imgs = root.querySelectorAll(".island-slot-pic, .island-vn-sprite");
    var ready = imgs.length
      ? Promise.all(
          Array.prototype.map.call(imgs, function (img) {
            return waitOnePic(img, timeoutMs);
          })
        )
      : Promise.resolve();
    return ready.then(afterPaint).then(function () {
      try {
        window.dispatchEvent(new Event("resize"));
      } catch (err) {
        /* 旧浏览器 */
      }
      return afterPaint();
    });
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
    showVeil("正在准备 26 个地点…", true);
    setBusy(true, name ? "enroll" : "enter");
    return withTimeout(postSession(key, name), 12000, "号还没接上。再点一次进入地图。")
      .then(function (data) {
        if (!data.enrolled) {
          hideVeil();
          if (enrollForm) enrollForm.classList.remove("island-hidden");
          toast("先起一个岛上的名字。");
          hint("下面写下岛上的名字，再点登记登岛。");
          return;
        }
        hint("");
        return handoff(data, name ? "home" : "map");
      })
      .catch(function (err) {
        hideVeil();
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
    showVeil: showVeil,
    hideVeil: hideVeil,
    preload: preload,
    preloadAllScenes: preloadAllScenes,
    waitPics: waitPics,
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
