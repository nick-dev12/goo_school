/**
 * Bulletins — temps réel (liste, config, vue élève)
 */
(function () {
  'use strict';

  var refreshTimer = null;

  function showToast(message) {
    if (window.AriaLive && AriaLive.showPageSuccess && message) {
      AriaLive.showPageSuccess(message);
    }
  }

  function captureBulletinsTabState() {
    var activeMain = document.querySelector('.tab-panel.active');
    var activeClasse = document.querySelector('.classe-subtab-content.active');
    return {
      mainTabId: activeMain ? activeMain.id : null,
      classeTabId: activeClasse ? activeClasse.id : null,
    };
  }

  function restoreBulletinsTabState(state) {
    if (!state) {
      return;
    }
    if (state.mainTabId && window.switchMainTab) {
      window.switchMainTab(state.mainTabId);
    }
    if (state.classeTabId) {
      var content = document.getElementById(state.classeTabId);
      if (content) {
        var panel = content.closest('.tab-panel');
        if (panel) {
          panel.querySelectorAll('.classe-subtab-content').forEach(function (el) {
            el.classList.remove('active');
          });
          panel.querySelectorAll('.classe-subtab-btn').forEach(function (el) {
            el.classList.remove('active');
          });
          content.classList.add('active');
          var btn = panel.querySelector('[data-subtab="' + state.classeTabId + '"]');
          if (btn) {
            btn.classList.add('active');
          }
        }
      }
    }
  }

  function replaceFromFetch(selectors, message, force) {
    if (!force && window.AriaLive && AriaLive.shouldSkipWs && AriaLive.shouldSkipWs()) {
      return;
    }

    var state = captureBulletinsTabState();

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
        selectors.forEach(function (sel) {
          var current = document.querySelector(sel);
          var fresh = doc.querySelector(sel);
          if (current && fresh) {
            current.outerHTML = fresh.outerHTML;
          }
        });
        restoreBulletinsTabState(state);
        var page = document.body.getAttribute('data-live-page');
        if (page === 'bulletins-liste') {
          bindVisibilityForms();
        } else if (page === 'bulletins-config-moyennes' || page === 'bulletins-config-standards') {
          bindConfigForms();
        }
        if (message) {
          showToast(message);
        }
      })
      .catch(function () {
        /* silencieux */
      });
  }

  function scheduleRefresh(selectors, message, force) {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
    }
    refreshTimer = setTimeout(function () {
      refreshTimer = null;
      replaceFromFetch(selectors, message, force);
    }, 350);
  }

  function payloadMatchesPage(payload) {
    if (!payload) {
      return true;
    }
    var page = document.body.getAttribute('data-live-page');
    if (page === 'bulletins-voir') {
      var classeId = parseInt(document.body.getAttribute('data-classe-id') || '0', 10);
      var eleveId = parseInt(document.body.getAttribute('data-eleve-id') || '0', 10);
      var periodeId = parseInt(document.body.getAttribute('data-periode-id') || '0', 10);
      if (payload.eleve_id && eleveId && payload.eleve_id !== eleveId) {
        return payload.classe_id === classeId;
      }
      if (payload.classe_id && classeId && payload.classe_id !== classeId) {
        return false;
      }
      if (payload.periode_id && periodeId && payload.periode_id !== periodeId) {
        return false;
      }
      return true;
    }
    if (page === 'bulletins-liste' && payload.classe_id) {
      return true;
    }
    return true;
  }

  function handleBulletinEvent(eventType, payload, message) {
    if (!payloadMatchesPage(payload)) {
      return;
    }

    var page = document.body.getAttribute('data-live-page');

    if (page === 'bulletins-liste') {
      scheduleRefresh(['.bulletins-overview', '.tabs-container'], message);
      return;
    }

    if (page === 'bulletins-config-moyennes') {
      scheduleRefresh(['.config-container'], message);
      return;
    }

    if (page === 'bulletins-config-standards') {
      scheduleRefresh(['.standards-form-wrapper'], message);
      return;
    }

    if (page === 'bulletins-voir') {
      var msg = message || 'Bulletin mis à jour.';
      scheduleRefresh(['.bulletin-sheet', '.bulletin-actions'], msg);
    }
  }

  function bindVisibilityForms() {
    document.querySelectorAll('.students-visibility-form').forEach(function (form) {
      if (!window.AriaLive) {
        return;
      }
      AriaLive.bindLiveForm(form, {
        onSuccess: function () {
          scheduleRefresh(['.bulletins-overview', '.tabs-container'], 'Visibilité mise à jour.', true);
        },
      });
    });
  }

  function bindPublishButtons() {
    if (!window.AriaLive || document.body.getAttribute('data-publish-delegated') === '1') {
      return;
    }
    document.body.setAttribute('data-publish-delegated', '1');
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.btn-publish');
      if (!btn || btn.disabled) {
        return;
      }
      e.preventDefault();
      var form = btn.form;
      var url = btn.getAttribute('formaction');
      if (!form || !url) {
        return;
      }
      btn.disabled = true;
      fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': AriaLive.csrf(),
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
        body: new FormData(form),
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok || !result.payload.ok) {
            alert((result.payload && result.payload.message) || 'Erreur lors de la publication.');
            return;
          }
          scheduleRefresh(
            ['.bulletins-overview', '.tabs-container'],
            result.payload.message || 'Bulletins publiés.',
            true
          );
        })
        .catch(function () {
          alert('Erreur réseau.');
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  function bindConfigForms() {
    if (!window.AriaLive) {
      return;
    }
    ['formConfigMoyennes', 'general-form', 'conseil-form', 'matieres-form'].forEach(function (id) {
      var form = document.getElementById(id);
      if (!form) {
        return;
      }
      AriaLive.bindLiveForm(form, {
        onSuccess: function (payload) {
          var page = document.body.getAttribute('data-live-page');
          if (page === 'bulletins-config-moyennes') {
            scheduleRefresh(['.config-container'], payload.message, true);
          } else if (page === 'bulletins-config-standards') {
            scheduleRefresh(['.standards-form-wrapper'], payload.message, true);
          }
        },
      });
    });
  }

  function initBulletinsListe() {
    bindVisibilityForms();
    bindPublishButtons();

    document.addEventListener('aria:realtime', function (e) {
      var d = e.detail || {};
      if (d.type === 'bulletin.publie') {
        handleBulletinEvent(d.type, d.payload, 'Bulletins publiés — ' + ((d.payload && d.payload.classe_nom) || ''));
      } else if (d.type === 'bulletin.mise_a_jour') {
        var p = d.payload || {};
        var msg = 'Bulletins mis à jour';
        if (p.classe_nom) {
          msg += ' — ' + p.classe_nom;
        }
        handleBulletinEvent(d.type, p, msg);
      } else if (d.type === 'notes.mise_a_jour') {
        handleBulletinEvent(d.type, d.payload, 'Notes mises à jour — rechargement des bulletins.');
      }
    });
  }

  function initBulletinsConfig() {
    bindConfigForms();
    document.addEventListener('aria:realtime', function (e) {
      var d = e.detail || {};
      if (d.type === 'bulletin.mise_a_jour') {
        handleBulletinEvent(d.type, d.payload, 'Configuration synchronisée.');
      }
    });
  }

  function initBulletinsVoir() {
    document.addEventListener('aria:realtime', function (e) {
      var d = e.detail || {};
      if (d.type === 'bulletin.publie' || d.type === 'bulletin.mise_a_jour' || d.type === 'notes.mise_a_jour') {
        handleBulletinEvent(d.type, d.payload, 'Bulletin actualisé.');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var page = document.body.getAttribute('data-live-page');
    if (page === 'bulletins-liste') {
      initBulletinsListe();
    } else if (page === 'bulletins-config-moyennes' || page === 'bulletins-config-standards') {
      initBulletinsConfig();
    } else if (page === 'bulletins-voir') {
      initBulletinsVoir();
    }
  });

  window.refreshBulletinsLiveNow = function (message, force) {
    var page = document.body.getAttribute('data-live-page');
    if (page === 'bulletins-liste') {
      scheduleRefresh(['.bulletins-overview', '.tabs-container'], message, force);
    } else if (page === 'bulletins-voir') {
      scheduleRefresh(['.bulletin-sheet', '.bulletin-actions'], message, force);
    }
  };
})();
