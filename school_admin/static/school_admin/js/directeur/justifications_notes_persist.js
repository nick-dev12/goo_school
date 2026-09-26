/**
 * Justifications notes — persistance ?periode= & ?classe= + localStorage
 */
(function () {
  'use strict';

  var KEY = 'directeur:justifications-notes';

  function boot() {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.mergeUrlFromStore(KEY, ['periode', 'classe']);
    var params = new URLSearchParams(window.location.search);
    window.directeurTabStorage.syncUrlAndStore(KEY, {
      periode: params.get('periode') || '',
      classe: params.get('classe') || '',
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
