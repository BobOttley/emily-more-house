<!-- script.js (self-injecting backup) -->
<script>
/* ────────────────────────────────────────────────────────────
   PEN.ai Chatbot – self-injecting backup (bubble + consent UI)
   - Injects minimal HTML + styles if missing
   - Fetch shim to hit chatbot origin across services
   - Preserves existing behaviour and labels
───────────────────────────────────────────────────────────── */

console.log("✅ PEN.ai self-injecting script.js loaded");

// === 0) Config: set your chatbot backend origin here (or window.PENAI_CHATBOT_ORIGIN) ===
const CHATBOT_ORIGIN = window.PENAI_CHATBOT_ORIGIN || "https://emily-more-house.onrender.com";

// === 1) Fetch shim: route same-origin paths to chatbot backend when site + bot are separate ===
(function () {
  const origFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    if (typeof input === "string" && input.startsWith("/")) input = CHATBOT_ORIGIN + input;
    return origFetch(input, init);
  };
})();

// === 2) Inject minimal styles once (only if not already present) ===
(function ensureStyles() {
  if (document.getElementById("penai-styles")) return;
  const css = `
  :root { --primary-color:#091825; --accent-color:#FF9F1C; --text-color:#fff; --chat-bg:#f9f9f9; --border-color:#e0e0e0; --button-bg:#f0f0f0; --button-fg:#444; }
  #penai-toggle{position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:var(--accent-color);color:#fff;font-size:28px;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2);z-index:100000;}
  #penai-toggle:hover{background:#e98f14;}
  #penai-chatbox{display:none;flex-direction:column;position:fixed;bottom:90px;right:20px;width:360px;max-height:600px;background:#fff;border:1px solid var(--border-color);border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.15);z-index:100000;overflow:hidden;}
  #penai-chatbox.open{display:flex;animation:penai-slideUp .25s ease-out;}
  @keyframes penai-slideUp{from{transform:translateY(16px);opacity:0}to{transform:translateY(0);opacity:1}}
  #penai-header{display:flex;align-items:center;gap:8px;padding:10px 12px;background:var(--primary-color);color:#fff;}
  #penai-header h2{margin:0;font-size:16px;flex:1;}
  #penai-close{background:none;border:none;color:#fff;font-size:18px;cursor:pointer;line-height:1;padding:4px 6px;border-radius:6px;}
  #penai-close:hover{background-color:rgba(255,255,255,.12);}
  #language-selector{font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #ccc;background:#fff;color:#000;}
  .penai-ctl{padding:6px 10px;background:var(--button-bg);color:var(--button-fg);font-size:12px;border-radius:6px;border:1px solid #ccc;cursor:pointer;}
  .penai-ctl.hidden{display:none!important;}
  #welcome-message{padding:10px 15px;background:#f9f9f9;color:#091825;font-size:14px;}
  #chat-history{flex:1;padding:15px 15px 100px;overflow-y:auto;background:var(--chat-bg);border-top:1px solid var(--border-color);border-bottom:1px solid var(--border-color);scroll-behavior:smooth;}
  .message{margin-bottom:12px;padding:10px;font-size:14px;line-height:1.4;max-width:85%;word-wrap:break-word;border:1px solid #e0e0e0;border-radius:8px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.05);}
  .message.user{text-align:right;align-self:flex-end;color:#333;}
  .message.bot{text-align:left;align-self:flex-start;color:#091825;}
  .message.bot p::before{content:"Emily: ";font-weight:700;}
  .chat-link{display:block;margin-top:5px;text-decoration:underline;font-size:14px;color:#0056b3;}
  #button-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;padding:10px;background:#f1f1f1;border-top:1px solid #ddd;border-bottom:1px solid #ddd;}
  .quick-reply{padding:6px 8px;background:var(--button-bg);color:var(--button-fg);font-size:12px;border-radius:20px;border:1px solid #ccc;cursor:pointer;}
  .quick-reply:hover{background:#e0e0e0;}
  #penai-input-container{display:flex;padding:10px;background:#fff;}
  #question-input{flex:1;padding:8px;border:1px solid var(--border-color);border-radius:5px;font-size:14px;}
  #send-button{margin-left:8px;padding:8px 12px;background:var(--primary-color);color:#fff;border:none;border-radius:5px;font-size:14px;cursor:pointer;}
  #send-button:hover{background-color:#0c2235;}
  #thinking-text{padding:10px 15px;display:none;font-style:italic;color:#777;}
  #thinking-text::after{content:"";display:inline-block;width:1em;text-align:left;animation:penai-dots 1.2s steps(3,end) infinite;}
  @keyframes penai-dots{0%{content:""}33%{content:"."}66%{content:".."}100%{content:"..."}}
  .voice-indicator.hidden{display:none!important;}
  `;
  const style = document.createElement("style");
  style.id = "penai-styles";
  style.textContent = css;
  document.head.appendChild(style);
})();

