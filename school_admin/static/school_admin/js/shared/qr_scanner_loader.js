/* Scanner QR : la bibliothèque (375 Ko) n'est téléchargée qu'à la première ouverture du scanner,
   plus à chaque page. window.ariaChargerScannerQR() renvoie une promesse résolue quand Html5Qrcode est prêt. */
(function () {
  var chargement = null;
  window.ariaChargerScannerQR = function () {
    if (window.Html5Qrcode) return Promise.resolve();
    if (!chargement) {
      chargement = new Promise(function (resolve, reject) {
        var script = document.createElement('script');
        script.src = '/static/school_admin/vendor/html5-qrcode/html5-qrcode.min.js?v=2.3.8';
        script.onload = function () { window.Html5Qrcode ? resolve() : reject(new Error('Html5Qrcode absent')); };
        script.onerror = function () { chargement = null; reject(new Error('Chargement du scanner impossible')); };
        document.head.appendChild(script);
      });
    }
    return chargement;
  };
})();
