/**
 * Client WebSocket temps réel — Goo School / Aria
 * Connexion automatique, reconnexion, dispatch d'événements DOM + toasts.
 */
(function () {
  'use strict';

  var RECONNECT_DELAY_MS = 3000;
  var MAX_RECONNECT_DELAY_MS = 30000;
  var TOAST_DURATION_MS = 6000;
  var reconnectAttempts = 0;
  var socket = null;
  var reconnectTimer = null;
  var toastContainer = null;

  var EVENT_LABELS = {
    'eleve.inscrit': {
      title: 'Nouvel élève inscrit',
      body: function (p) {
        var item = p.item || p;
        return (item.nom_complet || 'Un élève') + (item.classe_nom ? ' — ' + item.classe_nom : '');
      },
      tone: 'success',
    },
    'annonce.publiee': {
      title: 'Annonce publiée',
      body: function (p) {
        return p.titre || 'Une nouvelle annonce est disponible.';
      },
      tone: 'info',
    },
    'emploi.publie': {
      title: 'Emploi du temps mis à jour',
      body: function (p) {
        return p.classe_nom ? 'Classe ' + p.classe_nom : 'Consultez le nouvel emploi du temps.';
      },
      tone: 'info',
    },
    'bulletin.publie': {
      title: 'Bulletins publiés',
      body: function (p) {
        return (p.classe_nom || 'Une classe') + (p.periode_nom ? ' — ' + p.periode_nom : '');
      },
      tone: 'success',
    },
    'bulletin.mise_a_jour': {
      title: 'Bulletins mis à jour',
      body: function (p) {
        return (p.classe_nom || 'Mise à jour') + (p.action ? ' (' + p.action + ')' : '');
      },
      tone: 'info',
    },
    'notes.mise_a_jour': {
      title: 'Notes mises à jour',
      body: function (p) {
        return (p.classe_nom || 'Une classe') + (p.matiere_nom ? ' — ' + p.matiere_nom : '');
      },
      tone: 'info',
    },
    'evaluation.creee': {
      title: 'Évaluation programmée',
      body: function (p) {
        return (p.matiere_nom || 'Matière') + (p.date ? ' — ' + p.date : '');
      },
      tone: 'warning',
    },
    'evaluation.modifiee': {
      title: 'Évaluation modifiée',
      body: function (p) {
        return p.titre || p.matiere_nom || 'Une évaluation a été mise à jour.';
      },
      tone: 'info',
    },
    'evaluation.supprimee': {
      title: 'Évaluation supprimée',
      body: function (p) {
        return p.titre || 'Une évaluation a été retirée.';
      },
      tone: 'info',
    },
    'sanction.ajoutee': {
      title: 'Sanction enregistrée',
      body: function (p) {
        return (p.eleve_nom || 'Élève') + (p.type_sanction ? ' — ' + p.type_sanction : '');
      },
      tone: 'warning',
    },
    'exercice.modifie': {
      title: 'Exercice mis à jour',
      body: function (p) {
        return p.titre || 'Un exercice a été modifié.';
      },
      tone: 'info',
    },
    'exercice.publie': {
      title: 'Nouvel exercice',
      body: function (p) {
        return p.titre || 'Un exercice a été publié.';
      },
      tone: 'info',
    },
    'presence.mise_a_jour': {
      title: 'Présences enregistrées',
      body: function (p) {
        return (p.classe_nom || 'Classe') + (p.count ? ' — ' + p.count + ' ligne(s)' : '');
      },
      tone: 'info',
    },
    'justification.soumise': {
      title: 'Justification de note',
      body: function () {
        return 'Une nouvelle justification nécessite votre attention.';
      },
      tone: 'warning',
    },
    'classe.creee': {
      title: 'Nouvelle classe',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || item.nom || 'Une classe a été ajoutée.';
      },
      tone: 'success',
    },
    'classe.modifiee': {
      title: 'Classe mise à jour',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || item.nom || 'Une classe a été modifiée.';
      },
      tone: 'info',
    },
    'classe.supprimee': {
      title: 'Classe supprimée',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || item.nom || 'Une classe a été supprimée.';
      },
      tone: 'warning',
    },
    'salle.creee': {
      title: 'Nouvelle salle',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || item.nom || 'Une salle a été ajoutée.';
      },
      tone: 'success',
    },
    'matiere.creee': {
      title: 'Nouvelle matière',
      body: function (p) {
        var item = p.item || p;
        return item.nom || 'Une matière a été ajoutée.';
      },
      tone: 'success',
    },
    'matiere.modifiee': {
      title: 'Matière mise à jour',
      body: function (p) {
        var item = p.item || p;
        return item.nom || 'Une matière a été modifiée.';
      },
      tone: 'info',
    },
    'matiere.supprimee': {
      title: 'Matière supprimée',
      body: function (p) {
        var item = p.item || p;
        return item.nom || 'Une matière a été supprimée.';
      },
      tone: 'warning',
    },
    'salle.modifiee': {
      title: 'Salle mise à jour',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || item.nom || 'Une salle a été modifiée.';
      },
      tone: 'info',
    },
    'periode.creee': {
      title: 'Période créée',
      body: function (p) {
        var item = p.item || p;
        return item.nom_periode || 'Une période a été ajoutée.';
      },
      tone: 'success',
    },
    'comptabilite.mise_a_jour': {
      title: 'Comptabilité',
      body: function (p) {
        return (p.item && p.item.message) || 'Un paiement ou solde a été mis à jour.';
      },
      tone: 'info',
    },
    'comptabilite.parametres': {
      title: 'Paramètres comptabilité',
      body: function () {
        return 'Les paramètres de comptabilité ont été mis à jour.';
      },
      tone: 'info',
    },
    'professeur.cree': {
      title: 'Nouveau professeur',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || 'Un professeur a été ajouté.';
      },
      tone: 'success',
    },
    'personnel.cree': {
      title: 'Nouveau personnel',
      body: function (p) {
        var item = p.item || p;
        return item.nom_complet || 'Un membre du personnel a été ajouté.';
      },
      tone: 'success',
    },
    'affectation.mise_a_jour': {
      title: 'Affectations',
      body: function () {
        return 'Les affectations des professeurs ont été mises à jour.';
      },
      tone: 'info',
    },
    'emploi.mise_a_jour': {
      title: 'Emploi du temps',
      body: function () {
        return 'Un emploi du temps a été modifié.';
      },
      tone: 'info',
    },
  };

  function getWebSocketUrl() {
    var scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return scheme + '//' + window.location.host + '/ws/realtime/';
  }

  function ensureToastContainer() {
    if (toastContainer) {
      return toastContainer;
    }
    toastContainer = document.createElement('div');
    toastContainer.className = 'aria-realtime-toast-container';
    toastContainer.setAttribute('aria-live', 'polite');
    document.body.appendChild(toastContainer);
    return toastContainer;
  }

  function showToast(eventType, payload) {
    var config = EVENT_LABELS[eventType];
    if (!config) {
      return;
    }
    var container = ensureToastContainer();
    var toast = document.createElement('div');
    toast.className = 'aria-realtime-toast aria-realtime-toast--' + (config.tone || 'info');
    toast.innerHTML =
      '<p class="aria-realtime-toast-title">' + config.title + '</p>' +
      '<p class="aria-realtime-toast-body">' + config.body(payload || {}) + '</p>';
    container.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, TOAST_DURATION_MS);
  }

  function dispatchEvent(eventType, payload) {
    document.dispatchEvent(
      new CustomEvent('aria:realtime', {
        detail: { type: eventType, payload: payload || {} },
      })
    );

    if (eventType === 'eleve.inscrit') {
      document.dispatchEvent(new CustomEvent('aria:eleve-inscrit', { detail: payload }));
    }

    if (
      eventType === 'classe.creee' ||
      eventType === 'classe.modifiee' ||
      eventType === 'classe.supprimee'
    ) {
      document.dispatchEvent(
        new CustomEvent('aria:classes-live', {
          detail: Object.assign({ event: eventType }, payload || {}),
        })
      );
    }

    var directeurEvents = [
      'salle.creee', 'salle.modifiee',
      'matiere.creee', 'matiere.modifiee', 'matiere.supprimee',
      'periode.creee', 'periode.modifiee', 'periode.supprimee', 'annee_scolaire.creee',
      'comptabilite.parametres', 'comptabilite.mise_a_jour',
      'professeur.cree', 'personnel.cree', 'affectation.mise_a_jour', 'emploi.mise_a_jour',
    ];
    if (directeurEvents.indexOf(eventType) !== -1) {
      document.dispatchEvent(
        new CustomEvent('aria:live-directeur', {
          detail: Object.assign({ event: eventType }, payload || {}),
        })
      );
    }

    var enseignantEvents = [
      'evaluation.creee', 'evaluation.modifiee', 'evaluation.supprimee',
      'notes.mise_a_jour', 'presence.mise_a_jour', 'justification.soumise',
      'exercice.publie', 'exercice.modifie', 'sanction.ajoutee',
    ];
    if (enseignantEvents.indexOf(eventType) !== -1) {
      document.dispatchEvent(
        new CustomEvent('aria:live-enseignant', {
          detail: Object.assign({ type: eventType, payload: payload || {} }, payload || {}),
        })
      );
    }

    showToast(eventType, payload);
  }

  function scheduleReconnect() {
    if (reconnectTimer) {
      return;
    }
    var delay = Math.min(
      RECONNECT_DELAY_MS * Math.pow(1.5, reconnectAttempts),
      MAX_RECONNECT_DELAY_MS
    );
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      reconnectAttempts += 1;
      connect();
    }, delay);
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      socket = new WebSocket(getWebSocketUrl());
    } catch (err) {
      console.warn('[Aria Realtime] WebSocket non disponible', err);
      scheduleReconnect();
      return;
    }

    socket.onopen = function () {
      reconnectAttempts = 0;
      console.info('[Aria Realtime] Connecté');
    };

    socket.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        if (data.type === 'pong' || data.type === 'connection.established') {
          return;
        }
        dispatchEvent(data.type, data.payload);
      } catch (err) {
        console.warn('[Aria Realtime] Message invalide', err);
      }
    };

    socket.onclose = function () {
      scheduleReconnect();
    };

    socket.onerror = function () {
      if (socket) {
        socket.close();
      }
    };
  }

  function startHeartbeat() {
    setInterval(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 45000);
  }

  document.addEventListener('DOMContentLoaded', function () {
    connect();
    startHeartbeat();
  });

  window.AriaRealtime = {
    connect: connect,
    on: function (eventType, handler) {
      document.addEventListener('aria:realtime', function (e) {
        if (e.detail.type === eventType) {
          handler(e.detail.payload);
        }
      });
    },
  };
})();
