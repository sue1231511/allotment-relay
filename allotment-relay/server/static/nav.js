(function () {
  const drawer = document.getElementById('islandDrawer');
  const backdrop = document.getElementById('islandBackdrop');
  const closeBtn = document.getElementById('islandDrawerClose');
  const openBtns = document.querySelectorAll('[data-open-island]');

  if (!drawer || !backdrop || !openBtns.length) return;

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
})();
