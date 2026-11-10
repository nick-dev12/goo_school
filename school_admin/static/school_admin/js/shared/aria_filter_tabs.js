/* Adapt existing teacher filter markup to the shared tab component. */
(() => {
  const groups = '.prof-hub-filter-block, .prof-notes-filter-block, .prof-exercices-filter-block, .prof-noter-filter-group, .eval-filters, .notes-eval-filter';
  const kinds = { period: /period|periode|période/i, class: /classe|class/i, subject: /matiere|matière|subject/i, view: /vue|view/i };
  function enhance(root) {
    root.querySelectorAll(groups).forEach(group => {
      group.classList.add('aria-filter-tabs__group');
      if (!group.dataset.kind) {
        const name = group.className + ' ' + (group.getAttribute('aria-label') || '');
        group.dataset.kind = Object.keys(kinds).find(kind => kinds[kind].test(name)) || 'view';
      }
      group.querySelectorAll('.prof-hub-filter-label, .prof-notes-filter-label, .prof-exercices-filter-label, .prof-noter-filter-label').forEach(label => label.classList.add('aria-filter-tabs__label'));
      group.querySelectorAll('.matiere-tabs-bar, .ovf-bar').forEach(list => list.classList.add('aria-filter-tabs__list'));
      group.querySelectorAll('a.matiere-tab-btn, button.matiere-tab-btn, .ovf-tab, .notes-secondary-tab').forEach(tab => tab.classList.add('aria-filter-tabs__tab'));
    });
  }
  const start = () => {
    enhance(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === 1) enhance(node.closest?.(groups)?.parentElement || node);
    }))).observe(document.body, {childList:true,subtree:true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
