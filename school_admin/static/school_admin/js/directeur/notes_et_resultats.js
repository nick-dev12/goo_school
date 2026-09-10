/**
 * Notes et résultats — navigation, filtres, modale détails (UI v2)
 */

(function () {
  'use strict';

  var body = document.body;
  var periodeSelectionneeId = body.dataset.periodeId || '';
  var estSuperieur = body.dataset.estSuperieur === '1';
  var estPrimaire = body.dataset.estPrimaire === '1';
  var debloquerUrl = body.dataset.debloquerUrl || '';

  var detailsMatiereContext = {
    classeId: null,
    matiereId: null,
    matiereNom: null,
    periodeId: null,
    estPrimaire: true,
    apiUrl: null
  };

  function getCsrfToken() {
    var name = 'csrftoken=';
    var decodedCookie = decodeURIComponent(document.cookie || '');
    var cookies = decodedCookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name) === 0) {
        return c.substring(name.length, c.length);
      }
    }
    return '';
  }

  window.updateNotesNavUrl = function (tabId, classeId) {
    var params = new URLSearchParams(window.location.search);
    params.set('tab', tabId);
    if (classeId) {
      params.set('classe', classeId.replace('classe-', ''));
    }
    document.querySelectorAll('.nr-periodes-bar .periode-tab').forEach(function (link) {
      var url = new URL(link.href, window.location.origin);
      url.searchParams.set('tab', tabId);
      if (classeId) {
        url.searchParams.set('classe', classeId.replace('classe-', ''));
      }
      link.href = url.pathname + '?' + url.searchParams.toString();
    });
    history.replaceState({}, '', window.location.pathname + '?' + params.toString());
  };

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.tab-content-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    var activeClasseId = null;
    if (panel) {
      var activeClasseContent = panel.querySelector('.classe-subtab-content.active');
      if (!panel.querySelector('.classe-subtab-btn.active') && panel.querySelector('.classe-subtab-btn')) {
        var firstBtn = panel.querySelector('.classe-subtab-btn');
        var firstContent = panel.querySelector('.classe-subtab-content');
        firstBtn.classList.add('active');
        firstBtn.setAttribute('aria-selected', 'true');
        if (firstContent) firstContent.classList.add('active');
        activeClasseId = firstContent ? firstContent.id : null;
      } else if (activeClasseContent) {
        activeClasseId = activeClasseContent.id;
      }
    }
    window.updateNotesNavUrl(tabId, activeClasseId);
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId) {
    if (event) event.stopPropagation();
    var parentPanel = event && event.target
      ? event.target.closest('.tab-content-panel')
      : document.getElementById(classeId);
    if (parentPanel && !parentPanel.classList.contains('tab-content-panel')) {
      parentPanel = parentPanel.closest('.tab-content-panel');
    }
    if (!parentPanel) return;

    parentPanel.querySelectorAll('.classe-subtab-content').forEach(function (content) {
      content.classList.remove('active');
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var content = document.getElementById(classeId);
    if (content) content.classList.add('active');

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    window.updateNotesNavUrl(parentPanel.id, classeId);
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.ouvrirDetailsMatiere = function (classeId, matiereNom, event, matiereId) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    var modal = document.getElementById('modal-details-matiere');
    var matiereNomElement = document.getElementById('modal-matiere-nom');
    var modalBody = document.getElementById('modal-body-content');
    var trigger = event ? (event.currentTarget || event.target) : null;

    matiereNomElement.textContent = matiereNom;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    modalBody.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Chargement des données...</div>';

    var periodeId = trigger && trigger.dataset.periodeId ? trigger.dataset.periodeId : periodeSelectionneeId;
    var apiUrl = '';

    if (estPrimaire) {
      if (!periodeId) {
        modalBody.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Période scolaire introuvable pour cette classe.</div>';
        return;
      }
      apiUrl = '/api/details-notes-matiere/?classe_id=' + classeId + '&matiere_nom=' + encodeURIComponent(matiereNom) + '&periode_id=' + periodeId;
    } else {
      if (estSuperieur && !periodeId) {
        modalBody.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Période non indiquée : sélectionnez un semestre pour cette classe.</div>';
        return;
      }
      apiUrl = '/api/details-notes-matiere-secondaire/?classe_id=' + classeId + '&matiere_nom=' + encodeURIComponent(matiereNom);
      if (periodeId) apiUrl += '&periode_id=' + periodeId;
    }

    var periodMatch = apiUrl.match(/[?&]periode_id=([^&]+)/);
    detailsMatiereContext = {
      classeId: String(classeId),
      matiereId: matiereId ? String(matiereId) : (trigger && trigger.dataset.matiereId ? trigger.dataset.matiereId : null),
      matiereNom: matiereNom,
      periodeId: periodMatch ? decodeURIComponent(periodMatch[1]) : null,
      estPrimaire: estPrimaire,
      apiUrl: apiUrl
    };

    var unlockBtn = document.getElementById('btn-debloquer-releve');
    if (unlockBtn) unlockBtn.disabled = !detailsMatiereContext.periodeId;

    chargerDetailsMatiere(apiUrl, estPrimaire);
  };

  function chargerDetailsMatiere(apiUrl, isPrimaire) {
    var modalBody = document.getElementById('modal-body-content');
    fetch(apiUrl, {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json'
      }
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.success) {
          afficherDetailsNotes(data, isPrimaire);
        } else {
          modalBody.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> ' + (data.message || 'Erreur lors du chargement des données') + '</div>';
        }
      })
      .catch(function () {
        modalBody.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Erreur de connexion au serveur</div>';
      });
  }

  window.debloquerReleveMatiere = function () {
    var ctx = detailsMatiereContext || {};
    var modalBody = document.getElementById('modal-body-content');
    var btn = document.getElementById('btn-debloquer-releve');

    if (!ctx.classeId || !ctx.matiereNom || !ctx.periodeId) {
      modalBody.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Informations insuffisantes pour débloquer ce relevé.</div>';
      return;
    }

    if (!window.confirm('Confirmer le déblocage du relevé pour "' + ctx.matiereNom + '" ?\nLe professeur pourra modifier à nouveau les notes et soumettre de nouveau.')) {
      return;
    }

    var oldHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Déblocage...';

    fetch(debloquerUrl, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCsrfToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        classe_id: ctx.classeId,
        matiere_id: ctx.matiereId,
        matiere_nom: ctx.matiereNom,
        periode_id: ctx.periodeId
      })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.message || 'Erreur inconnue');
        alert(data.message || 'Déblocage effectué avec succès.');
        if (window.refreshLiveTabsNow) {
          window.refreshLiveTabsNow('Relevé débloqué.', true);
        }
        if (ctx.apiUrl) chargerDetailsMatiere(ctx.apiUrl, !!ctx.estPrimaire);
      })
      .catch(function (error) {
        alert('Erreur: ' + error.message);
      })
      .finally(function () {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
      });
  };

  window.fermerDetailsMatiere = function () {
    var modal = document.getElementById('modal-details-matiere');
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
  };

  function getNoteColorClass(note) {
    if (note >= 16) return 'note-excellent';
    if (note >= 14) return 'note-bien';
    if (note >= 12) return 'note-assez-bien';
    if (note >= 10) return 'note-passable';
    return 'note-insuffisant';
  }

  function getMoyenneColorClass(moyenne) {
    if (moyenne === null) return '';
    if (moyenne >= 16) return 'text-excellent';
    if (moyenne >= 14) return 'text-bien';
    if (moyenne >= 12) return 'text-assez-bien';
    if (moyenne >= 10) return 'text-passable';
    return 'text-insuffisant';
  }

  function afficherDetailsNotes(data, isPrimaire) {
    var modalBody = document.getElementById('modal-body-content');
    if (!data.eleves || data.eleves.length === 0) {
      modalBody.innerHTML = '<div class="empty-state-modal"><i class="fas fa-inbox"></i><p>Aucune moyenne calculée pour cette matière</p></div>';
      return;
    }

    var maxNotesRetenues = 0;
    data.eleves.forEach(function (eleve) {
      if (eleve.notes_retenues) {
        var nbRetenues = isPrimaire
          ? eleve.notes_retenues.filter(function (n) { return n.retenue; }).length
          : eleve.notes_retenues.length;
        if (nbRetenues > maxNotesRetenues) maxNotesRetenues = nbRetenues;
      }
    });

    var html = '<div class="details-notes-container">';
    html += '<div class="info-matiere-modal">';
    html += '<div class="info-item-modal"><i class="fas fa-chalkboard"></i> <strong>Classe:</strong> ' + data.classe + '</div>';
    html += '<div class="info-item-modal"><i class="fas fa-calendar"></i> <strong>Période:</strong> ' + data.periode + '</div>';
    html += '<div class="info-item-modal"><i class="fas fa-users"></i> <strong>Élèves:</strong> ' + data.eleves.length + '</div>';
    html += '</div>';
    html += '<div class="table-wrapper-modal"><table class="table-notes-modal"><thead><tr>';
    html += '<th class="th-rang">Rang</th><th class="th-eleve">Élève</th>';
    for (var i = 1; i <= maxNotesRetenues; i++) {
      html += '<th class="th-note">Note ' + i + '</th>';
    }
    html += '<th class="th-examen">Examen</th><th class="th-moyenne">Moyenne</th></tr></thead><tbody>';

    data.eleves.forEach(function (eleve, index) {
      var rankClass = index === 0 ? 'rank-gold' : index === 1 ? 'rank-silver' : index === 2 ? 'rank-bronze' : '';
      html += '<tr>';
      html += '<td class="td-rang"><span class="rank-badge ' + rankClass + '">' + (index + 1) + '</span></td>';
      html += '<td class="td-eleve"><span class="eleve-avatar">' + eleve.initiales + '</span><span class="eleve-nom">' + eleve.nom + '</span></td>';

      var notesRetenues = eleve.notes_retenues
        ? (isPrimaire ? eleve.notes_retenues.filter(function (n) { return n.retenue; }) : eleve.notes_retenues)
        : [];
      for (var j = 0; j < maxNotesRetenues; j++) {
        if (j < notesRetenues.length) {
          var note = notesRetenues[j];
          var noteValue = typeof note.note === 'number' ? note.note : null;
          if (noteValue !== null) {
            html += '<td class="td-note"><span class="note-text ' + getNoteColorClass(noteValue) + '">' + noteValue.toFixed(2) + '/' + (note.bareme || 20) + '</span></td>';
          } else {
            html += '<td class="td-note"><span class="note-vide">-</span></td>';
          }
        } else {
          html += '<td class="td-note"><span class="note-vide">-</span></td>';
        }
      }

      html += '<td class="td-examen">';
      if (eleve.note_examen !== null && eleve.note_examen !== undefined) {
        var examenValue = typeof eleve.note_examen === 'number' ? eleve.note_examen : parseFloat(eleve.note_examen);
        if (!isNaN(examenValue)) {
          var absentBadge = eleve.note_examen_absent ? ' <span class="note-absent">(absent)</span>' : '';
          html += '<span class="note-text ' + getNoteColorClass(examenValue) + '">' + examenValue.toFixed(2) + '/20</span>' + absentBadge;
        } else {
          html += '<span class="note-vide">-</span>';
        }
      } else {
        html += '<span class="note-vide">-</span>';
      }
      html += '</td>';

      html += '<td class="td-moyenne">';
      var moyenneValue = typeof eleve.moyenne === 'number' ? eleve.moyenne : (eleve.moyenne ? parseFloat(eleve.moyenne) : null);
      if (moyenneValue !== null && !isNaN(moyenneValue)) {
        html += '<span class="moyenne-text ' + getMoyenneColorClass(moyenneValue) + '">' + moyenneValue.toFixed(2) + '/20</span>';
      } else {
        html += '<span class="moyenne-text">-</span>';
      }
      html += '</td></tr>';
    });

    html += '</tbody></table></div></div>';
    modalBody.innerHTML = html;
  }

  function matchesPerformance(moyenneTri, performanceValue) {
    if (!performanceValue) return true;
    if (performanceValue === 'excellent') return moyenneTri >= 16;
    if (performanceValue === 'bien') return moyenneTri >= 14 && moyenneTri < 16;
    if (performanceValue === 'assez-bien') return moyenneTri >= 12 && moyenneTri < 14;
    if (performanceValue === 'passable') return moyenneTri >= 10 && moyenneTri < 12;
    if (performanceValue === 'insuffisant') return moyenneTri < 10 && moyenneTri > 0;
    return true;
  }

  window.filterNotesStudents = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-' + classeId);
    var filterPerformance = document.getElementById('filter-performance-' + classeId);
    var clearButton = document.getElementById('clear-search-notes-' + classeId);
    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    var performanceValue = filterPerformance ? filterPerformance.value : '';
    if (clearButton) clearButton.hidden = !searchTerm;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;
    classeContent.querySelectorAll('.student-row').forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var nomComplet = row.dataset.nomComplet || '';
      var moyenneTri = parseFloat(row.dataset.moyenneTri || '0');
      var matchesSearch = !searchTerm || nom.includes(searchTerm) || prenom.includes(searchTerm) || nomComplet.includes(searchTerm);
      var ok = matchesSearch && matchesPerformance(moyenneTri, performanceValue);
      row.style.display = ok ? (row.classList.contains('student-card') ? 'block' : '') : 'none';
    });
  };

  window.clearNotesSearch = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-' + classeId);
    if (searchInput) searchInput.value = '';
    window.filterNotesStudents(classeId);
  };

  window.resetNotesFilters = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-' + classeId);
    var filterPerformance = document.getElementById('filter-performance-' + classeId);
    if (searchInput) searchInput.value = '';
    if (filterPerformance) filterPerformance.value = '';
    window.filterNotesStudents(classeId);
  };

  window.filterNotesPrimaireStudents = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-primaire-' + classeId);
    var filterPerformance = document.getElementById('filter-performance-primaire-' + classeId);
    var clearButton = document.getElementById('clear-search-notes-primaire-' + classeId);
    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    var performanceValue = filterPerformance ? filterPerformance.value : '';
    if (clearButton) clearButton.hidden = !searchTerm;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;
    classeContent.querySelectorAll('.student-row').forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var nomComplet = row.dataset.nomComplet || '';
      var matchesSearch = !searchTerm || nom.includes(searchTerm) || prenom.includes(searchTerm) || nomComplet.includes(searchTerm);

      var perfOk = true;
      if (performanceValue) {
        var moyennes = [];
        row.querySelectorAll('.moyenne-text, .matiere-card-value.moyenne-text').forEach(function (cell) {
          var match = cell.textContent.match(/([\d.,]+)\/20/);
          if (match) moyennes.push(parseFloat(match[1].replace(',', '.')));
        });
        if (!moyennes.length) {
          perfOk = false;
        } else {
          var avg = moyennes.reduce(function (a, b) { return a + b; }, 0) / moyennes.length;
          perfOk = matchesPerformance(avg, performanceValue);
        }
      }

      var ok = matchesSearch && perfOk;
      row.style.display = ok ? (row.classList.contains('student-card') ? 'block' : '') : 'none';
    });
  };

  window.clearNotesPrimaireSearch = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-primaire-' + classeId);
    if (searchInput) searchInput.value = '';
    window.filterNotesPrimaireStudents(classeId);
  };

  window.resetNotesPrimaireFilters = function (classeId) {
    var searchInput = document.getElementById('search-input-notes-primaire-' + classeId);
    var filterPerformance = document.getElementById('filter-performance-primaire-' + classeId);
    if (searchInput) searchInput.value = '';
    if (filterPerformance) filterPerformance.value = '';
    window.filterNotesPrimaireStudents(classeId);
  };

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.tab-btn[data-tab]');
    if (tabBtn) {
      window.switchMainTab(tabBtn.getAttribute('data-tab'), tabBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') window.fermerDetailsMatiere();
  });

  document.addEventListener('DOMContentLoaded', function () {
    var params = new URLSearchParams(window.location.search);
    var tabId = params.get('tab');
    var classeParam = params.get('classe');
    if (tabId) {
      window.updateNotesNavUrl(tabId, classeParam ? 'classe-' + classeParam : null);
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
