// More House Emily - Text Chat Interface (Complete Fixed Version)
// With contact collection and database logging

console.log("✅ More House Emily chatbot loaded");

// ==================== Configuration ====================
const CHATBOT_ORIGIN = window.EMILY_CHATBOT_ORIGIN || "";

// Extract and persist family_id
let FAMILY_ID = new URLSearchParams(window.location.search).get('family_id');

if (FAMILY_ID) {
  try {
    localStorage.setItem('emily_family_id', FAMILY_ID);
    console.log('✅ Family ID saved:', FAMILY_ID);
  } catch (e) {
    console.error('Failed to save family_id:', e);
  }
}

if (!FAMILY_ID) {
  try {
    FAMILY_ID = localStorage.getItem('emily_family_id');
    if (FAMILY_ID) {
      console.log('✅ Family ID from storage:', FAMILY_ID);
    }
  } catch (e) {
    console.error('Failed to load family_id:', e);
  }
}

// ==================== State Management ====================
let chatHistory = [];
let sessionId = null;
let isProcessing = false;
let contactDetails = {
  parent_name: '',
  parent_email: '',
  parent_phone: '',
  child_name: '',
  year_group: ''
};
let awaitingContactDetails = false;
let pendingRequest = '';

// ==================== UI Injection ====================
(function injectUI() {
  if (document.getElementById("emily-styles")) return;
  
  // Inject styles
  const styles = document.createElement('style');
  styles.id = 'emily-styles';
  styles.textContent = `
    :root {
      --mh-primary: #091825;
      --mh-accent: #FF9F1C;
      --mh-text: #333;
      --mh-bg: #f9f9f9;
      --mh-border: #e0e0e0;
    }
    
    #emily-toggle {
      position: fixed;
      bottom: 20px;
      right: 20px;
      width: 70px;
      height: 70px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--mh-accent) 0%, #e68a00 100%);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0,0,0,0.2);
      z-index: 10000;
      transition: all 0.3s ease;
    }
    
    #emily-toggle:hover {
      transform: scale(1.1);
      box-shadow: 0 6px 25px rgba(0,0,0,0.3);
    }
    
    #emily-toggle svg {
      width: 35px;
      height: 35px;
      fill: white;
    }
    
    #emily-greeting {
      position: fixed;
      bottom: 100px;
      right: 20px;
      background: white;
      padding: 15px 20px;
      border-radius: 18px;
      box-shadow: 0 4px 15px rgba(0,0,0,0.15);
      max-width: 280px;
      animation: slideInRight 0.5s ease;
      z-index: 9999;
    }
    
    @keyframes slideInRight {
      from {
        transform: translateX(100px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    
    #emily-chatbox {
      display: none;
      flex-direction: column;
      position: fixed;
      bottom: 100px;
      right: 20px;
      width: 400px;
      height: 650px;
      background: white;
      border-radius: 16px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.2);
      z-index: 10001;
      overflow: hidden;
    }
    
    #emily-chatbox.open {
      display: flex;
      animation: slideUp 0.3s ease;
    }
    
    @keyframes slideUp {
      from {
        transform: translateY(20px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }
    
    #emily-header {
      background: linear-gradient(135deg, var(--mh-primary) 0%, #1a2f45 100%);
      color: white;
      padding: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    
    #emily-header h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }
    
    #emily-close {
      background: rgba(255,255,255,0.2);
      border: none;
      color: white;
      width: 30px;
      height: 30px;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.3s;
      font-size: 18px;
    }
    
    #emily-close:hover {
      background: rgba(255,255,255,0.3);
    }
    
    #chat-history {
      flex: 1;
      padding: 20px;
      overflow-y: auto;
      background: var(--mh-bg);
      scroll-behavior: smooth;
    }
    
    .message {
      margin-bottom: 15px;
      animation: fadeIn 0.3s ease;
    }
    
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    .message.user {
      text-align: right;
    }
    
    .message.user .bubble {
      background: var(--mh-accent);
      color: white;
      display: inline-block;
      padding: 10px 15px;
      border-radius: 18px 18px 4px 18px;
      max-width: 80%;
      word-wrap: break-word;
    }
    
    .message.bot .bubble {
      background: white;
      color: var(--mh-text);
      display: inline-block;
      padding: 10px 15px;
      border-radius: 18px 18px 18px 4px;
      max-width: 80%;
      word-wrap: break-word;
      border: 1px solid var(--mh-border);
    }
    
    .message.bot .bubble strong {
      color: var(--mh-primary);
    }
    
    .contact-form {
      background: #f0f8ff;
      padding: 15px;
      border-radius: 8px;
      margin-top: 10px;
      border: 1px solid #FF9F1C;
    }
    
    .contact-form h4 {
      margin: 0 0 10px 0;
      color: var(--mh-primary);
      font-size: 14px;
    }
    
    .contact-form input,
    .contact-form select {
      width: 100%;
      padding: 8px;
      margin: 5px 0;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
    }
    
    .contact-form input:focus,
    .contact-form select:focus {
      outline: none;
      border-color: var(--mh-accent);
    }
    
    .contact-form button {
      background: var(--mh-accent);
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      cursor: pointer;
      margin-top: 10px;
      font-weight: 600;
      width: 100%;
    }
    
    .contact-form button:hover {
      background: #e68a00;
    }
    
    .email-confirmation {
      background: #d4edda;
      border: 1px solid #c3e6cb;
      color: #155724;
      padding: 12px;
      border-radius: 8px;
      margin-top: 10px;
    }
    
    #button-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      padding: 15px;
      background: white;
      border-top: 1px solid var(--mh-border);
    }
    
    .quick-reply {
      padding: 10px;
      background: white;
      color: var(--mh-primary);
      border: 1px solid var(--mh-border);
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
    }
    
    .quick-reply:hover {
      background: var(--mh-accent);
      color: white;
      border-color: var(--mh-accent);
    }
    
    #emily-input-container {
      display: flex;
      padding: 15px;
      background: white;
      border-top: 1px solid var(--mh-border);
    }
    
    #question-input {
      flex: 1;
      padding: 10px 15px;
      border: 1px solid var(--mh-border);
      border-radius: 25px;
      font-size: 14px;
      outline: none;
    }
    
    #question-input:focus {
      border-color: var(--mh-accent);
    }
    
    #ask-button {
      background: var(--mh-accent);
      color: white;
      border: none;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      margin-left: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.3s;
    }
    
    #ask-button:hover {
      background: #e68a00;
    }
    
    #ask-button:disabled {
      background: #ccc;
      cursor: not-allowed;
    }
    
    .typing-indicator {
      display: inline-block;
      padding: 10px 15px;
      background: white;
      border: 1px solid var(--mh-border);
      border-radius: 18px;
    }
    
    .typing-indicator span {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--mh-primary);
      margin: 0 2px;
      animation: typing 1.4s infinite;
    }
    
    .typing-indicator span:nth-child(2) {
      animation-delay: 0.2s;
    }
    
    .typing-indicator span:nth-child(3) {
      animation-delay: 0.4s;
    }
    
    @keyframes typing {
      0%, 60%, 100% {
        transform: translateY(0);
        opacity: 0.5;
      }
      30% {
        transform: translateY(-10px);
        opacity: 1;
      }
    }
    
    @media (max-width: 480px) {
      #emily-chatbox {
        width: 100%;
        height: 100%;
        bottom: 0;
        right: 0;
        border-radius: 0;
      }
    }
  `;
  document.head.appendChild(styles);
  
  // Inject HTML
  const chatHTML = `
    <div id="emily-toggle">
      <svg viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
    </div>
    
    <div id="emily-greeting" style="display: none;">
      <strong>Hello! I'm Emily 👋</strong><br>
      I'm here to help with any questions about More House School.
    </div>
    
    <div id="emily-chatbox">
      <div id="emily-header">
        <h2>Chat with Emily</h2>
        <button id="emily-close">✕</button>
      </div>
      
      <div id="chat-history"></div>
      
      <div id="button-grid">
        <button class="quick-reply" data-query="Book a tour">Book a Tour</button>
        <button class="quick-reply" data-query="Admissions process">Admissions</button>
        <button class="quick-reply" data-query="Fees and scholarships">Fees</button>
        <button class="quick-reply" data-query="Curriculum">Curriculum</button>
      </div>
      
      <div id="emily-input-container">
        <input type="text" id="question-input" placeholder="Type your question..." />
        <button id="ask-button">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
    </div>
  `;
  
  const container = document.createElement('div');
  container.innerHTML = chatHTML;
  document.body.appendChild(container);
})();

