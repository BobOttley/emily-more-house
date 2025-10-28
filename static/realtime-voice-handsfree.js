// /static/realtime-voice-handsfree.js
(function () {
  // DOM
  const chatbox   = document.getElementById('penai-chatbox');
  const toggleBtn = document.getElementById('penai-toggle');

  const consent   = document.getElementById('voiceConsent');
  const agree     = document.getElementById('agreeVoice');
  const startBtn  = document.getElementById('startVoice');
  const cancelBtn = document.getElementById('cancelVoice');

  const headerLangSel = document.getElementById('language-selector');
  const consentLangSel= document.getElementById('vc-lang');

  const startHeaderBtn= document.getElementById('start-button');
  const pauseBtn      = document.getElementById('pause-button');
  const endBtn        = document.getElementById('end-button');
  const aiAudio       = document.getElementById('aiAudio');
  const indicator     = document.getElementById('voiceIndicator');

  // State
  let pc = null;           // RTCPeerConnection
  let dc = null;           // DataChannel
  let micStream = null;    // MediaStream
  let started = false;
  let isPaused = false;
  let sessionId = null;
  let familyId = null;
  let currentLang = headerLangSel?.value || 'en';

  // === Fallback watchdog ===
  let fallbackTimer = null;
  const FALLBACK_TIMEOUT_MS = 3000; // 3s

  function resetFallbackTimer() {
    if (fallbackTimer) clearTimeout(fallbackTimer);
    fallbackTimer = setTimeout(() => {
      console.warn("âš ï¸ No response from Emily, sending fallback.");
      playFallbackMessage("Sorry, I didnâ€™t catch that â€” could you repeat the question?");
    }, FALLBACK_TIMEOUT_MS);
  }

  function cancelFallbackTimer() {
    if (fallbackTimer) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
  }

  function playFallbackMessage(msg) {
    // Show in chat (if you have addMessage helper)
    if (typeof addMessage === "function") addMessage("PEN.ai", msg);

    // Speak it (force TTS via response.create)
    sendEvent({
      type: 'response.create',
      response: { instructions: msg }
    });
  }

  // Language â†’ Voice
  const voiceByLang = {
    en: 'shimmer', fr: 'alloy', es: 'verse',
    de: 'luna', zh: 'alloy', ar: 'luna',
    it: 'verse', ru: 'alloy'
  };

  // Localisation for consent
  const i18n = {
    en: { title:'Enable Emily (voice)', desc:'To chat by voice, we need one-time permission to use your microphone and play audio responses.', agree:'I agree to voice processing for this session.', cancel:'Not now', start:'Start conversation' },
    fr: { title:'Activer Emily (voix)', desc:'Pour discuter Ã  la voix, nous avons besoin dâ€™une autorisation unique pour utiliser votre microphone et lire les rÃ©ponses audio.', agree:'Jâ€™accepte le traitement vocal pour cette session.', cancel:'Pas maintenant', start:'Commencer la conversation' },
    es: { title:'Activar Emily (voz)', desc:'Para hablar por voz, necesitamos permiso Ãºnico para usar tu micrÃ³fono y reproducir respuestas de audio.', agree:'Acepto el procesamiento de voz para esta sesiÃ³n.', cancel:'Ahora no', start:'Iniciar conversaciÃ³n' },
    de: { title:'Emily (Sprache) aktivieren', desc:'FÃ¼r die Sprachfunktion benÃ¶tigen wir einmalige Berechtigung fÃ¼r Ihr Mikrofon und die Audiowiedergabe.', agree:'Ich stimme der Sprachverarbeitung fÃ¼r diese Sitzung zu.', cancel:'Nicht jetzt', start:'Konversation starten' },
    zh: { title:'å¯ç”¨ Emilyï¼ˆè¯­éŸ³ï¼‰', desc:'è¦è¿›è¡Œè¯­éŸ³èŠå¤©ï¼Œæˆ‘ä»¬éœ€è¦ä¸€æ¬¡æ€§æŽˆæƒä½¿ç”¨æ‚¨çš„éº¦å…‹é£Žå¹¶æ’­æ”¾éŸ³é¢‘å›žå¤ã€‚', agree:'æˆ‘åŒæ„åœ¨æœ¬æ¬¡ä¼šè¯ä¸­è¿›è¡Œè¯­éŸ³å¤„ç†ã€‚', cancel:'æš‚ä¸', start:'å¼€å§‹å¯¹è¯' },
    ar: { title:'ØªÙØ¹ÙŠÙ„ Ø¥Ù…ÙŠÙ„ÙŠ (ØµÙˆØª)', desc:'Ù„Ù„Ø¯Ø±Ø¯Ø´Ø© Ø¨Ø§Ù„ØµÙˆØªØŒ Ù†Ø­ØªØ§Ø¬ Ø¥Ù„Ù‰ Ø¥Ø°Ù† Ù„Ù…Ø±Ø© ÙˆØ§Ø­Ø¯Ø© Ù„Ø§Ø³ØªØ®Ø¯Ø§Ù… Ø§Ù„Ù…ÙŠÙƒØ±ÙˆÙÙˆÙ† ÙˆØªØ´ØºÙŠÙ„ Ø§Ù„Ø±Ø¯ÙˆØ¯ Ø§Ù„ØµÙˆØªÙŠØ©.', agree:'Ø£ÙˆØ§ÙÙ‚ Ø¹Ù„Ù‰ Ù…Ø¹Ø§Ù„Ø¬Ø© Ø§Ù„ØµÙˆØª Ù„Ù‡Ø°Ù‡ Ø§Ù„Ø¬Ù„Ø³Ø©.', cancel:'Ù„ÙŠØ³ Ø§Ù„Ø¢Ù†', start:'Ø¨Ø¯Ø¡ Ø§Ù„Ù…Ø­Ø§Ø¯Ø«Ø©' },
    it: { title:'Abilita Emily (voce)', desc:'Per parlare con la voce, serve unâ€™autorizzazione una tantum per usare il microfono e riprodurre risposte audio.', agree:'Accetto lâ€™elaborazione vocale per questa sessione.', cancel:'Non ora', start:'Avvia conversazione' },
    ru: { title:'Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Emily (Ð³Ð¾Ð»Ð¾Ñ)', desc:'Ð§Ñ‚Ð¾Ð±Ñ‹ Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ Ð³Ð¾Ð»Ð¾ÑÐ¾Ð¼, Ð½Ð°Ð¼ Ð½ÑƒÐ¶Ð½Ð¾ Ñ€Ð°Ð·Ð¾Ð²Ð¾Ðµ Ñ€Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð¸Ðµ Ð½Ð° Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð²Ð°ÑˆÐµÐ³Ð¾ Ð¼Ð¸ÐºÑ€Ð¾Ñ„Ð¾Ð½Ð° Ð¸ Ð²Ð¾ÑÐ¿Ñ€Ð¾Ð¸Ð·Ð²ÐµÐ´ÐµÐ½Ð¸Ðµ Ð°ÑƒÐ´Ð¸Ð¾Ð¾Ñ‚Ð²ÐµÑ‚Ð¾Ð².', agree:'Ð¯ ÑÐ¾Ð³Ð»Ð°ÑÐµÐ½ Ð½Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÑƒ Ð³Ð¾Ð»Ð¾ÑÐ° Ð² ÑÑ‚Ð¾Ð¼ ÑÐµÐ°Ð½ÑÐµ.', cancel:'ÐÐµ ÑÐµÐ¹Ñ‡Ð°Ñ', start:'ÐÐ°Ñ‡Ð°Ñ‚ÑŒ Ñ€Ð°Ð·Ð³Ð¾Ð²Ð¾Ñ€' }
  };

  // Localise consent UI
  const vcTitle = document.getElementById('vc-title');
  const vcDesc  = document.getElementById('vc-desc');
  const vcAgree = document.getElementById('vc-agree');

  function applyConsentLocale(lang) {
    const t = i18n[lang] || i18n.en;
    vcTitle.textContent = t.title;
    vcDesc.textContent  = t.desc;
    vcAgree.textContent = t.agree;
    cancelBtn.textContent = t.cancel;
    startBtn.textContent  = t.start;
  }

  function syncLanguage(lang) {
    currentLang = lang;
    if (headerLangSel && headerLangSel.value !== lang) headerLangSel.value = lang;
    if (consentLangSel && consentLangSel.value !== lang) consentLangSel.value = lang;
    applyConsentLocale(lang);
  }

  headerLangSel?.addEventListener('change', e => syncLanguage(e.target.value));
  consentLangSel?.addEventListener('change', e => syncLanguage(e.target.value));

  // Status indicator
  function showIndicator(stateText) {
    if (!indicator) return;
    indicator.textContent = stateText || 'Ready';
    indicator.classList.remove('hidden');
  }
  function hideIndicator() { indicator?.classList.add('hidden'); }

  function updateUIForStart() {
    started = true; isPaused = false;
    startHeaderBtn?.classList.add('hidden');
    pauseBtn?.classList.remove('hidden');
    endBtn?.classList.remove('hidden');
    if (pauseBtn) pauseBtn.textContent = 'Pause';
  }

  function updateUIForEnd() {
    started = false; isPaused = false;
    startHeaderBtn?.classList.remove('hidden');
    pauseBtn?.classList.add('hidden');
    endBtn?.classList.add('hidden');
    showIndicator('Ready');
  }

  function maybeShowConsent() {
    if (started) return;
    if (consent) {
      syncLanguage(currentLang);
      consent.style.display = 'flex';
    }
  }

  const observer = new MutationObserver(() => {
    if (chatbox?.classList.contains('open')) maybeShowConsent();
  });
  if (chatbox) observer.observe(chatbox, { attributes:true, attributeFilter:['class'] });

  toggleBtn?.addEventListener('click', () => {
    setTimeout(() => {
      if (chatbox?.classList.contains('open')) maybeShowConsent();
    }, 50);
  });

  // Consent interactions
  agree?.addEventListener('change', () => { startBtn.disabled = !agree.checked; });
  cancelBtn?.addEventListener('click', () => { consent.style.display = 'none'; });

  startHeaderBtn?.addEventListener('click', () => {
    if (!chatbox?.classList.contains('open')) chatbox.classList.add('open');
    if (consent) {
      agree.checked = false;
      startBtn.disabled = true;
      syncLanguage(currentLang);
      consent.style.display = 'flex';
    }
  });

  startBtn?.addEventListener('click', async () => {
    startBtn.disabled = true;
    showIndicator('Connectingâ€¦');
    try {
      await startVoiceSession();
      consent.style.display = 'none';
      updateUIForStart();
      showIndicator('Listeningâ€¦');
    } catch (err) {
      console.error('Voice start error:', err);
      startBtn.disabled = false;
      showIndicator('Error');
      alert('Could not start voice. Please check mic permissions and try again.');
    }
  });

  pauseBtn?.addEventListener('click', () => {
    if (!micStream) return;
    const track = micStream.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    isPaused = !track.enabled;
    pauseBtn.textContent = isPaused ? 'Resume' : 'Pause';
    showIndicator(isPaused ? 'Paused' : 'Listeningâ€¦');
  });

  endBtn?.addEventListener('click', () => {
    teardownSession();
    updateUIForEnd();
  });

  document.addEventListener('visibilitychange', () => {
    if (!micStream) return;
    const enable = document.visibilityState === 'visible';
    micStream.getAudioTracks().forEach(t => t.enabled = enable && !isPaused);
  });
  window.addEventListener('beforeunload', teardownSession);

  // === Voice session ===
  async function startVoiceSession() {
    const sessRes = await fetch('/realtime/session', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        model: 'gpt-4o-realtime-preview',
        voice: voiceByLang[currentLang] || 'shimmer',
        language: currentLang
      })
    });
    if (!sessRes.ok) throw new Error('Failed to create realtime session: ' + (await sessRes.text().catch(()=>'')));
    const sess = await sessRes.json();
    sessionId = sess.session_id;

    const token =
      sess.token ||
      (sess.session && sess.session.client_secret && (sess.session.client_secret.value || sess.session.client_secret)) ||
      (sess.client_secret && (sess.client_secret.value || sess.client_secret)) ||
      sess.value;
    if (!token) throw new Error('No ephemeral token returned');

    pc = new RTCPeerConnection();

    pc.ontrack = (e) => {
      if (aiAudio) {
        aiAudio.srcObject = e.streams[0];
        aiAudio.play().catch(()=>{});
      }
      cancelFallbackTimer(); // got audio, cancel watchdog
    };

    dc = pc.createDataChannel('oai-events');
    dc.onopen = () => {
      sendEvent({
        type: 'response.create',
        response: {
          instructions: `Please greet the user in their selected language (${currentLang}). Keep replies concise and helpful, and continue in this language unless they ask to switch.`
        }
      });
      resetFallbackTimer(); // start watchdog after greeting request
    };
    dc.onmessage = onEventMessage;

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation:true, noiseSuppression:true, autoGainControl:true },
      video: false
    });
    micStream.getTracks().forEach(t => pc.addTrack(t, micStream));

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpRes = await fetch('https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/sdp'
      },
      body: offer.sdp
    });
    if (!sdpRes.ok) throw new Error('Realtime SDP error: ' + (await sdpRes.text().catch(()=>'')));

    const answer = { type:'answer', sdp: await sdpRes.text() };
    await pc.setRemoteDescription(answer);
  }

  function sendEvent(obj){
    if (dc && dc.readyState === 'open') {
      dc.send(JSON.stringify(obj));
    }
  }

  function onEventMessage(evt){
    let msg; try{ msg = JSON.parse(evt.data); } catch { return; }
    console.log("📥 Voice event:", msg.type);
    switch (msg.type) {
      case 'input_audio_buffer.speech_started':
        showIndicator('Listeningâ€¦'); break;
      case 'input_audio_buffer.speech_stopped':
        showIndicator('Thinkingâ€¦');
        resetFallbackTimer(); // user finished â†’ wait for reply
        break;
      case 'response.audio.started':
        showIndicator('Speakingâ€¦');
        cancelFallbackTimer(); // reply began
        break;
      case 'response.audio.done':
        showIndicator('Listeningâ€¦');
        cancelFallbackTimer(); // reply finished
        break;

      // Handle function calls
      case 'response.function_call_arguments.done':
        // Emily called a tool - execute it
        handleToolCall(msg);
        break;

      default: break;
    }
  }


  async function handleToolCall(msg) {
    const callId = msg.call_id;
    const functionName = msg.name;
    let args = {};

    try {
      args = JSON.parse(msg.arguments);
    } catch (e) {
      console.error('Failed to parse tool arguments:', e);
    }

    console.log(`🔧 Tool called: ${functionName}`, args);

    let result = null;
    let error = null;

    try {
      if (functionName === 'send_enquiry_email') {
        showIndicator('Sending email…');

        const response = await fetch('/realtime/tool/send_enquiry_email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            parent_name: args.parent_name,
            parent_email: args.parent_email,
            parent_phone: args.parent_phone,
            message: args.message
          })
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        result = data;
        console.log('✅ Email sent');

      } else if (functionName === 'get_open_days') {
        const response = await fetch('/realtime/tool/get_open_days', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        result = await response.json();
        console.log('✅ Open days fetched');

      } else if (functionName === 'kb_search') {
        const response = await fetch('/realtime/tool/kb_search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: args.query })
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        result = await response.json();
        console.log('✅ KB search completed');

      } else {
        error = `Unknown tool: ${functionName}`;
      }

    } catch (e) {
      console.error(`Tool execution error:`, e);
      error = e.message;
    }

    // Send the result back to Emily
    sendEvent({
      type: 'conversation.item.create',
      item: {
        type: 'function_call_output',
        call_id: callId,
        output: error ? JSON.stringify({ error }) : JSON.stringify(result)
      }
    });

    // Tell Emily to generate a response with the tool result
    sendEvent({
      type: 'response.create'
    });
  }
  function teardownSession() {
    try { micStream?.getTracks().forEach(t => t.stop()); } catch {}
    try { pc?.close(); } catch {}
    micStream = null; pc = null; dc = null; sessionId = null;
    cancelFallbackTimer();
  }

  const urlParams = new URLSearchParams(window.location.search);
  familyId = urlParams.get('family_id') || urlParams.get('id') || null;

  syncLanguage(currentLang);
})();