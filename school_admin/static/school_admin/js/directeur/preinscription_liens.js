/**
 * Liens préinscription — onglets, QR code, copie URL (UI v2)
 */

(function () {
  'use strict';

  function switchSplTab(tabId, btn) {
    document.querySelectorAll('.spl-tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.spl-tab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.spl-tab-btn[data-spl-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
  }

  function initQrCode() {
    var container = document.getElementById('spl-qrcode');
    if (!container || typeof QRCode === 'undefined') return;
    var url = container.getAttribute('data-url');
    if (!url) return;
    container.innerHTML = '';
    new QRCode(container, {
      text: url,
      width: 220,
      height: 220,
      colorDark: '#111827',
      colorLight: '#ffffff',
      correctLevel: QRCode.CorrectLevel.M,
    });
  }

  function copyUrl() {
    var input = document.getElementById('spl-url-input');
    var btn = document.getElementById('spl-copy-btn');
    if (!input || !btn) return;

    var text = input.value;
    var done = function () {
      btn.classList.add('spl-copy-btn--ok');
      var icon = btn.querySelector('i');
      var label = btn.querySelector('span');
      if (icon) icon.className = 'fas fa-check';
      if (label) label.textContent = 'Copié !';
      setTimeout(function () {
        btn.classList.remove('spl-copy-btn--ok');
        if (icon) icon.className = 'fas fa-copy';
        if (label) label.textContent = 'Copier';
      }, 2000);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        input.select();
        document.execCommand('copy');
        done();
      });
    } else {
      input.select();
      document.execCommand('copy');
      done();
    }
  }

  function printQrCode() {
    var qrContainer = document.getElementById('spl-qrcode');
    var nomEcole = document.body.getAttribute('data-ecole-nom') || '';
    var url = document.getElementById('spl-url-input')?.value || '';
    if (!qrContainer) return;

    var printWindow = window.open('', '_blank');
    if (!printWindow) return;

    printWindow.document.write(
      '<!DOCTYPE html><html><head><title>QR Code préinscription</title>' +
      '<style>body{font-family:Arial,sans-serif;text-align:center;padding:24px}' +
      'h1{font-size:22px;margin-bottom:8px}p{color:#4b5563;font-size:14px}' +
      '.qr{margin:24px 0}.steps{text-align:left;max-width:420px;margin:24px auto;padding:16px;background:#f3f4f6;border-radius:8px}' +
      '</style></head><body>' +
      '<h1>QR Code de préinscription</h1>' +
      '<p><strong>École :</strong> ' + nomEcole + '</p>' +
      '<p><strong>URL :</strong> ' + url + '</p>' +
      '<div class="qr">' + qrContainer.innerHTML + '</div>' +
      '<div class="steps"><strong>Instructions pour les parents</strong><ol>' +
      '<li>Ouvrez l’appareil photo du téléphone</li><li>Scannez le QR code</li>' +
      '<li>Suivez le lien affiché</li><li>Remplissez le formulaire</li></ol></div>' +
      '</body></html>'
    );
    printWindow.document.close();
    setTimeout(function () {
      printWindow.print();
    }, 400);
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.spl-tab-btn[data-spl-tab]');
    if (tabBtn) {
      switchSplTab(tabBtn.getAttribute('data-spl-tab'), tabBtn);
    }
    if (event.target.closest('#spl-copy-btn') || event.target.closest('[data-copy-url]')) {
      copyUrl();
    }
    if (event.target.closest('#spl-print-qr')) {
      printQrCode();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    switchSplTab('spl-panel-lien');
    if (typeof QRCode !== 'undefined') {
      initQrCode();
    } else {
      var tries = 0;
      var timer = setInterval(function () {
        tries += 1;
        if (typeof QRCode !== 'undefined') {
          clearInterval(timer);
          initQrCode();
        } else if (tries > 30) {
          clearInterval(timer);
        }
      }, 100);
    }
  });
})();
