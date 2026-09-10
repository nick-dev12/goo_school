(function () {
  function initBanner() {
    var banner = document.getElementById("aria-offline-banner");
    if (!banner || !window.AriaOffline) {
      return;
    }
    if (banner.dataset.bound === "1") {
      return;
    }
    banner.dataset.bound = "1";

    function render(online, pending) {
      var count = pending || 0;
      banner.hidden = online && count === 0;
      banner.classList.toggle("is-offline", !online);
      banner.classList.toggle("has-pending", count > 0);
      var label = banner.querySelector("[data-offline-label]");
      if (!label) {
        return;
      }
      if (!online) {
        label.textContent =
          count > 0
            ? "Hors ligne — " + count + " action(s) en attente"
            : "Hors ligne — les actions seront synchronisées au retour du réseau";
        return;
      }
      label.textContent = count + " action(s) en attente de synchronisation";
    }

    window.addEventListener("aria-connectivity", function (event) {
      var detail = (event && event.detail) || {};
      render(!!detail.online, detail.pending || 0);
    });

    if (window.__ARIA_OFFLINE_STATUS) {
      render(
        !!window.__ARIA_OFFLINE_STATUS.online,
        window.__ARIA_OFFLINE_STATUS.pending || 0
      );
      return;
    }

    Promise.all([
      window.AriaOffline.isOnline(),
      window.AriaOffline.pendingCount(),
    ])
      .then(function (values) {
        render(!!values[0], values[1] || 0);
      })
      .catch(function () {});
  }

  if (window.AriaOffline) {
    initBanner();
  }
  window.addEventListener("aria-offline-ready", initBanner);
})();
