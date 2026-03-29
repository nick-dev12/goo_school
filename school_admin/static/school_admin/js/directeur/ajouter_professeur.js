/**
 * Ajouter Professeur — interactions UI (filière, niveau LMD, filtrage matières, recherche).
 * La validation et l'enregistrement sont gérés par Django.
 */

(function () {
    'use strict';

    function normalize(s) {
        var t = (s || '').toString().toLowerCase();
        try {
            if (typeof t.normalize === 'function') {
                t = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            }
        } catch (e) {
            /* navigateurs très anciens */
        }
        return t;
    }

    /**
     * Enseignement supérieur : filière → niveau LMD → matières (même logique partout).
     * @param {object} [config]
     * @param {string} [config.submitButtonId] — ex. bouton « Ajouter » du modal détail professeur
     * @param {string} [config.niveauEmptyOptionText] — libellé 1re option du select niveau
     */
    window.initProfesseurSuperieurMatierePicker = function (config) {
        config = config || {};
        var submitButtonId = config.submitButtonId || null;
        var niveauEmptyOptionText = config.niveauEmptyOptionText || 'Sélectionnez un niveau (L1, L2, M1…)';

        var departmentSelect = document.getElementById('department');
        var niveauWrap = document.getElementById('niveau-lmd-wrap');
        var niveauSelect = document.getElementById('niveau_lmd');
        var matieresContainer = document.getElementById('matieres-superieur-container');
        var principaleSearch = document.getElementById('matiere-principale-search');
        var principaleList = document.getElementById('matiere-principale-list');
        var principaleHidden = document.getElementById('input_matiere_principale');
        var selectedBar = document.getElementById('matiere-principale-selected-bar');
        var selectedLabel = document.getElementById('matiere-principale-selected-label');
        var clearPrincipaleBtn = document.getElementById('matiere-principale-clear');

        if (!principaleList || !principaleHidden) {
            return;
        }

        var pickItems = principaleList.querySelectorAll('.matiere-pick-item');
        var noResultsMsg = document.getElementById('matiere-principale-no-results');

        /** Même séparateur que côté Django (professeur_controller) pour data-niveau-lmd-keys. */
        var NIVEAU_KEYS_SEP = '\x1f';

        function niveauKeysFromButton(btn) {
            if (!btn) {
                return [];
            }
            var raw = btn.getAttribute('data-niveau-lmd-keys');
            if (raw !== null && raw !== '') {
                return raw.split(NIVEAU_KEYS_SEP)
                    .map(function (s) { return String(s).trim(); })
                    .filter(Boolean);
            }
            var legacy = String(btn.getAttribute('data-niveau-lmd-key') || '').trim();
            return legacy ? [legacy] : [];
        }

        function buttonMatchesNiveau(btn, nivNorm) {
            if (!nivNorm) {
                return false;
            }
            return niveauKeysFromButton(btn).indexOf(nivNorm) !== -1;
        }

        var niveauxParDep = {};
        var dataEl = document.getElementById('niveaux-lmd-par-filiere-data');
        if (dataEl && dataEl.textContent) {
            try {
                niveauxParDep = JSON.parse(dataEl.textContent);
            } catch (e2) {
                niveauxParDep = {};
            }
        }

        function getPrincipaleId() {
            return principaleHidden ? principaleHidden.value : '';
        }

        function getDepId() {
            return departmentSelect ? departmentSelect.value : '';
        }

        function getNiveauKey() {
            return niveauSelect ? String(niveauSelect.value || '').trim() : '';
        }

        function syncSubmitButtonIfAny() {
            if (!submitButtonId) {
                return;
            }
            var btn = document.getElementById(submitButtonId);
            if (!btn) {
                return;
            }
            var mid = (principaleHidden.value || '').trim();
            var depOk = !!(departmentSelect && String(departmentSelect.value || '').trim());
            var nivOk = !!(niveauSelect && String(niveauSelect.value || '').trim());
            btn.disabled = !(mid && depOk && nivOk);
        }

        /** Reconstruit les options du select niveau à partir du JSON (changement de filière). */
        function rebuildNiveauOptions(depId) {
            if (!niveauSelect) {
                return;
            }
            var preserved = niveauSelect.value;
            niveauSelect.innerHTML = '';
            var opt0 = document.createElement('option');
            opt0.value = '';
            opt0.textContent = niveauEmptyOptionText;
            niveauSelect.appendChild(opt0);
            var list = (depId && niveauxParDep[depId]) || [];
            list.forEach(function (item) {
                var o = document.createElement('option');
                o.value = item.key;
                o.textContent = item.label;
                niveauSelect.appendChild(o);
            });
            var stillValid = list.some(function (x) {
                return String(x.key) === String(preserved);
            });
            if (stillValid && preserved) {
                niveauSelect.value = preserved;
            } else {
                niveauSelect.value = '';
            }
        }

        function updateMatiereSectionVisibility() {
            var depId = getDepId();
            var niv = getNiveauKey();
            var showNivWrap = !!depId;
            if (niveauWrap) {
                niveauWrap.style.display = showNivWrap ? 'block' : 'none';
            }
            if (niveauSelect) {
                niveauSelect.disabled = !depId;
            }
            var showMat = !!depId && !!niv;
            if (matieresContainer) {
                matieresContainer.style.display = showMat ? 'block' : 'none';
            }
            if (principaleSearch) {
                principaleSearch.disabled = !showMat;
                if (!showMat) {
                    principaleSearch.value = '';
                }
            }
            if (!showMat) {
                clearPrincipaleOnly();
            }
            filterPrincipaleList();
            syncSubmitButtonIfAny();
        }

        function clearPrincipaleOnly() {
            principaleHidden.value = '';
            pickItems.forEach(function (btn) {
                btn.classList.remove('is-selected');
                btn.setAttribute('aria-selected', 'false');
            });
            if (selectedBar) {
                selectedBar.hidden = true;
            }
            if (selectedLabel) {
                selectedLabel.textContent = '';
            }
            syncSubmitButtonIfAny();
        }

        function filterPrincipaleList() {
            var depId = getDepId();
            var niv = getNiveauKey();
            var rawQ = principaleSearch ? principaleSearch.value : '';
            var q = normalize(rawQ);
            var principaleId = getPrincipaleId();
            var visibleCount = 0;
            var nivNorm = (niv || '').trim();
            pickItems.forEach(function (btn) {
                if (!depId || !nivNorm) {
                    btn.hidden = true;
                    return;
                }
                var itemDep = String(btn.getAttribute('data-department-id') || '').trim();
                if (itemDep !== String(depId).trim() || !buttonMatchesNiveau(btn, nivNorm)) {
                    btn.hidden = true;
                    return;
                }
                var mid = btn.getAttribute('data-matiere-id') || '';
                var isSelected = principaleId && mid === String(principaleId);
                var haystack = btn.getAttribute('data-matiere-search');
                var text = normalize(haystack != null && haystack !== '' ? haystack : btn.textContent);
                var matchQ = !q || text.indexOf(q) !== -1;
                var show = matchQ || isSelected;
                btn.hidden = !show;
                if (show) {
                    visibleCount += 1;
                }
            });
            if (noResultsMsg) {
                var showEmpty = !!depId && !!niv && visibleCount === 0 && pickItems.length > 0;
                noResultsMsg.hidden = !showEmpty;
            }
            syncSubmitButtonIfAny();
        }

        function setPrincipaleSelection(matiereId, labelText) {
            principaleHidden.value = matiereId || '';
            pickItems.forEach(function (btn) {
                var id = btn.getAttribute('data-matiere-id');
                var sel = matiereId && id === String(matiereId);
                btn.classList.toggle('is-selected', sel);
                btn.setAttribute('aria-selected', sel ? 'true' : 'false');
            });
            if (selectedBar && selectedLabel) {
                if (matiereId && labelText) {
                    selectedLabel.textContent = labelText;
                    selectedBar.hidden = false;
                } else {
                    selectedLabel.textContent = '';
                    selectedBar.hidden = true;
                }
            }
            filterPrincipaleList();
        }

        function clearPrincipaleSelection() {
            clearPrincipaleOnly();
            if (principaleSearch) {
                principaleSearch.value = '';
            }
            filterPrincipaleList();
        }

        pickItems.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (!getDepId() || !getNiveauKey()) {
                    return;
                }
                if (btn.hidden) {
                    return;
                }
                var mid = btn.getAttribute('data-matiere-id');
                var mainEl = btn.querySelector('.matiere-pick-main');
                var labelText = mainEl ? mainEl.textContent.trim() : btn.textContent.trim();
                setPrincipaleSelection(mid, labelText);
            });
        });

        if (clearPrincipaleBtn) {
            clearPrincipaleBtn.addEventListener('click', clearPrincipaleSelection);
        }

        if (principaleSearch) {
            var runFilter = function () {
                filterPrincipaleList();
            };
            principaleSearch.addEventListener('input', runFilter);
            principaleSearch.addEventListener('keyup', runFilter);
            principaleSearch.addEventListener('search', runFilter);
            principaleSearch.addEventListener('paste', function () {
                requestAnimationFrame(runFilter);
            });
            principaleSearch.addEventListener('cut', function () {
                requestAnimationFrame(runFilter);
            });
        }

        if (departmentSelect) {
            departmentSelect.addEventListener('change', function () {
                var depId = getDepId();
                rebuildNiveauOptions(depId);
                var pid = getPrincipaleId();
                if (pid && depId) {
                    var currentBtn = principaleList.querySelector(
                        '.matiere-pick-item[data-matiere-id="' + pid + '"]'
                    );
                    if (
                        currentBtn &&
                        String(currentBtn.getAttribute('data-department-id') || '').trim() !== String(depId).trim()
                    ) {
                        clearPrincipaleOnly();
                        if (principaleSearch) {
                            principaleSearch.value = '';
                        }
                    }
                } else if (!depId) {
                    clearPrincipaleOnly();
                    if (principaleSearch) {
                        principaleSearch.value = '';
                    }
                }
                updateMatiereSectionVisibility();
            });
        }

        if (niveauSelect) {
            niveauSelect.addEventListener('change', function () {
                var pid = getPrincipaleId();
                var niv = getNiveauKey();
                if (pid && niv) {
                    var btn = principaleList.querySelector(
                        '.matiere-pick-item[data-matiere-id="' + pid + '"]'
                    );
                    if (btn && !buttonMatchesNiveau(btn, niv)) {
                        clearPrincipaleOnly();
                        if (principaleSearch) {
                            principaleSearch.value = '';
                        }
                    }
                } else if (!niv) {
                    clearPrincipaleOnly();
                    if (principaleSearch) {
                        principaleSearch.value = '';
                    }
                }
                updateMatiereSectionVisibility();
            });
        }

        (function restoreState() {
            var depId = getDepId();
            if (depId && niveauSelect && niveauSelect.options.length <= 1) {
                rebuildNiveauOptions(depId);
            }
            updateMatiereSectionVisibility();
            var niv = getNiveauKey();
            var pid = principaleHidden.value;
            if (pid && depId && niv) {
                var btn = principaleList.querySelector(
                    '.matiere-pick-item[data-matiere-id="' + pid + '"]'
                );
                if (
                    btn &&
                    String(btn.getAttribute('data-department-id') || '').trim() === String(depId).trim() &&
                    buttonMatchesNiveau(btn, niv)
                ) {
                    var mainEl = btn.querySelector('.matiere-pick-main');
                    var labelText = mainEl ? mainEl.textContent.trim() : '';
                    setPrincipaleSelection(pid, labelText);
                } else {
                    clearPrincipaleOnly();
                }
            } else if (pid && (!depId || !niv)) {
                clearPrincipaleOnly();
            }
            syncSubmitButtonIfAny();
        })();
    };

    /**
     * Page « Ajouter un professeur » (supérieur).
     */
    window.initAjouterProfesseurSuperieur = function () {
        window.initProfesseurSuperieurMatierePicker({});
    };
})();
