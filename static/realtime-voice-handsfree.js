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
    en: 'alloy', fr: 'alloy', es: 'verse',
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
          instructions: `You are Emily, an admissions assistant for More House School in London. Please greet the user warmly in their selected language (${currentLang}). Keep replies concise and helpful, and continue in this language unless they ask to switch.

IMPORTANT FACTS YOU MUST KNOW:
- School fees 2025-2026:
  • Years 5 and 6: £7,800 per term (inc VAT)
  • Years 7-13: £10,950 per term (inc VAT)
- Location: 22-24 Pont Street, Chelsea, London SW1X 0AA
- Contact: 020 7235 2855 or registrar@morehousemail.org.uk
- We're an independent all-girls school for ages 9-18 (Years 5-13)

When speaking English, use British English vocabulary:
- Use "lovely", "brilliant", "wonderful" instead of "awesome"
- Say "enquiry" not "inquiry", "at the weekend" not "on the weekend"
- Speak warmly and professionally

BOOKING/VISIT REQUESTS:
If the user asks about booking an open day, visiting the school, arranging a tour, or attending an open event:
1. Ask them: "Have you already registered or enquired with More House School before?"
2. If YES: Tell them "Please complete the booking form that will appear in the text window below."
3. If NO: Tell them "Please complete the enquiry form that will appear in the text window below. You'll receive a prospectus once complete, then you can book your visit."
4. DO NOT collect booking details via voice - always direct them to the text-based form.`
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

    // Handle function calls from the AI
    if (msg.type === 'response.function_call_arguments.done') {
      handleFunctionCall(msg);
      return;
    }

    // Handle text delta for booking detection
    if (msg.type === 'response.text.delta') {
      checkForBookingTrigger(msg.delta);
    }

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

  let currentResponseText = '';

  function checkForBookingTrigger(delta) {
    currentResponseText += delta;
    console.log('🔍 Voice delta:', delta);

    // Check if response contains the booking trigger phrase
    if (currentResponseText.includes('follow the on-screen instructions') ||
        currentResponseText.includes("I'll be here when you're done")) {
      console.log('🎯 ✅ BOOKING TRIGGER DETECTED!');
      console.log('📝 Full text:', currentResponseText);

      // Trigger the visual booking flow via EmilyBooking
      // Wait for both EmilyBooking and appendBotResponse to be available
      const waitForDeps = (retries = 0) => {
        const appendFn = window.appendBotResponse;

        if (window.EmilyBooking && typeof appendFn === 'function') {
          console.log('📝 Triggering visual booking form...');
          // Trigger the booking flow
          window.EmilyBooking.startBookingFlow(appendFn);

          // Set callback for when booking completes
          window.EmilyBooking.onBookingComplete = () => {
            console.log('✅ Booking complete, voice Emily resuming...');
            // Send a message to Emily to acknowledge completion
            if (dc && dc.readyState === 'open') {
              sendEvent({
                type: 'conversation.item.create',
                item: {
                  type: 'message',
                  role: 'user',
                  content: [{
                    type: 'input_text',
                    text: '[Booking completed successfully via form]'
                  }]
                }
              });
              sendEvent({
                type: 'response.create',
                response: {
                  instructions: 'The user has completed their booking via the visual form. Welcome them back warmly and ask if there is anything else you can help them with about the school.'
                }
              });
            }
          };
        } else if (retries < 10) {
          console.log(`⏳ Waiting for dependencies... (attempt ${retries + 1}/10)`);
          setTimeout(() => waitForDeps(retries + 1), 200);
        } else {
          console.error('❌ Failed to load booking dependencies after 10 retries');
        }
      };

      setTimeout(waitForDeps, 2000); // Give voice time to finish speaking

      // Reset for next response
      currentResponseText = '';
    }
  }

  async function handleFunctionCall(msg) {
    const functionName = msg.name;
    const callId = msg.call_id;
    let args = {};

    try {
      args = JSON.parse(msg.arguments || '{}');
    } catch (e) {
      console.error('Failed to parse function arguments:', e);
    }

    console.log(`🔧 Function call: ${functionName}`, args);

    if (functionName === 'get_open_day_dates') {
      console.log('📅 GET_OPEN_DAY_DATES tool called!');
      showIndicator('Checking dates…');

      try {
        const response = await fetch('/api/emily/get-events');
        const data = await response.json();

        const events = (data.events || []).filter(e => new Date(e.event_date) >= new Date());

        let result;
        if (events.length === 0) {
          result = "We don't have any open days scheduled at the moment, but I can help you arrange a private tour instead.";
        } else {
          const eventList = events.map(e => {
            const date = new Date(e.event_date);
            return `${e.title} on ${date.toLocaleDateString('en-GB', {weekday: 'long', day: 'numeric', month: 'long'})} at ${e.start_time}`;
          }).join(', ');
          result = `We have the following open days coming up: ${eventList}`;
        }

        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify({ dates: result })
          }
        });
        sendEvent({ type: 'response.create' });

        console.log('✅ Open day dates sent to AI');
      } catch (error) {
        console.error('❌ Error fetching open days:', error);
        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify({ error: 'Could not fetch open day dates' })
          }
        });
        sendEvent({ type: 'response.create' });
      }
      return;
    }

    if (functionName === 'show_booking_form') {
      console.log('📝 SHOW_BOOKING_FORM tool called!');

      // Trigger the visual booking form
      const appendFn = window.appendBotResponse;

      if (window.EmilyBooking && typeof appendFn === 'function') {
        console.log('✅ Triggering booking flow...');
        window.EmilyBooking.startBookingFlow(appendFn);

        // Set callback for completion
        window.EmilyBooking.onBookingComplete = () => {
          console.log('✅ Booking complete, voice resuming...');
          if (dc && dc.readyState === 'open') {
            sendEvent({
              type: 'conversation.item.create',
              item: {
                type: 'function_call_output',
                call_id: callId,
                output: JSON.stringify({ success: true, message: 'Booking form displayed' })
              }
            });
            sendEvent({
              type: 'response.create',
              response: {
                instructions: 'The booking form has been completed. Welcome the user back warmly and ask what else you can help with.'
              }
            });
          }
        };

        // Respond to the tool call immediately
        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify({ success: true, message: 'Booking form displayed' })
          }
        });
        sendEvent({ type: 'response.create' });
      } else {
        console.error('❌ EmilyBooking or appendBotResponse not available');
      }
      return;
    }

    if (functionName === 'kb_search') {
      showIndicator('Searching…');
      try {
        const response = await fetch('/realtime/tool/kb_search', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ query: args.query })
        });

        const result = await response.json();

        // Send the result back to the AI
        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify({
              answer: result.answer || 'No information found',
              source: result.source
            })
          }
        });

        // Request AI to respond with the information
        sendEvent({ type: 'response.create' });

        console.log('✅ KB search completed:', result.answer?.substring(0, 100));
      } catch (error) {
        console.error('❌ KB search failed:', error);

        // Send error back to AI
        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify({
              error: 'Failed to search knowledge base',
              answer: 'I apologize, but I had trouble accessing that information. Let me try to help another way.'
            })
          }
        });
        sendEvent({ type: 'response.create' });
      }
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
