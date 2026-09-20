(function () {
  const NUDGE_DAY = "tidal-nudge-day";
  let deferredPrompt = null;

  function $(id) {
    return document.getElementById(id);
  }

  function utcDay() {
    return new Date().toISOString().slice(0, 10);
  }

  function register() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
  }

  function showInstall(on) {
    const btn = $("tidal-install");
    if (!btn) return;
    btn.classList.toggle("hidden", !on);
    btn.hidden = !on;
  }

  function paintNotifyBtn() {
    const btn = $("tidal-notify");
    if (!btn) return;
    if (!("Notification" in window) || Notification.permission !== "default") {
      btn.classList.add("hidden");
      btn.hidden = true;
      return;
    }
    btn.classList.remove("hidden");
    btn.hidden = false;
  }

  function alreadyToday() {
    try {
      return localStorage.getItem(NUDGE_DAY) === utcDay();
    } catch (err) {
      return true;
    }
  }

  function markToday() {
    try {
      localStorage.setItem(NUDGE_DAY, utcDay());
    } catch (err) { /* ignore quota */ }
  }

  function ripeCount(dash) {
    const parcels = (dash && dash.parcels) || [];
    return parcels.filter(function (p) {
      return p.state === "ready" || p.state === "overripe";
    }).length;
  }

  function dutyUrgent(dash) {
    const line = (dash && dash.meter_lines && dash.meter_lines.bar_duty) || "";
    return String(line).indexOf("\u26a0") === 0;
  }

  function taxArrears(dash) {
    const dues = (dash && dash.dues) || {};
    return Number(dues.tax_arrears || 0);
  }

  function summary(dash) {
    const bits = [];
    const ripe = ripeCount(dash);
    if (ripe) bits.push("有 " + ripe + " 块已经成熟");
    if (dutyUrgent(dash)) bits.push("酒吧值班快到期了");
    const tax = taxArrears(dash);
    if (tax) bits.push("岸税欠 " + tax);
    return bits.join("。");
  }

  function fire(body) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    if (alreadyToday()) return;
    try {
      new Notification("潮汐岛", {
        body: body,
        tag: "tidal-daily",
        icon: "/static/pwa/icon.svg",
      });
      markToday();
    } catch (err) { /* iOS old Notification ctor */ }
  }

  function askNotify() {
    if (!("Notification" in window)) return;
    Notification.requestPermission().then(function () {
      paintNotifyBtn();
    });
  }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    showInstall(true);
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    showInstall(false);
  });

  document.addEventListener("click", function (e) {
    const install = e.target && e.target.closest && e.target.closest("#tidal-install");
    if (install && deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        showInstall(false);
      });
      return;
    }
    const notify = e.target && e.target.closest && e.target.closest("#tidal-notify");
    if (notify) askNotify();
  });

  window.tidalPwa = {
    nudgeFromDash: function (dash) {
      paintNotifyBtn();
      const body = summary(dash);
      if (!body) return;
      fire(body + "。");
    },
  };

  register();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paintNotifyBtn);
  } else {
    paintNotifyBtn();
  }
})();
