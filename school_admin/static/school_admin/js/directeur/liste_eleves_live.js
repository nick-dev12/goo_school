/**

 * Liste élèves — modal inscription + temps réel + reçu dynamique

 */

(function () {

  'use strict';



  function esc(text) {

    if (window.AriaLive && AriaLive.escapeHtml) {

      return AriaLive.escapeHtml(text || '');

    }

    var d = document.createElement('div');

    d.textContent = text || '';

    return d.innerHTML;

  }



  function lockBody(open) {

    document.body.classList.toggle('modal-personnel-open', open);

  }



  window.openModalInscriptionEleve = function () {

    var modal = document.getElementById('modalInscriptionEleve');

    if (!modal) {

      return;

    }

    modal.classList.add('active');

    lockBody(true);

    if (window.initInscriptionFormExtras) {

      window.initInscriptionFormExtras();

    }

  };



  window.closeModalInscriptionEleve = function () {

    var modal = document.getElementById('modalInscriptionEleve');

    if (!modal) {

      return;

    }

    modal.classList.remove('active');

    if (!document.getElementById('modalRecuEleve') || !document.getElementById('modalRecuEleve').classList.contains('active')) {

      lockBody(false);

    }

  };



  window.closeModalRecuEleve = function () {

    var modal = document.getElementById('modalRecuEleve');

    if (!modal) {

      return;

    }

    modal.classList.remove('active');

    lockBody(false);

  };



  window.activateMainTab = function (tabId) {

    document.querySelectorAll('.tab-panel').forEach(function (panel) {

      panel.classList.remove('active');

    });

    document.querySelectorAll('.tab-button').forEach(function (btn) {

      btn.classList.remove('active');

    });

    var panel = document.getElementById(tabId);

    if (panel) {

      panel.classList.add('active');

    }

    var btn = document.querySelector('.tab-button[data-tab="' + tabId + '"]');

    if (btn) {

      btn.classList.add('active');

    }

  };



  window.activateClasseTab = function (classeId) {

    var content = document.getElementById('classe-' + classeId);

    if (!content) {

      return;

    }

    var panel = content.closest('.tab-panel');

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

    var subBtn = panel.querySelector('.classe-subtab-btn[data-subtab="classe-' + classeId + '"]');

    if (subBtn) {

      subBtn.classList.add('active');

    }

  };



  function renderEleveRow(item) {

    var row = document.createElement('div');

    row.className = 'list-row eleve-row-live eleve-row-new';

    row.setAttribute('data-eleve-id', String(item.id));

    row.setAttribute('data-nom', (item.nom || '').toLowerCase());

    row.setAttribute('data-prenom', (item.prenom || '').toLowerCase());

    row.setAttribute('data-email', (item.email || '').toLowerCase());

    row.setAttribute('data-matricule', (item.matricule || '').toLowerCase());

    row.setAttribute('data-statut', item.statut || '');

    row.setAttribute('data-sexe', item.sexe || '');

    row.setAttribute('data-absences', String(item.nombre_absences || 0));

    row.setAttribute('data-actif', item.actif !== false ? 'true' : 'false');



    var abs = item.nombre_absences || 0;

    var absBadge =

      abs > 0

        ? '<span class="badge-absences ' +

          (abs >= 5 ? 'danger' : abs >= 3 ? 'warning' : 'info') +

          '"><i class="fas fa-exclamation-triangle"></i> ' +

          abs +

          '</span>'

        : '<span class="badge-absences success"><i class="fas fa-check"></i> 0</span>';



    row.innerHTML =

      '<div class="list-cell student-cell">' +

      '<div class="student-avatar-small"><i class="fas fa-user"></i></div>' +

      '<div class="student-info-compact"><h4 class="student-name">' +

      '<span class="student-name-full">' +

      esc(item.nom_complet) +

      '</span>' +

      '<span class="student-name-mobile">' +

      esc(item.premier_nom) +

      ' ' +

      esc(item.premier_prenom) +

      '</span></h4></div></div>' +

      '<div class="list-cell" data-label="Numéro"><span class="student-number">' +

      esc(item.matricule) +

      '</span></div>' +

      '<div class="list-cell" data-label="Âge"><span class="student-age">' +

      item.age +

      ' ans</span></div>' +

      '<div class="list-cell" data-label="Absences">' +

      absBadge +

      '</div>' +

      '<div class="list-cell" data-label="Inscription"><span class="inscription-date">' +

      esc(item.date_inscription) +

      '</span></div>' +

      '<div class="list-cell" data-label="Actions">' +

      '<div class="student-actions-compact">' +

      '<a href="' +

      esc(item.detail_url) +

      '" class="btn-action-small btn-view" title="Voir détails"><i class="fas fa-eye"></i></a>' +

      '<button class="btn-action-small btn-sanction" title="Ajouter une sanction" onclick="ouvrirModalSanction(' +

      item.id +

      ", '" +

      esc(item.nom_complet).replace(/'/g, "\\'") +

      "', " +

      item.classe_id +

      ')"><i class="fas fa-gavel"></i></button>' +

      '</div></div>';



    setTimeout(function () {

      row.classList.remove('eleve-row-new');

    }, 2500);

    return row;

  }



  function ensureStudentsList(classePanel) {

    var section = classePanel.querySelector('.students-section');

    if (!section) {

      return null;

    }

    var list = section.querySelector('.students-list');

    if (list) {

      return list;

    }

    var empty = section.querySelector('.empty-state');

    if (empty) {

      empty.remove();

    }

    list = document.createElement('div');

    list.className = 'students-list';

    list.innerHTML =

      '<div class="list-header">' +

      '<div class="list-cell header-cell">Élève</div>' +

      '<div class="list-cell header-cell">Numéro</div>' +

      '<div class="list-cell header-cell">Âge</div>' +

      '<div class="list-cell header-cell">Absences</div>' +

      '<div class="list-cell header-cell">Inscription</div>' +

      '<div class="list-cell header-cell">Actions</div>' +

      '</div>';

    section.appendChild(list);

    return list;

  }



  function bumpTextCount(el, delta) {

    if (!el) {

      return;

    }

    var m = (el.textContent || '').match(/(\d+)/);

    if (!m) {

      return;

    }

    var n = parseInt(m[1], 10) + delta;

    el.textContent = el.textContent.replace(/\d+/, String(Math.max(0, n)));

  }



  function updateClasseStats(classePanel, delta) {

    if (!classePanel || !delta) {

      return;

    }

    classePanel.querySelectorAll('.stat-item').forEach(function (item) {

      var label = item.querySelector('.stat-label');

      var value = item.querySelector('.stat-value');

      if (!label || !value) {

        return;

      }

      var t = label.textContent.trim().toLowerCase();

      if (t.indexOf('inscrit') >= 0) {

        bumpTextCount(value, delta);

      }

      if (t.indexOf('disponib') >= 0) {

        bumpTextCount(value, -delta);

      }

    });

    var title = classePanel.querySelector('.section-title');

    if (title) {

      bumpTextCount(title, delta);

    }

  }



  function appendEleveItem(item) {

    if (!item || !item.id) {

      return false;

    }

    if (document.querySelector('[data-eleve-id="' + item.id + '"]')) {

      return false;

    }



    if (item.main_tab_id) {

      activateMainTab(item.main_tab_id);

    }

    activateClasseTab(item.classe_id);



    var panel = document.getElementById('classe-' + item.classe_id);

    if (!panel) {

      return false;

    }



    var list = ensureStudentsList(panel);

    if (!list) {

      return false;

    }



    list.appendChild(renderEleveRow(item));

    updateClasseStats(panel, 1);



    var subBtn = document.querySelector('.classe-subtab-btn[data-subtab="classe-' + item.classe_id + '"]');

    if (subBtn) {

      var countEl = subBtn.querySelector('.classe-count');

      if (countEl) {

        bumpTextCount(countEl, 1);

      }

    }



    if (item.main_tab_id) {

      var mainBtn = document.querySelector('.tab-button[data-tab="' + item.main_tab_id + '"]');

      if (mainBtn) {

        var sc = mainBtn.querySelector('.students-count');

        if (sc) {

          var n = parseInt(sc.textContent, 10);

          if (!isNaN(n)) {

            sc.textContent = String(n + 1);

          }

        }

      }

    }



    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    return true;

  }



  function initRecuQrCodes(root) {

    if (typeof QRCode === 'undefined' || !root) {

      return;

    }

    root.querySelectorAll('.qr-code-container[data-qr-url]').forEach(function (el) {

      if (el.querySelector('canvas') || el.querySelector('img')) {

        return;

      }

      new QRCode(el, {

        text: el.dataset.qrUrl,

        width: 120,

        height: 120,

        colorDark: '#000000',

        colorLight: '#ffffff',

        correctLevel: QRCode.CorrectLevel.M,

      });

    });

  }



  function openModalRecuEleve(recuUrl) {

    var modal = document.getElementById('modalRecuEleve');

    var body = document.getElementById('modalRecuEleveBody');

    if (!modal || !body || !recuUrl) {

      return;

    }



    body.innerHTML =

      '<div class="recu-loading"><i class="fas fa-spinner fa-spin"></i> Chargement du reçu...</div>';

    modal.classList.add('active');

    lockBody(true);



    fetch(recuUrl, {

      method: 'GET',

      credentials: 'same-origin',

      headers: {

        'X-Requested-With': 'XMLHttpRequest',

        Accept: 'text/html',

      },

    })

      .then(function (response) {

        if (!response.ok) {

          throw new Error('HTTP ' + response.status);

        }

        return response.text();

      })

      .then(function (html) {

        body.innerHTML = html;

        initRecuQrCodes(body);

      })

      .catch(function () {

        body.innerHTML =

          '<div class="recu-error"><i class="fas fa-exclamation-triangle"></i> Impossible de charger le reçu.</div>';

      });

  }



  window.printRecuEleveModal = function () {

    var content = document.getElementById('recuEleveContent');

    if (!content) {

      return;

    }

    var printWindow = window.open('', '_blank');

    if (!printWindow) {

      return;

    }

    var recuCss = document.body.getAttribute('data-recu-css') || '/static/school_admin/css/directeur/reçu_inscription_eleve.css?v=1.0.2';

    printWindow.document.write(

      '<html><head><title>Reçu inscription</title>' +

      '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" />' +

      '<link rel="stylesheet" href="' + recuCss + '" />' +

      '</head><body>' +

      content.outerHTML +

      '</body></html>'

    );

    printWindow.document.close();

    printWindow.focus();

    setTimeout(function () {

      printWindow.print();

    }, 400);

  };



  function handleEleveInscrit(detail) {

    if (!detail) {

      return;

    }

    var item = detail.item || detail;

    if (!item || !item.id) {

      return;

    }

    if (window.AriaLive && AriaLive.isLocalItem(item.id)) {

      return;

    }

    appendEleveItem(item);

  }



  function initListeElevesLive() {

    var form = document.getElementById('inscriptionForm');

    if (form && window.AriaLive) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function (payload) {

          closeModalInscriptionEleve();

          form.reset();

          var phoneFull = document.getElementById('parent_telephone_full');

          if (phoneFull) {

            phoneFull.value = '';

          }



          if (payload.item) {

            appendEleveItem(payload.item);

            if (payload.item.id) {

              AriaLive.markLocalItem(payload.item.id);

            }

          }



          var recuUrl = payload.recu_url;

          if (!recuUrl && payload.item && payload.item.id) {

            recuUrl = '/reçu/eleve/' + payload.item.id + '/';

          }

          if (recuUrl) {

            openModalRecuEleve(recuUrl);

          } else if (payload.message && AriaLive.showPageSuccess) {

            AriaLive.showPageSuccess(payload.message);

          }

        },

      });

    }



    document.addEventListener('aria:eleve-inscrit', function (e) {

      handleEleveInscrit(e.detail || {});

    });



    document.addEventListener('aria:realtime', function (e) {

      var d = e.detail || {};

      if (d.type === 'eleve.inscrit') {

        handleEleveInscrit(Object.assign({ event: d.type }, d.payload || {}));

      }

    });



    if (document.body.getAttribute('data-open-inscription-modal') === '1') {

      openModalInscriptionEleve();

    }

  }



  document.addEventListener('keydown', function (e) {

    if (e.key === 'Escape') {

      closeModalRecuEleve();

      closeModalInscriptionEleve();

    }

  });



  document.addEventListener('DOMContentLoaded', initListeElevesLive);

})();


