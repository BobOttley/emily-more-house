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
      console.warn("⚠️ No response from Emily, sending fallback.");
      playFallbackMessage("Sorry, I didn’t catch that — could you repeat the question?");
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

  // Language → Voice
  const voiceByLang = {
    en: 'shimmer', fr: 'alloy', es: 'verse',
    de: 'luna', zh: 'alloy', ar: 'luna',
    it: 'verse', ru: 'alloy'
  };

  // Localisation for consent
  const i18n = {
    en: { title:'Enable Emily (voice)', desc:'To chat by voice, we need one-time permission to use your microphone and play audio responses.', agree:'I agree to voice processing for this session.', cancel:'Not now', start:'Start conversation' },
    fr: { title:'Activer Emily (voix)', desc:'Pour discuter à la voix, nous avons besoin d’une autorisation unique pour utiliser votre microphone et lire les réponses audio.', agree:'J’accepte le traitement vocal pour cette session.', cancel:'Pas maintenant', start:'Commencer la conversation' },
    es: { title:'Activar Emily (voz)', desc:'Para hablar por voz, necesitamos permiso único para usar tu micrófono y reproducir respuestas de audio.', agree:'Acepto el procesamiento de voz para esta sesión.', cancel:'Ahora no', start:'Iniciar conversación' },
    de: { title:'Emily (Sprache) aktivieren', desc:'Für die Sprachfunktion benötigen wir einmalige Berechtigung für Ihr Mikrofon und die Audiowiedergabe.', agree:'Ich stimme der Sprachverarbeitung für diese Sitzung zu.', cancel:'Nicht jetzt', start:'Konversation starten' },
    zh: { title:'启用 Emily（语音）', desc:'要进行语音聊天，我们需要一次性授权使用您的麦克风并播放音频回复。', agree:'我同意在本次会话中进行语音处理。', cancel:'暂不', start:'开始对话' },
    ar: { title:'تفعيل إميلي (صوت)', desc:'للدردشة بالصوت، نحتاج إلى إذن لمرة واحدة لاستخدام الميكروفون وتشغيل الردود الصوتية.', agree:'أوافق على معالجة الصوت لهذه الجلسة.', cancel:'ليس الآن', start:'بدء المحادثة' },
    it: { title:'Abilita Emily (voce)', desc:'Per parlare con la voce, serve un’autorizzazione una tantum per usare il microfono e riprodurre risposte audio.', agree:'Accetto l’elaborazione vocale per questa sessione.', cancel:'Non ora', start:'Avvia conversazione' },
    ru: { title:'Включить Emily (голос)', desc:'Чтобы общаться голосом, нам нужно разовое разрешение на использование вашего микрофона и воспроизведение аудиоответов.', agree:'Я согласен на обработку голоса в этом сеансе.', cancel:'Не сейчас', start:'Начать разговор' }
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
    showIndicator('Connecting…');
    try {
      await startVoiceSession();
      consent.style.display = 'none';
      updateUIForStart();
      showIndicator('Listening…');
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
    showIndicator(isPaused ? 'Paused' : 'Listening…');
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
    switch (msg.type) {
      case 'input_audio_buffer.speech_started':
        showIndicator('Listening…'); break;
      case 'input_audio_buffer.speech_stopped':
        showIndicator('Thinking…');
        resetFallbackTimer(); // user finished → wait for reply
        break;
      case 'response.audio.started':
        showIndicator('Speaking…');
        cancelFallbackTimer(); // reply began
        break;
      case 'response.audio.done':
        showIndicator('Listening…');
        cancelFallbackTimer(); // reply finished
        break;
      default: break;
    }
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