// === 3) Inject required DOM if missing ===
function ensureEl(tag, attrs = {}, parent = document.body) {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "text") el.textContent = v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v);
  });
  parent.appendChild(el);
  return el;
}

function ensureChatSkeleton() {
  // Toggle button
  if (!document.getElementById("penai-toggle")) {
    ensureEl("div", { id: "penai-toggle", "aria-label": "Open chat", text: "💬" });
  }

  // Chatbox container + header + body
  if (!document.getElementById("penai-chatbox")) {
    const box = ensureEl("div", { id: "penai-chatbox", "aria-live": "polite" });

    const header = ensureEl("div", { id: "penai-header" }, box);
    ensureEl("h2", { html: "Chat with Emily" }, header);

    // Language selector
    const lang = ensureEl("select", { id: "language-selector", "aria-label": "Language" }, header);
    lang.innerHTML = `
      <option value="en">🇬🇧 English</option>
      <option value="fr">🇫🇷 Français</option>
      <option value="es">🇪🇸 Español</option>
      <option value="de">🇩🇪 Deutsch</option>
      <option value="zh">🇨🇳 中文</option>
      <option value="ar">🇸🇦 العربية</option>
      <option value="it">🇮🇹 Italiano</option>
      <option value="ru">🇷🇺 Русский</option>
    `;

    // Controls
    ensureEl("button", { id: "start-button", class: "penai-ctl", text: "Start conversation" }, header);
    ensureEl("button", { id: "pause-button", class: "penai-ctl hidden", type: "button", text: "Pause" }, header);
    ensureEl("button", { id: "end-button", class: "penai-ctl hidden", type: "button", text: "End chat" }, header);
    ensureEl("button", { id: "penai-close", type: "button", "aria-label": "Close chat", html: "✕" }, header);

    // Body
    ensureEl("div", { id: "welcome-message" }, box);
    ensureEl("div", { id: "chat-history" }, box);
    ensureEl("div", { id: "thinking-text", text: "Thinking" }, box);
    ensureEl("div", { id: "button-grid" }, box);

    // Input row
    const inputRow = ensureEl("div", { id: "penai-input-container" }, box);
    ensureEl("input", { id: "question-input", type: "text", placeholder: "Ask a question…" }, inputRow);
    ensureEl("button", { id: "send-button", text: "Send" }, inputRow);
  }

  // Voice consent modal + indicator + audio (so realtime-voice-handsfree.js won’t crash)
  if (!document.getElementById("voiceConsent")) {
    const modal = ensureEl("div", { id: "voiceConsent", style: "position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:999999;" });
    const panel = ensureEl("div", { style: "background:#fff;padding:20px;border-radius:12px;max-width:460px;width:92%;box-shadow:0 8px 30px rgba(0,0,0,.2);" }, modal);
    const row = ensureEl("div", { style: "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px;" }, panel);
    ensureEl("h3", { id: "vc-title", style: "margin:0", text: "Enable Emily (voice)" }, row);
    const vcSel = ensureEl("select", { id: "vc-lang", style: "font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #ccc;background:#fff;color:#000;" }, row);
    vcSel.innerHTML = `
      <option value="en">🇬🇧 English</option>
      <option value="fr">🇫🇷 Français</option>
      <option value="es">🇪🇸 Español</option>
      <option value="de">🇩🇪 Deutsch</option>
      <option value="zh">🇨🇳 中文</option>
      <option value="ar">🇸🇦 العربية</option>
      <option value="it">🇮🇹 Italiano</option>
      <option value="ru">🇷🇺 Русский</option>
    `;
    ensureEl("p", { id: "vc-desc", text: "To chat by voice, we need one-time permission to use your microphone and play audio responses." }, panel);
    const lab = ensureEl("label", { style: "display:block;margin:8px 0;" }, panel);
    ensureEl("input", { id: "agreeVoice", type: "checkbox" }, lab);
    ensureEl("span", { id: "vc-agree", html: " I agree to voice processing for this session." }, lab);
    const btns = ensureEl("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:12px;" }, panel);
    ensureEl("button", { id: "cancelVoice", type: "button", text: "Not now" }, btns);
    ensureEl("button", { id: "startVoice", type: "button", text: "Start conversation", disabled: "" }, btns);
  }

  if (!document.getElementById("voiceIndicator")) {
    ensureEl("div", { id: "voiceIndicator", class: "voice-indicator hidden", style: "position:fixed;right:20px;bottom:700px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:6px 10px;font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,.1);", text: "Ready" });
  }
  if (!document.getElementById("aiAudio")) {
    ensureEl("audio", { id: "aiAudio", autoplay: "", playsinline: "" });
  }
}

