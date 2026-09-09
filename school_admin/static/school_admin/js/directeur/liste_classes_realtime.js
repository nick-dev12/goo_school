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
      var anchor = document.querySelector('.content-container .container');
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
    var nums = document.querySelectorAll('.stats-section .stat-number');
    if (!nums[index]) {
      return;
    }
    var current = parseInt(nums[index].textContent, 10) || 0;
    nums[index].textContent = current + delta;
  }

  function findGrid(item) {
    if (!item) {
      return null;
    }
    if (item.est_superieur) {
      var panel = document.querySelector(
        '.tab-panel[data-filiere-nom="' + CSS.escape(item.filiere_nom) + '"]'
      );
      if (!panel) {
        return null;
      }
      var niveauPanel = panel.querySelector(
        '.classes-niveau-panel[data-niveau-key="' + CSS.escape(item.niveau_key) + '"]'
      );
      return niveauPanel ? niveauPanel.querySelector('.classes-grid') : null;
    }
    var tab = document.getElementById('niveau-scolaire-' + item.niveau_scolaire);
    return tab ? tab.querySelector('.classes-grid') : null;
  }

  function renderExamensBlock(item) {
    if (!item.examens || !item.examens.length) {
      return '';
    }
    var tags = item.examens
      .map(function (ex) {
        return (
          '<span class="classe-examen-tag" title="' +
          escapeHtml(ex.description) +
          '"><i class="fas fa-certificate"></i> ' +
          escapeHtml(ex.libelle) +
          '</span>'
        );
      })
      .join('');
    return (
      '<div class="classe-card-examens">' +
      '<div class="classe-card-examens-label"><i class="fas fa-flag-checkered"></i> Examens & concours</div>' +
      '<div class="classe-card-examens-tags">' +
      tags +
      '</div></div>'
    );
  }

  function renderClasseCard(item) {
    var card = document.createElement('div');
    card.className = 'classe-card';
    card.setAttribute('data-classe-id', String(item.id));

    var statusClass = item.actif ? 'active' : 'inactive';
    var statusIcon = item.actif ? 'check-circle' : 'times-circle';
    var statusLabel = item.actif ? 'Active' : 'Inactive';
    var toggleIcon = item.actif ? 'pause' : 'play';
    var toggleLabel = item.actif ? 'Désactiver' : 'Activer';
    var toggleActive = item.actif ? ' active' : '';

    if (item.est_superieur) {
      card.innerHTML =
        '<div class="classe-header">' +
        '<div class="classe-icon"><i class="fas fa-book"></i></div>' +
        '<div class="classe-info">' +
        '<h3 class="classe-nom">' +
        escapeHtml(item.nom) +
        '</h3>' +
        '<p class="classe-niveau">' +
        escapeHtml(item.niveau_display) +
        '</p>' +
        '<div class="classe-badge niveau-superieur"><span>' +
        escapeHtml(item.niveau_display) +
        '</span></div></div>' +
        '<div class="classe-status"><div class="status-badge status-' +
        statusClass +
        '"><i class="fas fa-' +
        statusIcon +
        '"></i><span>' +
        statusLabel +
        '</span></div></div></div>' +
        '<div class="classe-details">' +
        '<div class="detail-row">' +
        '<div class="detail-item"><i class="fas fa-user-graduate"></i> <span class="detail-label">Élèves:</span> <span class="detail-value">' +
        item.nombre_eleves +
        '/' +
        item.capacite_max +
        '</span></div>' +
        '<div class="detail-item"><i class="fas fa-chalkboard-teacher"></i> <span class="detail-label">Enseignants:</span> <span class="detail-value">' +
        item.nombre_enseignants +
        '</span></div></div>' +
        '<div class="detail-row">' +
        '<div class="detail-item"><i class="fas fa-chart-pie"></i> <span class="detail-label">Occupation:</span> <span class="detail-value">' +
        item.taux_occupation +
        '%</span></div>' +
        '<div class="detail-item"><i class="fas fa-code"></i> <span class="detail-label">Code:</span> <span class="detail-value">' +
        escapeHtml(item.code_classe) +
        '</span></div></div></div>' +
        renderExamensBlock(item) +
        '<div class="classe-actions">' +
        '<a href="' +
        escapeHtml(item.detail_url) +
        '" class="btn-action btn-detail"><i class="fas fa-eye"></i> <span>Détails</span></a>' +
        '<a href="' +
        escapeHtml(item.toggle_url) +
        '" class="btn-action btn-toggle' +
        toggleActive +
        '"><i class="fas fa-' +
        toggleIcon +
        '"></i> <span>' +
        toggleLabel +
        '</span></a></div>';
      return card;
    }

    card.innerHTML =
      '<div class="classe-header">' +
      '<div class="classe-icon"><i class="fas fa-' +
      escapeHtml(item.icon) +
      '"></i></div>' +
      '<div class="classe-info">' +
      '<h3 class="classe-nom">' +
      escapeHtml(item.nom) +
      '</h3>' +
      '<p class="classe-niveau">' +
      escapeHtml(item.niveau_display) +
      '</p>' +
      '<div class="classe-badge ' +
      escapeHtml(item.niveau_badge_class) +
      '"><span>' +
      escapeHtml(item.niveau_display) +
      '</span></div></div>' +
      '<div class="classe-status"><div class="status-badge status-' +
      statusClass +
      '"><i class="fas fa-' +
      statusIcon +
      '"></i><span>' +
      statusLabel +
      '</span></div></div></div>' +
      '<div class="classe-details">' +
      '<div class="detail-row">' +
      '<div class="detail-item"><i class="fas fa-user-graduate"></i> <span class="detail-label">Élèves:</span> <span class="detail-value">' +
      item.nombre_eleves +
      '/' +
      item.capacite_max +
      '</span></div>' +
      '<div class="detail-item"><i class="fas fa-chalkboard-teacher"></i> <span class="detail-label">Enseignants:</span> <span class="detail-value">' +
      item.nombre_enseignants +
      '</span></div></div>' +
      '<div class="detail-row">' +
      '<div class="detail-item"><i class="fas fa-chart-pie"></i> <span class="detail-label">Occupation:</span> <span class="detail-value">' +
      item.taux_occupation +
      '%</span></div>' +
      '<div class="detail-item"><i class="fas fa-calendar-plus"></i> <span class="detail-label">Créée:</span> <span class="detail-value">' +
      escapeHtml(item.date_creation) +
      '</span></div></div>' +
      '<div class="detail-row"><div class="detail-item full-width"><i class="fas fa-code"></i> <span class="detail-label">Code:</span> <span class="detail-value">' +
      escapeHtml(item.code_classe) +
      '</span></div></div></div>' +
      '<div class="classe-actions">' +
      '<a href="' +
      escapeHtml(item.detail_url) +
      '" class="btn-action btn-detail"><i class="fas fa-eye"></i> <span>Détails</span></a>' +
      '<a href="' +
      escapeHtml(item.toggle_url) +
      '" class="btn-action btn-toggle' +
      toggleActive +
      '"><i class="fas fa-' +
      toggleIcon +
      '"></i> <span>' +
      toggleLabel +
      '</span></a></div>';
    return card;
  }

  function appendClasseCard(item) {
    if (!item || !item.id) {
      return false;
    }
    if (document.querySelector('.empty-state')) {
      window.location.reload();
      return false;
    }
    if (document.querySelector('.classe-card[data-classe-id="' + item.id + '"]')) {
      return true;
    }
    var grid = findGrid(item);
    if (!grid) {
      window.location.reload();
      return false;
    }
    var card = renderClasseCard(item);
    card.classList.add('classe-card--new');
    grid.appendChild(card);
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
