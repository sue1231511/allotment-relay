(function () {
  const moreBtn = document.getElementById('nav-more-btn');
  const sheet = document.getElementById('navMoreSheet');
  const backdrop = document.getElementById('navSheetBackdrop');
  const closeBtn = document.getElementById('navSheetClose');

  if (!moreBtn || !sheet || !backdrop) return;

  function openMore() {
    sheet.classList.add('is-open');
    backdrop.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    moreBtn.setAttribute('aria-expanded', 'true');
    document.body.classList.add('nav-sheet-open');
  }

  function closeMore() {
    sheet.classList.remove('is-open');
    backdrop.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    moreBtn.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('nav-sheet-open');
  }

  moreBtn.addEventListener('click', () => {
    if (sheet.classList.contains('is-open')) closeMore();
    else openMore();
  });

  closeBtn?.addEventListener('click', closeMore);
  backdrop.addEventListener('click', closeMore);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMore();
  });
})();
