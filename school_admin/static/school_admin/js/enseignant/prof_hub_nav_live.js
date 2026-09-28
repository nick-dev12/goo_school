/**
 * Navigation hub professeur sans rechargement — hub_partial + replaceState.
 */
(function () {
  'use strict';

  function hubEnabled() {
    return document.body.getAttribute('data-prof-hub-nav-live') === '1';
  }

  function hubFields() {
    var raw = document.body.getAttribute('data-prof-hub-fields') || '';
    return raw
      .split(',')
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
  }

  function hubStorageKey() {
    return document.body.getAttribute('data-prof-hub-key') || '';
  }

  function layoutOverflow() {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function syncStoreFromUrl(url) {
    var key = hubStorageKey();
    if (!key || !window.professeurTabStorage) {
      return;
    }
    var params = url.searchParams;
    var values = {};
    hubFields().forEach(function (name) {
      values[name] = params.get(name) || '';
    });
    window.professeurTabStorage.syncUrlAndStore(key, values);
  }

  function buildFetchUrl(link) {
    // Base = URL courante (pas seulement origin) : href "?classe=…" doit
    // garder /enseignant/classes/ sinon pathname devient "/" et le clic est
    // avalé par preventDefault sans navigation.
    var url = new URL(link.getAttribute('href'), window.location.href);
    if (!url.pathname || url.pathname === '/') {
      url.pathname = window.location.pathname;
    }
    if (url.pathname !== window.location.pathname) {
      return null;
    }
    url.searchParams.set('hub_partial', 'hub');
    return url;
  }

  function swapHubFragment(doc, id) {
    var fresh = doc.getElementById(id);
    var el = document.getElementById(id);
    if (fresh && el) {
      el.innerHTML = fresh.innerHTML;
    }
  }

  function applySwap(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    swapHubFragment(doc, 'prof-hub-header');
    swapHubFragment(doc, 'prof-hub-chrome');
    swapHubFragment(doc, 'prof-hub-panel');
    layoutOverflow();
    document.dispatchEvent(new CustomEvent('prof-hub-panel-loaded'));
  }

  function setLoading(loading) {
    var panel = document.getElementById('prof-hub-panel');
    if (!panel) {
      return;
    }
    panel.classList.toggle('prof-hub-panel-loading', loading);
  }

  function navigateHub(link) {
    var fetchUrl = buildFetchUrl(link);
    if (!fetchUrl) {
      return false;
    }
    setLoading(true);
    fetch(fetchUrl.toString(), {
      method: 'GET',
      credentials: 'same-origin',
      redirect: 'follow',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        Accept: 'text/html',
        'Cache-Control': 'no-cache',
      },
    })
      .then(function (response) {
        if (response.redirected && /\/connexion\/?(\?|$)/.test(response.url)) {
          throw new Error('auth-redirect');
        }
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        if (!html || html.indexOf('id="prof-hub-chrome"') === -1) {
          throw new Error('invalid-hub-partial');
        }
        applySwap(html);
        var clean = new URL(fetchUrl.toString());
        clean.searchParams.delete('hub_partial');
        window.history.replaceState({ profHub: true }, '', clean.pathname + clean.search);
        syncStoreFromUrl(clean);
      })
      .catch(function (err) {
        console.warn('[ProfHubNavLive] fallback navigation:', err);
        var href = link.getAttribute('href') || link.href;
        window.location.assign(new URL(href, window.location.href).toString());
      })
      .finally(function () {
        setLoading(false);
      });
    return true;
  }

  function onLinkClick(event) {
    if (!hubEnabled()) {
      return;
    }
    var link = event.target.closest('a.prof-hub-nav-link');
    if (!link || link.target === '_blank' || event.metaKey || event.ctrlKey || event.shiftKey) {
      return;
    }
    if (link.hasAttribute('data-hub-full-nav')) {
      return;
    }
    var href = link.getAttribute('href') || '';
    if (!href || href === '#') {
      return;
    }
    if (navigateHub(link)) {
      event.preventDefault();
    }
  }

  document.addEventListener('click', onLinkClick);

  function onPopState() {
    if (!hubEnabled()) {
      return;
    }
    var url = new URL(window.location.href);
    url.searchParams.set('hub_partial', 'hub');
    setLoading(true);
    fetch(url.toString(), {
      method: 'GET',
      credentials: 'same-origin',
      redirect: 'follow',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        Accept: 'text/html',
        'Cache-Control': 'no-cache',
      },
    })
      .then(function (response) {
        if (response.redirected && /\/connexion\/?(\?|$)/.test(response.url)) {
          throw new Error('auth-redirect');
        }
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        if (!html || html.indexOf('id="prof-hub-chrome"') === -1) {
          throw new Error('invalid-hub-partial');
        }
        applySwap(html);
      })
      .catch(function () {
        window.location.reload();
      })
      .finally(function () {
        setLoading(false);
      });
  }

  window.addEventListener('popstate', onPopState);

  window.ProfHubNavLive = {
    navigateHub: navigateHub,
    applySwap: applySwap,
    layoutOverflow: layoutOverflow,
  };
})();
