(() => {
  const form = document.getElementById('personnalisation-form');
  const preview = document.querySelector('.personnalisation-preview');
  const status = document.getElementById('personnalisation-status');
  const dialog = document.getElementById('modeles-dialog');
  const openModeles = document.getElementById('choisir-modele');
  const choices = [...dialog.querySelectorAll('[data-modele]')];
  const modelNames = Object.fromEntries(choices.map(button => [button.dataset.modele,
    button.querySelector('.modele-nom').childNodes[0].textContent.trim()]));
  const fields = {pays_nom: '.idcard-country', devise_pays: '.idcard-motto',
    titre_carte: '.idcard-title', devise_etablissement: '.idcard-back-motto'};
  const update = () => {
    Object.entries(fields).forEach(([name, selector]) => {
      preview.querySelectorAll(selector).forEach(element => { element.textContent = form.elements[name].value; });
    });
    const wrapper = preview.querySelector('.student-idcard-wrapper');
    wrapper.dataset.carteModele = form.elements.modele.value;
    document.getElementById('modele-actuel').textContent = modelNames[form.elements.modele.value] || 'Classique';
    choices.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.modele === form.elements.modele.value)));
    ['principale', 'secondaire', 'fond', 'texte'].forEach(nom => {
      wrapper.style.setProperty('--carte-' + nom, form.elements['couleur_' + nom].value);
    });
    const hex = form.elements.couleur_principale.value;
    const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
    wrapper.style.setProperty('--carte-contraste', rgb.reduce((s, c, i) => s + c * [.2126, .7152, .0722][i], 0) > .179 ? '#111827' : '#ffffff');
  };
  update();
  form.addEventListener('input', () => {
    update();
    status.textContent = 'Aperçu mis à jour. Enregistrez pour appliquer les modifications.';
  });
  form.addEventListener('change', update);
  const resizeMiniatures = () => {
    choices.forEach(button => {
      const miniature = button.querySelector('.modele-miniature');
      const wrapper = miniature.firstElementChild;
      if (wrapper && miniature.clientWidth) wrapper.style.zoom = String(miniature.clientWidth / 480);
    });
  };
  openModeles.addEventListener('click', () => {
    const original = preview.querySelector('.student-idcard-wrapper');
    choices.forEach(button => {
      const wrapper = document.createElement('div');
      wrapper.className = 'student-idcard-wrapper';
      wrapper.dataset.carteModele = button.dataset.modele;
      ['principale', 'secondaire', 'fond', 'texte', 'contraste'].forEach(name => {
        wrapper.style.setProperty('--carte-' + name, original.style.getPropertyValue('--carte-' + name));
      });
      wrapper.append(original.querySelector('.student-idcard-front').cloneNode(true));
      button.querySelector('.modele-miniature').replaceChildren(wrapper);
    });
    dialog.showModal();
    resizeMiniatures();
    (choices.find(button => button.dataset.modele === form.elements.modele.value) || choices[0]).focus();
  });
  dialog.querySelector('.modeles-fermer').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    }
  });
  dialog.addEventListener('close', () => openModeles.focus());
  choices.forEach(button => button.addEventListener('click', () => {
    form.elements.modele.value = button.dataset.modele;
    update();
    status.textContent = 'Modèle ' + modelNames[button.dataset.modele] + ' sélectionné. Enregistrez pour appliquer les modifications.';
    dialog.close();
  }));
  if ('ResizeObserver' in window) {
    const miniatureObserver = new ResizeObserver(() => { if (dialog.open) resizeMiniatures(); });
    choices.forEach(button => miniatureObserver.observe(button.querySelector('.modele-miniature')));
  } else {
    window.addEventListener('resize', () => { if (dialog.open) resizeMiniatures(); });
  }
  preview.querySelectorAll('[data-face]').forEach(button => button.addEventListener('click', () => {
    preview.dataset.face = button.dataset.face;
    preview.querySelectorAll('[data-face]').forEach(other => {
      other.setAttribute('aria-pressed', String(other === button));
    });
  }));
  form.addEventListener('submit', () => {
    form.querySelector('[type="submit"]').disabled = true;
    status.textContent = 'Enregistrement en cours…';
  });
})();
