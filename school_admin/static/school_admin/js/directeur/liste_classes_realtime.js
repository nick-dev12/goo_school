/**
 * Liste des classes — temps réel (modèle TimaLove messages).
 * POST JSON → { ok, item } + WebSocket → appendClasseCard(item), sans reload.
 */
(function () {
  'use strict';

  var skipRealtimeUntil = 0;
  var localSentIds = {};

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    if (m) {
      return decodeURIComponent(m[1]);
    }
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function resetSubmitButton() {
    var btn = document.getElementById('submitAddClasse');
    if (!btn) {
      return;
    }
    btn.disabled = false;
    var label = btn.querySelector('span');
    if (label) {
      label.textContent = btn.getAttribute('data-label-default') || 'Ajouter la classe';
    }
  }

  function setSubmitLoading() {
    var btn = document.getElementById('submitAddClasse');
    if (!btn) {
      return;
    }
    if (!btn.getAttribute('data-label-default')) {
      var span = btn.querySelector('span');
      if (span) {
        btn.setAttribute('data-label-default', span.textContent);
      }
    }
    btn.disabled = true;
    var label = btn.querySelector('span');
    if (label) {
      label.textContent = 'Enregistrement…';
    }
  }

  function closeModal() {
    var modal = document.getElementById('addClasseModal');
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = 'auto';
    }
  }

  function resetForm() {
    var form = document.getElementById('addClasseForm');
    if (!form) {
      return;
    }
    form.reset();
    form.querySelectorAll('.is-invalid').forEach(function (el) {
      el.classList.remove('is-invalid');
    });
    form.querySelectorAll('.invalid-feedback.dynamic').forEach(function (el) {
      el.remove();
    });
    var alert = form.querySelector('.alert.dynamic-form-alert');
    if (alert) {
      alert.remove();
    }
  }

  function showPageSuccess(message) {
    var container = document.querySelector('.messages-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'messages-container';
      var anchor = document.querySelector('.content-container.gcl-page');
      if (anchor) {
        anchor.insertBefore(container, anchor.children[1] || null);
      } else {
        document.body.prepend(container);
      }
    }
    var msg = document.createElement('div');
    msg.className = 'message message-success';
    msg.innerHTML =
      '<div class="message-icon"><i class="fas fa-check-circle"></i></div>' +
      '<div class="message-content"><div class="message-text"></div></div>' +
      '<button type="button" class="message-close" title="Fermer"><i class="fas fa-times"></i></button>' +
      '<div class="message-progress"></div>';
    msg.querySelector('.message-text').textContent = message;
    msg.querySelector('.message-close').addEventListener('click', function () {
      msg.remove();
    });
    container.prepend(msg);
    setTimeout(function () {
      if (msg.parentNode) {
        msg.remove();
      }
    }, 5000);
  }

  function bumpStat(index, delta) {
    var pill = document.querySelector('.gcl-stat-pill[data-stat-index="' + index + '"] .gcl-stat-num');
    if (!pill) {
      return;
    }
    var current = parseInt(pill.textContent, 10) || 0;
    pill.textContent = current + delta;
  }

  function findGrid(item) {
    if (!item) {
      return null;
    }
    if (item.est_superieur) {
      var panel = document.querySelector(
        '.gcl-filiere-panel[data-filiere-nom="' + CSS.escape(item.filiere_nom) + '"]'
      );
      if (!panel) {
        return null;
      }
      var niveauPanel = panel.querySelector(
        '.gcl-niveau-panel[data-niveau-key="' + CSS.escape(item.niveau_key) + '"]'
      );
      return niveauPanel ? niveauPanel.querySelector('.gcl-list') : null;
    }
    if (item.categorie_slug) {
      var catPanel = document.getElementById('panel-' + item.categorie_slug);
      return catPanel ? catPanel.querySelector('.gcl-list') : null;
    }
    return null;
  }

  function renderClasseListRow(item) {
    var row = document.createElement('div');
    row.className = 'gcl-list-row gcl-list-row--new';
    row.setAttribute('data-classe-id', String(item.id));

    var toggleIcon = item.actif ? 'pause' : 'play';
    var toggleLabel = item.actif ? 'Désactiver' : 'Activer';
    var toggleClass = item.actif ? ' gcl-act-btn--toggle-on' : '';
    var statusBadge = item.actif
      ? '<span class="gcl-badge gcl-badge--ok">Active</span>'
      : '<span class="gcl-badge gcl-badge--muted">Inactive</span>';

    var niveauCell;
    if (item.est_superieur) {
      niveauCell =
        (item.department_nom
          ? '<span class="gcl-badge gcl-badge--info">' + escapeHtml(item.department_nom) + '</span> '
          : '') +
        (item.niveau_display
          ? '<span class="gcl-badge gcl-badge--muted">' + escapeHtml(item.niveau_display) + '</span>'
          : '');
    } else {
      niveauCell = '<span class="gcl-badge gcl-badge--info">' + escapeHtml(item.niveau_display) + '</span>';
    }

    row.innerHTML =
      '<div class="gcl-list-cell gcl-list-cell--title">' +
      '<p class="gcl-item-title"><i class="fas fa-chalkboard"></i> ' + escapeHtml(item.nom) + '</p>' +
      '<p class="gcl-item-sub">' + escapeHtml(item.code_classe) + '</p></div>' +
      '<div class="gcl-list-cell">' + niveauCell + '</div>' +
      '<div class="gcl-list-cell gcl-list-cell--num">' + item.nombre_eleves + '/' + item.capacite_max + '</div>' +
      '<div class="gcl-list-cell gcl-list-cell--num">' + item.nombre_enseignants + '</div>' +
      '<div class="gcl-list-cell gcl-list-cell--num">' + item.taux_occupation + '%</div>' +
      '<div class="gcl-list-cell">' + statusBadge + '</div>' +
      '<div class="gcl-list-cell gcl-list-cell--actions">' +
      '<div class="gcl-actions-group">' +
      '<a href="' + escapeHtml(item.detail_url) + '" class="gcl-act-btn gcl-act-btn--view">' +
      '<i class="fas fa-eye"></i><span>Détails</span></a>' +
      '<a href="' + escapeHtml(item.toggle_url) + '" class="gcl-act-btn gcl-act-btn--toggle' + toggleClass + '">' +
      '<i class="fas fa-' + toggleIcon + '"></i><span>' + toggleLabel + '</span></a>' +
      '</div></div>';

    return row;
  }

  function appendClasseCard(item) {
    if (!item || !item.id) {
      return false;
    }
    if (document.querySelector('.gcl-empty-state')) {
      window.location.reload();
      return false;
    }
    if (document.querySelector('.gcl-list-row[data-classe-id="' + item.id + '"]')) {
      return true;
    }
    var list = findGrid(item);
    if (!list) {
      window.location.reload();
      return false;
    }
    list.appendChild(renderClasseListRow(item));
    bumpStat(0, 1);
    bumpStat(1, 1);
    return true;
  }

  function applyFieldErrors(fieldErrors) {
    var form = document.getElementById('addClasseForm');
    if (!form) {
      return;
    }
    form.querySelectorAll('.is-invalid').forEach(function (el) {
      el.classList.remove('is-invalid');
    });
    form.querySelectorAll('.invalid-feedback.dynamic').forEach(function (el) {
      el.remove();
    });
    var oldAlert = form.querySelector('.alert.dynamic-form-alert');
    if (oldAlert) {
      oldAlert.remove();
    }

    if (fieldErrors.__all__) {
      var alert = document.createElement('div');
      alert.className = 'alert alert-error dynamic-form-alert';
      alert.innerHTML =
        '<i class="fas fa-exclamation-triangle"></i> <strong>Erreur :</strong> ' +
        escapeHtml(fieldErrors.__all__);
      form.prepend(alert);
    }

    Object.keys(fieldErrors).forEach(function (field) {
      if (field === '__all__') {
        return;
      }
      var input = form.querySelector('[name="' + field + '"]');
      if (!input) {
        return;
      }
      input.classList.add('is-invalid');
      var feedback = document.createElement('div');
      feedback.className = 'invalid-feedback dynamic';
      feedback.textContent = fieldErrors[field];
      input.parentNode.appendChild(feedback);
    });

    var modal = document.getElementById('addClasseModal');
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  }

  function handleClasseCreated(item, fromSelf) {
    if (!item) {
      return;
    }
    if (fromSelf) {
      localSentIds[item.id] = true;
      closeModal();
      resetForm();
      resetSubmitButton();
    }
    appendClasseCard(item);
  }

  function handleRealtimePayload(payload) {
    if (!payload || !payload.item) {
      return;
    }
    if (payload.event === 'classe.creee') {
      if (localSentIds[payload.item.id]) {
        return;
      }
      appendClasseCard(payload.item);
      return;
    }
    if (payload.event === 'classe.modifiee' || payload.event === 'classe.supprimee') {
      if (Date.now() < skipRealtimeUntil) {
        return;
      }
      window.location.reload();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('addClasseForm');
    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        skipRealtimeUntil = Date.now() + 12000;
        setSubmitLoading();

        var data = new FormData(form);
        fetch(form.action, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'X-CSRFToken': csrf(),
            'X-Requested-With': 'XMLHttpRequest',
            Accept: 'application/json',
          },
          body: data,
        })
          .then(function (response) {
            return response.json().then(function (payload) {
              return { ok: response.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok || !result.payload.ok) {
              applyFieldErrors(result.payload.field_errors || { __all__: 'Erreur lors de l\'ajout.' });
              resetSubmitButton();
              return;
            }
            if (result.payload.message) {
              showPageSuccess(result.payload.message);
            }
            handleClasseCreated(result.payload.item, true);
            resetSubmitButton();
          })
          .catch(function () {
            applyFieldErrors({ __all__: 'Une erreur réseau est survenue.' });
            resetSubmitButton();
          });
      });
    }

    document.addEventListener('aria:realtime', function (e) {
      var detail = e.detail || {};
      if (
        detail.type === 'classe.creee' ||
        detail.type === 'classe.modifiee' ||
        detail.type === 'classe.supprimee'
      ) {
        handleRealtimePayload(Object.assign({ event: detail.type }, detail.payload || {}));
      }
    });

    document.addEventListener('aria:classes-live', function (e) {
      handleRealtimePayload(e.detail || {});
    });
  });
})();
