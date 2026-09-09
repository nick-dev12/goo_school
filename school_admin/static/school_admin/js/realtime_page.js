/**
 * Utilitaires temps réel partagés (modèle TimaLove).
 */
(function () {
  'use strict';

  var skipRealtimeUntil = 0;
  var localItemIds = {};

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

  function bumpStatCard(index, delta) {
    var nums = document.querySelectorAll('.stats-section .stat-number, .stats-grid .stat-number, .stats-container .stat-card h3');
    if (!nums[index]) {
      return;
    }
    var current = parseInt(nums[index].textContent, 10) || 0;
    nums[index].textContent = current + delta;
  }

  function showPageSuccess(message) {
    if (!message) {
      return;
    }
    var container = document.querySelector('.messages-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'messages-container';
      var anchor = document.querySelector('.container, .content-container .container, .page-container, .main-content-container');
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
      '<button type="button" class="message-close" title="Fermer"><i class="fas fa-times"></i></button>';
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

  function applyFieldErrors(form, fieldErrors) {
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
    if (!fieldErrors) {
      return;
    }
    if (fieldErrors.__all__ || fieldErrors.message) {
      var alert = document.createElement('div');
      alert.className = 'alert alert-error dynamic-form-alert';
      alert.innerHTML =
        '<i class="fas fa-exclamation-triangle"></i> ' +
        escapeHtml(fieldErrors.__all__ || fieldErrors.message);
      form.prepend(alert);
    }
    Object.keys(fieldErrors).forEach(function (field) {
      if (field === '__all__' || field === 'message') {
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
  }

  function formActionUrl(form) {
    // Ne pas utiliser form.action : un <input name="action"> masque l'URL du formulaire
    // et renvoie "[object HTMLInputElement]" (ex. création de période scolaire).
    var attr = form.getAttribute('action');
    if (attr) {
      return attr;
    }
    return window.location.href;
  }

  function formMethod(form) {
    var methodAttr = form.getAttribute('method');
    if (methodAttr) {
      return methodAttr.toUpperCase();
    }
    return 'POST';
  }

  function postForm(form, options) {
    options = options || {};
    skipRealtimeUntil = Date.now() + 12000;
    var submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
    }
    return fetch(formActionUrl(form), {
      method: formMethod(form),
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrf(),
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
          applyFieldErrors(form, result.payload.field_errors || { __all__: result.payload.message || 'Erreur.' });
          if (options.onError) {
            options.onError(result.payload);
          }
          return result.payload;
        }
        if (result.payload.message) {
          showPageSuccess(result.payload.message);
        }
        if (options.onSuccess) {
          options.onSuccess(result.payload);
        }
        return result.payload;
      })
      .catch(function () {
        applyFieldErrors(form, { __all__: 'Erreur réseau.' });
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
        }
      });
  }

  function bindLiveForm(form, options) {
    if (!form || form.getAttribute('data-live-bound') === '1') {
      return;
    }
    form.setAttribute('data-live-bound', '1');
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      postForm(form, options || {});
    });
  }

  function markLocalItem(id) {
    if (id) {
      localItemIds[id] = true;
    }
  }

  function isLocalItem(id) {
    return Boolean(id && localItemIds[id]);
  }

  function shouldSkipWs() {
    return Date.now() < skipRealtimeUntil;
  }

  function reloadUnlessSkip() {
    if (!shouldSkipWs()) {
      window.location.reload();
    }
  }

  function fetchJsonUrl(url, options) {
    options = options || {};
    skipRealtimeUntil = Date.now() + 12000;
    return fetch(url, {
      method: options.method || 'GET',
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrf(),
        'X-Requested-With': 'XMLHttpRequest',
        Accept: 'application/json',
      },
      body: options.body || null,
    })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          if (result.payload.message) {
            alert(result.payload.message);
          }
          return result.payload;
        }
        if (result.payload.message) {
          showPageSuccess(result.payload.message);
        }
        if (options.onSuccess) {
          options.onSuccess(result.payload);
        }
        return result.payload;
      })
      .catch(function () {
        alert('Erreur réseau.');
      });
  }

  window.AriaLive = {
    csrf: csrf,
    escapeHtml: escapeHtml,
    bumpStatCard: bumpStatCard,
    showPageSuccess: showPageSuccess,
    applyFieldErrors: applyFieldErrors,
    postForm: postForm,
    fetchJsonUrl: fetchJsonUrl,
    bindLiveForm: bindLiveForm,
    markLocalItem: markLocalItem,
    isLocalItem: isLocalItem,
    shouldSkipWs: shouldSkipWs,
    reloadUnlessSkip: reloadUnlessSkip,
  };
})();
