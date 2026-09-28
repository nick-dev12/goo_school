/**
 * Convocations élève — filtres par statut (interaction uniquement)
 */
document.addEventListener('DOMContentLoaded', function () {
    initConvocationFilters();
});

function initConvocationFilters() {
    const tabs = document.querySelectorAll('.ele-conv .filter-tab');
    const cards = document.querySelectorAll('.ele-conv .convocation-card');

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            const statut = this.getAttribute('data-filter');
            filterConvocations(statut, tabs, cards);
        });
    });
}

function filterConvocations(statut, tabs, cards) {
    tabs.forEach(function (tab) {
        const isActive = tab.getAttribute('data-filter') === statut;
        tab.classList.toggle('active', isActive);
        tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    cards.forEach(function (card) {
        const show = statut === 'toutes' || card.getAttribute('data-statut') === statut;
        card.classList.toggle('is-hidden', !show);
    });
}