// ==================== Initialize Session ====================
async function initializeSession() {
  try {
    // Get or create session ID
    sessionId = localStorage.getItem('emily_session_id');
    if (!sessionId) {
      sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      localStorage.setItem('emily_session_id', sessionId);
    }
    
    // Load saved contact details if available
    const savedDetails = localStorage.getItem('emily_parent_details');
    if (savedDetails) {
      try {
        const details = JSON.parse(savedDetails);
        contactDetails.parent_name = details.name || '';
        contactDetails.parent_email = details.email || '';
        contactDetails.parent_phone = details.phone || '';
        console.log('✅ Loaded saved contact details');
      } catch (e) {
        console.error('Failed to parse saved details:', e);
      }
    }
    
    // Initialize with family context if available
    if (FAMILY_ID) {
      const response = await fetch('/api/family/init', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          family_id: FAMILY_ID,
          session_id: sessionId
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Session initialized with family context');
        
        // Update contact details from family context
        if (data.parent_name) contactDetails.parent_name = data.parent_name;
        if (data.parent_email) contactDetails.parent_email = data.parent_email;
        if (data.child_name) contactDetails.child_name = data.child_name;
        if (data.year_group) contactDetails.year_group = data.year_group;
        
        // Show personalized greeting if we have family data
        if (data.parent_name) {
          showPersonalizedGreeting(data.parent_name);
        }
      }
    }
  } catch (e) {
    console.error('Session init error:', e);
  }
}

