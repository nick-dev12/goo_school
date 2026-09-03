/**
 * Client WebSocket temps réel — Goo School / Aria
 * Connexion automatique, reconnexion, dispatch d'événements DOM.
 */
(function () {
  'use strict';

  var RECONNECT_DELAY_MS = 3000;
  var MAX_RECONNECT_DELAY_MS = 30000;
  var reconnectAttempts = 0;
  var socket = null;
  var reconnectTimer = null;

  function getWebSocketUrl() {
    var scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return scheme + '//' + window.location.host + '/ws/realtime/';
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
