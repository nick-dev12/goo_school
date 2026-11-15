/* Synthèse d'arrivée et centre « À faire » — commun à tous les espaces.
   Les situations viennent du serveur (services/context_popups.py) ; rien n'est décidé ici. */
const endpoint = '/api/context-popup/';
const storageKey = 'aria-context-visit';
const newVisitKey = () => crypto.randomUUID().replaceAll('-', '');
let visit, dialog, previousFocus, pill, greeting = null, progress = null, total = 0, running = false, styled;
let visitKey;
try {
  visitKey = sessionStorage.getItem(storageKey);
  const navigation = performance.getEntriesByType('navigation')[0];
  const external = document.referrer && new URL(document.referrer).origin !== location.origin;
  if (!visitKey || external || (!document.referrer && navigation?.type === 'navigate')) visitKey = newVisitKey();
  sessionStorage.setItem(storageKey, visitKey);
} catch { visitKey = newVisitKey(); }
const cookie = document.cookie.split('; ').find(value => value.startsWith('csrftoken='));
const csrf = cookie ? decodeURIComponent(cookie.substring('csrftoken='.length)) : '';

async function send(action, key) {
  const response = await fetch(endpoint, {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
    body: JSON.stringify({action, visit, key, visit_key: visitKey})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Informations indisponibles.');
  return data;
}

/* ---------- Construction du DOM (texte toujours via textContent) ---------- */
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}
const ICONS = {
  devoir: '<path d="M12 7v13"/><path d="M3 5h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5v13h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3H3z"/>',
  evaluation: '<rect x="5" y="4" width="14" height="17" rx="2.5"/><path d="M9 4V3h6v1"/><path d="m9 13 2 2 4-4.5"/>',
  convocation: '<path d="M4 10v4a1 1 0 0 0 1 1h2l5 4V5L7 9H5a1 1 0 0 0-1 1z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 6.5a8 8 0 0 1 0 11"/>',
  scolarite: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/><path d="M15.5 14.5h2"/>',
  dossier: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  famille: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17.5" cy="9.5" r="2.4"/><path d="M16.5 15.2A4.6 4.6 0 0 1 21 20"/>',
  cloche: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  appel: '<circle cx="10" cy="8" r="3.4"/><path d="M3.5 20a6.5 6.5 0 0 1 11.2-4.5"/><path d="m15 17.5 2 2 4-4.5"/>',
  notes: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  cahier: '<rect x="6" y="3" width="13" height="18" rx="2.5"/><path d="M4 7h3M4 12h3M4 17h3"/><path d="M11 8h4M11 12h4"/>',
  planning: '<rect x="4" y="5" width="16" height="16" rx="2.5"/><path d="M4 10h16"/><path d="M8.5 3v4M15.5 3v4"/>',
  work: '<path d="m9 12 2 2 4-4.5"/><circle cx="12" cy="12" r="9"/>',
  finance: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/>',
  important: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4.5"/><path d="M12 17.4v.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6v.1"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  list: '<path d="m4 6 1.5 1.5L8 5"/><path d="m4 12 1.5 1.5L8 11"/><path d="m4 18 1.5 1.5L8 17"/><path d="M12 6.5h8M12 12.5h8M12 18.5h8"/>',
  done: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/>',
  spark: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/>',
};
function icon(name, className) {
  const holder = node('span', className);
  holder.setAttribute('aria-hidden', 'true');
  // Tracés constants définis ci-dessus : aucune donnée serveur n'entre dans ce HTML.
  holder.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.info}</svg>`;
  return holder;
}
function button(className, label, iconName) {
  const element = node('button', className);
  element.type = 'button';
  element.append(node('span', '', label));
  if (iconName) element.append(icon(iconName, 'arp-btn__icon'));
  return element;
}
function loadStyles() {
  if (styled) return styled;
  styled = new Promise(resolve => {
    const stylesheet = node('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = new URL('../../css/shared/context_popups.css?v=8', import.meta.url).href;
    stylesheet.onload = stylesheet.onerror = resolve;
    document.head.append(stylesheet);
  });
  return styled;
}

/* ---------- Fenêtre ---------- */
function close() {
  if (!dialog) return;
  dialog.close(); dialog.remove(); dialog = null;
  previousFocus?.focus?.();
}
function safeToShow() {
  if (document.visibilityState !== 'visible') return false;
  if (document.activeElement?.matches('input,textarea,select,[contenteditable=true]')) return false;
  return ![...document.querySelectorAll('dialog[open],[role=dialog]:not([aria-hidden=true])')]
    .some(element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
}
const GROUPS = [
  ['now', 'À faire maintenant'],
  ['soon', 'À venir'],
  ['news', 'Nouveautés'],
  ['later', 'Reportées'],
];
const TONES = ['work', 'finance', 'important', 'info'];
const plural = (count, one, many) => count > 1 ? `${count} ${many}` : one;

function headline(cards, mode) {
  const actions = cards.filter(card => card.group !== 'news' && !card.snoozed).length;
  if (mode === 'centre' && !cards.length) return 'Tout est à jour.';
  if (!actions) return plural(cards.length, 'Une nouveauté à découvrir.', 'nouveautés à découvrir.');
  return plural(actions, 'Une action vous attend.', 'actions vous attendent.');
}

function buildCard(card, mode, list, refresh) {
  const tone = TONES.includes(card.tone) ? card.tone : 'info';
  const article = node('article', `arp-card arp-card--${tone}${card.late ? ' arp-card--late' : ''}${card.snoozed ? ' arp-card--snoozed' : ''}`);
  const mark = icon(card.icon, 'arp-card__icon');
  if (card.count > 1) mark.append(node('span', 'arp-card__count', String(card.count)));
  const body = node('div', 'arp-card__body');
  const top = node('div', 'arp-card__top');
  top.append(node('p', 'arp-card__context', card.context));
  if (card.due) {
    const due = node('span', `arp-due${card.late ? ' arp-due--late' : card.group === 'now' ? ' arp-due--near' : ''}`);
    due.append(icon('clock', 'arp-due__icon'), node('span', '', card.due));
    top.append(due);
  }
  body.append(top, node('h3', '', card.title), node('p', 'arp-card__text', card.text));
  const actions = node('div', 'arp-card__actions');
  const open = button('arp-btn arp-btn--primary', card.action, 'arrow');
  const error = node('p', 'arp-card__error');
  error.setAttribute('role', 'status');
  open.onclick = async () => {
    open.disabled = true;
    try {
      const result = await send(mode === 'centre' ? 'go' : 'open', card.key);
      const href = new URL(result.url, location.origin);
      if (href.origin !== location.origin) throw new Error('Lien indisponible.');
      location.assign(href.href);
    } catch (e) { error.textContent = e.message; open.disabled = false; }
  };
  actions.append(open);
  if (!card.snoozed) {
    const later = button('arp-btn arp-btn--ghost', 'Plus tard');
    later.onclick = async () => {
      later.disabled = true;
      try {
        await send(mode === 'centre' ? 'later' : 'snooze', card.key);
        article.remove();
        refresh();
      } catch (e) { error.textContent = e.message; later.disabled = false; }
    };
    actions.append(later);
  }
  body.append(actions, error);
  article.append(mark, body);
  list.append(article);
}

async function display(cards, mode) {
  await loadStyles();
  if (dialog || (mode === 'popup' && !safeToShow())) return;
  previousFocus = document.activeElement;
  dialog = node('dialog', `arp arp--${mode}`);
  dialog.setAttribute('aria-labelledby', 'arp-title');
  const dismiss = () => { if (mode === 'popup') send('dismiss').catch(() => {}); close(); };

  const header = node('header', 'arp__header');
  const heading = node('div', 'arp__heading');
  const eyebrow = node('p', 'arp__eyebrow');
  const today = new Date().toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'});
  eyebrow.append(icon(mode === 'centre' ? 'list' : 'spark', 'arp__eyebrow-icon'),
    node('span', '', mode === 'centre' ? 'Mes actions' : `Votre essentiel · ${today}`));
  const title = node('h2', '', mode === 'centre' ? 'À faire'
    : `${greeting?.hello || 'Bonjour'}${greeting?.name ? ` ${greeting.name}` : ''}`);
  title.id = 'arp-title';
  const intro = node('p', 'arp__intro', headline(cards, mode));
  heading.append(eyebrow, title, intro);
  if (progress?.total) {
    // Avancement des tâches du jour (professeur) : jauge discrète sous le titre.
    const gauge = node('div', 'arp-progress');
    const bar = node('div', 'arp-progress__bar');
    const fill = node('span', 'arp-progress__fill');
    fill.style.width = `${Math.round(Math.min(1, progress.done / progress.total) * 100)}%`;
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', String(progress.total));
    bar.setAttribute('aria-valuenow', String(progress.done)); bar.setAttribute('aria-label', progress.label);
    bar.append(fill);
    gauge.append(bar, node('span', 'arp-progress__label', progress.label));
    heading.append(gauge);
  }
  const x = node('button', 'arp__close');
  x.type = 'button'; x.setAttribute('aria-label', 'Fermer'); x.append(icon('close'));
  x.onclick = dismiss;
  header.append(heading, x);

  const content = node('div', 'arp__content');
  const refresh = () => {
    for (const section of content.querySelectorAll('.arp-group')) {
      const count = section.querySelectorAll('.arp-card').length;
      if (!count) section.remove(); else section.querySelector('.arp-group__count').textContent = String(count);
    }
    const left = content.querySelectorAll('.arp-card').length;
    if (!left && mode === 'popup') return close();
    if (!left) content.replaceChildren(emptyState());
    total = Math.max(0, total - 1); renderPill();
  };
  if (!cards.length) content.append(emptyState());
  for (const [id, label] of GROUPS) {
    const subset = cards.filter(card => (card.snoozed ? 'later' : card.group || 'now') === id);
    if (!subset.length) continue;
    const section = node('section', `arp-group arp-group--${id}`);
    const head = node('h4', 'arp-group__title');
    head.append(node('span', 'arp-group__dot'), node('span', '', label), node('span', 'arp-group__count', String(subset.length)));
    const list = node('div', 'arp-group__list');
    for (const card of subset) buildCard(card, mode, list, refresh);
    section.append(head, list);
    content.append(section);
  }

  const footer = node('footer', 'arp__footer');
  if (mode === 'popup' && total > cards.length) {
    const all = button('arp-btn arp-btn--link', `Voir mes ${total} actions`, 'arrow');
    all.onclick = () => { dismiss(); openCentre(); };
    footer.append(all);
  } else {
    footer.append(node('span', 'arp__hint', 'Cette liste se met à jour dès qu’une action est faite.'));
  }
  const done = button('arp-btn arp-btn--soft', mode === 'centre' ? 'Fermer' : 'J’ai compris');
  done.onclick = dismiss;
  footer.append(done);

  dialog.append(header, content, footer);
  dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(); });
  dialog.addEventListener('click', event => { if (event.target === dialog) dismiss(); });
  document.body.append(dialog);
  dialog.showModal();
}
function emptyState() {
  const empty = node('div', 'arp-empty');
  empty.append(icon('done', 'arp-empty__icon'), node('p', 'arp-empty__title', 'Tout est à jour'),
    node('p', 'arp-empty__text', 'Aucune action ne vous attend pour le moment.'));
  return empty;
}

/* ---------- Pastille « À faire » : rouvre la liste à tout moment ---------- */
async function renderPill() {
  if (!total) { pill?.remove(); pill = null; return; }
  await loadStyles();
  if (!pill) {
    pill = node('button', 'arp-pill');
    pill.type = 'button';
    pill.append(icon('list', 'arp-pill__icon'), node('span', 'arp-pill__label', 'À faire'), node('span', 'arp-pill__count'));
    pill.onclick = openCentre;
    document.body.append(pill);
  }
  pill.querySelector('.arp-pill__count').textContent = String(total);
  pill.setAttribute('aria-label', `Ouvrir mes actions à faire (${total})`);
}
async function openCentre() {
  if (dialog) return;
  try {
    const response = await fetch(`${endpoint}?centre=1`, {credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    greeting = data.greeting || greeting; total = data.total || 0; progress = data.progress || null;
    renderPill();
    await display(data.cards || [], 'centre');
  } catch (error) { console.debug('[Aria] Centre indisponible :', error?.message); }
}

/* ---------- Démarrage : une synthèse par visite ---------- */
async function start() {
  if (running || dialog) return;
  running = true;
  try {
    if (!csrf || !('HTMLDialogElement' in window)) return;
    for (let attempt = 0; attempt < 12 && !safeToShow(); attempt++) await new Promise(resolve => setTimeout(resolve, 1500));
    if (!safeToShow()) return;
    try {
      const result = await send('claim');
      visit = result.visit; greeting = result.greeting || greeting; total = result.total || 0;
      progress = result.progress || null;
      renderPill();
      if (!result.cards?.length) return;
      const confirmed = await send('shown');
      if (confirmed.cards?.length) await display(confirmed.cards, 'popup');
    } catch (error) { console.debug('[Aria] Synthèse indisponible :', error.message); }
  } finally { running = false; }
}
function renew() {
  if (dialog) return;
  visitKey = newVisitKey(); visit = undefined;
  try { sessionStorage.setItem(storageKey, visitKey); } catch {}
  setTimeout(start, 800);
}
let leftSite = document.visibilityState === 'hidden';
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') { leftSite = true; return; }
  if (leftSite) { leftSite = false; renew(); }
});
window.addEventListener('pageshow', event => { if (event.persisted) renew(); });
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(start, 1200), {once: true});
else setTimeout(start, 1200);
