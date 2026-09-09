/**

 * Notes et résultats + Suivi présence — temps réel sans rechargement complet

 */

(function () {

  'use strict';



  var refreshTimer = null;



  function activateMainTab(tabId) {

    if (!tabId) {

      return;

    }

    document.querySelectorAll('.tab-content-panel').forEach(function (panel) {

      panel.classList.remove('active');

    });

    document.querySelectorAll('.tab-btn').forEach(function (btn) {

      btn.classList.remove('active');

    });

    var panel = document.getElementById(tabId);

    if (panel) {

      panel.classList.add('active');

    }

    var btn = document.querySelector('.tab-btn[data-tab="' + tabId + '"]');

    if (btn) {

      btn.classList.add('active');

    }

  }



  function activateClasseTab(classeId) {

    if (!classeId) {

      return;

    }

    var content = document.getElementById(classeId);

    if (!content) {

      return;

    }

    var panel = content.closest('.tab-content-panel');

    if (!panel) {

      return;

    }

    panel.querySelectorAll('.classe-subtab-content').forEach(function (el) {

      el.classList.remove('active');

    });

    panel.querySelectorAll('.classe-subtab-btn').forEach(function (el) {

      el.classList.remove('active');

    });

    content.classList.add('active');

    var subBtn = panel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');

    if (!subBtn) {

      subBtn = panel.querySelector('.classe-subtab-btn[onclick*="' + classeId + '"]');

    }

    if (subBtn) {

      subBtn.classList.add('active');

    }

  }



  function activateMoisTab(moisId) {

    if (!moisId) {

      return;

    }

    var content = document.getElementById(moisId);

    if (!content) {

      return;

    }

    var panel = content.closest('.classe-subtab-content');

    if (!panel) {

      return;

    }

    panel.querySelectorAll('.mois-content').forEach(function (el) {

      el.classList.remove('active');

    });

    panel.querySelectorAll('.mois-tab-btn').forEach(function (el) {

      el.classList.remove('active');

    });

    content.classList.add('active');

    var moisBtn = panel.querySelector('.mois-tab-btn[onclick*="' + moisId + '"]');

    if (moisBtn) {

      moisBtn.classList.add('active');

    }

  }



  function captureTabState() {

    var activeMain = document.querySelector('.tab-content-panel.active');

    var activeClasse = document.querySelector('.classe-subtab-content.active');

    var activeMois = document.querySelector('.mois-content.active');

    return {

      mainTabId: activeMain ? activeMain.id : null,

      classeTabId: activeClasse ? activeClasse.id : null,

      moisTabId: activeMois ? activeMois.id : null,

    };

  }



  function restoreTabState(state) {

    if (!state) {

      return;

    }

    if (state.mainTabId) {

      activateMainTab(state.mainTabId);

    }

    if (state.classeTabId) {

      activateClasseTab(state.classeTabId);

    }

    if (state.moisTabId) {

      activateMoisTab(state.moisTabId);

    }

  }



  function showLiveRefreshToast(message) {

    if (window.AriaLive && AriaLive.showPageSuccess) {

      AriaLive.showPageSuccess(message || 'Données mises à jour.');

    }

  }



  function softRefreshTabsContainer(message) {

    var container = document.querySelector('.tabs-container');

    if (!container) {

      return;

    }



    var state = captureTabState();



    fetch(window.location.href, {

      method: 'GET',

      credentials: 'same-origin',

      headers: {

        'X-Requested-With': 'XMLHttpRequest',

        Accept: 'text/html',

      },

    })

      .then(function (response) {

        return response.text();

      })

      .then(function (html) {

        var doc = new DOMParser().parseFromString(html, 'text/html');

        var fresh = doc.querySelector('.tabs-container');

        if (!fresh) {

          return;

        }

        container.innerHTML = fresh.innerHTML;

        restoreTabState(state);

        if (message) {

          showLiveRefreshToast(message);

        }

      })

      .catch(function () {

        /* silencieux */

      });

  }



  function scheduleSoftRefresh(message, force) {

    if (refreshTimer) {

      clearTimeout(refreshTimer);

    }

    refreshTimer = setTimeout(function () {

      refreshTimer = null;

      if (!force && window.AriaLive && AriaLive.shouldSkipWs && AriaLive.shouldSkipWs()) {

        return;

      }

      softRefreshTabsContainer(message);

    }, 350);

  }



  function handleNotesUpdate(payload) {

    var page = document.body.getAttribute('data-live-page');

    if (page !== 'notes-resultats') {

      return;

    }

    var msg = 'Notes mises à jour';

    if (payload && payload.classe_nom) {

      msg += ' — ' + payload.classe_nom;

    }

    if (payload && payload.matiere_nom) {

      msg += ' (' + payload.matiere_nom + ')';

    }

    scheduleSoftRefresh(msg);

  }



  function handlePresenceUpdate(payload) {

    var page = document.body.getAttribute('data-live-page');

    if (page !== 'suivi-presence') {

      return;

    }

    var msg = 'Présences mises à jour';

    if (payload && payload.classe_nom) {

      msg += ' — ' + payload.classe_nom;

    }

    scheduleSoftRefresh(msg);

  }



  function initNotesResultatsLive() {

    document.addEventListener('aria:realtime', function (e) {

      var d = e.detail || {};

      if (d.type === 'notes.mise_a_jour') {

        handleNotesUpdate(d.payload || {});

      }

    });

  }



  function initSuiviPresenceLive() {

    var form = document.getElementById('formJustifierAbsence');

    if (form && window.AriaLive) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function () {

          if (typeof window.fermerModalJustification === 'function') {

            window.fermerModalJustification();

          }

          scheduleSoftRefresh('Absence justifiée avec succès.', true);

        },

      });

    }



    document.addEventListener('aria:realtime', function (e) {

      var d = e.detail || {};

      if (d.type === 'presence.mise_a_jour') {

        handlePresenceUpdate(d.payload || {});

      }

    });

  }



  document.addEventListener('DOMContentLoaded', function () {

    var page = document.body.getAttribute('data-live-page');

    if (page === 'notes-resultats') {

      initNotesResultatsLive();

    } else if (page === 'suivi-presence') {

      initSuiviPresenceLive();

    }

  });

  window.refreshLiveTabsNow = function (message, force) {
    scheduleSoftRefresh(message, force !== false);
  };

})();


