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

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });
})();
