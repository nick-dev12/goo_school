(function () {
  'use strict';

  var root = document.getElementById('assistant-vocal-root');
  if (!root) {
    return;
  }

  var fab = document.getElementById('assistant-vocal-fab');
  var panel = document.getElementById('assistant-vocal-panel');
  var closeBtn = document.getElementById('assistant-vocal-close');
  var form = document.getElementById('assistant-vocal-form');
  var input = document.getElementById('assistant-vocal-input');
  var micBtn = document.getElementById('assistant-vocal-mic');
  var micCancelBtn = document.getElementById('assistant-vocal-mic-cancel');
  var sendBtn = document.getElementById('assistant-vocal-send');
  var messages = document.getElementById('assistant-vocal-messages');
  var emptyState = document.getElementById('assistant-vocal-empty');
  var statusEl = document.getElementById('assistant-vocal-status');
  var confirmBox = document.getElementById('assistant-vocal-confirm');
  var confirmYes = document.getElementById('assistant-vocal-confirm-yes');
  var confirmNo = document.getElementById('assistant-vocal-confirm-no');
  var muteBtn = document.getElementById('assistant-vocal-mute');
  var voiceTimerEl = document.getElementById('assistant-vocal-voice-timer');
  var liveBox = document.getElementById('assistant-vocal-live');

  var SILENCE_MS = 1600;
  var CACHE_KEY = 'aria.assistant.cache';
  var MUTE_KEY = 'aria.assistant.muted';
  var PARENT_LANG_KEY = 'aria.parent.lang_pref';
  var ELEVE_LANG_KEY = 'aria.eleve.lang_pref';
  var ANNONCE_DRAFT_KEY = 'aria.annonce.draft';
  var CHARS_PER_SECOND = 13;
  var TARGET_RATE = 16000;
  var SPEAK_RMS = 0.045;
  var QUIET_RMS = 0.018;
  var NAV_FALLBACK = 120;
  var MAX_VOICE_SEC = 90;

  var socket = null;
  var reconnectTimer = null;
  var audioUnlocked = false;
  var audioContext = null;
  var currentAssistantBubble = null;
  var spokenPlain = '';
  var audioQueue = [];
  var isPlaying = false;
  var currentAudio = null;
  var typewriterTimer = null;
  var liveMode = false;
  var pendingTranscript = '';
  var silenceTimer = null;
  var busy = false;
  var ignoreIncoming = false;
  var pendingDone = false;
  var liveStream = null;
  var captureCtx = null;
  var captureSource = null;
  var captureProcessor = null;
  var captureMute = null;
  var pcmChunks = [];
  var isVoicing = false;
  var lastVoiceAt = 0;
  var voiceStartedAt = 0;
  var lastLiveText = '';
  var committedFinals = '';
  var noiseFloor = 0.012;
  var booted = false;
  var panelWatchersBound = false;
  var sttBusy = false;
  var voiceMuted = false;
  var mediaRecorder = null;
  var recordedChunks = [];
  var recordedMime = '';
  var voiceNoteUrl = '';
  var voiceStartedMs = 0;
  var voiceTimer = null;
  var pendingDelta = '';
  var receivedVoiceSentence = false;
  var voiceSendAfterStop = false;
  var currentActionCard = null;
  var reloadAfterAction = false;
  var avatarUrl = root.getAttribute('data-avatar-url') || '';
  var chatLog = [];
  var restoring = false;
  var pendingNavigate = null;
  var lastSuggestionHost = null;
  var thinkingTurn = null;
  var lastResultStamp = '';
  var lastResultAt = 0;
  var pendingActionResult = null;
  var RESULT_VISIBLE_MS = 1400;
  var serverWelcomeText = '';

  function setStatus(_text) {
    return;
  }

  function scrollToEnd() {
    if (!messages) {
      return;
    }
    window.requestAnimationFrame(function () {
      messages.scrollTop = messages.scrollHeight;
      window.setTimeout(function () {
        messages.scrollTop = messages.scrollHeight;
      }, 40);
    });
  }

  function thinkingMarkup(label) {
    var ack = label
      ? '<p class="assistant-vocal-ack">' + escapeHtml(label) + '</p>'
      : '';
    return (
      ack +
      '<div class="assistant-vocal-thinking" aria-label="Aria réfléchit">' +
      '<span></span><span></span><span></span></div>'
    );
  }

  function showWorkingAck(label) {
    hideEmpty();
    var text = (label || '').trim() || 'Je cherche ça.';
    if (thinkingTurn && thinkingTurn.parentNode) {
      var bubble = thinkingTurn.querySelector('.assistant-vocal-bubble');
      if (bubble) {
        bubble.classList.add('is-thinking', 'is-ack');
        bubble.innerHTML = thinkingMarkup(text);
      }
      scrollToEnd();
      return;
    }
    var box = document.createElement('div');
    box.className = 'assistant-vocal-bubble is-assistant is-thinking is-ack';
    box.innerHTML = thinkingMarkup(text);
    thinkingTurn = appendAssistantTurn(box).closest('.assistant-vocal-turn');
    scrollToEnd();
  }

  function showThinking() {
    hideEmpty();
    if (thinkingTurn && thinkingTurn.parentNode) {
      scrollToEnd();
      return;
    }
    var box = document.createElement('div');
    box.className = 'assistant-vocal-bubble is-assistant is-thinking';
    box.innerHTML = thinkingMarkup('');
    thinkingTurn = appendAssistantTurn(box).closest('.assistant-vocal-turn');
    scrollToEnd();
  }

  function hideThinking() {
    if (thinkingTurn && thinkingTurn.parentNode) {
      thinkingTurn.parentNode.removeChild(thinkingTurn);
    }
    thinkingTurn = null;
  }

  function hideEmpty() {
    if (emptyState) {
      emptyState.hidden = true;
    }
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function stripAssistantMarkup(text) {
    if (!text) {
      return '';
    }
    var spoken = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    var lines = spoken.split('\n');
    var kept = [];
    lines.forEach(function (line) {
      var stripped = line.trim();
      if (!stripped) {
        return;
      }
      if (/^\|?[\s:\-]+(\|[\s:\-]+)+\|?$/.test(stripped)) {
        return;
      }
      if ((stripped.match(/\|/g) || []).length >= 2) {
        var cells = stripped.replace(/^\||\|$/g, '').split('|').map(function (cell) {
          return cell.trim();
        }).filter(function (cell) {
          return cell && !/^[-: ]+$/.test(cell);
        });
        if (cells.length) {
          kept.push(cells.join(', ') + '.');
        }
        return;
      }
      kept.push(stripped);
    });
    spoken = kept.join(' ');
    spoken = spoken.replace(/^#{1,6}\s+/gm, '');
    spoken = spoken.replace(/^\s*[-*•]\s+/gm, '');
    spoken = spoken.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
    spoken = spoken.replace(/\*\*([^*]+)\*\*/g, '$1');
    spoken = spoken.replace(/__([^_]+)__/g, '$1');
    spoken = spoken.replace(/`([^`]+)`/g, '$1');
    spoken = spoken.replace(/(^|[^\w])\*([^*]+)\*(?!\w)/g, '$1$2');
    spoken = spoken.replace(/\|/g, ' ');
    spoken = spoken.replace(/-{3,}/g, ' ');
    spoken = spoken.replace(/[*_`#\[\]]+/g, '');
    spoken = spoken.replace(/\s+/g, ' ').replace(/\s+([,.;:!?])/g, '$1').trim();
    return spoken;
  }

  function highlightData(text) {
    if (!text) {
      return '';
    }
    var source = stripAssistantMarkup(text);
    var patterns = [
      { cls: 'session', re: /\b20\d{2}\s*[-–\/]\s*20\d{2}\b/g },
      { cls: 'money', re: /\b\d+(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:FCFA|XOF|EUR|USD|F\b|€)\b/gi },
      { cls: 'percent', re: /\b\d+(?:[.,]\d+)?\s*%/g },
      { cls: 'code', re: /\b(?:SUP[-A-Z0-9]+|[A-Z]{2,}\d{4,})\b/g },
      { cls: 'classe', re: /\b[A-Z]{1,8}(?:\s+[A-Z0-9]{1,6}){1,3}\b/g },
      {
        cls: 'nom',
        re: /\b[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç']{2,}(?:\s+[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç']{2,})+\b/g,
      },
      { cls: 'number', re: /\b\d+(?:[.,]\d+)?\b/g },
    ];
    var ranges = [];
    patterns.forEach(function (pattern) {
      pattern.re.lastIndex = 0;
      var match;
      while ((match = pattern.re.exec(source)) !== null) {
        var start = match.index;
        var end = start + match[0].length;
        var overlaps = ranges.some(function (range) {
          return start < range.end && end > range.start;
        });
        if (!overlaps) {
          ranges.push({ start: start, end: end, cls: pattern.cls });
        }
      }
    });
    ranges.sort(function (a, b) {
      return a.start - b.start;
    });
    var html = '';
    var cursor = 0;
    ranges.forEach(function (range) {
      html += escapeHtml(source.slice(cursor, range.start));
      html +=
        '<mark class="assistant-vocal-hl assistant-vocal-hl-' +
        range.cls +
        '">' +
        escapeHtml(source.slice(range.start, range.end)) +
        '</mark>';
      cursor = range.end;
    });
    html += escapeHtml(source.slice(cursor));
    return html;
  }

  function paintAssistant(text, withCaret) {
    if (!currentAssistantBubble) {
      return;
    }
    var html = highlightData(text);
    if (withCaret) {
      html += '<span class="assistant-vocal-caret" aria-hidden="true"></span>';
    }
    currentAssistantBubble.innerHTML = html || '<span class="assistant-vocal-wait">…</span>';
    scrollToEnd();
  }

  function createAvatar() {
    var img = document.createElement('img');
    img.className = 'assistant-vocal-avatar';
    img.src = avatarUrl;
    img.alt = '';
    return img;
  }

  function appendAssistantTurn(contentEl) {
    var turn = document.createElement('div');
    turn.className = 'assistant-vocal-turn';
    var body = document.createElement('div');
    body.className = 'assistant-vocal-turn-body';
    body.appendChild(contentEl);
    turn.appendChild(createAvatar());
    turn.appendChild(body);
    messages.appendChild(turn);
    scrollToEnd();
    return contentEl;
  }

  function persistCache(forceOpen) {
    if (restoring) {
      return;
    }
    try {
      sessionStorage.setItem(
        CACHE_KEY,
        JSON.stringify({
          log: chatLog,
          open: forceOpen === true || root.classList.contains('is-open'),
        })
      );
    } catch (err) {
      /* quota */
    }
  }

  function historyForServer() {
    return chatLog
      .filter(function (item) {
        return !item.local && (item.role === 'user' || item.role === 'assistant') && item.text;
      })
      .map(function (item) {
        return { role: item.role, content: item.text };
      });
  }

  function isParentPersona() {
    return (root.getAttribute('data-persona') || '').trim() === 'parent';
  }

  function isElevePersona() {
    return (root.getAttribute('data-persona') || '').trim() === 'eleve';
  }

  function hasLangPrefPersona() {
    return isParentPersona() || isElevePersona();
  }

  function langPrefStorageKey() {
    if (isElevePersona()) {
      return ELEVE_LANG_KEY;
    }
    if (isParentPersona()) {
      return PARENT_LANG_KEY;
    }
    return '';
  }

  function getLangPref() {
    if (!hasLangPrefPersona()) {
      return 'auto';
    }
    try {
      var stored = sessionStorage.getItem(langPrefStorageKey());
      if (stored === 'fr' || stored === 'wo' || stored === 'auto') {
        return stored;
      }
    } catch (err) {
      /* quota */
    }
    return 'auto';
  }

  function setLangPref(value, syncServer) {
    if (!hasLangPrefPersona()) {
      return;
    }
    var pref = value === 'fr' || value === 'wo' ? value : 'auto';
    try {
      sessionStorage.setItem(langPrefStorageKey(), pref);
    } catch (err) {
      /* quota */
    }
    var chips = root.querySelectorAll('[data-lang-pref]');
    chips.forEach(function (chip) {
      var active = chip.getAttribute('data-lang-pref') === pref;
      chip.classList.toggle('is-active', active);
      chip.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    if (syncServer !== false && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'set_lang_pref', value: pref }));
    }
  }

  function bindLangPrefChips() {
    if (!hasLangPrefPersona()) {
      return;
    }
    var chips = root.querySelectorAll('[data-lang-pref]');
    if (!chips.length) {
      return;
    }
    setLangPref(getLangPref(), false);
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        setLangPref(chip.getAttribute('data-lang-pref') || 'auto', true);
      });
    });
  }

  function greetingText() {
    if (serverWelcomeText) {
      return serverWelcomeText;
    }
    var persona = (root.getAttribute('data-persona') || '').trim();
    if (persona === 'parent') {
      return (
        'Bonjour ! Man degg Wolof ak Français. Dama la dimbali ci sa xale yi. ' +
        'Wax ma ci Wolof walla ci Français — je suis Aria, votre assistante famille.'
      );
    }
    if (persona === 'eleve') {
      return (
        'Nanga def ! Man degg Wolof ak Français. Dama la dimbali ngir nga organize sa école. ' +
        'Wax ma ci Wolof walla ci Français — Salut, je suis Aria, ton assistante.'
      );
    }
    var hour = new Date().getHours();
    var hello = hour >= 5 && hour < 18 ? 'Bonjour' : 'Bonsoir';
    var name = (root.getAttribute('data-user-name') || '').replace(/\s+/g, ' ').trim();
    var etab = (root.getAttribute('data-etablissement') || '').trim();
    var text = name ? hello + ' ' + name : hello;
    if (etab && etab.toLowerCase() !== name.toLowerCase()) {
      text += ', ' + etab;
    }
    return text + '. Comment puis-je vous aider ?';
  }

  function showWelcomeIfNeeded() {
    if (chatLog.length) {
      return;
    }
    hideEmpty();
    appendBubble('assistant', greetingText());
    if (chatLog.length) {
      chatLog[chatLog.length - 1].local = true;
      persistCache();
    }
  }

  function restoreCache() {
    var raw;
    try {
      raw = JSON.parse(sessionStorage.getItem(CACHE_KEY) || 'null');
    } catch (err) {
      return false;
    }
    if (!raw || !raw.log || !raw.log.length) {
      return false;
    }
    restoring = true;
    hideEmpty();
    chatLog = raw.log;
    raw.log.forEach(function (item) {
      if (item.kind === 'voice') {
        appendVoiceNote(item.audio || '', item.duration || 0, item.text || '', true);
      } else if (item.role === 'result') {
        renderActionResult(item, true);
      } else if (item.role === 'user' || item.role === 'assistant' || item.role === 'error') {
        appendBubble(item.role, item.text || '');
      }
    });
    restoring = false;
    scrollToEnd();
    return !!raw.open;
  }

  function goToPage(url) {
    if (!url) {
      return;
    }
    persistCache(true);
    window.location.href = url;
  }

  function applyAnnonceForm(data) {
    if (!data) {
      return;
    }
    try {
      sessionStorage.setItem(ANNONCE_DRAFT_KEY, JSON.stringify({
        titre: data.titre || '',
        contenu: data.contenu || '',
        destinataires: data.destinataires || [],
      }));
    } catch (err) {
      /* quota */
    }
    var titre = document.getElementById('titre');
    var contenu = document.getElementById('contenu');
    if (titre && data.titre) {
      titre.value = data.titre;
    }
    if (contenu && data.contenu) {
      contenu.value = data.contenu;
    }
    var dests = data.destinataires || [];
    if (dests.length && document.querySelectorAll('input[name="destinataires"]').length) {
      document.querySelectorAll('input[name="destinataires"]').forEach(function (box) {
        box.checked = dests.indexOf(box.value) !== -1 || (dests.indexOf('tous') !== -1 && box.value === 'tous');
      });
    }
  }

  function restoreAnnonceForm() {
    try {
      var draft = JSON.parse(sessionStorage.getItem(ANNONCE_DRAFT_KEY) || 'null');
      if (draft) {
        applyAnnonceForm(draft);
      }
    } catch (err) {
      /* ignore */
    }
  }

  function choiceHost() {
    var host = lastSuggestionHost || currentAssistantBubble;
    if (!host) {
      return messages;
    }
    var body = host.closest ? host.closest('.assistant-vocal-turn-body') : null;
    if (body) {
      return body;
    }
    var turn = host.closest ? host.closest('.assistant-vocal-turn') : host.parentNode;
    if (turn && turn.classList && turn.classList.contains('assistant-vocal-turn')) {
      var existing = turn.querySelector('.assistant-vocal-turn-body');
      if (existing) {
        return existing;
      }
      var col = document.createElement('div');
      col.className = 'assistant-vocal-turn-body';
      Array.from(turn.children).forEach(function (child) {
        if (!child.classList.contains('assistant-vocal-avatar')) {
          col.appendChild(child);
        }
      });
      turn.appendChild(col);
      return col;
    }
    return host;
  }

  function disableChoices(box) {
    if (!box) {
      return;
    }
    box.querySelectorAll('button, select').forEach(function (btn) {
      btn.disabled = true;
    });
    box.classList.add('is-used');
  }

  function handleChoice(item) {
    var intent = (item && item.intent) || 'chat';
    var value = (item && (item.value || item.label)) || '';
    if (busy) {
      interruptAssistant();
    }
    ignoreIncoming = false;
    unlockAudio(true);
    receivedVoiceSentence = false;
    connect();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      if (intent === 'open' && item.url) {
        goToPage(item.url);
        return;
      }
      sendQuestion(value);
      return;
    }
    appendBubble('user', (item && item.label) || value);
    currentAssistantBubble = null;
    spokenPlain = '';
    pendingDone = false;
    pendingDelta = '';
    pendingActionResult = null;
    ignoreIncoming = false;
    setBusy(true);
    showThinking();
    socket.send(
      JSON.stringify({
        type: 'choice',
        intent: intent,
        value: value,
        label: (item && item.label) || '',
        url: (item && item.url) || '',
        publier: intent === 'confirm',
      })
    );
  }

  function renderChoices(items, widget, placeholder) {
    if (!items || !items.length) {
      return;
    }
    var host = choiceHost();
    var box = document.createElement('div');
    var useSelect = widget === 'select' || (items[0] && items[0].widget === 'select');
    box.className = useSelect
      ? 'assistant-vocal-choices is-select'
      : 'assistant-vocal-choices';
    if (useSelect) {
      var select = document.createElement('select');
      select.className = 'assistant-vocal-select';
      var empty = document.createElement('option');
      empty.value = '';
      empty.textContent = placeholder || items[0].placeholder || 'Choisir';
      empty.disabled = true;
      empty.selected = true;
      select.appendChild(empty);
      items.forEach(function (item) {
        if (!item || !item.label) {
          return;
        }
        var option = document.createElement('option');
        option.value = item.value || item.label;
        option.textContent = item.label;
        option.setAttribute('data-intent', item.intent || 'fill');
        select.appendChild(option);
      });
      select.addEventListener('change', function () {
        var selected = items.filter(function (item) {
          return item && (item.value || item.label) === select.value;
        })[0];
        if (!selected) {
          return;
        }
        select.disabled = true;
        disableChoices(box);
        handleChoice(selected);
      });
      box.appendChild(select);
      host.appendChild(box);
      scrollToEnd();
      return;
    }
    items.slice(0, 5).forEach(function (item) {
      if (!item || !item.label) {
        return;
      }
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'assistant-vocal-choice';
      if (item.intent === 'confirm') {
        btn.classList.add('is-primary');
      }
      if (item.intent === 'cancel') {
        btn.classList.add('is-ghost');
      }
      btn.textContent = item.label;
      btn.addEventListener('click', function () {
        disableChoices(box);
        handleChoice(item);
      });
      box.appendChild(btn);
    });
    if (!box.children.length) {
      return;
    }
    host.appendChild(box);
    scrollToEnd();
  }

  function renderSuggestions(items) {
    renderChoices(
      (items || []).map(function (item) {
        var label = item.label || item.titre || item.nom || '';
        var url = item.url || '';
        var intent = item.intent || (url ? 'open' : 'chat');
        return {
          label: label,
          value: item.value || label,
          url: url,
          intent: intent,
        };
      })
    );
  }

  function formatVoiceTime(seconds) {
    var total = Math.max(0, Math.round(seconds || 0));
    var mins = Math.floor(total / 60);
    var secs = total % 60;
    return mins + ':' + (secs < 10 ? '0' : '') + secs;
  }

  function appendVoiceNote(src, duration, transcript, fromCache) {
    hideEmpty();
    var bubble = document.createElement('div');
    bubble.className = 'assistant-vocal-bubble is-user is-voice';
    var bars = '';
    for (var i = 0; i < 12; i += 1) {
      bars +=
        '<span style="--bar:' +
        (28 + ((i * 17) % 55)) +
        '%;--delay:' +
        (i * 0.05) +
        's"></span>';
    }
    bubble.innerHTML =
      '<button type="button" class="assistant-vocal-voice-play" aria-label="Écouter la note vocale">' +
      '<i class="fas fa-play"></i></button>' +
      '<div class="assistant-vocal-voice-meta">' +
      '<div class="assistant-vocal-voice-bars">' +
      bars +
      '</div>' +
      '<div class="assistant-vocal-voice-time">' +
      formatVoiceTime(duration) +
      '</div></div>';
    var playBtn = bubble.querySelector('.assistant-vocal-voice-play');
    var noteAudio = src ? new Audio(src) : null;
    if (!noteAudio) {
      playBtn.disabled = true;
    } else {
      playBtn.addEventListener('click', function () {
        if (noteAudio.paused) {
          document.querySelectorAll('.assistant-vocal-bubble.is-voice.is-playing').forEach(function (el) {
            el.classList.remove('is-playing');
          });
          noteAudio.currentTime = 0;
          noteAudio.play();
          bubble.classList.add('is-playing');
          playBtn.innerHTML = '<i class="fas fa-pause"></i>';
        } else {
          noteAudio.pause();
          bubble.classList.remove('is-playing');
          playBtn.innerHTML = '<i class="fas fa-play"></i>';
        }
      });
      noteAudio.onended = function () {
        bubble.classList.remove('is-playing');
        playBtn.innerHTML = '<i class="fas fa-play"></i>';
      };
    }
    messages.appendChild(bubble);
    scrollToEnd();
    if (!fromCache) {
      chatLog.push({
        role: 'user',
        kind: 'voice',
        text: transcript || '',
        duration: duration || 0,
        audio: src && String(src).indexOf('data:') === 0 ? src : '',
      });
      persistCache();
    }
    return bubble;
  }

  function markLastVoiceFailed() {
    if (!chatLog.length) {
      return;
    }
    var last = chatLog[chatLog.length - 1];
    if (last && last.kind === 'voice') {
      last.text = last.text || '';
      persistCache();
    }
  }

  function updateMuteButton() {
    if (!muteBtn) {
      return;
    }
    muteBtn.classList.toggle('is-muted', voiceMuted);
    muteBtn.setAttribute('aria-pressed', voiceMuted ? 'true' : 'false');
    muteBtn.setAttribute(
      'aria-label',
      voiceMuted ? 'Activer le son des réponses' : 'Couper le son des réponses'
    );
    muteBtn.title = voiceMuted ? 'Son coupé' : 'Couper le son';
    muteBtn.innerHTML = voiceMuted
      ? '<i class="fas fa-volume-mute"></i>'
      : '<i class="fas fa-volume-up"></i>';
  }

  function setVoiceMuted(value) {
    voiceMuted = !!value;
    try {
      localStorage.setItem(MUTE_KEY, voiceMuted ? '1' : '0');
    } catch (err) {
      /* ignore */
    }
    updateMuteButton();
    if (voiceMuted && currentAudio) {
      currentAudio.onended = null;
      currentAudio.pause();
      currentAudio = null;
      clearTypewriter();
      isPlaying = false;
      playNext();
    }
  }

  function appendBubble(role, text) {
    hideEmpty();
    var bubble = document.createElement('div');
    bubble.className = 'assistant-vocal-bubble is-' + role;
    if (role === 'assistant') {
      bubble.innerHTML = highlightData(text);
      lastSuggestionHost = bubble;
    } else {
      bubble.textContent = text;
    }
    if (role === 'assistant' || role === 'error') {
      appendAssistantTurn(bubble);
    } else {
      messages.appendChild(bubble);
      scrollToEnd();
    }
    if (!restoring) {
      chatLog.push({ role: role, text: text || '' });
      persistCache();
    }
    return bubble;
  }

  function ensureAssistantBubble() {
    hideThinking();
    if (!currentAssistantBubble) {
      currentAssistantBubble = appendBubble('assistant', '');
      spokenPlain = '';
      paintAssistant('', true);
    }
    return currentAssistantBubble;
  }

  function unlockAudio(force) {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) {
        audioContext = audioContext || new Ctx();
        if (audioContext.state === 'suspended' || force || !audioUnlocked) {
          audioContext.resume();
        }
      }
      if (!audioUnlocked || force) {
        var silent = new Audio(
          'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA'
        );
        silent.volume = 0.01;
        var playPromise = silent.play();
        if (playPromise && playPromise.catch) {
          playPromise.catch(function () { });
        }
      }
      audioUnlocked = true;
    } catch (err) {
      audioUnlocked = true;
    }
  }

  function getWebSocketUrl() {
    var scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return scheme + '//' + window.location.host + '/ws/assistant/';
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    socket = new WebSocket(getWebSocketUrl());
    socket.onopen = function () {
      refreshStatus();
      var history = historyForServer();
      if (history.length && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'restore_history', messages: history }));
      }
    };
    socket.onclose = function () {
      socket = null;
      if (root.classList.contains('is-open')) {
        setStatus('Connexion interrompue…');
        window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, 1500);
      }
    };
    socket.onerror = function () {
      setStatus('Erreur de connexion');
    };
    socket.onmessage = function (event) {
      handleServerMessage(event.data);
    };
  }

  function handleServerMessage(raw) {
    var data;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      return;
    }
    if (ignoreIncoming && data.type !== 'done' && data.type !== 'pong' && data.type !== 'error') {
      return;
    }
    if (data.type === 'assistant.welcome') {
      serverWelcomeText = (data.text || '').trim() || serverWelcomeText;
      if (root.classList.contains('is-open') && !chatLog.length) {
        showWelcomeIfNeeded();
      }
      return;
    }
    if (data.type === 'lang_pref') {
      if (data.value) {
        setLangPref(data.value, false);
      }
      return;
    }
    if (data.type === 'ack') {
      showThinking();
      return;
    }
    if (data.type === 'status') {
      if (data.phase === 'searching' || data.phase === 'speaking' || data.phase === 'working') {
        if (!currentAssistantBubble && !spokenPlain && !(thinkingTurn && thinkingTurn.parentNode)) {
          showThinking();
        }
      }
      return;
    }
    if (data.type === 'text_delta') {
      var piece = stripToolMarkup(data.text || '');
      if (piece) {
        pendingDelta += piece;
      }
      return;
    }
    if (data.type === 'audio_sentence') {
      receivedVoiceSentence = true;
      enqueueSentence(
        data.text || '',
        data.audio_base64 || '',
        data.audio_mime || 'audio/wav'
      );
      return;
    }
    if (data.type === 'error') {
      var genericFail = /n[’']ai pas pu (répondre|exécuter)/i.test(data.message || '');
      if (genericFail && (spokenPlain || receivedVoiceSentence || lastResultStamp)) {
        pendingDone = true;
        finishIfIdle();
        return;
      }
      appendBubble('error', data.message || 'Une erreur est survenue.');
      pendingDone = true;
      finishIfIdle();
      return;
    }
    if (data.type === 'done') {
      if (data.cancelled || ignoreIncoming) {
        abortLocalTurn();
        return;
      }
      pendingDone = true;
      finishIfIdle();
      return;
    }
    if (data.type === 'transcript') {
      sttBusy = false;
      var heard = (data.text || '').trim();
      if (data.stt_weak && data.fallback_message) {
        markLastVoiceFailed();
        appendBubble('assistant', data.fallback_message);
        if (heard && input) {
          input.value = heard;
        }
        setBusy(false);
        setStatus('Prête');
        pendingDone = true;
        finishIfIdle();
        return;
      }
      if (heard) {
        pendingTranscript = heard;
        sendQuestion(heard, { skipUserBubble: true });
      } else {
        markLastVoiceFailed();
        appendBubble('error', "Je n’ai pas compris la note vocale. Réessayez.");
        pendingDone = true;
        finishIfIdle();
      }
      return;
    }
    if (data.type === 'action.pending') {
      renderActionCard(data);
      return;
    }
    if (data.type === 'action.result') {
      queueActionResult(data);
      return;
    }
    if (data.type === 'action.cancelled') {
      settleActionCard('cancelled');
      return;
    }
    if (data.type === 'action.done') {
      if (!lastResultStamp) {
        queueActionResult({
          status: 'success',
          title: 'Action réalisée',
          message: data.message || 'L’action a bien été réalisée.',
          url: data.url || '',
        });
      }
      settleActionCard('done', data);
      try {
        sessionStorage.removeItem(ANNONCE_DRAFT_KEY);
      } catch (err) {
        /* ignore */
      }
      if (data.url) {
        pendingNavigate = data.url;
        persistCache(true);
        if (!isTurnHoldingResult()) {
          window.setTimeout(function () {
            if (pendingNavigate === data.url) {
              window.location.href = data.url;
            }
          }, RESULT_VISIBLE_MS);
        }
      }
      return;
    }
    if (data.type === 'navigate') {
      var nextUrl = data.url || '';
      var nextPath = nextUrl.split('?')[0];
      if (nextPath && nextPath === window.location.pathname) {
        pendingNavigate = '';
        return;
      }
      pendingNavigate = nextUrl;
      if (data.immediate && nextUrl && !isTurnHoldingResult()) {
        persistCache(true);
        window.setTimeout(function () {
          window.location.href = nextUrl;
        }, RESULT_VISIBLE_MS);
      }
      return;
    }
    if (data.type === 'suggestions') {
      renderSuggestions(data.items || []);
      return;
    }
    if (data.type === 'choices') {
      renderChoices(data.choices || [], data.widget || '', data.placeholder || '');
      return;
    }
    if (data.type === 'form.fill') {
      applyAnnonceForm(data);
    }
  }

  function renderActionCard(data) {
    hideEmpty();
    settleActionCard('cancelled');
    var card = document.createElement('div');
    card.className = 'assistant-vocal-action';
    var isAnnonce = !data.action || data.action === 'creer_publier_annonce';
    var kicker = isAnnonce
      ? 'Annonce à confirmer'
      : data.destructive
        ? 'Action destructive à confirmer'
        : 'Action à confirmer';
    var meta = '';
    if (isAnnonce) {
      var dest = data.destinataires_libelle || 'Tous';
      var statut = data.publier ? 'Publication' : 'Brouillon';
      meta = statut + ' · ' + dest;
    } else if (data.action) {
      meta = data.action.replace(/_/g, ' ');
    }
    card.innerHTML =
      '<p class="assistant-vocal-action-kicker">' +
      escapeHtml(kicker) +
      '</p>' +
      '<h3 class="assistant-vocal-action-title">' +
      escapeHtml(data.titre || 'Sans titre') +
      '</h3>' +
      '<p class="assistant-vocal-action-body">' +
      escapeHtml(data.contenu || '') +
      '</p>' +
      (meta
        ? '<p class="assistant-vocal-action-meta">' + escapeHtml(meta) + '</p>'
        : '');
    appendAssistantTurn(card);
    currentActionCard = card;
    lastSuggestionHost = card;
    if (data.choices && data.choices.length) {
      renderChoices(data.choices);
    }
  }

  function isTurnHoldingResult() {
    return busy || isPlaying || audioQueue.length > 0 || !!currentAssistantBubble || !!spokenPlain || pendingDone;
  }

  function queueActionResult(data) {
    pendingActionResult = data;
    if (isTurnHoldingResult()) {
      return;
    }
    flushPendingActionResult();
  }

  function flushPendingActionResult() {
    if (!pendingActionResult) {
      return;
    }
    var payload = pendingActionResult;
    pendingActionResult = null;
    renderActionResult(payload);
  }

  function renderActionResult(data, fromCache) {
    if (!data) {
      return;
    }
    hideThinking();
    hideEmpty();
    var status = data.status || 'success';
    if (status !== 'error' && status !== 'cancelled') {
      status = 'success';
    }
    var title = data.title || (
      status === 'error' ? 'Action échouée' : status === 'cancelled' ? 'Action annulée' : 'Action réalisée'
    );
    var message = data.message || data.text || '';
    var stamp = status + '|' + title + '|' + message;
    if (!fromCache && stamp && lastResultStamp === stamp) {
      return;
    }
    lastResultStamp = stamp;
    if (!fromCache) {
      lastResultAt = Date.now();
    }
    var box = document.createElement('div');
    box.className = 'assistant-vocal-result is-' + status;
    var icon =
      status === 'error' ? 'fa-times-circle' : status === 'cancelled' ? 'fa-ban' : 'fa-check-circle';
    box.innerHTML =
      '<p class="assistant-vocal-result-kicker"><i class="fas ' +
      icon +
      '"></i> ' +
      escapeHtml(title) +
      '</p>' +
      '<p class="assistant-vocal-result-body">' +
      escapeHtml(message) +
      '</p>';
    lastSuggestionHost = appendAssistantTurn(box);
    if (!fromCache) {
      chatLog.push({
        role: 'result',
        status: status,
        title: title,
        text: message,
      });
      persistCache(true);
    }
    scrollToEnd();
    return box;
  }

  function settleActionCard(state, data) {
    if (!currentActionCard) {
      return;
    }
    currentActionCard.classList.add(state === 'done' ? 'is-done' : 'is-cancelled');
    var buttons = currentActionCard.querySelector('.assistant-vocal-action-btns');
    if (buttons) {
      buttons.hidden = true;
    }
    if (state === 'done') {
      var note = document.createElement('p');
      note.className = 'assistant-vocal-action-success';
      note.textContent =
        (data && data.message) || 'Annonce publiée avec succès. Ouverture du détail…';
      currentActionCard.appendChild(note);
    }
    currentActionCard = null;
  }

  function sendActionDecision(type, label, extra) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    if (busy) {
      interruptAssistant();
    }
    ignoreIncoming = false;
    stopAudio();
    unlockAudio(true);
    appendBubble('user', label);
    currentAssistantBubble = null;
    spokenPlain = '';
    pendingDone = false;
    receivedVoiceSentence = false;
    pendingActionResult = null;
    setBusy(true);
    showThinking();
    var payload = { type: type };
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key];
      });
    }
    socket.send(JSON.stringify(payload));
  }

  function enqueueSentence(text, audioBase64, audioMime) {
    ensureAssistantBubble();
    var mime = audioMime || 'audio/wav';
    audioQueue.push({
      text: text,
      src: !voiceMuted && audioBase64 ? 'data:' + mime + ';base64,' + audioBase64 : '',
    });
    playNext();
  }

  function clearTypewriter() {
    if (typewriterTimer) {
      window.clearInterval(typewriterTimer);
      typewriterTimer = null;
    }
  }

  function stripToolMarkup(text) {
    return String(text || '')
      .replace(/<\|?\s*\/?\s*DSML\s*\|?>/gi, '')
      .replace(/<｜\/?DSML｜>/g, '')
      .replace(/<\/?tool_calls?>/gi, '')
      .replace(/invoke\s+name=["'][^"']+["']/gi, '')
      .replace(/\s+/g, ' ');
  }

  function textAlreadyShown(sentence) {
    var clean = stripToolMarkup(sentence).trim();
    if (!clean || !spokenPlain) {
      return false;
    }
    return spokenPlain.replace(/\s+/g, ' ').indexOf(clean.replace(/\s+/g, ' ')) !== -1;
  }

  function joinSentence(prefix, sentence) {
    if (prefix && sentence && !/\s$/.test(prefix) && !/^[.,;:!?]/.test(sentence)) {
      return prefix + ' ' + sentence;
    }
    return prefix + sentence;
  }

  function typeAlongDuration(sentence, durationMs, onComplete) {
    var prefix = spokenPlain;
    var total = joinSentence(prefix, sentence);
    var startAt = prefix ? joinSentence(prefix, '').length : 0;
    var length = Math.max(1, total.length - startAt);
    var started = Date.now();
    var minDuration = Math.max(durationMs || 0, Math.round((length / CHARS_PER_SECOND) * 1000));
    clearTypewriter();
    typewriterTimer = window.setInterval(function () {
      var elapsed = Date.now() - started;
      var progress = Math.min(1, elapsed / minDuration);
      var count = Math.max(1, Math.ceil(progress * length));
      paintAssistant(total.slice(0, startAt + count), progress < 1);
      if (progress >= 1) {
        clearTypewriter();
        spokenPlain = total;
        paintAssistant(spokenPlain, false);
        if (onComplete) {
          onComplete();
        }
      }
    }, 40);
  }

  function bindVoiceTypewriter(audio, sentence) {
    var prefix = spokenPlain;
    var total = joinSentence(prefix, sentence);
    var startAt = prefix ? joinSentence(prefix, '').length : 0;
    var length = Math.max(1, total.length - startAt);
    var startedAt = Date.now();
    var finished = false;

    var complete = function () {
      if (finished) {
        return;
      }
      finished = true;
      clearTypewriter();
      spokenPlain = total;
      paintAssistant(spokenPlain, false);
      isPlaying = false;
      currentAudio = null;
      playNext();
    };

    var reveal = function () {
      var duration = audio.duration;
      var progress;
      if (duration && isFinite(duration) && duration > 0) {
        progress = Math.min(1, audio.currentTime / duration);
      } else {
        progress = Math.min(0.92, ((Date.now() - startedAt) / 1000) * CHARS_PER_SECOND / length);
      }
      var count = Math.max(1, Math.ceil(progress * length));
      paintAssistant(total.slice(0, startAt + count), progress < 1);
    };

    audio.ontimeupdate = reveal;
    audio.onended = complete;
    reveal();
  }

  function playAudioSafely(audio, onFail) {
    unlockAudio(true);
    if (audioContext && audioContext.state === 'suspended') {
      audioContext.resume();
    }
    var failed = false;
    var failOnce = function () {
      if (failed) {
        return;
      }
      failed = true;
      if (onFail) {
        onFail();
      }
    };
    var attempt = function (left) {
      var playPromise = audio.play();
      if (playPromise && playPromise.catch) {
        playPromise.catch(function () {
          if (left > 0) {
            unlockAudio(true);
            window.setTimeout(function () {
              attempt(left - 1);
            }, 80);
            return;
          }
          failOnce();
        });
      }
    };
    attempt(2);
  }

  function playNext() {
    if (isPlaying) {
      return;
    }
    if (!audioQueue.length) {
      finishIfIdle();
      return;
    }

    isPlaying = true;
    ensureAssistantBubble();
    var item = audioQueue.shift();
    var sentence = stripToolMarkup(item.text || '');
    setStatus('Aria parle…');

    if (voiceMuted || !item.src) {
      typeAlongDuration(sentence, 0, function () {
        isPlaying = false;
        playNext();
      });
      return;
    }

    currentAudio = new Audio(item.src);
    currentAudio.preload = 'auto';
    var started = false;
    var fallbackType = function () {
      if (started) {
        return;
      }
      started = true;
      typeAlongDuration(sentence, 0, function () {
        isPlaying = false;
        currentAudio = null;
        playNext();
      });
    };
    var startSynced = function () {
      if (started || !currentAudio) {
        return;
      }
      started = true;
      bindVoiceTypewriter(currentAudio, sentence);
    };

    currentAudio.onerror = fallbackType;
    currentAudio.onplaying = startSynced;
    currentAudio.oncanplay = function () {
      if (!started && currentAudio && currentAudio.paused) {
        playAudioSafely(currentAudio, fallbackType);
      }
    };
    window.setTimeout(function () {
      if (!started && sentence) {
        paintAssistant(joinSentence(spokenPlain, sentence).slice(0, spokenPlain.length + 1), true);
      }
    }, 350);
    playAudioSafely(currentAudio, fallbackType);
  }

  function stopAudio() {
    audioQueue = [];
    clearTypewriter();
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    isPlaying = false;
  }

  function finishIfIdle() {
    if (!pendingDone || isPlaying || audioQueue.length) {
      return;
    }
    if (!spokenPlain && pendingDelta && !receivedVoiceSentence) {
      isPlaying = true;
      ensureAssistantBubble();
      var leftoverText = stripToolMarkup(pendingDelta);
      pendingDelta = '';
      typeAlongDuration(leftoverText, 0, function () {
        isPlaying = false;
        finishIfIdle();
      });
      return;
    }
    pendingDone = false;
    pendingDelta = '';
    receivedVoiceSentence = false;
    hideThinking();
    if (currentAssistantBubble && spokenPlain) {
      paintAssistant(spokenPlain, false);
      if (chatLog.length && chatLog[chatLog.length - 1].role === 'assistant') {
        chatLog[chatLog.length - 1].text = spokenPlain;
        persistCache();
      }
    }
    currentAssistantBubble = null;
    spokenPlain = '';
    setBusy(false);
    refreshStatus();
    flushPendingActionResult();
    if (pendingNavigate) {
      var nextUrl = pendingNavigate;
      pendingNavigate = null;
      persistCache(true);
      var elapsed = lastResultAt ? Date.now() - lastResultAt : RESULT_VISIBLE_MS;
      var wait = lastResultAt ? Math.max(400, RESULT_VISIBLE_MS - elapsed) : 400;
      window.setTimeout(function () {
        window.location.href = nextUrl;
      }, wait);
      return;
    }
    if (reloadAfterAction) {
      reloadAfterAction = false;
      persistCache(true);
      window.setTimeout(function () {
        window.location.reload();
      }, 700);
      return;
    }
  }

  function setBusy(value) {
    busy = value;
    syncSendButton();
  }

  function syncSendButton() {
    if (!sendBtn) {
      return;
    }
    sendBtn.disabled = false;
    if (busy) {
      sendBtn.classList.add('is-stop');
      sendBtn.setAttribute('aria-label', 'Arrêter');
      sendBtn.setAttribute('title', 'Arrêter');
      sendBtn.type = 'button';
      sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
      if (input) {
        input.removeAttribute('required');
      }
      return;
    }
    sendBtn.classList.remove('is-stop');
    sendBtn.setAttribute('aria-label', 'Envoyer');
    sendBtn.setAttribute('title', 'Envoyer');
    sendBtn.type = 'submit';
    sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
    if (input) {
      input.setAttribute('required', 'required');
    }
  }

  function abortLocalTurn() {
    ignoreIncoming = false;
    stopAudio();
    pendingDone = false;
    pendingDelta = '';
    hideThinking();
    if (currentAssistantBubble && spokenPlain) {
      paintAssistant(spokenPlain, false);
      if (chatLog.length && chatLog[chatLog.length - 1].role === 'assistant') {
        chatLog[chatLog.length - 1].text = spokenPlain;
        persistCache();
      }
    }
    currentAssistantBubble = null;
    spokenPlain = '';
    setBusy(false);
    refreshStatus();
  }

  function interruptAssistant() {
    ignoreIncoming = true;
    stopAudio();
    hideThinking();
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'stop' }));
    }
    abortLocalTurn();
    ignoreIncoming = true;
    setStatus('Arrêtée');
  }

  function refreshStatus() {
    if (busy && isPlaying) {
      setStatus('Aria parle…');
      return;
    }
    if (busy) {
      setStatus('Aria réfléchit…');
      return;
    }
    if (liveMode) {
      setStatus('Je vous écoute…');
      return;
    }
    setStatus('Prête');
  }

  function sendQuestion(text, options) {
    var question = (text || '').trim();
    var opts = options || {};
    if (!question) {
      return;
    }
    if (busy) {
      interruptAssistant();
    }
    unlockAudio(true);
    receivedVoiceSentence = false;
    connect();
    if (!socket || socket.readyState === WebSocket.CONNECTING) {
      setStatus('Connexion…');
      window.setTimeout(function () {
        sendQuestion(question, opts);
      }, 350);
      return;
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setStatus('Connexion…');
      window.setTimeout(function () {
        sendQuestion(question, opts);
      }, 350);
      return;
    }
    clearSilenceTimer();
    pendingTranscript = '';
    committedFinals = '';
    lastLiveText = '';
    pendingDelta = '';
    if (opts.skipUserBubble) {
      if (chatLog.length && chatLog[chatLog.length - 1].kind === 'voice') {
        chatLog[chatLog.length - 1].text = question;
        persistCache();
      }
    } else {
      appendBubble('user', question);
    }
    currentAssistantBubble = null;
    spokenPlain = '';
    pendingDone = false;
    pendingActionResult = null;
    ignoreIncoming = false;
    setBusy(true);
    showThinking();
    var payload = { type: 'chat', text: question };
    if (hasLangPrefPersona()) {
      payload.lang_pref = getLangPref();
    }
    socket.send(JSON.stringify(payload));
    if (input) {
      input.value = '';
    }
  }

  function attachAssistantToBody() {
    if (document.body && root.parentNode !== document.body) {
      document.body.appendChild(root);
    }
  }

  function placePanel() {
    attachAssistantToBody();
    var header = document.querySelector('.dashboard-header-horizontal');
    var nav = document.querySelector('.bottom-nav-directeur') ||
      document.querySelector('.enseignant-bottom-nav');
    var headerBottom = 72;
    if (header) {
      headerBottom = Math.max(56, Math.round(header.getBoundingClientRect().bottom));
    }
    var bottomGap = NAV_FALLBACK;
    if (nav) {
      var navBox = nav.getBoundingClientRect();
      var navHeight = Math.round(navBox.height || nav.offsetHeight || 0);
      var fromBottom = Math.round(window.innerHeight - navBox.top);
      var navInView = navHeight > 8 && navBox.top >= 0 && navBox.top < window.innerHeight;
      if (navInView) {
        bottomGap = Math.max(NAV_FALLBACK, navHeight + 20, fromBottom);
      } else if (navHeight > 8) {
        bottomGap = Math.max(NAV_FALLBACK, navHeight + 24);
      }
    }
    var margin = 12;
    root.style.setProperty('--assistant-offset-top', headerBottom + 'px');
    root.style.setProperty('--assistant-offset-bottom', bottomGap + 'px');
    if (panel) {
      panel.style.top = headerBottom + margin + 'px';
      panel.style.bottom = bottomGap + margin + 'px';
      panel.style.height = 'auto';
      panel.style.maxHeight = 'none';
    }
  }

  function openPanel() {
    root.classList.add('is-open');
    fab.classList.add('is-open');
    fab.setAttribute('aria-expanded', 'true');
    panel.setAttribute('aria-hidden', 'false');
    placePanel();
    showWelcomeIfNeeded();
    persistCache();
    unlockAudio(true);
    connect();
    scrollToEnd();
    window.setTimeout(scrollToEnd, 80);
    window.setTimeout(scrollToEnd, 280);
    if (input) {
      input.focus();
    }
  }

  function closePanel() {
    root.classList.remove('is-open');
    fab.classList.remove('is-open');
    fab.setAttribute('aria-expanded', 'false');
    panel.setAttribute('aria-hidden', 'true');
    stopLiveMode();
    stopAudio();
    persistCache();
    if (fab) {
      fab.focus();
    }
  }

  function togglePanel() {
    if (root.classList.contains('is-open')) {
      closePanel();
    } else {
      openPanel();
    }
  }

  function hasSpokenWords(text) {
    return /[a-zàâäéèêëïîôùûüç]/i.test(String(text || ''));
  }

  function setMeter(level) {
    if (!liveBox) {
      return;
    }
    liveBox.style.setProperty('--voice-level', String(Math.min(1, level * 8)));
  }

  function updateVoiceTimer() {
    if (!voiceTimerEl) {
      return;
    }
    var elapsed = voiceStartedMs ? (Date.now() - voiceStartedMs) / 1000 : 0;
    voiceTimerEl.textContent = formatVoiceTime(elapsed);
    if (elapsed >= MAX_VOICE_SEC && liveMode) {
      finishVoiceNote(true);
    }
  }

  function startVoiceTimer() {
    window.clearInterval(voiceTimer);
    voiceStartedMs = Date.now();
    updateVoiceTimer();
    voiceTimer = window.setInterval(updateVoiceTimer, 250);
  }

  function stopVoiceTimer() {
    window.clearInterval(voiceTimer);
    voiceTimer = null;
  }

  function pickRecorderMime() {
    if (!window.MediaRecorder) {
      return '';
    }
    var types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    for (var i = 0; i < types.length; i += 1) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(types[i])) {
        return types[i];
      }
    }
    return '';
  }

  function updateMicVisual() {
    root.classList.toggle('is-live', liveMode);
    if (liveBox) {
      liveBox.hidden = !liveMode;
    }
    if (liveMode) {
      micBtn.classList.add('is-listening');
      micBtn.setAttribute('aria-pressed', 'true');
      micBtn.setAttribute('aria-label', 'Envoyer la note vocale');
      micBtn.title = 'Envoyer la note vocale';
      micBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
      if (micCancelBtn) {
        micCancelBtn.hidden = false;
      }
    } else {
      micBtn.classList.remove('is-listening');
      micBtn.setAttribute('aria-pressed', 'false');
      micBtn.setAttribute('aria-label', 'Note vocale');
      micBtn.title = 'Note vocale';
      micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
      if (micCancelBtn) {
        micCancelBtn.hidden = true;
      }
      setMeter(0);
    }
  }

  function clearSilenceTimer() {
    window.clearTimeout(silenceTimer);
    silenceTimer = null;
  }

  function downsampleTo16k(float32, inputRate) {
    if (!float32 || !float32.length) {
      return new Int16Array(0);
    }
    var ratio = inputRate / TARGET_RATE;
    var newLen = Math.max(1, Math.round(float32.length / ratio));
    var pcm = new Int16Array(newLen);
    var offset = 0;
    for (var i = 0; i < newLen; i += 1) {
      var next = Math.min(float32.length, Math.round((i + 1) * ratio));
      var sum = 0;
      var count = 0;
      for (var j = offset; j < next; j += 1) {
        sum += float32[j];
        count += 1;
      }
      offset = next;
      var sample = count ? sum / count : 0;
      sample = Math.max(-1, Math.min(1, sample));
      pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm;
  }

  function encodeWav(pcm) {
    var buffer = new ArrayBuffer(44 + pcm.length * 2);
    var view = new DataView(buffer);
    var writeString = function (offset, value) {
      for (var i = 0; i < value.length; i += 1) {
        view.setUint8(offset + i, value.charCodeAt(i));
      }
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + pcm.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, TARGET_RATE, true);
    view.setUint32(28, TARGET_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, pcm.length * 2, true);
    var idx = 44;
    for (var i = 0; i < pcm.length; i += 1) {
      view.setInt16(idx, pcm[i], true);
      idx += 2;
    }
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var b = 0; b < bytes.length; b += 1) {
      binary += String.fromCharCode(bytes[b]);
    }
    return window.btoa(binary);
  }

  function flushPcmToStt() {
    if (sttBusy || busy || !pcmChunks.length) {
      pcmChunks = [];
      return false;
    }
    var length = 0;
    pcmChunks.forEach(function (chunk) {
      length += chunk.length;
    });
    if (length < TARGET_RATE * 0.28) {
      pcmChunks = [];
      return false;
    }
    var merged = new Float32Array(length);
    var offset = 0;
    pcmChunks.forEach(function (chunk) {
      merged.set(chunk, offset);
      offset += chunk.length;
    });
    pcmChunks = [];
    var rate = (captureCtx && captureCtx.sampleRate) || 44100;
    var wav = encodeWav(downsampleTo16k(merged, rate));
    var sendWav = function () {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }
      sttBusy = true;
      setStatus('Je transcris…');
      var sttPayload = { type: 'stt', audio_base64: wav };
      if (hasLangPrefPersona()) {
        sttPayload.lang_pref = getLangPref();
      }
      socket.send(JSON.stringify(sttPayload));
    };
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      connect();
      window.setTimeout(sendWav, 350);
      return true;
    }
    sendWav();
    return true;
  }

  function speechThreshold() {
    return Math.max(SPEAK_RMS, noiseFloor * 3.4);
  }

  function handleVoiceLevel(rms, frame) {
    if (!liveMode || busy) {
      return;
    }
    setMeter(rms);
    pcmChunks.push(frame);
    var now = Date.now();
    if (rms >= speechThreshold()) {
      if (!isVoicing) {
        isVoicing = true;
        voiceStartedAt = now;
      }
      lastVoiceAt = now;
    } else {
      noiseFloor = noiseFloor * 0.96 + rms * 0.04;
    }
  }

  function stopMicCapture(keepPcm) {
    if (captureProcessor) {
      captureProcessor.onaudioprocess = null;
      try {
        captureProcessor.disconnect();
      } catch (err) {
        /* ignore */
      }
    }
    if (captureSource) {
      try {
        captureSource.disconnect();
      } catch (err) {
        /* ignore */
      }
    }
    if (captureMute) {
      try {
        captureMute.disconnect();
      } catch (err) {
        /* ignore */
      }
    }
    captureProcessor = null;
    captureSource = null;
    captureMute = null;
    if (liveStream) {
      liveStream.getTracks().forEach(function (track) {
        track.stop();
      });
      liveStream = null;
    }
    if (!keepPcm) {
      pcmChunks = [];
    }
    isVoicing = false;
  }

  function startMicCapture(stream) {
    liveStream = stream;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      return;
    }
    captureCtx = captureCtx || new Ctx();
    if (captureCtx.state === 'suspended') {
      captureCtx.resume();
    }
    captureSource = captureCtx.createMediaStreamSource(stream);
    captureProcessor = captureCtx.createScriptProcessor(4096, 1, 1);
    captureMute = captureCtx.createGain();
    captureMute.gain.value = 0;
    captureProcessor.onaudioprocess = function (event) {
      var inputData = event.inputBuffer.getChannelData(0);
      var copy = new Float32Array(inputData.length);
      copy.set(inputData);
      var sum = 0;
      for (var i = 0; i < copy.length; i += 1) {
        sum += copy[i] * copy[i];
      }
      handleVoiceLevel(Math.sqrt(sum / copy.length), copy);
    };
    captureSource.connect(captureProcessor);
    captureProcessor.connect(captureMute);
    captureMute.connect(captureCtx.destination);
  }

  function hideConfirmCancel() {
    if (confirmBox) {
      confirmBox.hidden = true;
    }
  }

  function showConfirmCancel() {
    if (confirmBox) {
      confirmBox.hidden = false;
    }
  }

  function resetVoiceState() {
    recordedChunks = [];
    recordedMime = '';
    voiceNoteUrl = '';
    voiceSendAfterStop = false;
    pendingTranscript = '';
    committedFinals = '';
    lastLiveText = '';
    stopVoiceTimer();
    voiceStartedMs = 0;
  }

  function stopRecorder() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try {
        mediaRecorder.stop();
      } catch (err) {
        /* ignore */
      }
    }
    mediaRecorder = null;
  }

  function stopRecording(clearAll) {
    liveMode = false;
    voiceSendAfterStop = false;
    stopRecorder();
    stopMicCapture(!clearAll);
    stopVoiceTimer();
    if (clearAll) {
      resetVoiceState();
      if (input) {
        input.value = '';
      }
    }
    updateMicVisual();
    hideConfirmCancel();
  }

  function stopLiveMode() {
    stopRecording(true);
  }

  function publishVoiceNote(blob) {
    var duration = voiceStartedMs ? (Date.now() - voiceStartedMs) / 1000 : 0;
    var url = blob ? URL.createObjectURL(blob) : '';
    appendVoiceNote(url, duration, '', false);
    if (blob && blob.size < 450000 && chatLog.length && chatLog[chatLog.length - 1].kind === 'voice') {
      var reader = new FileReader();
      reader.onloadend = function () {
        if (chatLog.length && chatLog[chatLog.length - 1].kind === 'voice') {
          chatLog[chatLog.length - 1].audio = reader.result || '';
          persistCache();
        }
      };
      reader.readAsDataURL(blob);
    }
    connect();
    if (!flushPcmToStt()) {
      markLastVoiceFailed();
      appendBubble('error', "La note vocale est trop courte. Réessayez.");
    }
  }

  function finishVoiceNote(shouldSend) {
    if (!liveMode) {
      return;
    }
    voiceSendAfterStop = !!shouldSend;
    liveMode = false;
    stopVoiceTimer();
    updateMicVisual();
    hideConfirmCancel();
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try {
        mediaRecorder.requestData();
        mediaRecorder.stop();
      } catch (err) {
        stopMicCapture(shouldSend);
        if (shouldSend) {
          publishVoiceNote(null);
        } else {
          pcmChunks = [];
        }
      }
      return;
    }
    stopMicCapture(shouldSend);
    if (shouldSend) {
      publishVoiceNote(null);
    } else {
      pcmChunks = [];
    }
  }

  function startLiveMode() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      appendBubble('error', 'Micro indisponible. Utilisez le clavier.');
      return;
    }
    liveMode = true;
    resetVoiceState();
    noiseFloor = 0.012;
    updateMicVisual();
    setStatus('Note vocale…');
    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      .then(function (stream) {
        if (!liveMode) {
          stream.getTracks().forEach(function (track) {
            track.stop();
          });
          return;
        }
        recordedChunks = [];
        recordedMime = pickRecorderMime();
        if (window.MediaRecorder) {
          mediaRecorder = recordedMime
            ? new MediaRecorder(stream, { mimeType: recordedMime })
            : new MediaRecorder(stream);
          recordedMime = mediaRecorder.mimeType || recordedMime;
          mediaRecorder.ondataavailable = function (event) {
            if (event.data && event.data.size) {
              recordedChunks.push(event.data);
            }
          };
          mediaRecorder.onstop = function () {
            var sendIt = voiceSendAfterStop;
            var chunks = recordedChunks.slice();
            var mime = recordedMime || 'audio/webm';
            stopMicCapture(sendIt);
            mediaRecorder = null;
            if (!sendIt) {
              pcmChunks = [];
              resetVoiceState();
              return;
            }
            var blob = chunks.length ? new Blob(chunks, { type: mime }) : null;
            publishVoiceNote(blob);
            resetVoiceState();
          };
          mediaRecorder.start(200);
        }
        startMicCapture(stream);
        startVoiceTimer();
      })
      .catch(function () {
        liveMode = false;
        updateMicVisual();
        appendBubble('error', 'Autorisez le micro du navigateur pour envoyer une note vocale.');
      });
  }

  fab.addEventListener('click', togglePanel);
  closeBtn.addEventListener('click', closePanel);

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    if (busy && !(input && input.value.trim())) {
      interruptAssistant();
      return;
    }
    sendQuestion(input.value);
  });

  if (sendBtn) {
    sendBtn.addEventListener('click', function (event) {
      if (!busy) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      if (input && input.value.trim()) {
        sendQuestion(input.value);
        return;
      }
      interruptAssistant();
    });
  }

  micBtn.addEventListener('click', function () {
    if (micBtn.disabled) {
      return;
    }
    unlockAudio(true);
    connect();
    if (liveMode) {
      finishVoiceNote(true);
      return;
    }
    startLiveMode();
  });

  if (micCancelBtn) {
    micCancelBtn.addEventListener('click', function () {
      if (!liveMode) {
        return;
      }
      showConfirmCancel();
    });
  }
  if (confirmYes) {
    confirmYes.addEventListener('click', function () {
      finishVoiceNote(false);
      stopRecording(true);
    });
  }
  if (confirmNo) {
    confirmNo.addEventListener('click', function () {
      hideConfirmCancel();
    });
  }

  function bindPanelWatchers() {
    if (panelWatchersBound) {
      return;
    }
    panelWatchersBound = true;
    window.addEventListener('resize', function () {
      if (root.classList.contains('is-open')) {
        placePanel();
      }
    });
    window.addEventListener(
      'scroll',
      function () {
        if (root.classList.contains('is-open')) {
          placePanel();
        }
      },
      true
    );
    if (!window.ResizeObserver) {
      return;
    }
    var observer = new ResizeObserver(function () {
      if (root.classList.contains('is-open')) {
        placePanel();
      }
    });
    var header = document.querySelector('.dashboard-header-horizontal');
    var nav =
      document.querySelector('.bottom-nav-directeur') ||
      document.querySelector('.enseignant-bottom-nav');
    if (header) {
      observer.observe(header);
    }
    if (nav) {
      observer.observe(nav);
    }
  }

  function bootAssistant() {
    if (booted) {
      return;
    }
    if (!document.body) {
      document.addEventListener('DOMContentLoaded', bootAssistant);
      return;
    }
    booted = true;
    try {
      voiceMuted = localStorage.getItem(MUTE_KEY) === '1';
    } catch (err) {
      voiceMuted = false;
    }
    updateMuteButton();
    if (muteBtn) {
      muteBtn.addEventListener('click', function () {
        setVoiceMuted(!voiceMuted);
      });
    }
    attachAssistantToBody();
    bindPanelWatchers();
    bindLangPrefChips();
    restoreAnnonceForm();
    if (restoreCache()) {
      openPanel();
    }
    [60, 250, 600, 1200].forEach(function (delay) {
      window.setTimeout(function () {
        if (root.classList.contains('is-open')) {
          placePanel();
          scrollToEnd();
        }
      }, delay);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootAssistant);
  } else {
    bootAssistant();
  }
  window.addEventListener('load', function () {
    attachAssistantToBody();
    bindPanelWatchers();
    syncSendButton();
    if (root.classList.contains('is-open')) {
      placePanel();
    }
  });
})();
