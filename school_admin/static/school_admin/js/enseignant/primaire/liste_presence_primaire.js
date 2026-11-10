// Compat : la page primaire charge désormais liste_presence.js.
(function () {
  'use strict';
  if (typeof window.initPresenceFormUi === 'function') {
    document.addEventListener('DOMContentLoaded', function () {
      window.initPresenceFormUi(document);
    });
  }
})();
