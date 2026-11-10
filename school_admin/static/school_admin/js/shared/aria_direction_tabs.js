/* Branche toutes les barres d’onglets direction sur le composant aria-filter-tabs. */
(() => {
  const SKIP_ROOT = '.ax-dock, .qr-scanner-modal, .gtranslate, footer, .bottom-nav';
  const SKIP_TAB = '.matiere-tabs-more-btn, .ovf-more-btn, .aria-filter-tabs__label';
  const SKIP_PARENT = '.tabs-container, .nr-niveau-tabs, .content-container, .main-content, .axd-page, body, main';
  const BAR_SELECTOR = [
    '.matiere-tabs-bar',
    '.tabs-nav',
    '.tabs-navigation',
    '.period-tabs',
    '.niveau-tabs-nav',
    '.niveau-tabs-row',
    '.type-tabs-nav',
    '.adm-onglets',
    '.fe-tabs',
    '.fe-subtabs',
    '.edtd-main-tabs-nav',
    '.edtd-semestres',
    '.dlb-filtres',
    '.cg-pages-tabs',
    '.nr-periodes-bar',
    '.sp-periodes-bar',
    '.periodes-tabs-container',
    '.periodes-tabs-horizontal',
    '.periodes-nav',
    '.ele-classe-nav',
    '.ele-niveau-nav',
  ].join(',');
  const PANEL_SEL = '.tab-panel, .tab-content-panel, .tab-content, [role="tabpanel"], .classe-subtab-content, .ele-niveau-panel, .caisse-tabs-content, .tabs-content, .fe-panel, .fe-subpanel';

  const kindFor = (el) => {
    const labels = [
      el.getAttribute('aria-label'),
      el.dataset.overflowItemLabel,
      el.dataset.overflowItemsLabel,
    ].join(' ').toLowerCase();
    const cls = [el.className, el.parentElement && el.parentElement.className]
      .join(' ')
      .replace(/matiere-tabs-\S+/gi, '')
      .toLowerCase();
    const hint = `${labels} ${cls}`;
    if (/période|periode|trimestre|semestre/.test(hint)) return 'period';
    if (/classe/.test(hint)) return 'class';
    if (/niveau|cycle|filière|filiere|catégorie|categorie/.test(hint)) return 'class';
    if (/matière|matiere|module|subject/.test(hint)) return 'subject';
    return 'view';
  };

  const markTabs = (root) => {
    root.querySelectorAll('a, button, [role="tab"]').forEach((tab) => {
      if (tab.closest('.matiere-tabs-overflow-menu') || tab.matches(SKIP_TAB)) return;
      tab.classList.add('aria-filter-tabs__tab');
    });
  };

  const hasPanels = (el) => !!(el && el.querySelector(PANEL_SEL));

  const ensureGroup = (bar) => {
    let existing = bar.closest('.aria-filter-tabs__group');
    if (existing && !hasPanels(existing) && !existing.matches(SKIP_PARENT)) {
      if (!existing.dataset.kind) existing.dataset.kind = kindFor(bar);
      return existing;
    }
    if (existing && (hasPanels(existing) || existing.matches(SKIP_PARENT))) {
      existing.classList.remove('aria-filter-tabs__group');
      delete existing.dataset.kind;
    }
    const parent = bar.parentElement;
    const tooWide = !parent || parent.matches(SKIP_PARENT);
    if (parent && !tooWide && !hasPanels(parent) && parent.children.length <= 4) {
      parent.classList.add('aria-filter-tabs__group');
      parent.dataset.kind = kindFor(bar);
      return parent;
    }
    const group = document.createElement('section');
    group.className = 'aria-filter-tabs__group';
    group.dataset.kind = kindFor(bar);
    const prev = bar.previousElementSibling;
    bar.parentNode.insertBefore(group, bar);
    if (prev && /kicker|hint|label|nav-kicker/.test(prev.className || '')) {
      prev.classList.add('aria-filter-tabs__label');
      group.appendChild(prev);
    }
    group.appendChild(bar);
    return group;
  };

  const enhance = (root) => {
    if (!root || root.nodeType !== 1) return;
    if (root.closest && root.closest(SKIP_ROOT)) return;
    const bars = [
      ...(root.matches && root.matches(BAR_SELECTOR) ? [root] : []),
      ...root.querySelectorAll(BAR_SELECTOR),
    ];
    bars.forEach((bar) => {
      if (bar.closest(SKIP_ROOT)) return;
      const group = ensureGroup(bar);
      bar.classList.add('aria-filter-tabs__list');
      bar.dataset.ariaTabsKind = group.dataset.kind;
      markTabs(bar);
    });
  };

  const start = () => {
    enhance(document.body);
    new MutationObserver((records) => {
      records.forEach((record) => {
        record.addedNodes.forEach((node) => {
          if (node.nodeType === 1) enhance(node);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
