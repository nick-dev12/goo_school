/**
 * Ajout dynamique de lignes de documents (UI uniquement)
 */
function ajouterLigneDocument(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;

    var rows = container.querySelectorAll('.document-upload-row');
    var template = rows[0];
    if (!template) return;

    var clone = template.cloneNode(true);
    clone.querySelectorAll('input').forEach(function (input) {
        input.value = '';
    });
    container.appendChild(clone);
}