// ==================== Greeting Bubble ====================
function showPersonalizedGreeting(parentName) {
  const greeting = document.getElementById('emily-greeting');
  if (greeting) {
    greeting.innerHTML = `
      <strong>Hello ${parentName}! 👋</strong><br>
      Welcome back! How can I help you today?
    `;
    greeting.style.display = 'block';
    
    setTimeout(() => {
      greeting.style.display = 'none';
    }, 8000);
  }
}

// Show greeting after delay
setTimeout(() => {
  const greeting = document.getElementById('emily-greeting');
  const chatbox = document.getElementById('emily-chatbox');
  
  if (greeting && !chatbox.classList.contains('open')) {
    // Only show generic greeting if we don't have family data
    if (!contactDetails.parent_name) {
      greeting.style.display = 'block';
      
      setTimeout(() => {
        greeting.style.display = 'none';
      }, 8000);
    }
  }
}, 5000);

// ==================== Chat Functions ====================
async function sendMessage(question, isUserMessage = true) {
  if (!question || isProcessing) return;
  
  isProcessing = true;
  const chatHistory = document.getElementById('chat-history');
  
  // Add user message
  if (isUserMessage) {
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.innerHTML = `<div class="bubble">${escapeHtml(question)}</div>`;
    chatHistory.appendChild(userMsg);
  }
  
  // Show typing indicator
  const typingDiv = document.createElement('div');
  typingDiv.className = 'message bot';
  typingDiv.innerHTML = `
    <div class="typing-indicator">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;
  chatHistory.appendChild(typingDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  
  try {
    // Check if this is an email/tour request
    const emailKeywords = ['book', 'tour', 'visit', 'contact', 'email', 'admissions', 'prospectus', 'apply', 'see the school'];
    const isEmailRequest = emailKeywords.some(keyword => question.toLowerCase().includes(keyword));
    
    // If awaiting contact details, handle them
    if (awaitingContactDetails) {
      handleContactResponse(question);
      typingDiv.remove();
      isProcessing = false;
      return;
    }
    
    const endpoint = isEmailRequest ? '/ask-with-tools' : '/ask';
    
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question: question,
        family_id: FAMILY_ID,
        session_id: sessionId,
        language: 'en'
      })
    });
    
    const data = await response.json();
    
    // Remove typing indicator
    typingDiv.remove();
    
    // Add bot response
    const botMsg = document.createElement('div');
    botMsg.className = 'message bot';
    
    if (data.requires_details && (!contactDetails.parent_email || !contactDetails.parent_phone)) {
      // Need to collect email details
      awaitingContactDetails = true;
      pendingRequest = question;
      
      botMsg.innerHTML = `
        <div class="bubble">
          <strong>Emily:</strong> ${data.answer}
          <div class="contact-form">
            <h4>Please provide your contact details:</h4>
            <input type="text" id="cf-name" placeholder="Your full name" value="${contactDetails.parent_name}" />
            <input type="email" id="cf-email" placeholder="Your email address" value="${contactDetails.parent_email}" />
            <input type="tel" id="cf-phone" placeholder="Your phone number" value="${contactDetails.parent_phone}" />
            <input type="text" id="cf-child" placeholder="Your daughter's name" value="${contactDetails.child_name}" />
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
            <button onclick="submitContactDetails()">Send Tour Request</button>
          </div>
        </div>
      `;
      
      // Pre-select year group if we have it
      if (contactDetails.year_group) {
        setTimeout(() => {
          const yearSelect = document.getElementById('cf-year');
          if (yearSelect) yearSelect.value = contactDetails.year_group;
        }, 100);
      }
    } else {
      botMsg.innerHTML = `<div class="bubble"><strong>Emily:</strong> ${data.answer}</div>`;
      
      // If email was sent successfully, show confirmation
      if (data.answer.includes('sent') && data.answer.includes('admissions')) {
        const confirmDiv = document.createElement('div');
        confirmDiv.className = 'email-confirmation';
        confirmDiv.innerHTML = `✅ Your request has been sent to the admissions team.`;
        botMsg.querySelector('.bubble').appendChild(confirmDiv);
      }
    }
    
    chatHistory.appendChild(botMsg);
    
    // Update quick replies if provided
    if (data.queries && data.queries.length > 0) {
      updateQuickReplies(data.queries.slice(0, 4));
    }
    
  } catch (error) {
    console.error('Error sending message:', error);
    typingDiv.remove();
    
    const errorMsg = document.createElement('div');
    errorMsg.className = 'message bot';
    errorMsg.innerHTML = `
      <div class="bubble">
        <strong>Emily:</strong> I apologize, but I'm having trouble connecting right now. 
        Please try again or contact us directly at office@morehousemail.org.uk
      </div>
    `;
    chatHistory.appendChild(errorMsg);
  }
  
  chatHistory.scrollTop = chatHistory.scrollHeight;
  isProcessing = false;
}

// Handle contact detail collection
function handleContactResponse(response) {
  // Try to extract contact info from response
  const emailMatch = response.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/);
  const phoneMatch = response.match(/\b(?:07\d{9}|01\d{9}|02\d{9}|\+447\d{9})\b/);
  
  if (emailMatch) contactDetails.parent_email = emailMatch[0];
  if (phoneMatch) contactDetails.parent_phone = phoneMatch[0];
  
  // If response contains a name pattern
  const nameMatch = response.match(/(?:my name is|i'm|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/i);
  if (nameMatch) contactDetails.parent_name = nameMatch[1];
  
  // Check if we have enough details now
  if (contactDetails.parent_email && contactDetails.parent_phone && contactDetails.parent_name) {
    awaitingContactDetails = false;
    submitContactDetails();
  } else {
    // Ask for missing details
    const chatHistory = document.getElementById('chat-history');
    const botMsg = document.createElement('div');
    botMsg.className = 'message bot';
    
    let missingFields = [];
    if (!contactDetails.parent_name) missingFields.push('your full name');
    if (!contactDetails.parent_email) missingFields.push('your email address');
    if (!contactDetails.parent_phone) missingFields.push('your phone number');
    
    botMsg.innerHTML = `
      <div class="bubble">
        <strong>Emily:</strong> Thank you! I still need ${missingFields.join(' and ')} to send your request.
      </div>
    `;
    chatHistory.appendChild(botMsg);
  }
}

// Submit email details for tour booking
window.submitContactDetails = async function() {
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
  
  // Store details for future use
  localStorage.setItem('emily_parent_details', JSON.stringify({
    name: contactDetails.parent_name,
    email: contactDetails.parent_email,
    phone: contactDetails.parent_phone,
    child: contactDetails.child_name,
    year: contactDetails.year_group
  }));
  
  // Send via backend
  try {
    const response = await fetch('/submit-contact', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        parent_name: contactDetails.parent_name,
        parent_email: contactDetails.parent_email,
        parent_phone: contactDetails.parent_phone,
        original_request: pendingRequest,
        family_id: FAMILY_ID,
        session_id: sessionId
      })
    });
    
    const result = await response.json();
    
    // Show confirmation
    const chatHistory = document.getElementById('chat-history');
    const confirmMsg = document.createElement('div');
    confirmMsg.className = 'message bot';
    
    if (result.success) {
      confirmMsg.innerHTML = `
        <div class="bubble">
          <strong>Emily:</strong> ✅ Perfect! I've sent your tour request to our admissions team. 
          They'll contact you at ${contactDetails.parent_email} within 24 hours. 
          Is there anything else I can help you with today?
          <div class="email-confirmation">
            Tour request sent for ${contactDetails.child_name || 'your daughter'} 
            ${contactDetails.year_group ? `(${contactDetails.year_group})` : ''}
          </div>
        </div>
      `;
    } else {
      confirmMsg.innerHTML = `
        <div class="bubble">
          <strong>Emily:</strong> ${result.message}
        </div>
      `;
    }
    
    chatHistory.appendChild(confirmMsg);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    
    // Reset state
    awaitingContactDetails = false;
    pendingRequest = '';
    
  } catch (error) {
    console.error('Error sending contact details:', error);
    alert('Sorry, there was an error sending your request. Please try again or contact us directly.');
  }
};

function updateQuickReplies(queries) {
  const grid = document.getElementById('button-grid');
  if (!grid || !queries || queries.length === 0) return;
  
  grid.innerHTML = '';
  queries.forEach(query => {
    const button = document.createElement('button');
    button.className = 'quick-reply';
    button.textContent = query;
    button.onclick = () => sendMessage(query);
    grid.appendChild(button);
  });
}

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

// ==================== Event Listeners ====================
document.addEventListener('DOMContentLoaded', function() {
  // Toggle chat
  const toggle = document.getElementById('emily-toggle');
  const chatbox = document.getElementById('emily-chatbox');
  const closeBtn = document.getElementById('emily-close');
  const input = document.getElementById('question-input');
  const askBtn = document.getElementById('ask-button');
  
  toggle.addEventListener('click', () => {
    chatbox.classList.add('open');
    document.getElementById('emily-greeting').style.display = 'none';
    input.focus();
    
    // Send welcome message if first open
    const chatHistory = document.getElementById('chat-history');
    if (chatHistory.children.length === 0) {
      const welcomeMsg = document.createElement('div');
      welcomeMsg.className = 'message bot';
      
      if (contactDetails.parent_name) {
        welcomeMsg.innerHTML = `
          <div class="bubble">
            <strong>Emily:</strong> Hello ${contactDetails.parent_name}! Welcome back to More House School. 
            How can I help you today?
          </div>
        `;
      } else {
        welcomeMsg.innerHTML = `
          <div class="bubble">
            <strong>Emily:</strong> Hello! I'm Emily, your AI assistant for More House School. 
            How can I help you today? You can ask me about admissions, tours, fees, curriculum, or anything else about our school.
          </div>
        `;
      }
      chatHistory.appendChild(welcomeMsg);
    }
  });
  
  closeBtn.addEventListener('click', () => {
    chatbox.classList.remove('open');
    
    // Save conversation summary if we have a session
    if (sessionId) {
      fetch('/api/conversation/end', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          session_id: sessionId,
          family_id: FAMILY_ID
        })
      }).catch(e => console.error('Failed to save conversation:', e));
    }
  });
  
  // Send message on enter
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !isProcessing) {
      const question = input.value.trim();
      if (question) {
        sendMessage(question);
        input.value = '';
      }
    }
  });
  
  // Send button
  askBtn.addEventListener('click', () => {
    const question = input.value.trim();
    if (question && !isProcessing) {
      sendMessage(question);
      input.value = '';
    }
  });
  
  // Quick reply buttons
  document.querySelectorAll('.quick-reply').forEach(button => {
    button.addEventListener('click', (e) => {
      const query = e.target.getAttribute('data-query') || e.target.textContent;
      if (query) {
        sendMessage(query);
      }
    });
  });
  
  // Initialize session
  initializeSession();
});

// ==================== Auto-save conversation ====================
window.addEventListener('beforeunload', function() {
  if (sessionId) {
    // Use sendBeacon for reliable last-minute requests
    navigator.sendBeacon('/api/conversation/end', JSON.stringify({
      session_id: sessionId,
      family_id: FAMILY_ID
    }));
  }
});

console.log('✅ More House Emily ready - Contact collection and database logging enabled');