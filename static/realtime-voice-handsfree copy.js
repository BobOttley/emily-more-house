// /static/realtime-voice-handsfree.js
(function () {
  const chatbox   = document.getElementById('penai-chatbox');
  const toggleBtn = document.getElementById('penai-toggle');
  const consent   = document.getElementById('voiceConsent');
  const agree     = document.getElementById('agreeVoice');
  const startBtn  = document.getElementById('startVoice');
  const cancelBtn = document.getElementById('cancelVoice');
  const aiAudio   = document.getElementById('aiAudio');

  let pc = null;              // RTCPeerConnection
  let micStream = null;       // MediaStream
  let dc = null;              // DataChannel ('oai-events')
  let started = false;

  function maybeShowConsent() {
    if (started) return;
    if (consent) consent.style.display = 'flex';
  }

  const observer = new MutationObserver(() => {
    if (chatbox?.classList.contains('open')) maybeShowConsent();
  });
  if (chatbox) observer.observe(chatbox, { attributes: true, attributeFilter: ['class'] });
  toggleBtn?.addEventListener('click', () => setTimeout(() => { if (chatbox?.classList.contains('open')) maybeShowConsent(); }, 50));
  agree?.addEventListener('change', () => { if (startBtn) startBtn.disabled = !agree.checked; });
  cancelBtn?.addEventListener('click', () => { if (consent) consent.style.display = 'none'; });

  startBtn?.addEventListener('click', async () => {
    if (startBtn) startBtn.disabled = true;
    try {
      await startHandsFreeSession();
      started = true;
      if (consent) consent.style.display = 'none';
    } catch (err) {
      console.error('Voice start error:', err);
      if (startBtn) startBtn.disabled = false;
      alert('Could not start voice. Please check mic permissions and try again.');
    }
  });

  async function startHandsFreeSession() {
    // 1) Mint an ephemeral session token
    const sessRes = await fetch('/realtime/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model: 'gpt-4o-realtime-preview', voice: 'coral' })
    });
    if (!sessRes.ok) throw new Error('Failed to create realtime session: ' + (await sessRes.text().catch(()=>'')));
    const sess = await sessRes.json();
    const token =
      sess.token ||
      (sess.session && sess.session.client_secret && (sess.session.client_secret.value || sess.session.client_secret)) ||
      (sess.client_secret && (sess.client_secret.value || sess.client_secret)) ||
      sess.value;
    if (!token) throw new Error('No ephemeral token returned');

    // 2) Peer connection and audio
    pc = new RTCPeerConnection();
    pc.ontrack = (e) => { if (aiAudio) aiAudio.srcObject = e.streams[0]; };

    // 3) Realtime "events" data channel (required for tool calling)
    dc = pc.createDataChannel('oai-events');
    dc.onopen = () => {
      // Kick off listening; tell the model it can use kb_search
      sendEvent({
        type: 'response.create',
        response: {
          instructions: "You are Emily. Always call the tool `kb_search` before answering anything."
        }
      });
      
    };
    dc.onmessage = onEventMessage;

    // 4) Mic capture
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    micStream.getTracks().forEach(t => pc.addTrack(t, micStream));

    // 5) SDP exchange with OpenAI Realtime
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpRes = await fetch('https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/sdp' },
      body: offer.sdp
    });
    if (!sdpRes.ok) throw new Error('Realtime SDP error: ' + (await sdpRes.text().catch(()=>'')));
    const answer = { type: 'answer', sdp: await sdpRes.text() };
    await pc.setRemoteDescription(answer);
  }

  function sendEvent(obj) {
    if (dc && dc.readyState === 'open') {
      dc.send(JSON.stringify(obj));
    }
  }

  async function onEventMessage(evt) {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }

    // Optional live captions:
    if (msg.type === 'response.output_text.delta') {
      // console.log('AI:', msg.delta);
    }

    // Handle tool calls:
    if (msg.type === 'tool.call') {
      const call = msg;
      if (call.name === 'kb_search') {
        try {
          const args = typeof call.arguments === 'string' ? JSON.parse(call.arguments) : (call.arguments || {});
          const question  = args.question || '';
          const language  = args.language || 'en';
          const family_id = args.family_id || null;

          // Call your existing RAG endpoint
          const ragRes = await fetch('/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ question, language, family_id })
          });
          const rag = await ragRes.json().catch(() => ({}));

          const lines = [];
          if (rag && rag.answer) lines.push(rag.answer);
          if (rag && rag.url && rag.link_label) lines.push(`Source: ${rag.link_label}`);
          const outputText = lines.join('\n\n') || 'No result.';

          // Return tool output
          sendEvent({
            type: 'tool.output',
            call_id: call.call_id,
            output: { type: 'output_text', text: outputText }
          });

          // Ask the model to speak the result
          sendEvent({ type: 'response.create' });

        } catch (err) {
          console.error('kb_search tool handler error:', err);
          sendEvent({
            type: 'tool.output',
            call_id: call.call_id,
            output: { type: 'output_text', text: 'KB error: unable to fetch an answer.' }
          });
          sendEvent({ type: 'response.create' });
        }
      }
    }
  }

  // Housekeeping
  document.addEventListener('visibilitychange', () => {
    if (!micStream) return;
    const enable = document.visibilityState === 'visible';
    micStream.getAudioTracks().forEach(t => t.enabled = enable);
  });
  window.addEventListener('beforeunload', () => {
    try { micStream?.getTracks().forEach(t => t.stop()); } catch {}
    try { pc?.close(); } catch {}
  });
})();
