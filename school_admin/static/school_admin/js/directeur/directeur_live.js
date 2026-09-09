/**

 * Pages directeur — temps réel (modèle TimaLove).

 */

(function () {

  'use strict';



  if (!window.AriaLive) {

    return;

  }



  var esc = AriaLive.escapeHtml;



  function fmtMoney(amount, devise) {

    return (

      new Intl.NumberFormat('fr-FR', {

        minimumFractionDigits: 0,

        maximumFractionDigits: 0,

      }).format(amount || 0) +

      ' ' +

      (devise || 'FCFA')

    );

  }



  function findSalleGrid(item) {

    var panel = document.getElementById('type-' + item.type_salle);

    return panel ? panel.querySelector('.salles-grid') : null;

  }



  function renderSalleCard(item) {

    var card = document.createElement('div');

    card.className = 'salle-card';

    card.setAttribute('data-salle-id', String(item.id));

    var actif = item.actif !== false;

    var etatIcon =

      item.etat === 'disponible' ? 'check-circle' : item.etat === 'occupee' ? 'times-circle' : item.etat === 'maintenance' ? 'tools' : 'lock';

    card.innerHTML =

      '<div class="salle-header">' +

      '<div class="salle-icon"><i class="fas fa-' + esc(item.icon) + '"></i></div>' +

      '<div class="salle-info"><h3 class="salle-nom">' + esc(item.nom) + '</h3>' +

      '<p class="salle-numero">' + esc(item.numero) + '</p>' +

      '<div class="salle-badge type-' + esc(item.type_salle) + '"><span>' + esc(item.type_display) + '</span></div></div>' +

      '<div class="salle-status"><div class="status-badge status-' + esc(item.etat) + '">' +

      '<i class="fas fa-' + etatIcon + '"></i><span>' + esc(item.etat_display) + '</span></div></div></div>' +

      '<div class="salle-details"><div class="detail-row">' +

      '<div class="detail-item"><i class="fas fa-users"></i><span class="detail-label">Capacité:</span>' +

      '<span class="detail-value">' + item.capacite_max + '</span></div>' +

      '<div class="detail-item"><i class="fas fa-calendar-plus"></i><span class="detail-label">Créée:</span>' +

      '<span class="detail-value">' + esc(item.date_creation) + '</span></div></div></div>' +

      '<div class="salle-actions">' +

      '<a href="' + esc(item.detail_url) + '" class="btn-action btn-detail"><i class="fas fa-eye"></i><span>Détails</span></a>' +

      '<a href="' +

      esc(item.toggle_url) +

      '" class="btn-action btn-toggle ' +

      (actif ? 'active' : '') +

      '" data-live-toggle="salle"><i class="fas fa-' +

      (actif ? 'pause' : 'play') +

      '"></i><span>' +

      (actif ? 'Désactiver' : 'Activer') +

      '</span></a></div>';

    return card;

  }



  function appendSalle(item) {

    if (!item || document.querySelector('[data-salle-id="' + item.id + '"]')) {

      return;

    }

    if (document.querySelector('.empty-state')) {

      window.location.reload();

      return;

    }

    var grid = findSalleGrid(item);

    if (!grid) {

      window.location.reload();

      return;

    }

    grid.appendChild(renderSalleCard(item));

    AriaLive.bumpStatCard(0, 1);

    AriaLive.bumpStatCard(1, 1);

  }



  function updateSalleCard(item) {

    if (!item) {

      return;

    }

    var existing = document.querySelector('[data-salle-id="' + item.id + '"]');

    if (!existing) {

      appendSalle(item);

      return;

    }

    var oldPanel = existing.closest('.tab-panel');

    var oldType = oldPanel ? oldPanel.id.replace('type-', '') : item.previous_type_salle;

    if (oldType && oldType !== item.type_salle) {

      existing.remove();

      appendSalle(item);

      return;

    }

    existing.replaceWith(renderSalleCard(item));

  }



  function updateSalleDetailPage(item) {

    if (!item) {

      return;

    }

    document.querySelectorAll('.header-title h1, .salle-info h2').forEach(function (el) {

      el.textContent = item.nom;

    });

    document.querySelectorAll('.salle-info p, .header-title p').forEach(function (el, idx) {

      if (idx === 0) {

        el.textContent = item.numero + ' - ' + item.type_display;

      }

    });

    document.querySelectorAll('.info-item .info-value').forEach(function (el) {

      var label = el.parentNode.querySelector('.info-label');

      if (!label) {

        return;

      }

      var text = label.textContent || '';

      if (text.indexOf('Nom') !== -1) {

        el.textContent = item.nom;

      } else if (text.indexOf('Numéro') !== -1) {

        el.textContent = item.numero;

      } else if (text.indexOf('Type') !== -1) {

        el.textContent = item.type_display;

      } else if (text.indexOf('État') !== -1) {

        el.textContent = item.etat_display;

        el.className = 'info-value status-' + item.etat;

      } else if (text.indexOf('Capacité') !== -1) {

        el.textContent = item.capacite_max + ' personnes';

      }

    });

    var form = document.querySelector('.modifier-form');

    if (form) {

      var nomInput = form.querySelector('[name="nom"]');

      var numeroInput = form.querySelector('[name="numero"]');

      var typeInput = form.querySelector('[name="type_salle"]');

      var etatInput = form.querySelector('[name="etat"]');

      var capInput = form.querySelector('[name="capacite_max"]');

      if (nomInput) {

        nomInput.value = item.nom;

      }

      if (numeroInput) {

        numeroInput.value = item.numero;

      }

      if (typeInput) {

        typeInput.value = item.type_salle;

      }

      if (etatInput) {

        etatInput.value = item.etat;

      }

      if (capInput) {

        capInput.value = item.capacite_max;

      }

    }

  }



  function bindSalleToggleLinks() {

    document.querySelectorAll('a.btn-toggle[data-live-toggle="salle"], a.btn-toggle[href*="/toggle/"]').forEach(function (link) {

      if (link.getAttribute('data-live-bound') === '1') {

        return;

      }

      link.setAttribute('data-live-bound', '1');

      link.addEventListener('click', function (event) {

        event.preventDefault();

        AriaLive.fetchJsonUrl(link.getAttribute('href'), {

          onSuccess: function (payload) {

            if (payload.item) {

              AriaLive.markLocalItem(payload.item.id);

              updateSalleCard(payload.item);

            }

          },

        });

      });

    });

  }



  function findMatiereGrid(item) {

    if (item.est_superieur && item.dep_id) {

      var panel = document.querySelector('.department-panel[data-dep-id="' + item.dep_id + '"]');

      return panel ? panel.querySelector('.matieres-cards-grid, .matieres-grid') : null;

    }

    return document.querySelector('.matieres-grid');

  }



  function renderMatiereCard(item) {

    var card = document.createElement('div');

    card.className = 'matiere-card';

    card.setAttribute('data-matiere-id', String(item.id));

    var coeff =

      item.est_lycee && item.coefficients_par_groupe && Object.keys(item.coefficients_par_groupe).length

        ? 'Coeff: Variable par groupe'

        : 'Coeff: ' + item.coefficient;

    var extra = '';

    if (item.est_superieur && item.department_nom) {

      extra += '<div class="detail-item"><i class="fas fa-building"></i><span>' + esc(item.department_nom) + '</span></div>';

    }

    if (item.est_superieur && item.module_nom) {

      extra +=

        '<div class="detail-item"><i class="fas fa-coins"></i><span>Crédits: ' +

        esc(item.credits || '0') +

        ' • ' +

        esc(item.module_nom) +

        '</span></div>';

    }

    card.innerHTML =

      '<div class="card-header"><div class="matiere-info"><h3 class="matiere-nom">' +

      esc(item.nom) +

      '</h3>' +

      '<p class="matiere-type">' +

      esc(item.type_display) +

      '</p></div>' +

      '<div class="matiere-actions"><a href="' +

      esc(item.detail_url) +

      '" class="action-btn primary"><i class="fas fa-eye"></i></a></div></div>' +

      '<div class="card-content"><div class="matiere-details">' +

      '<div class="detail-item"><i class="fas fa-graduation-cap"></i><span>' +

      esc(item.niveau_display) +

      '</span></div>' +

      extra +

      '<div class="detail-item"><i class="fas fa-weight-hanging"></i><span>' +

      coeff +

      '</span></div>' +

      '<div class="detail-item"><i class="fas fa-users"></i><span>' +

      item.nb_classes +

      ' classe(s)</span></div></div></div>';

    return card;

  }



  function appendMatiere(item) {

    if (!item || document.querySelector('[data-matiere-id="' + item.id + '"]')) {

      return;

    }

    var grid = findMatiereGrid(item);

    if (!grid) {

      window.location.reload();

      return;

    }

    grid.appendChild(renderMatiereCard(item));

    AriaLive.bumpStatCard(0, 1);

  }



  function updateMatiereCard(item) {

    if (!item) {

      return;

    }

    var existing = document.querySelector('[data-matiere-id="' + item.id + '"]');

    if (existing) {

      var oldDep = existing.closest('.department-panel');

      var newCard = renderMatiereCard(item);

      existing.replaceWith(newCard);

      if (item.est_superieur && item.dep_id && oldDep && oldDep.getAttribute('data-dep-id') !== String(item.dep_id)) {

        var targetGrid = findMatiereGrid(item);

        if (targetGrid && newCard.parentNode !== targetGrid) {

          newCard.remove();

          targetGrid.appendChild(newCard);

        }

      }

      return;

    }

    appendMatiere(item);

  }



  function removeMatiere(item) {

    if (!item || !item.id) {

      return;

    }

    var card = document.querySelector('[data-matiere-id="' + item.id + '"]');

    if (card) {

      card.remove();

    }

  }



  function updateMatiereDetailPage(item) {

    if (!item) {

      return;

    }

    document.querySelectorAll('.page-title, .matiere-details h2, .info-card h2').forEach(function (el) {

      el.textContent = item.nom;

    });

    document.querySelectorAll('.matiere-type, .page-subtitle').forEach(function (el) {

      if (el.classList.contains('matiere-type') || el.textContent.indexOf('Détails') !== -1) {

        if (el.classList.contains('matiere-type')) {

          el.textContent = item.type_display;

        }

      }

    });

    document.querySelectorAll('.badge-coefficient').forEach(function (el) {

      if (item.est_lycee && item.coefficients_par_groupe && Object.keys(item.coefficients_par_groupe).length) {

        el.textContent = 'Coeff: Variable par groupe';

      } else {

        el.textContent = 'Coeff: ' + item.coefficient;

      }

    });

  }



  function renderPeriodeCard(item) {

    var card = document.createElement('div');

    card.className = 'periode-card ' + item.status_class;

    card.setAttribute('data-periode-id', String(item.id));

    card.innerHTML =

      '<div class="periode-header"><div class="periode-titre">' +

      esc(item.nom_periode) +

      '</div>' +

      '<span class="periode-badge ' +

      (item.est_active ? 'actif' : 'inactif') +

      '">' +

      (item.est_active ? 'Actif' : 'Inactif') +

      '</span></div>' +

      '<div class="periode-info">' +

      '<div class="periode-info-item"><i class="fas fa-tag"></i><span>Type : ' +

      esc(item.type_display) +

      '</span></div>' +

      '<div class="periode-info-item"><i class="fas fa-calendar-day"></i><span>Du ' +

      esc(item.date_debut) +

      ' au ' +

      esc(item.date_fin) +

      '</span></div>' +

      '<div class="periode-info-item"><i class="fas fa-clock"></i><span>Durée : ' +

      item.duree_jours +

      ' jours</span></div></div>' +

      '<div class="periode-status ' +

      item.status_class +

      '"><i class="fas fa-circle"></i> Mise à jour</div>' +

      '<div class="periode-actions">' +

      '<button type="button" class="btn-action edit" data-id="' +

      item.id +

      '" data-nom="' +

      esc(item.nom_periode) +

      '" data-type="' +

      esc(item.type_periode) +

      '" data-niveau-lmd="' +

      esc(item.niveau_lmd) +

      '" data-debut="' +

      esc(item.date_debut_iso) +

      '" data-fin="' +

      esc(item.date_fin_iso) +

      '" data-annee="' +

      esc(item.annee_scolaire) +

      '" data-active="' +

      (item.est_active ? 'true' : 'false') +

      '" onclick="openEditPeriodeModal(this)"><i class="fas fa-pen"></i> Modifier</button>' +

      '<button type="button" class="btn-action delete" data-id="' +

      item.id +

      '" data-nom="' +

      esc(item.nom_periode) +

      '" onclick="openDeletePeriodeModal(this)"><i class="fas fa-trash"></i> Supprimer</button></div>';

    return card;

  }



  function appendPeriode(item) {

    if (!item) {

      return;

    }

    var existing = document.querySelector('[data-periode-id="' + item.id + '"]');

    if (existing) {

      existing.replaceWith(renderPeriodeCard(item));

      return;

    }

    if (document.querySelector('.empty-state')) {

      window.location.reload();

      return;

    }

    var grid = null;

    if (item.tab_key) {

      var panel = document.querySelector('.periodes-tab-panel[data-tab-panel="' + item.tab_key + '"]');

      if (panel) {

        grid = panel.querySelector('.periodes-grid');

      }

    }

    if (!grid) {

      grid = document.querySelector('.periodes-grid');

    }

    if (!grid) {

      window.location.reload();

      return;

    }

    grid.appendChild(renderPeriodeCard(item));

  }



  function removePeriode(item) {

    if (!item || !item.id) {

      return;

    }

    var card = document.querySelector('[data-periode-id="' + item.id + '"]');

    if (card) {

      card.remove();

    }

  }



  function renderMensualiteBadge(row) {

    var style =

      row.statut_badge === 'warning'

        ? ' style="background-color: #fbbf24; color: #1f2937; font-weight: 600;"'

        : row.statut_badge === 'danger'

          ? ' style="background-color: #ef4444; color: white; font-weight: 600;"'

          : '';

    return '<span class="badge badge-' + row.statut_badge + '"' + style + '>' + esc(row.statut_display) + '</span>';

  }



  function renderFraisRow(row, devise) {

    var resteColor = row.reste_a_payer > 0 ? 'var(--accent, #ef4444)' : 'var(--success, #10b981)';

    var action = row.can_pay

      ? '<button type="button" class="btn btn-success" onclick="openPaiementModal(\'frais\', ' +

        row.id +

        ', ' +

        row.montant_total +

        ', ' +

        row.montant_paye +

        ', ' +

        row.reste_a_payer +

        ')" style="padding: 0.5rem 1rem; font-size: 0.875rem;"><i class="fas fa-money-bill-wave"></i> Payer</button>'

      : '<span class="badge badge-success">Payé</span>';

    return (

      '<tr data-frais-id="' +

      row.id +

      '">' +

      '<td>' +

      esc(row.type_display) +

      '</td>' +

      '<td><strong>' +

      fmtMoney(row.montant_total, devise) +

      '</strong></td>' +

      '<td>' +

      fmtMoney(row.montant_paye, devise) +

      '</td>' +

      '<td><span style="color: ' +

      resteColor +

      '; font-weight: 600;">' +

      fmtMoney(row.reste_a_payer, devise) +

      '</span></td>' +

      '<td>' +

      esc(row.date_echeance) +

      '</td>' +

      '<td><span class="badge badge-' +

      row.statut_badge +

      '">' +

      esc(row.statut_display) +

      '</span></td>' +

      '<td>' +

      action +

      '</td></tr>'

    );

  }



  function renderMensualiteRow(row, devise, eleveNom) {

    var resteColor = row.reste_a_payer > 0 ? 'var(--accent, #ef4444)' : 'var(--success, #10b981)';

    var action = row.can_pay

      ? '<button type="button" class="btn btn-success" onclick="openPaiementModal(\'mensualite\', ' +

        row.id +

        ', ' +

        row.montant_total +

        ', ' +

        row.montant_paye +

        ', ' +

        row.reste_a_payer +

        ')" style="padding: 0.5rem 1rem; font-size: 0.875rem;"><i class="fas fa-money-bill-wave"></i> Payer</button>'

      : '<span class="badge badge-success">Payé</span>';

    return (

      '<tr data-mensualite-id="' +

      row.id +

      '">' +

      '<td>' +

      esc(eleveNom) +

      '</td>' +

      '<td>' +

      esc(row.periode) +

      '</td>' +

      '<td><strong>' +

      fmtMoney(row.montant_total, devise) +

      '</strong></td>' +

      '<td>' +

      fmtMoney(row.montant_paye, devise) +

      '</td>' +

      '<td><span style="color: ' +

      resteColor +

      '; font-weight: 600;">' +

      fmtMoney(row.reste_a_payer, devise) +

      '</span></td>' +

      '<td>' +

      esc(row.date_echeance) +

      '</td>' +

      '<td>' +

      renderMensualiteBadge(row) +

      '</td>' +

      '<td>' +

      action +

      '</td></tr>'

    );

  }



  function renderPaiementRow(row, devise) {

    return (

      '<tr data-paiement-id="' +

      row.id +

      '">' +

      '<td>' +

      esc(row.date_paiement) +

      '</td>' +

      '<td>' +

      fmtMoney(row.montant, devise) +

      '</td>' +

      '<td>' +

      esc(row.type_display) +

      '</td>' +

      '<td>' +

      esc(row.methode_display) +

      '</td>' +

      '<td>' +

      esc(row.reference) +

      '</td></tr>'

    );

  }



  function applyComptaDetailsSnapshot(snapshot) {

    if (!snapshot) {

      return;

    }

    var pageEleveId = document.body.getAttribute('data-eleve-id');

    if (pageEleveId && String(snapshot.eleve_id) !== String(pageEleveId)) {

      return;

    }

    var devise = snapshot.devise || document.body.getAttribute('data-devise') || 'FCFA';

    var summary = snapshot.summary || {};



    var totalDu = document.querySelector('[data-summary="total_du"]');

    var totalPaye = document.querySelector('[data-summary="total_paye"]');

    var reste = document.querySelector('[data-summary="reste_a_payer"]');

    var statut = document.querySelector('[data-summary="statut_display"]');

    var resteCard = document.querySelector('[data-summary-card="reste"]');

    var statutCard = document.querySelector('[data-summary-card="statut"]');



    if (totalDu) {

      totalDu.textContent = fmtMoney(summary.total_du, devise);

    }

    if (totalPaye) {

      totalPaye.textContent = fmtMoney(summary.total_paye, devise);

    }

    if (reste) {

      reste.textContent = fmtMoney(summary.reste_a_payer, devise);

    }

    if (statut) {

      statut.className = 'badge badge-' + (summary.statut_badge || 'info');

      statut.textContent = summary.statut_display || '';

    }

    if (resteCard) {

      resteCard.classList.remove('success', 'danger');

      resteCard.classList.add(summary.reste_card_class || 'success');

    }

    if (statutCard) {

      statutCard.classList.remove('success', 'warning', 'danger');

      statutCard.classList.add(summary.statut_badge || 'info');

    }



    var fraisBody = document.getElementById('comptaFraisBody');

    if (fraisBody) {

      if (snapshot.frais && snapshot.frais.length) {

        fraisBody.innerHTML = snapshot.frais.map(function (row) {

          return renderFraisRow(row, devise);

        }).join('');

      } else {

        fraisBody.innerHTML = '';

      }

    }



    var mensualitesSection = document.getElementById('comptaMensualitesSection');

    if (mensualitesSection) {

      mensualitesSection.style.display = snapshot.show_mensualites ? '' : 'none';

    }

    var mensualitesBody = document.getElementById('comptaMensualitesBody');

    if (mensualitesBody) {

      if (snapshot.mensualites && snapshot.mensualites.length) {

        mensualitesBody.innerHTML = snapshot.mensualites

          .map(function (row) {

            return renderMensualiteRow(row, devise, snapshot.eleve_nom || '');

          })

          .join('');

      } else {

        mensualitesBody.innerHTML = '';

      }

    }



    var paiementsBody = document.getElementById('comptaPaiementsBody');

    if (paiementsBody) {

      if (snapshot.paiements && snapshot.paiements.length) {

        paiementsBody.innerHTML = snapshot.paiements

          .map(function (row) {

            return renderPaiementRow(row, devise);

          })

          .join('');

      } else {

        paiementsBody.innerHTML = '';

      }

    }



    if (typeof closePaiementModal === 'function') {

      closePaiementModal();

    }

  }



  function updateComptaParametres(item) {

    if (!item) {

      return;

    }

    var devise = document.body.getAttribute('data-devise') || 'FCFA';

    Object.keys(item).forEach(function (key) {

      var el = document.querySelector('[data-param="' + key + '"]');

      if (el) {

        if (el.classList.contains('amount')) {

          el.textContent = item[key] + ' ' + devise;

        } else if (el.classList.contains('boolean')) {

          var on = !!item[key];

          el.innerHTML = on

            ? '<span class="badge-success"><i class="fas fa-check"></i> Activé</span>'

            : '<span class="badge-danger"><i class="fas fa-times"></i> Désactivé</span>';

        } else {

          el.textContent = item[key];

        }

      }

      var input = document.querySelector('#parametresForm [name="' + key + '"]');

      if (input && input.type !== 'checkbox') {

        input.value = item[key];

      }

    });

    var modal = document.getElementById('parametresModal');

    if (modal) {

      modal.classList.remove('active');

      modal.style.display = 'none';

    }

  }



  function handleLiveDetail(detail) {

    if (!detail) {

      return;

    }

    var event = detail.event || detail.type;

    var item = detail.item;

    var items = detail.items;



    if (event === 'comptabilite.mise_a_jour' && item && item.snapshot) {

      if (document.body.getAttribute('data-live-page') === 'compta-details') {

        applyComptaDetailsSnapshot(item.snapshot);

        return;

      }

      if (document.body.getAttribute('data-live-page') === 'compta-liste') {

        AriaLive.reloadUnlessSkip();

        return;

      }

    }



    if (item && item.id && AriaLive.isLocalItem(item.id)) {

      return;

    }



    if (event === 'salle.creee' && item) {

      appendSalle(item);

    } else if (event === 'salle.modifiee' && item) {

      updateSalleCard(item);

      if (document.body.getAttribute('data-live-page') === 'salle-detail') {

        updateSalleDetailPage(item);

      }

    } else if (event === 'matiere.creee') {

      if (items && items.length) {

        items.forEach(appendMatiere);

      } else if (item) {

        appendMatiere(item);

      }

    } else if (event === 'matiere.modifiee' && item) {

      updateMatiereCard(item);

      if (document.body.getAttribute('data-live-page') === 'matiere-detail') {

        updateMatiereDetailPage(item);

      }

    } else if (event === 'matiere.supprimee' && item) {

      removeMatiere(item);

    } else if (event === 'periode.creee' && item) {

      appendPeriode(item);

    } else if (event === 'periode.modifiee' && item) {

      appendPeriode(item);

    } else if (event === 'periode.supprimee' && item) {

      removePeriode(item);

    } else if (event === 'annee_scolaire.creee') {

      AriaLive.reloadUnlessSkip();

    } else if (event === 'comptabilite.parametres' && item) {

      updateComptaParametres(item);

    } else if (event === 'comptabilite.mise_a_jour') {

      AriaLive.reloadUnlessSkip();

    } else if (event === 'professeur.cree' && item) {

      appendProfesseurCard(item);

    } else if (event === 'personnel.cree' && item) {

      appendPersonnelCard(item);

    } else if (event === 'affectation.mise_a_jour') {

      AriaLive.reloadUnlessSkip();

    } else if (event === 'emploi.mise_a_jour') {

      handleEmploiLive(item);

    }

  }



  function initSalles() {

    var form = document.querySelector('#addSalleModal form, form#addSalleForm');

    if (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function (payload) {

          AriaLive.markLocalItem(payload.item && payload.item.id);

          appendSalle(payload.item);

          var modal = document.getElementById('addSalleModal');

          if (modal) {

            modal.classList.remove('active');

          }

          form.reset();

          bindSalleToggleLinks();

        },

      });

    }

    bindSalleToggleLinks();

  }



  function initMatieres() {

    var form = document.getElementById('ajouterMatiereForm');

    if (!form) {

      return;

    }

    AriaLive.bindLiveForm(form, {

      onSuccess: function (payload) {

        if (payload.items) {

          payload.items.forEach(function (it) {

            AriaLive.markLocalItem(it.id);

            appendMatiere(it);

          });

        } else if (payload.item) {

          AriaLive.markLocalItem(payload.item.id);

          appendMatiere(payload.item);

        }

        var modal = document.getElementById('addFormContainer');

        if (modal) {

          modal.style.display = 'none';

        }

        form.reset();

      },

    });

  }



  function initMatiereDetail() {

    var form = document.getElementById('editMatiereForm');

    if (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function (payload) {

          if (payload.item) {

            AriaLive.markLocalItem(payload.item.id);

            updateMatiereDetailPage(payload.item);

          }

          if (typeof toggleEditForm === 'function') {

            var container = document.getElementById('editFormContainer');

            if (container && container.style.display === 'block') {

              toggleEditForm();

            }

          }

        },

      });

    }

    window.confirmDelete = function (matiereId) {

      if (!matiereId) {

        alert('Erreur : ID matière manquant.');

        return;

      }

      if (!confirm('Êtes-vous sûr de vouloir supprimer cette matière ? Cette action est irréversible.')) {

        return;

      }

      AriaLive.fetchJsonUrl('/matieres/' + matiereId + '/supprimer/', {

        onSuccess: function () {

          window.location.href = '/matieres/';

        },

      });

    };

  }



  function initSalleDetail() {

    var form = document.querySelector('.modifier-form');

    if (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function (payload) {

          if (payload.item) {

            AriaLive.markLocalItem(payload.item.id);

            updateSalleDetailPage(payload.item);

          }

        },

      });

    }

  }



  function initPeriodes() {

    function closeAllPeriodeModals() {
      if (typeof window.closePeriodeModal === 'function') {
        ['periodeAddModal', 'periodeEditModal', 'periodeDeleteModal'].forEach(function (id) {
          window.closePeriodeModal(id);
        });
      } else {
        document.querySelectorAll('.modal-periode-add, .modal-periode-edit, .modal-overlay.show').forEach(function (m) {
          m.classList.remove('show', 'active');
          m.setAttribute('aria-hidden', 'true');
        });
        document.body.classList.remove('periode-modal-open');
      }
    }

    ['formAjoutPeriode', 'formAnneeScolaire'].forEach(function (id) {

      var form = document.getElementById(id);

      if (form) {

        AriaLive.bindLiveForm(form, {

          onSuccess: function (payload) {

            if (payload.item) {

              AriaLive.markLocalItem(payload.item.id);

              if (payload.item.libelle) {

                AriaLive.reloadUnlessSkip();

              } else {

                appendPeriode(payload.item);

              }

            }

            closeAllPeriodeModals();

          },

        });

      }

    });

    document.querySelectorAll('#formEditPeriode, #formDeletePeriode').forEach(function (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function (payload) {

          if (payload.item) {

            AriaLive.markLocalItem(payload.item.id);

            if (form.id === 'formDeletePeriode') {

              removePeriode(payload.item);

            } else {

              appendPeriode(payload.item);

            }

          }

          closeAllPeriodeModals();

        },

      });

    });

  }



  function initComptaParametres() {

    var form = document.getElementById('parametresForm');

    if (!form) {

      return;

    }

    AriaLive.bindLiveForm(form, {

      onSuccess: function (payload) {

        updateComptaParametres(payload.item);

      },

    });

  }



  function initComptaDetails() {

    var form = document.getElementById('paiementForm');

    if (!form) {

      return;

    }

    AriaLive.bindLiveForm(form, {

      onSuccess: function (payload) {

        if (payload.item && payload.item.snapshot) {

          applyComptaDetailsSnapshot(payload.item.snapshot);

        }

      },

    });

  }



  function initComptaListe() {

    /* écoute WS uniquement */

  }



  function renderProfesseurCard(item) {

    var card = document.createElement('div');

    card.className = 'personnel-card professeur-card';

    card.setAttribute('data-professeur-id', String(item.id));

    if (item.matiere_id) {

      card.setAttribute('data-matiere', String(item.matiere_id));

    }

    var actif = item.actif !== false;

    card.innerHTML =

      '<div class="card-header">' +

      '<div class="avatar"><i class="fas fa-chalkboard-teacher"></i></div>' +

      '<div class="info"><h3 class="name">' + esc(item.nom_complet) + '</h3>' +

      '<p class="role">' + esc(item.matiere_display) + '</p>' +

      '<span class="badge">' + esc(item.niveau_display) + '</span></div>' +

      '<div class="status"><span class="status-dot ' + (actif ? 'active' : 'inactive') + '"></span></div></div>' +

      '<div class="card-content"><div class="contact-info">' +

      '<div class="contact-item"><i class="fas fa-envelope"></i><span>' + esc(item.email || '—') + '</span></div>' +

      '<div class="contact-item"><i class="fas fa-phone"></i><span>' + esc(item.telephone || '—') + '</span></div>' +

      '</div></div>' +

      '<div class="card-actions">' +

      '<a href="' + esc(item.detail_url) + '" class="action-btn primary" title="Voir détails"><i class="fas fa-eye"></i></a>' +

      '<button class="action-btn secondary" onclick="alert(\'Fonctionnalité de modification à venir\')" title="Modifier"><i class="fas fa-edit"></i></button>' +

      '<button class="action-btn ' + (actif ? 'danger' : 'success') + '" onclick="alert(\'Fonctionnalité de toggle à venir\')" title="Toggle"><i class="fas fa-' + (actif ? 'pause' : 'play') + '"></i></button>' +

      '</div>';

    return card;

  }



  function appendProfesseurCard(item) {

    if (!item || document.querySelector('[data-professeur-id="' + item.id + '"]')) {

      return;

    }

    var grid = document.getElementById('professeurs-grid');

    if (!grid) {

      return;

    }

    var empty = grid.querySelector('.empty-state');

    if (empty) {

      empty.remove();

    }

    grid.appendChild(renderProfesseurCard(item));

    var tabCount = document.querySelector('.tab-btn[data-tab="professeurs"] .tab-count');

    if (tabCount) {

      tabCount.textContent = String(grid.querySelectorAll('.professeur-card').length);

    }

  }



  function renderPersonnelCard(item) {

    var card = document.createElement('div');

    card.className = 'personnel-card';

    card.setAttribute('data-personnel-id', String(item.id));

    var actif = item.actif !== false;

    card.innerHTML =

      '<div class="card-header">' +

      '<div class="avatar"><i class="fas ' + esc(item.category_icon || 'fa-user-tie') + '"></i></div>' +

      '<div class="info"><h3 class="name">' + esc(item.nom_complet) + '</h3>' +

      '<p class="role">' + esc(item.fonction_display) + '</p>' +

      '<span class="badge">' + esc(item.numero_employe) + '</span></div>' +

      '<div class="status"><span class="status-dot ' + (actif ? 'active' : 'inactive') + '"></span></div></div>' +

      '<div class="card-content"><div class="contact-info">' +

      '<div class="contact-item"><i class="fas fa-envelope"></i><span>' + esc(item.email || '—') + '</span></div>' +

      '<div class="contact-item"><i class="fas fa-phone"></i><span>' + esc(item.telephone || '—') + '</span></div>' +

      '</div></div>' +

      '<div class="card-actions">' +

      '<a href="' + esc(item.detail_url) + '" class="action-btn primary" title="Voir détails"><i class="fas fa-eye"></i></a>' +

      '<a href="' + esc(item.toggle_url) + '" class="action-btn ' + (actif ? 'danger' : 'success') + '" title="Toggle"><i class="fas fa-' + (actif ? 'pause' : 'play') + '"></i></a>' +

      '</div>';

    return card;

  }



  function appendPersonnelCard(item) {

    if (!item || document.querySelector('[data-personnel-id="' + item.id + '"]')) {

      return;

    }

    var key = item.category_key || 'autres';

    var grid = document.getElementById(key + '-grid');

    if (!grid) {

      AriaLive.reloadUnlessSkip();

      return;

    }

    var empty = grid.querySelector('.empty-state');

    if (empty) {

      empty.remove();

    }

    grid.appendChild(renderPersonnelCard(item));

    var tabBtn = document.querySelector('.tab-btn[data-tab="' + key + '"]');

    if (!tabBtn) {

      AriaLive.reloadUnlessSkip();

      return;

    }

    var tabCount = tabBtn.querySelector('.tab-count');

    if (tabCount) {

      tabCount.textContent = String(grid.querySelectorAll('.personnel-card').length);

    }

  }



  function handleEmploiLive(item) {

    if (!item) {

      AriaLive.reloadUnlessSkip();

      return;

    }

    var page = document.body.getAttribute('data-live-page');

    var classeId = document.body.getAttribute('data-classe-id');

    if (page === 'emploi-detail' && classeId && item.classe_id && String(item.classe_id) !== String(classeId)) {

      return;

    }

    AriaLive.reloadUnlessSkip();

  }



  function initPersonnel() {

    var formPersonnel = document.getElementById('formAjouterPersonnel');

    if (formPersonnel) {

      AriaLive.bindLiveForm(formPersonnel, {

        onSuccess: function (payload) {

          AriaLive.markLocalItem(payload.item && payload.item.id);

          if (window.closeModalPersonnel) {

            closeModalPersonnel();

          }

          formPersonnel.reset();

          appendPersonnelCard(payload.item);

        },

      });

    }

    var formProf = document.getElementById('ajouterProfesseurForm');

    if (formProf) {

      AriaLive.bindLiveForm(formProf, {

        onSuccess: function (payload) {

          AriaLive.markLocalItem(payload.item && payload.item.id);

          if (window.closeModalProfesseur) {

            closeModalProfesseur();

          }

          formProf.reset();

          appendProfesseurCard(payload.item);

        },

      });

    }

  }



  function initAffectation() {

    document.querySelectorAll('.add-affectation-form').forEach(function (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function () {

          AriaLive.reloadUnlessSkip();

        },

      });

    });

    document.querySelectorAll('form[action*="affecter"]').forEach(function (form) {

      if (form.classList.contains('add-affectation-form')) {

        return;

      }

      AriaLive.bindLiveForm(form, {

        onSuccess: function () {

          AriaLive.reloadUnlessSkip();

        },

      });

    });

  }



  function initEmploiDetail() {

    document.querySelectorAll('#modalAjouterCreneau form, #modalModifierCreneau form').forEach(function (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function () {

          AriaLive.reloadUnlessSkip();

        },

      });

    });

    document.querySelectorAll('form[action*="supprimer_creneau"], form[action*="publier"]').forEach(function (form) {

      AriaLive.bindLiveForm(form, {

        onSuccess: function () {

          AriaLive.reloadUnlessSkip();

        },

      });

    });

  }



  function initEmploiListe() {

    /* écoute WS — rechargement via handleEmploiLive */

  }



  document.addEventListener('DOMContentLoaded', function () {

    var page = document.body.getAttribute('data-live-page');

    if (page === 'salles') {

      initSalles();

    } else if (page === 'matieres') {

      initMatieres();

    } else if (page === 'matiere-detail') {

      initMatiereDetail();

    } else if (page === 'salle-detail') {

      initSalleDetail();

    } else if (page === 'periodes') {

      initPeriodes();

    } else if (page === 'compta-parametres') {

      initComptaParametres();

    } else if (page === 'compta-details') {

      initComptaDetails();

    } else if (page === 'compta-liste') {

      initComptaListe();

    } else if (page === 'personnel') {

      initPersonnel();

    } else if (page === 'affectation') {

      initAffectation();

    } else if (page === 'emploi-liste') {

      initEmploiListe();

    } else if (page === 'emploi-detail') {

      initEmploiDetail();

    }



    document.addEventListener('aria:live-directeur', function (e) {

      handleLiveDetail(e.detail || {});

    });

    document.addEventListener('aria:realtime', function (e) {

      var d = e.detail || {};

      handleLiveDetail(Object.assign({ event: d.type }, d.payload || {}));

    });

  });

})();


