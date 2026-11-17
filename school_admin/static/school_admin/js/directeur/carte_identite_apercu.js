/* Le zoom CSS réduit aussi l'espace occupé dans la page, contrairement à transform: scale().
   La variable n'est consommée que par la feuille media="screen", jamais à l'impression. */
(() => {
  const wrappers = document.querySelectorAll('.student-idcard-wrapper');
  const adapter = wrapper => {
    const largeur = wrapper.clientWidth;
    if (largeur > 0) {
      wrapper.style.setProperty('--idcard-preview-scale', Math.min(1, largeur / 480));
    }
  };
  wrappers.forEach(adapter);
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(entries => entries.forEach(entry => adapter(entry.target)));
    wrappers.forEach(wrapper => observer.observe(wrapper));
  } else {
    window.addEventListener('resize', () => wrappers.forEach(adapter));
  }
})();
