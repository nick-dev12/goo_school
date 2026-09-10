(function () {
  var form = document.getElementById("presence-form");
  if (!form) {
    return;
  }

  var contextNode = document.getElementById("presence-offline-context");
  var context = {};
  if (contextNode) {
    try {
      context = JSON.parse(contextNode.textContent || "{}");
    } catch (e) {
      context = {};
    }
  }

  function cacheEleves() {
    if (!window.AriaOffline || !context.eleves || !context.eleves.length) {
      return;
    }
    window.AriaOffline.cachePut("eleves", context.eleves).catch(function () {});
    if (context.classe_id) {
      window.AriaOffline.cachePut("classes", [
        {
          id: context.classe_id,
          server_id: context.classe_id,
          nom: context.classe_nom || "",
        },
      ]).catch(function () {});
    }
  }

  function collectPresences() {
    var items = [];
    var radios = form.querySelectorAll('input[type="radio"][name^="presence_"]');
    var seen = {};
    radios.forEach(function (input) {
      if (!input.checked) {
        return;
      }
      var eleveId = input.name.replace("presence_", "");
      if (seen[eleveId]) {
        return;
      }
      seen[eleveId] = true;
      items.push({ eleve_id: parseInt(eleveId, 10), statut: input.value });
    });
    return items;
  }

  function showLocalMessage(text, type) {
    var box = document.getElementById("presence-offline-message");
    if (!box) {
      box = document.createElement("div");
      box.id = "presence-offline-message";
      box.className = "presence-offline-message";
      form.parentNode.insertBefore(box, form);
    }
    box.className = "presence-offline-message is-" + (type || "info");
    box.textContent = text;
    box.hidden = false;
  }

  function disableForm() {
    form.querySelectorAll("input, button, select").forEach(function (el) {
      el.disabled = true;
    });
  }

  if (window.AriaOffline) {
    cacheEleves();
  }
  window.addEventListener("aria-offline-ready", cacheEleves);

  form.addEventListener("submit", function (event) {
    if (!window.AriaOffline) {
      return;
    }

    var nativeOnline =
      typeof navigator.onLine === "boolean" ? navigator.onLine : true;

    event.preventDefault();
    Promise.resolve(window.AriaOffline.isOnline())
      .then(function (online) {
        if (online && nativeOnline) {
          form.submit();
          return;
        }

        var payload = {
          classe_id: context.classe_id,
          matiere_id: context.matiere_id || null,
          numero_appel: context.numero_appel || 1,
          date: context.date,
          niveau: context.niveau || "secondaire",
          presences: collectPresences(),
        };

        return window.AriaOffline.save({
          client_uuid:
            window.crypto && crypto.randomUUID
              ? crypto.randomUUID()
              : String(Date.now()),
          resource: "presence_liste",
          action: "CREATE",
          payload: payload,
        }).then(function () {
          showLocalMessage(
            "Liste enregistrée hors ligne. Elle sera envoyée automatiquement au retour du réseau.",
            "success"
          );
          disableForm();
        });
      })
      .catch(function (err) {
        showLocalMessage(
          "Impossible d'enregistrer hors ligne : " + (err && err.message ? err.message : err),
          "error"
        );
      });
  });
})();
