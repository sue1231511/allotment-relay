(function () {
  const hamburgerBtn = document.getElementById('navHamburgerBtn');
  const sidebar = document.getElementById('navSidebar');
  const backdrop = document.getElementById('navSidebarBackdrop');
  const closeBtn = document.getElementById('navSidebarClose');

  if (!hamburgerBtn || !sidebar || !backdrop) return;

  function openSidebar() {
    sidebar.classList.add('is-open');
    backdrop.hidden = false;
    sidebar.setAttribute('aria-hidden', 'false');
    hamburgerBtn.setAttribute('aria-expanded', 'true');
    document.body.classList.add('nav-sidebar-open');
  }

  function closeSidebar() {
    sidebar.classList.remove('is-open');
    backdrop.hidden = true;
    sidebar.setAttribute('aria-hidden', 'true');
    hamburgerBtn.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('nav-sidebar-open');
  }

  hamburgerBtn.addEventListener('click', () => {
    if (sidebar.classList.contains('is-open')) closeSidebar();
    else openSidebar();
  });

  closeBtn?.addEventListener('click', closeSidebar);
  backdrop.addEventListener('click', closeSidebar);

  sidebar.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', closeSidebar);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
  });
})();
