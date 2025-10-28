// More House Emily - Voice Interface (Complete Fixed Version)
// With proper tool handling and contact collection tracking

(function() {
  // ============================================================================
  // Configuration
  // ============================================================================
  const familyId = new URLSearchParams(window.location.search).get('family_id') || localStorage.getItem('emily_family_id');
  const DEBUG = true; // Enable detailed logging for troubleshooting
  
  // ============================================================================
  // UI Elements
  // ============================================================================
  let btnMic, btnEndCall, statusDiv, transcriptDiv, responseDiv;
  let debugDiv, volumeBar, contactForm;
  
  // ============================================================================
  // Voice Session State
  // ============================================================================
  let pc = null;
  let dc = null;
  let micStream = null;
  let sessionId = null;
  let sessionActive = false;
  let isListening = false;
  let lastTranscript = '';
  let currentLanguage = localStorage.getItem('emily_language') || 'en';
  
  // Contact collection state
  let collectingContact = false;
  let contactDetails = {
    parent_name: '',
    parent_email: '',
    parent_phone: '',
    child_name: '',
    year_group: ''
  };
  
  // Voice configuration by language
  const voiceByLang = {
    'en': 'shimmer',    // British female voice
    'zh': 'alloy',      // Better for Chinese
    'cn': 'alloy',
    'chinese': 'alloy',
    'mandarin': 'alloy'
  };
  
  // ============================================================================
  // Tool Execution State
  // ============================================================================
  let pendingTools = {};
  let toolExecutionInProgress = false;
  
  // ============================================================================
  // UI Creation and Management
  // ============================================================================
  function createVoiceUI() {
    const container = document.createElement('div');
    container.id = 'emily-voice-widget';
    container.innerHTML = `
      <div class="voice-header">
        <img src="/static/more-house-logo.png" alt="More House" class="school-logo" onerror="this.style.display='none'">
        <h3>Talk to Emily</h3>
      </div>
      
      <div class="voice-status" id="voice-status">
        <span class="status-dot"></span>
        <span class="status-text">Ready to chat</span>
      </div>
      
      <div class="voice-controls">
        <button id="btn-mic" class="btn-voice btn-mic">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M12 1C10.34 1 9 2.34 9 4V12C9 13.66 10.34 15 12 15C13.66 15 15 13.66 15 12V4C15 2.34 13.66 1 12 1Z" stroke="currentColor" stroke-width="2"/>
            <path d="M19 10V12C19 15.86 15.86 19 12 19C8.14 19 5 15.86 5 12V10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path d="M12 19V23M8 23H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <span>Start Call</span>
        </button>
        
        <button id="btn-end" class="btn-voice btn-end" style="display: none;">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M9 9L15 15M15 9L9 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <span>End Call</span>
        </button>
      </div>
      
      <div class="voice-volume" id="voice-volume" style="display: none;">
        <div class="volume-bar">
          <div class="volume-level" id="volume-level"></div>
        </div>
      </div>
      
      <div class="voice-transcript" id="voice-transcript" style="display: none;">
        <div class="transcript-label">You said:</div>
        <div class="transcript-text" id="transcript-text">...</div>
      </div>
      
      <div class="voice-response" id="voice-response" style="display: none;">
        <div class="response-label">Emily:</div>
        <div class="response-text" id="response-text">...</div>
      </div>
      
      <div class="contact-form" id="contact-form" style="display: none;">
        <div class="form-label">Contact Details Needed</div>
        <input type="text" id="cf-name" placeholder="Your full name" />
        <input type="email" id="cf-email" placeholder="Your email address" />
        <input type="tel" id="cf-phone" placeholder="Your phone number" />
        <input type="text" id="cf-child" placeholder="Your daughter's name" />
        <select id="cf-year">
          <option value="">Select year group</option>
          <option value="Reception">Reception</option>
          <option value="Year 1">Year 1</option>
          <option value="Year 2">Year 2</option>
          <option value="Year 3">Year 3</option>
          <option value="Year 4">Year 4</option>
          <option value="Year 5">Year 5</option>
          <option value="Year 6">Year 6</option>
          <option value="Year 7">Year 7</option>
          <option value="Year 8">Year 8</option>
          <option value="Year 9">Year 9</option>
          <option value="Year 10">Year 10</option>
          <option value="Year 11">Year 11</option>
          <option value="Sixth Form">Sixth Form</option>
        </select>
        <button id="cf-submit" class="btn-submit">Send Tour Request</button>
      </div>
      
      <div class="voice-debug" id="voice-debug" style="display: ${DEBUG ? 'block' : 'none'};">
        <div class="debug-label">Debug Log:</div>
        <div class="debug-content" id="debug-content"></div>
      </div>
      
      <audio id="ai-audio" autoplay style="display: none;"></audio>
    `;
    
    document.body.appendChild(container);
    
    // Get references
    btnMic = document.getElementById('btn-mic');
    btnEndCall = document.getElementById('btn-end');
    statusDiv = document.getElementById('voice-status');
    transcriptDiv = document.getElementById('voice-transcript');
    responseDiv = document.getElementById('voice-response');
    debugDiv = document.getElementById('debug-content');
    volumeBar = document.getElementById('voice-volume');
    contactForm = document.getElementById('contact-form');
    
    // Attach event listeners
    btnMic.addEventListener('click', startVoiceCall);
    btnEndCall.addEventListener('click', endVoiceCall);
    
    // Contact form submit
    const submitBtn = document.getElementById('cf-submit');
    if (submitBtn) {
      submitBtn.addEventListener('click', submitContactForm);
    }
    
    // Add styles
    addVoiceStyles();
    
    logDebug('🎤 Voice UI initialized');
    if (familyId) {
      logDebug(`👨‍👩‍👧 Family ID: ${familyId}`);
    }
  }
  
  function addVoiceStyles() {
    const style = document.createElement('style');
    style.textContent = `
      #emily-voice-widget {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 380px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.15);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        z-index: 10000;
        overflow: hidden;
      }
      
      .voice-header {
        background: linear-gradient(135deg, #091825 0%, #1a2f45 100%);
        color: white;
        padding: 20px;
        text-align: center;
      }
      
      .school-logo {
        height: 40px;
        margin-bottom: 10px;
      }
      
      .voice-header h3 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
      }
      
      .voice-status {
        display: flex;
        align-items: center;
        padding: 12px 20px;
        background: #f8f9fa;
        border-bottom: 1px solid #e9ecef;
      }
      
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #28a745;
        margin-right: 10px;
        animation: pulse 2s infinite;
      }
      
      .status-dot.active {
        background: #FF9F1C;
        animation: pulse 1s infinite;
      }
      
      .status-dot.error {
        background: #dc3545;
        animation: none;
      }
      
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }
      
      .voice-controls {
        padding: 20px;
        display: flex;
        justify-content: center;
        gap: 10px;
      }
      
      .btn-voice {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 24px;
        border: none;
        border-radius: 8px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
      }
      
      .btn-mic {
        background: #FF9F1C;
        color: white;
      }
      
      .btn-mic:hover {
        background: #e68a00;
        transform: translateY(-2px);
      }
      
      .btn-mic.active {
        background: #28a745;
      }
      
      .btn-end {
        background: #dc3545;
        color: white;
      }
      
      .btn-end:hover {
        background: #c82333;
      }
      
      .voice-volume {
        padding: 0 20px 15px;
      }
      
      .volume-bar {
        height: 6px;
        background: #e9ecef;
        border-radius: 3px;
        overflow: hidden;
      }
      
      .volume-level {
        height: 100%;
        background: #FF9F1C;
        width: 0%;
        transition: width 0.1s ease;
      }
      
      .voice-transcript,
      .voice-response {
        padding: 15px 20px;
        border-top: 1px solid #e9ecef;
      }
      
      .transcript-label,
      .response-label,
      .form-label {
        font-size: 12px;
        font-weight: 600;
        color: #6c757d;
        text-transform: uppercase;
        margin-bottom: 8px;
      }
      
      .transcript-text,
      .response-text {
        font-size: 14px;
        line-height: 1.5;
        color: #212529;
        max-height: 100px;
        overflow-y: auto;
      }
      
      .contact-form {
        padding: 20px;
        background: #f8f9fa;
        border-top: 2px solid #FF9F1C;
      }
      
      .contact-form input,
      .contact-form select {
        width: 100%;
        padding: 10px;
        margin-bottom: 10px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 14px;
      }
      
      .contact-form input:focus,
      .contact-form select:focus {
        outline: none;
        border-color: #FF9F1C;
      }
      
      .btn-submit {
        width: 100%;
        padding: 12px;
        background: #FF9F1C;
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.3s;
      }
      
      .btn-submit:hover {
        background: #e68a00;
      }
      
      .voice-debug {
        padding: 15px 20px;
        background: #f8f9fa;
        border-top: 1px solid #e9ecef;
      }
      
      .debug-label {
        font-size: 11px;
        font-weight: 600;
        color: #6c757d;
        text-transform: uppercase;
        margin-bottom: 8px;
      }
      
      .debug-content {
        font-family: 'Courier New', monospace;
        font-size: 11px;
        color: #495057;
        max-height: 150px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }
      
      .email-confirmation {
        padding: 15px;
        margin: 10px 20px;
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 8px;
        color: #155724;
        animation: slideDown 0.3s ease;
      }
      
      @keyframes slideDown {
        from {
          opacity: 0;
          transform: translateY(-10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
    `;
    document.head.appendChild(style);
  }
  
  // ============================================================================
  // Voice Session Management
  // ============================================================================
  async function startVoiceCall() {
    if (sessionActive) return;
    
    try {
      logDebug('🎬 Starting voice call...');
      updateStatus('Connecting...', 'active');
      
      // Update UI
      btnMic.style.display = 'none';
      btnEndCall.style.display = 'flex';
      volumeBar.style.display = 'block';
      transcriptDiv.style.display = 'block';
      responseDiv.style.display = 'block';
      
      // Create session
      await createRealtimeSession();
      
      // Setup WebRTC
      await setupWebRTC();
      
      sessionActive = true;
      isListening = true;
      updateStatus('Connected - Listening', 'active');
      
      logDebug('✅ Voice call started successfully');
      
    } catch (error) {
      console.error('Failed to start voice call:', error);
      logDebug(`❌ Error: ${error.message}`);
      updateStatus('Connection failed', 'error');
      resetUI();
    }
  }
  
  async function createRealtimeSession() {
    logDebug('📞 Creating realtime session...');
    
    const response = await fetch('/realtime/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        model: 'gpt-4o-realtime-preview',
        voice: voiceByLang[currentLanguage] || 'shimmer',
        language: currentLanguage,
        family_id: familyId
      })
    });
    
    if (!response.ok) {
      throw new Error(`Session creation failed: ${response.status}`);
    }
    
    const data = await response.json();
    sessionId = data.session_id;
    
    // Extract token
    const token = data.token || 
                  (data.client_secret && data.client_secret.value) ||
                  data.client_secret;
    
    if (!token) {
      throw new Error('No ephemeral token received');
    }
    
    // Store for WebRTC setup
    window.realtimeToken = token;
    
    logDebug(`✅ Session created: ${sessionId}`);
    logDebug(`🔑 Token received: ${token.substring(0, 20)}...`);
  }
  
  async function setupWebRTC() {
    logDebug('🌐 Setting up WebRTC connection...');
    
    // Create peer connection
    pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    });
    
    // Handle incoming audio
    pc.ontrack = (event) => {
      logDebug('🔊 Received audio track');
      const audio = document.getElementById('ai-audio');
      if (audio && event.streams[0]) {
        audio.srcObject = event.streams[0];
        audio.play().catch(e => console.error('Audio play error:', e));
      }
    };
    
    // Create data channel for events
    dc = pc.createDataChannel('oai-events');
    
    dc.onopen = () => {
      logDebug('📡 Data channel opened');
      
      // Send initial greeting trigger
      sendEvent({
        type: 'conversation.item.create',
        item: {
          type: 'message',
          role: 'user',
          content: [{
            type: 'input_text',
            text: 'Hello'
          }]
        }
      });
      
      // Request response
      sendEvent({
        type: 'response.create'
      });
    };
    
    dc.onmessage = handleRealtimeEvent;
    dc.onerror = (error) => {
      logDebug(`❌ Data channel error: ${error}`);
    };
    
    // Get user microphone
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      },
      video: false
    });
    
    // Add microphone to peer connection
    micStream.getTracks().forEach(track => {
      pc.addTrack(track, micStream);
    });
    
    // Monitor microphone volume
    monitorMicrophoneVolume();
    
    // Create offer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    
    logDebug('📤 Sending SDP offer to OpenAI...');
    
    // Send offer to OpenAI
    const sdpResponse = await fetch('https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${window.realtimeToken}`,
        'Content-Type': 'application/sdp'
      },
      body: offer.sdp
    });
    
    if (!sdpResponse.ok) {
      throw new Error(`SDP exchange failed: ${sdpResponse.status}`);
    }
    
    const answer = {
      type: 'answer',
      sdp: await sdpResponse.text()
    };
    
    await pc.setRemoteDescription(answer);
    
    logDebug('✅ WebRTC connection established');
  }
  
  // ============================================================================
  // Event Handling
  // ============================================================================
  function handleRealtimeEvent(event) {
    try {
      const data = JSON.parse(event.data);
      
      // Log all events except audio deltas
      if (DEBUG && data.type !== 'response.audio.delta') {
        logDebug(`📨 Event: ${data.type}`);
      }
      
      switch(data.type) {
        case 'conversation.item.created':
          if (data.item && data.item.role === 'user') {
            handleUserTranscript(data.item);
          }
          break;
          
        case 'response.text.delta':
          handleResponseDelta(data);
          break;
          
        case 'response.text.done':
          handleResponseComplete(data);
          break;
          
        case 'response.function_call_arguments.start':
          handleToolCallStart(data);
          break;
          
        case 'response.function_call_arguments.delta':
          handleToolCallDelta(data);
          break;
          
        case 'response.function_call_arguments.done':
          handleToolCallComplete(data);
          break;
          
        case 'response.done':
          if (data.response && data.response.output) {
            handleFinalResponse(data.response.output);
          }
          break;
          
        case 'error':
          handleError(data);
          break;
      }
    } catch (error) {
      console.error('Error handling realtime event:', error);
      logDebug(`❌ Event handling error: ${error.message}`);
    }
  }
  
  function handleUserTranscript(item) {
    if (item.content && item.content[0]) {
      const text = item.content[0].transcript || item.content[0].text || '';
      if (text && text !== 'Hello') { // Ignore our trigger message
        lastTranscript = text;
        updateTranscript(text);
        logDebug(`🎤 User: "${text}"`);
        
        // Check for contact information in transcript
        extractContactFromTranscript(text);
        
        // Check if this is a tour request
        checkForTourRequest(text);
      }
    }
  }
  
  function extractContactFromTranscript(text) {
    // Extract email
    const emailMatch = text.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/);
    if (emailMatch && !contactDetails.parent_email) {
      contactDetails.parent_email = emailMatch[0];
      logDebug(`📧 Extracted email: ${contactDetails.parent_email}`);
    }
    
    // Extract phone (UK patterns)
    const phoneMatch = text.match(/\b(?:07\d{9}|01\d{9}|02\d{9}|\+447\d{9})\b/);
    if (phoneMatch && !contactDetails.parent_phone) {
      contactDetails.parent_phone = phoneMatch[0];
      logDebug(`📞 Extracted phone: ${contactDetails.parent_phone}`);
    }
    
    // Extract name (if they say "my name is..." or "I'm...")
    const nameMatch = text.match(/(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/i);
    if (nameMatch && !contactDetails.parent_name) {
      contactDetails.parent_name = nameMatch[1];
      logDebug(`👤 Extracted name: ${contactDetails.parent_name}`);
    }
  }
  
  function checkForTourRequest(text) {
    const tourKeywords = ['tour', 'visit', 'book', 'see the school', 'admissions', 'apply'];
    if (tourKeywords.some(keyword => text.toLowerCase().includes(keyword))) {
      collectingContact = true;
      logDebug('🏫 Tour request detected - collecting contact details');
      
      // Show contact form if we don't have all details
      if (!contactDetails.parent_email || !contactDetails.parent_phone) {
        showContactForm();
      }
    }
  }
  
  function handleResponseDelta(data) {
    if (data.delta) {
      const currentText = document.getElementById('response-text').textContent;
      document.getElementById('response-text').textContent = currentText + data.delta;
    }
  }
  
  function handleResponseComplete(data) {
    if (data.text) {
      document.getElementById('response-text').textContent = data.text;
      logDebug(`🤖 Emily: "${data.text.substring(0, 100)}..."`);
      
      // Check if Emily is asking for contact details
      if (data.text.toLowerCase().includes('email') || 
          data.text.toLowerCase().includes('phone') ||
          data.text.toLowerCase().includes('contact')) {
        collectingContact = true;
      }
    }
  }
  
  function handleFinalResponse(output) {
    if (output && output[0]) {
      if (output[0].type === 'message' && output[0].content) {
        const content = output[0].content[0];
        if (content && content.text) {
          document.getElementById('response-text').textContent = content.text;
        }
      }
    }
  }
  
  // ============================================================================
  // Tool Execution
  // ============================================================================
  function handleToolCallStart(data) {
    logDebug(`🔧 Tool call starting: ${data.name || 'unknown'}`);
    
    if (data.call_id && data.name) {
      pendingTools[data.call_id] = {
        name: data.name,
        arguments: ''
      };
      toolExecutionInProgress = true;
    }
  }
  
  function handleToolCallDelta(data) {
    if (data.call_id && data.delta && pendingTools[data.call_id]) {
      pendingTools[data.call_id].arguments += data.delta;
    }
  }
  
  async function handleToolCallComplete(data) {
    if (!data.call_id || !pendingTools[data.call_id]) return;
    
    const tool = pendingTools[data.call_id];
    logDebug(`🔧 Executing tool: ${tool.name}`);
    
    try {
      let args = {};
      if (tool.arguments) {
        args = JSON.parse(tool.arguments);
      }
      
      // Add session context
      args.family_id = familyId;
      args.session_id = sessionId;
      
      // If this is send_email, capture the contact details
      if (tool.name === 'send_email') {
        if (args.parent_email) contactDetails.parent_email = args.parent_email;
        if (args.parent_phone) contactDetails.parent_phone = args.parent_phone;
        if (args.parent_name) contactDetails.parent_name = args.parent_name;
        
        logDebug(`📧 Sending email with collected details:`);
        logDebug(`   Name: ${args.parent_name}`);
        logDebug(`   Email: ${args.parent_email}`);
        logDebug(`   Phone: ${args.parent_phone}`);
      }
      
      logDebug(`📤 Tool args: ${JSON.stringify(args)}`);
      
      // Execute the tool
      let result = await executeToolCall(tool.name, args);
      
      // Send result back to the model
      sendEvent({
        type: 'conversation.item.create',
        item: {
          type: 'function_call_output',
          call_id: data.call_id,
          output: JSON.stringify(result)
        }
      });
      
      // Clean up
      delete pendingTools[data.call_id];
      toolExecutionInProgress = false;
      
      logDebug(`✅ Tool ${tool.name} executed successfully`);
      
      // Show email confirmation in UI if it was an email tool
      if (tool.name === 'send_email' && result.success) {
        showEmailConfirmation(args);
        hideContactForm();
      }
      
    } catch (error) {
      console.error(`Tool execution failed:`, error);
      logDebug(`❌ Tool error: ${error.message}`);
      
      // Send error back to model
      sendEvent({
        type: 'conversation.item.create',
        item: {
          type: 'function_call_output',
          call_id: data.call_id,
          output: JSON.stringify({
            error: error.message,
            success: false
          })
        }
      });
      
      delete pendingTools[data.call_id];
      toolExecutionInProgress = false;
    }
  }
  
  async function executeToolCall(toolName, args) {
    logDebug(`🚀 Calling tool endpoint: /realtime/tool/${toolName}`);
    
    const response = await fetch(`/realtime/tool/${toolName}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(args)
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Tool call failed (${response.status}): ${errorText}`);
    }
    
    const result = await response.json();
    logDebug(`📥 Tool response: ${JSON.stringify(result)}`);
    
    return result;
  }
  
  // ============================================================================
  // Contact Form Management
  // ============================================================================
  function showContactForm() {
    const form = document.getElementById('contact-form');
    if (form) {
      form.style.display = 'block';
      logDebug('📝 Showing contact form');
    }
  }
  
  function hideContactForm() {
    const form = document.getElementById('contact-form');
    if (form) {
      form.style.display = 'none';
    }
  }
  
  async function submitContactForm() {
    // Gather form data
    contactDetails.parent_name = document.getElementById('cf-name').value;
    contactDetails.parent_email = document.getElementById('cf-email').value;
    contactDetails.parent_phone = document.getElementById('cf-phone').value;
    contactDetails.child_name = document.getElementById('cf-child').value;
    contactDetails.year_group = document.getElementById('cf-year').value;
    
    if (!contactDetails.parent_name || !contactDetails.parent_email || !contactDetails.parent_phone) {
      alert('Please fill in all required fields (name, email, phone)');
      return;
    }
    
    logDebug('📤 Submitting contact form...');
    
    // Send via tool endpoint
    try {
      const result = await executeToolCall('send_email', {
        parent_name: contactDetails.parent_name,
        parent_email: contactDetails.parent_email,
        parent_phone: contactDetails.parent_phone,
        subject: `Tour Request - ${contactDetails.child_name || 'More House School'}`,
        body: `Tour request from ${contactDetails.parent_name} for ${contactDetails.child_name || 'their daughter'} (${contactDetails.year_group || 'Year group not specified'})`,
        family_id: familyId,
        session_id: sessionId
      });
      
      if (result.success) {
        showEmailConfirmation(contactDetails);
        hideContactForm();
        
        // Tell Emily we've sent the email
        sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'message',
            role: 'assistant',
            content: [{
              type: 'text',
              text: `Perfect! I've sent your tour request to our admissions team. They'll contact you at ${contactDetails.parent_email} within 24 hours.`
            }]
          }
        });
      }
    } catch (error) {
      console.error('Failed to submit contact form:', error);
      alert('Sorry, there was an error sending your request. Please try again.');
    }
  }
  
  function showEmailConfirmation(emailData) {
    const confirmDiv = document.createElement('div');
    confirmDiv.className = 'email-confirmation';
    confirmDiv.innerHTML = `
      <strong>✅ Email Sent Successfully!</strong><br>
      To: ${emailData.parent_email || 'Admissions'}<br>
      Subject: ${emailData.subject || 'Tour Enquiry'}<br>
      <small>The admissions team will contact you within 24 hours.</small>
    `;
    
    responseDiv.appendChild(confirmDiv);
    
    // Store contact details for future use
    if (emailData.parent_email) {
      localStorage.setItem('emily_parent_details', JSON.stringify({
        name: emailData.parent_name,
        email: emailData.parent_email,
        phone: emailData.parent_phone
      }));
    }
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
      confirmDiv.remove();
    }, 10000);
  }
  
  // ============================================================================
  // Utility Functions
  // ============================================================================
  function sendEvent(event) {
    if (dc && dc.readyState === 'open') {
      const eventStr = JSON.stringify(event);
      dc.send(eventStr);
      if (DEBUG && event.type !== 'response.create') {
        logDebug(`📤 Sent: ${event.type}`);
      }
    }
  }
  
  function updateStatus(text, state = 'normal') {
    const statusText = statusDiv.querySelector('.status-text');
    const statusDot = statusDiv.querySelector('.status-dot');
    
    statusText.textContent = text;
    statusDot.className = 'status-dot';
    
    if (state === 'active') {
      statusDot.classList.add('active');
    } else if (state === 'error') {
      statusDot.classList.add('error');
    }
  }
  
  function updateTranscript(text) {
    document.getElementById('transcript-text').textContent = text;
  }
  
  function handleError(error) {
    console.error('Realtime error:', error);
    logDebug(`❌ Error: ${JSON.stringify(error)}`);
    updateStatus('Error occurred', 'error');
  }
  
  function logDebug(message) {
    if (DEBUG && debugDiv) {
      const timestamp = new Date().toLocaleTimeString();
      debugDiv.textContent += `[${timestamp}] ${message}\n`;
      debugDiv.scrollTop = debugDiv.scrollHeight;
    }
    console.log(`[Emily Voice] ${message}`);
  }
  
  function monitorMicrophoneVolume() {
    if (!micStream) return;
    
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = audioContext.createAnalyser();
    const microphone = audioContext.createMediaStreamSource(micStream);
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    
    microphone.connect(analyser);
    analyser.fftSize = 256;
    
    function updateVolume() {
      if (!sessionActive) return;
      
      analyser.getByteFrequencyData(dataArray);
      const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
      const percentage = Math.min(100, (average / 128) * 100);
      
      const volumeLevel = document.getElementById('volume-level');
      if (volumeLevel) {
        volumeLevel.style.width = `${percentage}%`;
      }
      
      requestAnimationFrame(updateVolume);
    }
    
    updateVolume();
  }
  
  async function endVoiceCall() {
    logDebug('📴 Ending voice call...');
    
    sessionActive = false;
    isListening = false;
    
    // Save conversation summary if we collected contact
    if (sessionId && (contactDetails.parent_email || contactDetails.parent_phone)) {
      try {
        await fetch('/api/conversation/end', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            session_id: sessionId,
            contact_collected: true,
            contact_details: contactDetails
          })
        });
        logDebug('✅ Conversation summary saved');
      } catch (e) {
        console.error('Failed to save conversation summary:', e);
      }
    }
    
    // Close connections
    if (dc) {
      dc.close();
      dc = null;
    }
    
    if (pc) {
      pc.close();
      pc = null;
    }
    
    if (micStream) {
      micStream.getTracks().forEach(track => track.stop());
      micStream = null;
    }
    
    // Reset UI
    resetUI();
    updateStatus('Call ended', 'normal');
    
    logDebug('✅ Voice call ended');
  }
  
  function resetUI() {
    btnMic.style.display = 'flex';
    btnEndCall.style.display = 'none';
    volumeBar.style.display = 'none';
    transcriptDiv.style.display = 'none';
    responseDiv.style.display = 'none';
    contactForm.style.display = 'none';
    
    document.getElementById('transcript-text').textContent = '';
    document.getElementById('response-text').textContent = '';
    
    // Clear contact form
    document.getElementById('cf-name').value = '';
    document.getElementById('cf-email').value = '';
    document.getElementById('cf-phone').value = '';
    document.getElementById('cf-child').value = '';
    document.getElementById('cf-year').value = '';
  }
  
  // ============================================================================
  // Initialization
  // ============================================================================
  function init() {
    // Load saved contact details if available
    try {
      const saved = localStorage.getItem('emily_parent_details');
      if (saved) {
        const details = JSON.parse(saved);
        contactDetails.parent_name = details.name || '';
        contactDetails.parent_email = details.email || '';
        contactDetails.parent_phone = details.phone || '';
        logDebug('📋 Loaded saved contact details');
      }
    } catch (e) {
      console.error('Failed to load saved details:', e);
    }
    
    // Wait for DOM ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', createVoiceUI);
    } else {
      createVoiceUI();
    }
  }
  
  // Start initialization
  init();
  
})();