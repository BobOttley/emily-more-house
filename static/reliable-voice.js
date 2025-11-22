// /static/reliable-voice.js
// Reliable voice system: Whisper → Text Emily → TTS Nova

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
  const indicator     = document.getElementById('voiceIndicator');

  // State
  let mediaRecorder = null;
  let audioChunks = [];
  let micStream = null;
  let started = false;
  let isPaused = false;
  let isRecording = false;
  let sessionId = new Date().getTime().toString();
  let currentLang = headerLangSel?.value || 'en';
  let audioContext = null;
  let analyser = null;
  let silenceTimeout = null;
  let isSpeaking = false;

  // Localisation for consent (same as realtime-voice-handsfree.js)
  const i18n = {
    en: { title:'Enable Emily (voice)', desc:'To chat by voice, we need one-time permission to use your microphone and play audio responses.', agree:'I agree to voice processing for this session.', cancel:'Not now', start:'Start conversation' },
    fr: { title:'Activer Emily (voix)', desc:'Pour discuter a la voix, nous avons besoin d une autorisation unique pour utiliser votre microphone et lire les reponses audio.', agree:'J accepte le traitement vocal pour cette session.', cancel:'Pas maintenant', start:'Commencer la conversation' },
    es: { title:'Activar Emily (voz)', desc:'Para hablar por voz, necesitamos permiso único para usar tu micrófono y reproducir respuestas de audio.', agree:'Acepto el procesamiento de voz para esta sesión.', cancel:'Ahora no', start:'Iniciar conversación' },
    de: { title:'Emily (Sprache) aktivieren', desc:'Für die Sprachfunktion benötigen wir einmalige Berechtigung für Ihr Mikrofon und die Audiowiedergabe.', agree:'Ich stimme der Sprachverarbeitung für diese Sitzung zu.', cancel:'Nicht jetzt', start:'Konversation starten' },
    zh: { title:'启用 Emily（语音）', desc:'要进行语音聊天，我们需要一次性授权使用您的麦克风并播放音频回复。', agree:'我同意在本次会话中进行语音处理。', cancel:'暂不', start:'开始对话' },
    ar: { title:'تفعيل إميلي (صوت)', desc:'للدردشة بالصوت، نحتاج إلى إذن لمرة واحدة لاستخدام الميكروفون وتشغيل الردود الصوتية.', agree:'أوافق على معالجة الصوت لهذه الجلسة.', cancel:'ليس الآن', start:'بدء المحادثة' },
    it: { title:'Abilita Emily (voce)', desc:'Per parlare con la voce, serve un autorizzazione una tantum per usare il microfono e riprodurre risposte audio.', agree:'Accetto l elaborazione vocale per questa sessione.', cancel:'Non ora', start:'Avvia conversazione' },
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
      if (typeof addMessage === 'function') {
        addMessage('PEN.ai', 'Hello! I\'m Emily. How can I help you today?');
      }
    } catch (err) {
      console.error('Voice start error:', err);
      startBtn.disabled = false;
      showIndicator('Error');
      alert('Could not start voice. Please check mic permissions and try again.');
    }
  });

  pauseBtn?.addEventListener('click', () => {
    isPaused = !isPaused;
    pauseBtn.textContent = isPaused ? 'Resume' : 'Pause';
    showIndicator(isPaused ? 'Paused' : 'Tap to speak');
  });

  endBtn?.addEventListener('click', () => {
    teardownSession();
    updateUIForEnd();
  });

  // === Voice session ===
  async function startVoiceSession() {
    // Request microphone access
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });

    // Set up automatic voice activity detection
    setupVoiceActivityDetection();
  }

  function setupVoiceActivityDetection() {
    // Create audio context and analyser for voice detection
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(micStream);
    source.connect(analyser);

    analyser.fftSize = 2048;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Voice activity detection loop
    const SPEECH_THRESHOLD = 30; // Adjust sensitivity (lower = more sensitive)
    const SILENCE_DURATION = 1500; // ms of silence before stopping

    function detectVoiceActivity() {
      if (!started || isPaused) {
        requestAnimationFrame(detectVoiceActivity);
        return;
      }

      analyser.getByteFrequencyData(dataArray);
      const average = dataArray.reduce((a, b) => a + b) / bufferLength;

      // Speech detected
      if (average > SPEECH_THRESHOLD) {
        if (!isRecording) {
          startRecording();
        }
        // Reset silence timer
        if (silenceTimeout) clearTimeout(silenceTimeout);
        silenceTimeout = setTimeout(() => {
          if (isRecording) stopRecording();
        }, SILENCE_DURATION);
      }

      requestAnimationFrame(detectVoiceActivity);
    }

    detectVoiceActivity();
  }

  function startRecording() {
    if (isPaused || isRecording) return;

    isRecording = true;
    audioChunks = [];
    showIndicator('🎤 Recording…');

    mediaRecorder = new MediaRecorder(micStream, { mimeType: 'audio/webm' });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      isRecording = false;
      showIndicator('⏳ Processing…');

      // Create audio blob
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });

      // Send to backend for transcription + response
      try {
        await sendAudioToBackend(audioBlob);
      } catch (err) {
        console.error('Error sending audio:', err);
        showIndicator('❌ Error');
        setTimeout(() => showIndicator('Listening…'), 2000);
      }
    };

    mediaRecorder.start();
  }

  function stopRecording() {
    if (!isRecording || !mediaRecorder || mediaRecorder.state !== 'recording') return;
    mediaRecorder.stop();
  }

  async function sendAudioToBackend(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('language', currentLang);
    formData.append('session_id', sessionId);

    const response = await fetch('/voice/transcribe-and-respond', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error('Voice API error: ' + response.statusText);
    }

    // Get transcription and text from headers (URL-encoded)
    const transcriptionEncoded = response.headers.get('X-Transcription');
    const emilyTextEncoded = response.headers.get('X-Emily-Text');

    // Decode URL-encoded headers
    const transcription = transcriptionEncoded ? decodeURIComponent(transcriptionEncoded) : null;
    const emilyText = emilyTextEncoded ? decodeURIComponent(emilyTextEncoded) : null;

    // Display what user said
    if (transcription && typeof addMessage === 'function') {
      addMessage('You', transcription);
    }

    // Display Emily's text response
    if (emilyText && typeof addMessage === 'function') {
      addMessage('PEN.ai', emilyText);
    }

    // Play audio response
    const audioData = await response.arrayBuffer();
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuffer = await audioContext.decodeAudioData(audioData);
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    showIndicator('🔊 Speaking…');
    source.start(0);

    source.onended = () => {
      showIndicator('Tap to speak');
    };
  }

  function teardownSession() {
    try { micStream?.getTracks().forEach(t => t.stop()); } catch {}
    micStream = null;
    mediaRecorder = null;

    // Remove hold-to-talk button
    const talkBtn = document.getElementById('hold-to-talk-btn');
    if (talkBtn) talkBtn.remove();
  }

  const urlParams = new URLSearchParams(window.location.search);
  const familyId = urlParams.get('family_id') || urlParams.get('id') || null;

  syncLanguage(currentLang);
})();
