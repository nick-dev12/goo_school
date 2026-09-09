/**
 * Espace enseignant — temps réel + modals (modèle TimaLove)
 */
(function () {
  'use strict';

  var refreshTimer = null;

  var PAGE_REFRESH = {
    'notes-gestion': ['#gestion-notes-live-root'],
    'presence-gestion': ['#gestion-presence-live-root'],
    'notes-noter': ['.main-content-container'],
    'evaluations-liste': ['.main-content-container'],
    'presence-liste': ['.main-content-container', '.presence-sheet'],
    'presence-historique': ['.main-content-container'],
    'eleves-gestion': ['.main-content-container'],
    'eleve-detail': ['.main-content-container'],
    'exercices': ['.main-content-container'],
    'justifications': ['.main-content-container'],
    'profil': ['.main-content-container'],
  };

  var LIVE_EVENTS = [
    'evaluation.creee',
    'evaluation.modifiee',
    'evaluation.supprimee',
    'notes.mise_a_jour',
    'presence.mise_a_jour',
    'justification.soumise',
    'exercice.publie',
    'exercice.modifie',
    'sanction.ajoutee',
  ];

  var FORM_IDS = [
    'formAjouterSanction',
    'formJustifierAbsence',
    'formModifierPresence',
    'formJustificationNote',
    'formExerciceMaison',
    'formProfilInfos',
    'formProfilPassword',
    'formModifierEvaluation',
  ];

  function showToast(message) {
    if (window.AriaLive && AriaLive.showPageSuccess && message) {
      AriaLive.showPageSuccess(message);
    }
  }

  function currentPage() {
    return document.body.getAttribute('data-live-page') || '';
  }

  function payloadMatchesPage(payload) {
    if (!payload) {
      return true;
    }
    var classeId = parseInt(document.body.getAttribute('data-classe-id') || '0', 10);
    var eleveId = parseInt(document.body.getAttribute('data-eleve-id') || '0', 10);
    if (classeId && payload.classe_id && payload.classe_id !== classeId) {
      return false;
    }
    if (eleveId && payload.eleve_id && payload.eleve_id !== eleveId) {
      return false;
    }
    return true;
  }

  function buildLiveRefreshUrl(page, itemOrForm) {
    if (page === 'notes-gestion') {
      return buildNotesRefreshUrl(itemOrForm);
    }
    if (page === 'presence-gestion') {
      return buildRefreshUrl({ live_partial: 'presence' });
    }
    return buildRefreshUrl();
  }

  function bindLiveForms() {
    if (!window.AriaLive) {
      return;
    }
    FORM_IDS.forEach(function (id) {
      var form = document.getElementById(id);
      if (!form) {
        return;
      }
      AriaLive.bindLiveForm(form, {
        onSuccess: function (result) {
          var page = currentPage();
          var selectors = PAGE_REFRESH[page];
          if (selectors) {
            scheduleRefresh(selectors, result.message, true, buildLiveRefreshUrl(page, result.item || null));
          } else if (result.message) {
            showToast(result.message);
          }
        },
      });
    });
    document.querySelectorAll('[data-live-form="1"]').forEach(function (form) {
      if (form.id && FORM_IDS.indexOf(form.id) !== -1) {
        return;
      }
      if (form.id === 'presence-form' && form.closest('#modalPresenceAppelBody')) {
        return;
      }
      AriaLive.bindLiveForm(form, {
        onSuccess: function (result) {
          var page = currentPage();
          var selectors = PAGE_REFRESH[page];
          if (selectors) {
            scheduleRefresh(selectors, result.message, true, buildLiveRefreshUrl(page, result.item || null));
          }
        },
      });
    });
  }

  function captureNotesTabState() {
    var activeMain = document.querySelector('.tab-content-panel.active');
    var activeClasse = document.querySelector('.classe-content.active');
    return {
      mainTabId: activeMain ? activeMain.id : null,
      classeTabId: activeClasse ? activeClasse.id : null,
    };
  }

  function restoreNotesTabState(state) {
    if (!state) {
      return;
    }
    if (state.mainTabId && typeof window.switchTab === 'function') {
      window.switchTab(state.mainTabId);
    }
    if (state.classeTabId && typeof window.showClasse === 'function') {
      var classeEl = document.getElementById(state.classeTabId);
      if (classeEl) {
        var tabPanel = classeEl.closest('.tab-content-panel');
        if (tabPanel) {
          window.showClasse(state.classeTabId, tabPanel.id);
        }
      }
    }
  }

  function buildRefreshUrl(extraParams) {
    var url = new URL(window.location.href);
    url.searchParams.delete('_refresh');
    if (extraParams) {
      Object.keys(extraParams).forEach(function (key) {
        if (extraParams[key]) {
          url.searchParams.set(key, extraParams[key]);
        }
      });
    }
    url.searchParams.set('_refresh', String(Date.now()));
    return url.toString();
  }

  function periodeParamsFromItem(item) {
    if (!item || !item.periode_id) {
      return null;
    }
    var params = {};
    if (item.classe_id && document.querySelector('.periodes-par-classe-enseignant')) {
      params['periode_' + item.classe_id] = String(item.periode_id);
    } else {
      params.periode = String(item.periode_id);
    }
    return params;
  }

  function periodeParamsFromForm(form) {
    if (!form) {
      return null;
    }
    var isPrimaire = document.body.getAttribute('data-enseignant-space') === 'primaire';
    var fieldName = isPrimaire ? 'periode' : 'periode_scolaire';
    var input = form.querySelector('[name="' + fieldName + '"]');
    if (!input || !input.value) {
      return null;
    }
    var params = {};
    var formAction = form.getAttribute('action') || '';
    var match = formAction.match(/\/creer\/(\d+)\/?/);
    if (match && document.querySelector('.periodes-par-classe-enseignant')) {
      params['periode_' + match[1]] = input.value;
    } else {
      params.periode = input.value;
    }
    return params;
  }

  function buildNotesRefreshUrl(itemOrForm) {
    var params = { live_partial: 'notes' };
    if (itemOrForm && itemOrForm.periode_id) {
      Object.assign(params, periodeParamsFromItem(itemOrForm) || {});
    } else if (itemOrForm && itemOrForm.querySelector) {
      Object.assign(params, periodeParamsFromForm(itemOrForm) || {});
    }
    return buildRefreshUrl(params);
  }

  function syncNotesUrl(extraParams) {
    if (!extraParams) {
      return;
    }
    try {
      var nextUrl = new URL(buildRefreshUrl(extraParams));
      nextUrl.searchParams.delete('_refresh');
      nextUrl.searchParams.delete('live_partial');
      window.history.replaceState({}, '', nextUrl.toString());
    } catch (e) {
      /* ignore */
    }
  }

  function getLiveRootConfig() {
    var page = currentPage();
    if (page === 'notes-gestion' && document.getElementById('gestion-notes-live-root')) {
      return { rootId: 'gestion-notes-live-root', livePartial: 'notes' };
    }
    if (page === 'presence-gestion' && document.getElementById('gestion-presence-live-root')) {
      return { rootId: 'gestion-presence-live-root', livePartial: 'presence' };
    }
    return null;
  }

  function replaceFromFetch(selectors, message, force, fetchUrl) {
    if (!force && window.AriaLive && AriaLive.shouldSkipWs && AriaLive.shouldSkipWs()) {
      return;
    }
    var liveCfg = getLiveRootConfig();
    var tabState = liveCfg ? captureNotesTabState() : null;
    var url =
      fetchUrl ||
      buildRefreshUrl(liveCfg ? { live_partial: liveCfg.livePartial } : null);

    fetch(url, {
      method: 'GET',
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        Accept: 'text/html',
        'Cache-Control': 'no-cache',
      },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        if (liveCfg) {
          var root = document.getElementById(liveCfg.rootId);
          var fresh = doc.getElementById(liveCfg.rootId);
          if (root && fresh) {
            root.innerHTML = fresh.innerHTML;
            restoreNotesTabState(tabState);
          }
        } else {
          selectors.forEach(function (sel) {
            var current = document.querySelector(sel);
            var fresh = doc.querySelector(sel);
            if (current && fresh) {
              current.outerHTML = fresh.outerHTML;
            }
          });
        }
        bindLiveForms();
        initEvaluationModalTriggers();
        initPresenceModalTriggers();
        if (message) {
          showToast(message);
        }
      })
      .catch(function (err) {
        console.warn('[EnseignantLive] Rafraîchissement impossible:', err);
      });
  }

  function scheduleRefresh(selectors, message, force, fetchUrl) {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
    }
    refreshTimer = setTimeout(function () {
      refreshTimer = null;
      replaceFromFetch(selectors, message, force, fetchUrl);
    }, force ? 0 : 350);
  }

  function handleLiveEvent(eventType, payload, message) {
    if (!payloadMatchesPage(payload)) {
      return;
    }
    var evalId = payload && (payload.evaluation_id || (payload.item && payload.item.id));
    if (evalId && window.AriaLive && AriaLive.isLocalItem && AriaLive.isLocalItem(evalId)) {
      return;
    }
    var page = currentPage();
    var selectors = PAGE_REFRESH[page];
    if (!selectors) {
      return;
    }
    var fetchUrl =
      page === 'notes-gestion'
        ? buildNotesRefreshUrl(payload && payload.item ? payload.item : payload)
        : page === 'presence-gestion'
          ? buildRefreshUrl({ live_partial: 'presence' })
          : null;
    scheduleRefresh(selectors, message || 'Données mises à jour.', true, fetchUrl);
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modal.classList.add('active');
    document.body.classList.add('modal-enseignant-open');
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modal.classList.remove('active');
    document.body.classList.remove('modal-enseignant-open');
  }

  function bindPresenceFormInModal(form) {
    if (!form || !window.AriaLive) {
      return;
    }
    AriaLive.bindLiveForm(form, {
      onSuccess: function () {
        closeModal('modalPresenceAppel');
        scheduleRefresh(
          PAGE_REFRESH['presence-gestion'],
          null,
          true,
          buildRefreshUrl({ live_partial: 'presence' })
        );
      },
    });
  }

  function loadPresenceForm(classeId, matiereId) {
    var body = document.getElementById('modalPresenceAppelBody');
    if (!body) {
      return;
    }
    body.innerHTML =
      '<div class="modal-loading"><i class="fas fa-spinner fa-spin"></i> Chargement…</div>';
    openModal('modalPresenceAppel');
    var url =
      '/enseignant/presence/' +
      classeId +
      '/?partial=1' +
      (matiereId ? '&matiere=' + encodeURIComponent(matiereId) : '');
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'text/html' },
    })
      .then(function (r) {
        return r.text();
      })
      .then(function (html) {
        body.innerHTML = html;
        if (window.initPresenceFormUi) {
          initPresenceFormUi(body);
        }
        var form = body.querySelector('#presence-form');
        if (form) {
          form.setAttribute('data-live-bound', '0');
          bindPresenceFormInModal(form);
        }
        body.querySelectorAll('[data-close-presence-modal]').forEach(function (btn) {
          btn.addEventListener('click', function (e) {
            e.preventDefault();
            closeModal('modalPresenceAppel');
          });
        });
      })
      .catch(function () {
        body.innerHTML =
          '<p class="alert alert-danger">Impossible de charger la liste de présence.</p>';
      });
  }

  function loadEvaluationForm(classeId, matiereId, periodeId) {
    var body = document.getElementById('modalCreerEvaluationBody');
    if (!body) {
      return;
    }
    body.innerHTML =
      '<div class="modal-loading"><i class="fas fa-spinner fa-spin"></i> Chargement…</div>';
    openModal('modalCreerEvaluation');
    var isPrimaire = document.body.getAttribute('data-enseignant-space') === 'primaire';
    var base = isPrimaire
      ? '/enseignant/primaire/evaluation/creer/'
      : '/enseignant/evaluation/creer/';
    var url =
      base +
      classeId +
      '/?partial=1' +
      (matiereId ? '&matiere=' + encodeURIComponent(matiereId) : '') +
      (periodeId ? '&periode=' + encodeURIComponent(periodeId) : '');
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'text/html' },
    })
      .then(function (r) {
        return r.text();
      })
      .then(function (html) {
        body.innerHTML = html;
        var form = body.querySelector('form');
        if (form && window.AriaLive) {
          form.id = form.id || 'formCreerEvaluation';
          AriaLive.bindLiveForm(form, {
            onSuccess: function (result) {
              var item = result.item || null;
              if (item && item.id && AriaLive.markLocalItem) {
                AriaLive.markLocalItem(item.id);
              }
              var periodeParams = item
                ? periodeParamsFromItem(item)
                : periodeParamsFromForm(form);
              syncNotesUrl(periodeParams);
              closeModal('modalCreerEvaluation');
              scheduleRefresh(
                PAGE_REFRESH['notes-gestion'],
                null,
                true,
                buildNotesRefreshUrl(item || form)
              );
            },
          });
        }
        var cancel = body.querySelector('[data-close-eval-modal]');
        if (cancel) {
          cancel.addEventListener('click', function (e) {
            e.preventDefault();
            closeModal('modalCreerEvaluation');
          });
        }
      })
      .catch(function () {
        body.innerHTML = '<p class="alert alert-danger">Impossible de charger le formulaire.</p>';
      });
  }

  function initEvaluationModalTriggers() {
    if (document.body.getAttribute('data-eval-delegated') === '1') {
      return;
    }
    document.body.setAttribute('data-eval-delegated', '1');
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-open-evaluation-modal]');
      if (!btn) {
        return;
      }
      e.preventDefault();
      loadEvaluationForm(
        btn.getAttribute('data-classe-id'),
        btn.getAttribute('data-matiere-id'),
        btn.getAttribute('data-periode-id')
      );
    });
  }

  function initPresenceModalTriggers() {
    if (document.body.getAttribute('data-presence-delegated') === '1') {
      return;
    }
    document.body.setAttribute('data-presence-delegated', '1');
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-open-presence-modal]');
      if (!btn) {
        return;
      }
      e.preventDefault();
      loadPresenceForm(
        btn.getAttribute('data-classe-id'),
        btn.getAttribute('data-matiere-id')
      );
    });
    document.addEventListener('click', function (e) {
      var closeBtn = e.target.closest('[data-close-presence-modal]');
      if (closeBtn) {
        e.preventDefault();
        closeModal('modalPresenceAppel');
      }
    });
  }

  function initProfilModals() {
    document.querySelectorAll('[data-open-profil-modal]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openModal(btn.getAttribute('data-open-profil-modal'));
      });
    });
    document.querySelectorAll('[data-close-profil-modal]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        closeModal(btn.getAttribute('data-close-profil-modal'));
      });
    });
    document.querySelectorAll('.enseignant-form-modal .modal-creneau-overlay').forEach(function (ov) {
      ov.addEventListener('click', function () {
        var modal = ov.closest('.enseignant-form-modal');
        if (modal) {
          closeModal(modal.id);
        }
      });
    });
  }

  function initLiveListeners() {
    document.addEventListener('aria:live-enseignant', function (e) {
      var d = e.detail || {};
      var type = d.type || d.event;
      if (LIVE_EVENTS.indexOf(type) === -1) {
        return;
      }
      handleLiveEvent(type, d.payload || d, null);
    });
    document.addEventListener('aria:realtime', function (e) {
      var d = e.detail || {};
      if (LIVE_EVENTS.indexOf(d.type) === -1) {
        return;
      }
      handleLiveEvent(d.type, d.payload, null);
    });
  }

  function initPage() {
    bindLiveForms();
    initEvaluationModalTriggers();
    initPresenceModalTriggers();
    initProfilModals();
    initLiveListeners();
    if (document.body.getAttribute('data-open-evaluation-modal') === '1') {
      var c = document.body.getAttribute('data-eval-classe-id');
      var m = document.body.getAttribute('data-eval-matiere-id');
      var p = document.body.getAttribute('data-eval-periode-id');
      if (c) {
        loadEvaluationForm(c, m, p);
      }
    }
    if (document.body.getAttribute('data-open-modal-sanction') === '1') {
      openModal('modal-sanction');
    }
    if (document.body.getAttribute('data-open-modal-exercice') === '1') {
      openModal('modal-exercice');
    }
  }

  window.openModalEnseignant = openModal;
  window.closeModalEnseignant = closeModal;
  window.loadEvaluationFormModal = loadEvaluationForm;
  window.loadPresenceFormModal = loadPresenceForm;
  window.refreshEnseignantLiveNow = function (message, force) {
    var page = currentPage();
    var selectors = PAGE_REFRESH[page];
    if (selectors) {
      scheduleRefresh(selectors, message, force, buildLiveRefreshUrl(page, null));
    }
  };

  document.addEventListener('DOMContentLoaded', initPage);
})();
