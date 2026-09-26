/**
 * Détail emploi du temps — onglets, modals, créneaux (UI v2)
 */

(function () {
  'use strict';

  var EDTD_STORAGE = 'directeur:detail-emploi-du-temps';

  function edtdPersistVue(tabId) {
    if (!window.directeurTabStorage) return;
    var vue = tabId === 'edtd-panel-examens' ? 'examens' : 'cours';
    window.directeurTabStorage.syncUrlAndStore(EDTD_STORAGE, { vue: vue });
  }

  function switchEdtdMainTab(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.edtd-main-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.edtd-main-tab').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.edtd-main-tab[data-edtd-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (!opts.skipPersist) {
      edtdPersistVue(tabId);
    }
  }

  function initEdtdMainTabs() {
    if (window.directeurTabStorage) {
      var sel = window.directeurTabStorage.mergeUrlFromStore(EDTD_STORAGE, ['vue']);
      var tabId = sel.vue === 'examens' ? 'edtd-panel-examens' : 'edtd-panel-cours';
      switchEdtdMainTab(tabId, null, { skipPersist: true });
      edtdPersistVue(tabId);
    }
    document.addEventListener('click', function (event) {
      var tabBtn = event.target.closest('.edtd-main-tab[data-edtd-tab]');
      if (tabBtn) {
        switchEdtdMainTab(tabBtn.getAttribute('data-edtd-tab'), tabBtn);
      }
      var legendToggle = event.target.closest('.edtd-legend-toggle');
      if (legendToggle) {
        var wrap = legendToggle.closest('.edtd-legend-wrap');
        if (wrap) wrap.classList.toggle('is-open');
      }
    });
  }

  function initCreneauInteractions() {
    var creneauxInteractifs = document.querySelectorAll('.creneau-interactif');
    creneauxInteractifs.forEach(function (creneau) {
      creneau.addEventListener('click', function (e) {
        if (e.target.closest('.creneau-actions')) return;
        creneauxInteractifs.forEach(function (other) {
          if (other !== creneau) other.classList.remove('active');
        });
        creneau.classList.toggle('active');
      });
    });
    document.addEventListener('click', function (e) {
      if (!e.target.closest('.creneau-interactif')) {
        creneauxInteractifs.forEach(function (c) {
          c.classList.remove('active');
        });
      }
    });
  }

  function initModals() {
    var modal = document.getElementById('modalAjouterCreneau');
    var modalModifier = document.getElementById('modalModifierCreneau');
    var btnOuvrir = document.getElementById('btnOuvrirModalAjouterCreneau');
    var btnFermer = document.getElementById('btnFermerModalAjouterCreneau');
    var btnAnnuler = document.getElementById('btnAnnulerModal');
    var overlay = document.getElementById('modalOverlay');
    var form = document.getElementById('formAjouterCreneau');
    var overlayModifier = document.getElementById('modalOverlayModifier');
    var btnFermerModifier = document.getElementById('btnFermerModalModifierCreneau');
    var btnAnnulerModifier = document.getElementById('btnAnnulerModalModifier');
    var formModifier = document.getElementById('formModifierCreneau');
    var body = document.body;

    function setBodyScrollForModals() {
      var oneOpen = (modal && modal.classList.contains('active')) ||
        (modalModifier && modalModifier.classList.contains('active'));
      document.body.style.overflow = oneOpen ? 'hidden' : '';
    }

    function fermerModalAjouter() {
      if (!modal) return;
      modal.classList.remove('active');
      setBodyScrollForModals();
      if (form) {
        form.reset();
        modal.querySelectorAll('.error-message-modal').forEach(function (el) {
          el.style.display = 'none';
        });
        var g = document.getElementById('modalErrorsGlobales');
        if (g) g.style.display = 'none';
      }
    }

    function fermerModalModifier() {
      if (!modalModifier) return;
      modalModifier.classList.remove('active');
      setBodyScrollForModals();
      if (formModifier) {
        formModifier.reset();
        modalModifier.querySelectorAll('.error-message-modal').forEach(function (el) {
          el.style.display = 'none';
        });
        var gm = document.getElementById('modalModifErrorsGlobales');
        if (gm) gm.style.display = 'none';
      }
    }

    if (btnOuvrir) {
      btnOuvrir.addEventListener('click', function () {
        fermerModalModifier();
        modal.classList.add('active');
        setBodyScrollForModals();
      });
    }

    if (body.dataset.showModalCreneau === '1' && modal) {
      modal.classList.add('active');
      setBodyScrollForModals();
    }
    if (body.dataset.showModalModifier === '1' && modalModifier) {
      modalModifier.classList.add('active');
      setBodyScrollForModals();
    }

    if (btnFermer) btnFermer.addEventListener('click', fermerModalAjouter);
    if (btnAnnuler) btnAnnuler.addEventListener('click', fermerModalAjouter);
    if (overlay) overlay.addEventListener('click', fermerModalAjouter);
    if (modal) {
      var modalContent = modal.querySelector('.modal-creneau-content');
      if (modalContent) {
        modalContent.addEventListener('click', function (e) {
          e.stopPropagation();
        });
      }
    }

    if (btnFermerModifier) btnFermerModifier.addEventListener('click', fermerModalModifier);
    if (btnAnnulerModifier) btnAnnulerModifier.addEventListener('click', fermerModalModifier);
    if (overlayModifier) overlayModifier.addEventListener('click', fermerModalModifier);
    if (modalModifier) {
      var modalContentMod = modalModifier.querySelector('.modal-creneau-content');
      if (modalContentMod) {
        modalContentMod.addEventListener('click', function (e) {
          e.stopPropagation();
        });
      }
    }

    document.querySelectorAll('.js-ouvrir-modal-modifier-creneau').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!modalModifier || !formModifier) return;
        if (modal) modal.classList.remove('active');
        formModifier.action = btn.dataset.actionUrl || '#';
        var elJour = document.getElementById('modalModifJour');
        var elDeb = document.getElementById('modalModifHeureDebut');
        var elFin = document.getElementById('modalModifHeureFin');
        var elMat = document.getElementById('modalModifMatiere');
        var elProf = document.getElementById('modalModifProfesseur');
        var elSalle = document.getElementById('modalModifSalle');
        var elType = document.getElementById('modalModifTypeCours');
        if (elJour) elJour.value = btn.dataset.jour || '';
        if (elDeb) elDeb.value = btn.dataset.heureDebut || '';
        if (elFin) elFin.value = btn.dataset.heureFin || '';
        if (elMat) elMat.value = btn.dataset.matiereId ? String(btn.dataset.matiereId) : '';
        if (elProf) elProf.value = btn.dataset.professeurId ? String(btn.dataset.professeurId) : '';
        if (elSalle) elSalle.value = btn.dataset.salleId ? String(btn.dataset.salleId) : '';
        if (elType) elType.value = btn.dataset.typeCours || 'cours';
        modalModifier.querySelectorAll('.error-message-modal').forEach(function (el) {
          el.style.display = 'none';
        });
        var gm = document.getElementById('modalModifErrorsGlobales');
        if (gm) gm.style.display = 'none';
        modalModifier.classList.add('active');
        setBodyScrollForModals();
      });
    });

    function validerHeuresModales(heureDebut, heureFin, errorHeureFinId) {
      if (!heureDebut || !heureFin) return false;
      if (heureFin <= heureDebut) {
        var errorHeureFin = document.getElementById(errorHeureFinId);
        if (errorHeureFin) {
          var sp = errorHeureFin.querySelector('span');
          if (sp) sp.textContent = "L'heure de fin doit être après l'heure de début.";
          errorHeureFin.style.display = 'flex';
        }
        return false;
      }
      return true;
    }

    if (form) {
      form.addEventListener('submit', function (e) {
        var heureDebut = document.getElementById('modalHeureDebut').value;
        var heureFin = document.getElementById('modalHeureFin').value;
        if (!validerHeuresModales(heureDebut, heureFin, 'errorHeureFin')) {
          e.preventDefault();
        }
      });
    }

    if (formModifier) {
      formModifier.addEventListener('submit', function (e) {
        var heureDebut = document.getElementById('modalModifHeureDebut').value;
        var heureFin = document.getElementById('modalModifHeureFin').value;
        if (!validerHeuresModales(heureDebut, heureFin, 'errorModifHeureFin')) {
          e.preventDefault();
        }
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initEdtdMainTabs();
    initCreneauInteractions();
    initModals();
  });
})();