// === 4) Main app (same behaviour as your existing script) ===
document.addEventListener("DOMContentLoaded", () => {
  // Ensure skeleton exists so the rest never crashes
  ensureChatSkeleton();

  // Cache DOM refs
  const chatbox          = document.getElementById("penai-chatbox");
  const toggleBtn        = document.getElementById("penai-toggle");
  const closeBtn         = document.getElementById("penai-close");
  const history          = document.getElementById("chat-history");
  const input            = document.getElementById("question-input");
  const sendBtn          = document.getElementById("send-button");
  const thinking         = document.getElementById("thinking-text");
  const buttonGrid       = document.getElementById("button-grid");
  const languageSelector = document.getElementById("language-selector");
  const welcomeEl        = document.getElementById("welcome-message");

  // Safety check
  if (!chatbox || !toggleBtn || !closeBtn || !history || !input || !sendBtn || !thinking || !buttonGrid || !languageSelector || !welcomeEl) {
    console.error("🚫 Chatbot elements still missing – aborting.");
    return;
  }

  let currentLanguage = languageSelector.value;

  const UI_TEXT = {
    en: { welcome: "Hi there! Ask me anything about More House School.", placeholder: "Type your question…", enquire: "Enquire now" },
    fr: { welcome: "Bonjour ! Posez-moi vos questions sur More House School.", placeholder: "Tapez votre question…", enquire: "Faire une demande" },
    es: { welcome: "¡Hola! Pregúntame lo que quieras sobre More House School.", placeholder: "Escribe tu pregunta…", enquire: "Consultar ahora" },
    de: { welcome: "Hallo! Fragen Sie mich alles über die More House School.", placeholder: "Geben Sie Ihre Frage ein…", enquire: "Jetzt anfragen" },
    zh: { welcome: "您好！欢迎咨询 More House School。", placeholder: "请输入问题…", enquire: "现在咨询" }
  };

  const LABELS = {
    en: { fees: "Fees", admissions: "Admissions", contact: "Contact", open: "Open Events", enquire: UI_TEXT.en.enquire, prospectus: "Tailored Prospectus" },
    fr: { fees: "Frais", admissions: "Admissions", contact: "Contact", open: "Portes ouvertes", enquire: UI_TEXT.fr.enquire, prospectus: "Prospectus personnalisé" },
    es: { fees: "Tasas", admissions: "Admisiones", contact: "Contacto", open: "Jornadas abiertas", enquire: UI_TEXT.es.enquire, prospectus: "Prospecto personal" },
    de: { fees: "Gebühren", admissions: "Aufnahme", contact: "Kontakt", open: "Tage der offenen Tür", enquire: UI_TEXT.de.enquire, prospectus: "Individuelles Prospekt" },
    zh: { fees: "学费", admissions: "招生", contact: "联系方式", open: "开放日", enquire: UI_TEXT.zh.enquire, prospectus: "定制版招生简章" }
  };

  function clearButtons(){ buttonGrid.innerHTML = ""; }
  function getTranslatedLabel(k){ return LABELS[currentLanguage]?.[k] || k; }

  function createButton(label, query) {
    const btn = document.createElement("button");
    btn.className = "quick-reply";
    btn.innerText = label;
    btn.onclick = () => sendMessage(query);
    buttonGrid.appendChild(btn);
  }

  function showInitialButtons() {
    clearButtons();
    ["fees", "admissions", "contact", "open", "enquire", "prospectus"].forEach(key => {
      createButton(getTranslatedLabel(key), key);
    });
  }

  function appendExchange(questionText, answerText, url = null, linkLabel = null) {
    const exchangeDiv = document.createElement("div");
    exchangeDiv.className = "exchange";

    const userDiv = document.createElement("div");
    userDiv.className = "message user";
    const userP = document.createElement("p");

    const userPrefix = { en:"Me:", fr:"Moi :", de:"Ich:", es:"Yo:", zh:"我：" }[currentLanguage] || "Me:";
    const cleanedQ = questionText.replace(/^Me:|^Moi\s*:|^Ich:|^Yo:|^我：/, '').trim();
    userP.textContent = `${userPrefix} ${cleanedQ}`;
    userDiv.appendChild(userP);

    const botDiv = document.createElement("div");
    botDiv.className = "message bot";
    const botP = document.createElement("p");
    botP.textContent = answerText;
    botDiv.appendChild(botP);

    if (url && linkLabel) {
      const a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.className = "chat-link"; a.textContent = linkLabel;
      botDiv.appendChild(a);
    }

    exchangeDiv.appendChild(userDiv);
    exchangeDiv.appendChild(botDiv);
    history.appendChild(exchangeDiv);
    history.scrollTop = history.scrollHeight;
  }

  function updateWelcome() {
    const t = UI_TEXT[currentLanguage] || UI_TEXT.en;
    welcomeEl.innerText = t.welcome;
    input.placeholder = t.placeholder;
  }

  function renderDynamicButtons(queries = [], queryMap = {}) {
    clearButtons();
    // Always add Enquire first
    const t = UI_TEXT[currentLanguage] || UI_TEXT.en;
    createButton(t.enquire, "enquiry");

    // Add up to 5 contextual
    let count = 0;
    for (const key of queries) {
      if ((key || "").toLowerCase() === "enquiry") continue;
      const label = queryMap[key] || getTranslatedLabel(key);
      createButton(label, key);
      if (++count === 5) break;
    }

    // Pad with defaults if fewer than 5
    if (count < 5) {
      const defaults = ["fees", "admissions", "open", "contact", "prospectus"];
      for (const key of defaults) {
        if (queries.includes(key) || key === "enquiry") continue;
        createButton(getTranslatedLabel(key), key);
        if (++count === 5) break;
      }
    }
  }

  function sendMessage(msgText) {
    const rawQ = (msgText || input.value).trim();
    if (!rawQ) return;

    const cleanedQ = rawQ.replace(/^Me:|^Moi\s*:|^Ich:|^Yo:|^我：/, '').trim();

    input.value = "";
    thinking.style.display = "block";
    welcomeEl.style.display = "none";
    clearButtons();

    fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: cleanedQ, language: currentLanguage })
    })
    .then(r => r.json())
    .then(data => {
      thinking.style.display = "none";
      appendExchange(cleanedQ, data.answer, data.url, data.link_label);
      if (data.queries && data.queries.length) renderDynamicButtons(data.queries, data.query_map);
      else showInitialButtons();
    })
    .catch(err => {
      thinking.style.display = "none";
      console.error("❌ Fetch error:", err);
      appendExchange(cleanedQ, "Something went wrong – please try again.");
      showInitialButtons();
    });
  }

  // Toggle / close
  document.getElementById("penai-toggle").addEventListener("click", () => {
    chatbox.classList.toggle("open");
    if (chatbox.classList.contains("open")) { updateWelcome(); showInitialButtons(); }
  });
  closeBtn.addEventListener("click", () => { chatbox.classList.remove("open"); });

  // Language + send
  languageSelector.addEventListener("change", () => { currentLanguage = languageSelector.value; updateWelcome(); showInitialButtons(); });
  sendBtn.addEventListener("click", () => sendMessage());
  input.addEventListener("keypress", e => { if (e.key === "Enter") sendMessage(); });

  // Init UI
  updateWelcome();
  showInitialButtons();

  // === 5) (Optional) Load the voice helper file automatically from chatbot service if not present ===
  const hasVoice = !!document.querySelector('script[src*="realtime-voice-handsfree.js"]');
  if (!hasVoice) {
    const s = document.createElement("script");
    s.src = CHATBOT_ORIGIN + "/static/realtime-voice-handsfree.js";
    s.async = true;
    document.body.appendChild(s);
  }
});
</script>
