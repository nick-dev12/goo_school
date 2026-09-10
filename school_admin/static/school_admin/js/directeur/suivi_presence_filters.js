(function () {
    'use strict';

    var presenceCache = {};
    var referenceDate = null;

    function parseReferenceDate() {
        if (referenceDate) {
            return new Date(referenceDate + 'T12:00:00');
        }
        return new Date();
    }

    function startOfDay(date) {
        var d = new Date(date);
        d.setHours(12, 0, 0, 0);
        return d;
    }

    function formatIso(date) {
        var y = date.getFullYear();
        var m = String(date.getMonth() + 1).padStart(2, '0');
        var d = String(date.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + d;
    }

    function getWeekRange(reference, offsetWeeks) {
        var date = startOfDay(reference);
        var day = date.getDay();
        var diffToMonday = day === 0 ? -6 : 1 - day;
        var monday = new Date(date);
        monday.setDate(date.getDate() + diffToMonday + (offsetWeeks * 7));
        var sunday = new Date(monday);
        sunday.setDate(monday.getDate() + 6);
        return { start: monday, end: sunday };
    }

    function getDateRange(classeId) {
        var periodSelect = document.getElementById('filter-periode-' + classeId);
        var monthSelect = document.getElementById('filter-mois-' + classeId);
        var dateDebutInput = document.getElementById('filter-date-debut-' + classeId);
        var dateFinInput = document.getElementById('filter-date-fin-' + classeId);
        var ref = parseReferenceDate();

        if (dateDebutInput && dateFinInput && dateDebutInput.value && dateFinInput.value) {
            var startCustom = new Date(dateDebutInput.value + 'T12:00:00');
            var endCustom = new Date(dateFinInput.value + 'T12:00:00');
            if (startCustom > endCustom) {
                var temp = startCustom;
                startCustom = endCustom;
                endCustom = temp;
            }
            return {
                start: startCustom,
                end: endCustom,
                label: 'Du ' + dateDebutInput.value + ' au ' + dateFinInput.value,
            };
        }

        if (monthSelect && monthSelect.value) {
            var parts = monthSelect.value.split('-');
            var year = parseInt(parts[0], 10);
            var month = parseInt(parts[1], 10);
            var start = new Date(year, month - 1, 1, 12, 0, 0);
            var end = new Date(year, month, 0, 12, 0, 0);
            return { start: start, end: end, label: monthSelect.options[monthSelect.selectedIndex].text };
        }

        var period = periodSelect ? periodSelect.value : 'today';
        if (period === 'yesterday') {
            var yesterday = new Date(ref);
            yesterday.setDate(ref.getDate() - 1);
            return { start: yesterday, end: yesterday, label: 'Hier' };
        }
        if (period === 'this_week') {
            var currentWeek = getWeekRange(ref, 0);
            return { start: currentWeek.start, end: currentWeek.end, label: 'Cette semaine' };
        }
        if (period === 'last_week') {
            var lastWeek = getWeekRange(ref, -1);
            return { start: lastWeek.start, end: lastWeek.end, label: 'Semaine précédente' };
        }

        return { start: ref, end: ref, label: "Aujourd'hui" };
    }

    function isDateInRange(isoDate, range) {
        var date = new Date(isoDate + 'T12:00:00');
        return date >= range.start && date <= range.end;
    }

    function computeStats(presences) {
        var absencesDetails = presences.filter(function (p) { return p.statut === 'absent'; });
        return {
            total_jours: presences.length,
            presents: presences.filter(function (p) { return p.statut === 'present'; }).length,
            absents: absencesDetails.length,
            absents_justifies: presences.filter(function (p) { return p.statut === 'absent_justifie'; }).length,
            retards: presences.filter(function (p) { return p.statut === 'retard'; }).length,
            absences_details: absencesDetails,
        };
    }

    function loadPresenceData(classeId) {
        if (presenceCache[classeId]) {
            return presenceCache[classeId];
        }
        var scriptEl = document.getElementById('presence-json-' + classeId);
        if (!scriptEl) {
            presenceCache[classeId] = {};
            return presenceCache[classeId];
        }
        try {
            presenceCache[classeId] = JSON.parse(scriptEl.textContent);
        } catch (e) {
            presenceCache[classeId] = {};
        }
        return presenceCache[classeId];
    }

    function updatePrintLink(classeId, range) {
        var printLink = document.getElementById('print-link-' + classeId);
        if (!printLink) {
            return;
        }
        var month = range.start.getMonth() + 1;
        var year = range.start.getFullYear();
        var pattern = printLink.getAttribute('data-print-pattern') || '';
        var periodeQuery = printLink.getAttribute('data-periode-query') || '';
        if (pattern.indexOf('/0/0/') !== -1) {
            printLink.href = pattern.replace('/0/0/', '/' + month + '/' + year + '/') + periodeQuery;
        }
    }

    function updateRowStats(row, stats) {
        var jours = row.querySelector('.jours-count');
        var presents = row.querySelector('.presents-badge');
        var absents = row.querySelector('.absents-badge');
        var justifies = row.querySelector('.justifies-badge');
        var retards = row.querySelector('.retards-badge');
        if (jours) jours.textContent = stats.total_jours;
        if (presents) presents.textContent = stats.presents;
        if (absents) absents.textContent = stats.absents;
        if (justifies) justifies.textContent = stats.absents_justifies;
        if (retards) retards.textContent = stats.retards;
        row.dataset.absents = String(stats.absents);
        row.dataset.retards = String(stats.retards);
        row.dataset.absencesJson = JSON.stringify(stats.absences_details);

        var justifyBtn = row.querySelector('.btn-justify-absence');
        if (justifyBtn) {
            justifyBtn.style.display = stats.absences_details.length ? '' : 'none';
        }
    }

    window.filterPresenceStudents = function (classeId) {
        var searchInput = document.getElementById('search-input-presence-' + classeId);
        var clearButton = document.getElementById('clear-search-presence-' + classeId);
        var panel = document.getElementById('presence-panel-' + classeId);
        if (!panel) {
            return;
        }

        var searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';
        if (clearButton) {
            clearButton.hidden = !searchTerm;
        }

        var range = getDateRange(classeId);
        updatePrintLink(classeId, range);
        var data = loadPresenceData(classeId);
        var rows = panel.querySelectorAll('.student-row');

        rows.forEach(function (row) {
            var eleveId = row.dataset.eleveId;
            var nom = row.dataset.nom || '';
            var prenom = row.dataset.prenom || '';
            var matricule = row.dataset.matricule || '';
            var presences = (data[eleveId] || []).filter(function (p) {
                return isDateInRange(p.date, range);
            });
            var stats = computeStats(presences);
            updateRowStats(row, stats);

            var matchesSearch = !searchTerm || nom.includes(searchTerm) || prenom.includes(searchTerm) || matricule.includes(searchTerm);

            if (matchesSearch) {
                row.style.display = row.tagName === 'DIV' ? 'block' : '';
            } else {
                row.style.display = 'none';
            }
        });
    };

    window.clearPresenceSearch = function (classeId) {
        var searchInput = document.getElementById('search-input-presence-' + classeId);
        if (searchInput) {
            searchInput.value = '';
        }
        filterPresenceStudents(classeId);
    };

    function clearCustomDates(classeId) {
        var dateDebutInput = document.getElementById('filter-date-debut-' + classeId);
        var dateFinInput = document.getElementById('filter-date-fin-' + classeId);
        if (dateDebutInput) dateDebutInput.value = '';
        if (dateFinInput) dateFinInput.value = '';
    }

    window.handlePeriodFilterChange = function (classeId) {
        var monthSelect = document.getElementById('filter-mois-' + classeId);
        if (monthSelect) {
            monthSelect.value = '';
        }
        clearCustomDates(classeId);
        filterPresenceStudents(classeId);
    };

    window.handleMonthFilterChange = function (classeId) {
        var monthSelect = document.getElementById('filter-mois-' + classeId);
        if (monthSelect && monthSelect.value) {
            var periodSelect = document.getElementById('filter-periode-' + classeId);
            if (periodSelect) {
                periodSelect.value = 'today';
            }
            clearCustomDates(classeId);
        }
        filterPresenceStudents(classeId);
    };

    window.handleCustomDateChange = function (classeId) {
        var dateDebutInput = document.getElementById('filter-date-debut-' + classeId);
        var dateFinInput = document.getElementById('filter-date-fin-' + classeId);
        if ((dateDebutInput && dateDebutInput.value) || (dateFinInput && dateFinInput.value)) {
            var monthSelect = document.getElementById('filter-mois-' + classeId);
            if (monthSelect) monthSelect.value = '';
        }
        filterPresenceStudents(classeId);
    };

    window.resetPresenceFilters = function (classeId) {
        var searchInput = document.getElementById('search-input-presence-' + classeId);
        var periodSelect = document.getElementById('filter-periode-' + classeId);
        var monthSelect = document.getElementById('filter-mois-' + classeId);
        if (searchInput) searchInput.value = '';
        if (periodSelect) periodSelect.value = 'today';
        if (monthSelect) monthSelect.value = '';
        clearCustomDates(classeId);
        filterPresenceStudents(classeId);
    };

    window.ouvrirModalHistoriquePresence = function (eleveId, classeId, eleveNom) {
        var modal = document.getElementById('modalHistoriquePresence');
        var title = document.getElementById('historiqueEleveNom');
        var list = document.getElementById('historiquePresenceList');
        if (!modal || !list) {
            return;
        }

        var data = loadPresenceData(classeId);
        var range = getDateRange(classeId);
        var presences = (data[String(eleveId)] || []).filter(function (p) {
            return isDateInRange(p.date, range);
        });

        if (title) {
            title.textContent = eleveNom + ' — ' + range.label;
        }

        if (!presences.length) {
            list.innerHTML = '<p class="historique-empty"><i class="fas fa-info-circle"></i> Aucune présence enregistrée pour cette période.</p>';
        } else {
            list.innerHTML = presences.map(function (p) {
                var statutClass = 'statut-' + p.statut;
                return '<div class="historique-item ' + statutClass + '">' +
                    '<div class="historique-item-date"><i class="fas fa-calendar-day"></i> ' + p.label + '</div>' +
                    '<div class="historique-item-statut">' + p.statut_display + '</div>' +
                    '</div>';
            }).join('');
        }

        modal.classList.add('is-visible');
        modal.style.display = 'flex';
    };

    window.fermerModalHistoriquePresence = function () {
        var modal = document.getElementById('modalHistoriquePresence');
        if (modal) {
            modal.classList.remove('is-visible');
            modal.style.display = 'none';
        }
    };

    window.fermerModalJustification = function () {
        var modal = document.getElementById('modalJustification');
        var selectElement = document.getElementById('presenceSelect');
        if (modal) {
            modal.classList.remove('is-visible');
            modal.style.display = 'none';
        }
        if (selectElement) {
            selectElement.innerHTML = '<option value="">Sélectionnez une absence</option>';
        }
        var form = modal ? modal.querySelector('form') : null;
        if (form) {
            form.reset();
        }
    };

    window.ouvrirModalJustification = function (eleveId, eleveNom, classeId) {
        var modal = document.getElementById('modalJustification');
        var selectElement = document.getElementById('presenceSelect');
        if (!modal || !selectElement) {
            return;
        }

        var data = loadPresenceData(classeId);
        var range = getDateRange(classeId);
        var absences = (data[String(eleveId)] || []).filter(function (p) {
            return p.statut === 'absent' && isDateInRange(p.date, range);
        });

        if (!absences.length) {
            return;
        }

        selectElement.innerHTML = '<option value="">Sélectionnez une absence</option>' +
            absences.map(function (a) {
                return '<option value="' + a.id + '">' + a.label + '</option>';
            }).join('');

        document.getElementById('justificationEleveNom').textContent = eleveNom;
        modal.classList.add('is-visible');
        modal.style.display = 'flex';
    };

    document.addEventListener('DOMContentLoaded', function () {
        referenceDate = document.body.getAttribute('data-reference-date');
        document.querySelectorAll('.presence-panel').forEach(function (panel) {
            var classeId = panel.getAttribute('data-classe-id');
            if (classeId) {
                filterPresenceStudents(classeId);
            }
        });
    });

    window.addEventListener('click', function (event) {
        var historiqueModal = document.getElementById('modalHistoriquePresence');
        if (event.target === historiqueModal) {
            fermerModalHistoriquePresence();
        }
        var justificationModal = document.getElementById('modalJustification');
        if (event.target === justificationModal) {
            fermerModalJustification();
        }
    });
})();
