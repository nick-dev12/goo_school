/**
 * Liste classes — modal ajout + helpers formulaire LMD
 */

(function () {
    'use strict';

    function initAddClasseModal() {
        var addClasseBtn = document.getElementById('addClasseBtn');
        var addClasseBtnEmpty = document.getElementById('addClasseBtnEmpty');
        var modal = document.getElementById('addClasseModal');
        var closeBtn = document.getElementById('closeModal');
        var cancelBtn = document.getElementById('cancelAdd');

        if (!modal) return;

        function openModal() {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeModalFunc() {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }

        if (addClasseBtn) {
            addClasseBtn.addEventListener('click', function (e) {
                e.preventDefault();
                openModal();
            });
        }

        if (addClasseBtnEmpty) {
            addClasseBtnEmpty.addEventListener('click', function (e) {
                e.preventDefault();
                openModal();
            });
        }

        if (closeBtn) closeBtn.addEventListener('click', closeModalFunc);
        if (cancelBtn) cancelBtn.addEventListener('click', closeModalFunc);

        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModalFunc();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                closeModalFunc();
            }
        });

        var departmentSelect = document.getElementById('department');
        var nomInput = document.getElementById('nom');
        if (departmentSelect && nomInput) {
            departmentSelect.addEventListener('change', function () {
                var selected = this.options[this.selectedIndex];
                nomInput.value = this.value ? selected.text : '';
            });
        }

        var niveauLmdSelect = document.getElementById('niveau_lmd');
        var niveauLibelleGroup = document.getElementById('niveauLibelleGroup');
        var niveauLibelleInput = document.getElementById('niveau_libelle');
        if (niveauLmdSelect && niveauLibelleGroup && niveauLibelleInput) {
            function toggleNiveauLibelle() {
                if (niveauLmdSelect.value === 'AUTRE') {
                    niveauLibelleGroup.style.display = 'block';
                    niveauLibelleInput.required = true;
                } else {
                    niveauLibelleGroup.style.display = 'none';
                    niveauLibelleInput.required = false;
                    niveauLibelleInput.value = '';
                }
            }
            niveauLmdSelect.addEventListener('change', toggleNiveauLibelle);
            toggleNiveauLibelle();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAddClasseModal);
    } else {
        initAddClasseModal();
    }
})();
