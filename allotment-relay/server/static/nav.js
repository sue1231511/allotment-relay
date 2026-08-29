(function () {
  const drawer = document.getElementById('islandDrawer');
  const backdrop = document.getElementById('islandBackdrop');
  const closeBtn = document.getElementById('islandDrawerClose');
  const openBtns = document.querySelectorAll('[data-open-island]');

  if (drawer && backdrop && openBtns.length) {
    function openDrawer() {
      drawer.classList.add('is-open');
      backdrop.hidden = false;
      drawer.setAttribute('aria-hidden', 'false');
      openBtns.forEach((btn) => btn.setAttribute('aria-expanded', 'true'));
      document.body.classList.add('island-drawer-open');
    }

    function closeDrawer() {
      drawer.classList.remove('is-open');
      backdrop.hidden = true;
      drawer.setAttribute('aria-hidden', 'true');
      openBtns.forEach((btn) => btn.setAttribute('aria-expanded', 'false'));
      document.body.classList.remove('island-drawer-open');
    }

    openBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        if (drawer.classList.contains('is-open')) closeDrawer();
        else openDrawer();
      });
    });

    closeBtn?.addEventListener('click', closeDrawer);
    backdrop.addEventListener('click', closeDrawer);

    drawer.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', closeDrawer);
    });

    const tabs = drawer.querySelectorAll('[data-island-tab]');
    const panels = drawer.querySelectorAll('[data-island-panel]');

    function activateTab(id) {
      tabs.forEach((tab) => {
        const on = tab.dataset.islandTab === id;
        tab.classList.toggle('is-active', on);
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      panels.forEach((panel) => {
        panel.classList.toggle('is-active', panel.dataset.islandPanel === id);
      });
    }

    tabs.forEach((tab) => {
      tab.addEventListener('click', () => activateTab(tab.dataset.islandTab));
    });

    const activePlace = drawer.querySelector('.island-drawer-place.is-active');
    if (activePlace) {
      const panel = activePlace.closest('[data-island-panel]');
      if (panel?.dataset.islandPanel) activateTab(panel.dataset.islandPanel);
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDrawer();
    });
  }
})();

(function () {
  const STORAGE_KEY = 'ar_wedding_fold_open';
  const mq = window.matchMedia('(max-width: 860px)');

  function isMobile() {
    return mq.matches;
  }

  function setOpen(root, open, persist) {
    const toggle = root.querySelector('[data-wedding-fold-toggle]');
    const body = root.querySelector('[data-wedding-fold-body]');
    if (!toggle || !body) return;
    root.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    body.hidden = !open;
    if (persist && isMobile()) {
      try {
        sessionStorage.setItem(STORAGE_KEY, open ? '1' : '0');
      } catch (_) { /* ignore */ }
    }
  }

  function preferredOpen() {
    if (!isMobile()) return true;
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved === '1') return true;
      if (saved === '0') return false;
    } catch (_) { /* ignore */ }
    return false;
  }

  function syncAll() {
    const open = preferredOpen();
    document.querySelectorAll('[data-wedding-fold]').forEach((root) => {
      setOpen(root, open, false);
    });
  }

  document.addEventListener('click', (e) => {
    const toggle = e.target.closest('[data-wedding-fold-toggle]');
    if (!toggle) return;
    const root = toggle.closest('[data-wedding-fold]');
    if (!root) return;
    if (!isMobile()) return;
    e.preventDefault();
    const open = !root.classList.contains('is-open');
    document.querySelectorAll('[data-wedding-fold]').forEach((other) => {
      setOpen(other, open, other === root);
    });
  });

  if (typeof mq.addEventListener === 'function') {
    mq.addEventListener('change', syncAll);
  } else if (typeof mq.addListener === 'function') {
    mq.addListener(syncAll);
  }
  syncAll();

  window.__syncWeddingFolds = syncAll;
})();
