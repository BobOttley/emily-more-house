/* ────────────────────────────────────────────────────────────
   PEN.ai Chatbot – script.js (contextual + fixed prefixes)
───────────────────────────────────────────────────────────── */

console.log("✅ script.js is running");

document.addEventListener("DOMContentLoaded", () => {
  /* ─── Cache DOM refs ───────────────────────────────────── */
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

  if (
    !chatbox || !toggleBtn || !closeBtn || !history || !input || !sendBtn ||
    !thinking || !buttonGrid || !languageSelector || !welcomeEl
  ) {
    console.error("🚫 Missing chatbot elements in HTML. Aborting script.js");
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

  function clearButtons() {
    buttonGrid.innerHTML = "";
  }

  function getTranslatedLabel(k) {
    return LABELS[currentLanguage]?.[k] || k;
  }

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

    const userPrefix = {
      en: "Me:",
      fr: "Moi :",
      de: "Ich:",
      es: "Yo:",
      zh: "我："
    }[currentLanguage] || "Me:";

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
      a.href = url;
      a.target = "_blank";
      a.className = "chat-link";
      a.textContent = linkLabel;
      botDiv.appendChild(a);
    }

    exchangeDiv.appendChild(userDiv);
    exchangeDiv.appendChild(botDiv);
    history.appendChild(exchangeDiv);
    history.scrollTop = history.scrollHeight;
  }

  function updateWelcome() {
    const t = UI_TEXT[currentLanguage];
    welcomeEl.innerText = t.welcome;
    input.placeholder = t.placeholder;
  }

  function renderDynamicButtons(queries, queryMap) {
    clearButtons();

    // Always add Enquire first
    createButton(UI_TEXT[currentLanguage].enquire, "enquiry");

    // Add up to 5 other contextual ones
    let count = 0;
    for (const key of queries) {
      if (key.toLowerCase() === "enquiry") continue;
      const label = queryMap[key] || getTranslatedLabel(key);
      createButton(label, key);
      count++;
      if (count === 5) break;
    }

    // Pad with defaults if fewer than 5
    if (count < 5) {
      const defaults = ["fees", "admissions", "open", "contact", "prospectus"];
      for (const key of defaults) {
        if (queries.includes(key) || key === "enquiry") continue;
        const label = getTranslatedLabel(key);
        createButton(label, key);
        count++;
        if (count === 5) break;
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
        if (data.queries && data.queries.length) {
          renderDynamicButtons(data.queries, data.query_map);
        } else {
          showInitialButtons();
        }
      })
      .catch(err => {
        thinking.style.display = "none";
        console.error("❌ Fetch error:", err);
        appendExchange(cleanedQ, "Something went wrong – please try again.");
        showInitialButtons();
      });
  }

  toggleBtn.addEventListener("click", () => {
    chatbox.classList.toggle("open");
    if (chatbox.classList.contains("open")) {
      updateWelcome();
      showInitialButtons();
    }
  });

  closeBtn.addEventListener("click", () => {
    chatbox.classList.remove("open");
  });

  languageSelector.addEventListener("change", () => {
    currentLanguage = languageSelector.value;
    updateWelcome();
    showInitialButtons();
  });

  sendBtn.addEventListener("click", () => sendMessage());
  input.addEventListener("keypress", e => { if (e.key === "Enter") sendMessage(); });

  updateWelcome();
  showInitialButtons();
});
