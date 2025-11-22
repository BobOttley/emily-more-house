#!/usr/bin/env python3
"""PEN.ai Flask backend – Enhanced conversational voice with memory and proactive engagement"""

import os
import re
import json
import uuid
import pickle
import hashlib
import difflib
from datetime import datetime, date
from typing import Optional, Dict, Any, List

import numpy as np
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparse
from flask import Flask, request, jsonify, send_from_directory, session, redirect
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from flask import make_response

# Gmail API imports
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_AVAILABLE = True
except ImportError:
    print("⚠️ Gmail API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    GMAIL_AVAILABLE = False

# SMTP Email (fallback using booking app config)
import smtplib
GMAIL_USER = os.getenv("GMAIL_USER", "bob.ottley@morehousemail.org.uk")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "bybmrgqhhzxazrpy")
EMAIL_FROM = os.getenv("EMAIL_FROM", "More House CRM <bob.ottley@morehousemail.org.uk>")

# Booking App & Prospectus App URLs
BOOKING_APP_URL = os.getenv("BOOKING_APP_URL", "http://localhost:3002")
PROSPECTUS_APP_URL = os.getenv("PROSPECTUS_APP_URL", "http://localhost:3000")


# ── Boot ──────────────────────────────────────────────────────────────────
print("✅ Flask server is starting")
load_dotenv()

# ── OpenAI client ────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Gmail API Configuration ──────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/callback")
ADMISSIONS_EMAIL = os.getenv("ADMISSIONS_EMAIL", "office@morehousemail.org.uk")

GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

if GMAIL_AVAILABLE and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    print("✅ Gmail API configured")
else:
    if not GMAIL_AVAILABLE:
        print("⚠️ Gmail API libraries not available")
    elif not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("⚠️ Gmail OAuth credentials not set (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)")


# ── Flask app ────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")

# Configure CORS to allow iframe embedding
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": False
    }
})

# ── Conversation Memory Store ────────────────────────────────────────────
conversation_memory = {}  # In production, use Redis or similar

# ── Postgres (optional) ──────────────────────────────────────────────────
HAVE_DB = False
ConnectionPool = None
try:
    from psycopg_pool import ConnectionPool  # type: ignore
    HAVE_DB = True
except Exception:
    print("⚠️ psycopg_pool not installed. Run: pip install psycopg[binary,pool]")

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool: Optional[ConnectionPool] = None
if HAVE_DB and DATABASE_URL:
    try:
        db_pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=5, kwargs={"sslmode": "require"})
        print("🗄️  Postgres pool initialised")
    except Exception as e:
        print("⚠️ Postgres pool init failed:", e)
else:
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL not set. Family context endpoints will be disabled.")

# ── Knowledge base (embeddings already prepared) ────────────────────────
with open("kb_chunks/kb_chunks.pkl", "rb") as f:
    kb_chunks = pickle.load(f)

EMBEDDINGS = np.array([chunk["embedding"] for chunk in kb_chunks], dtype=np.float32)
METADATA = kb_chunks

# ── Conversation Intelligence ────────────────────────────────────────────
class ConversationTracker:
    def __init__(self, session_id: str, family_id: Optional[str] = None):
        self.session_id = session_id
        self.family_id = family_id
        self.started_at = datetime.now()
        self.interactions = []
        self.topics_discussed = set()
        self.concerns = []
        self.child_name = None
        self.parent_name = None
        self.year_group = None
        self.interests = []
        self.high_intent_signals = 0
        self.last_topic = None
        self.emotional_state = "neutral"
        
    def add_interaction(self, question: str, answer: str, topic: Optional[str] = None):
        self.interactions.append({
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "answer": answer[:200],  # Store truncated for memory
            "topic": topic
        })
        
        if topic:
            self.topics_discussed.add(topic)
            self.last_topic = topic
            
        # Detect high intent signals
        high_intent_keywords = ["apply", "visit", "fee", "scholarship", "when can", "how do I", "register"]
        if any(keyword in question.lower() for keyword in high_intent_keywords):
            self.high_intent_signals += 1
            
        # Detect concerns
        concern_keywords = ["worried", "concern", "anxiety", "difficult", "struggle", "help", "support", "nervous"]
        if any(keyword in question.lower() for keyword in concern_keywords):
            self.concerns.append(question)
            self.emotional_state = "concerned"
            
    def get_conversation_summary(self) -> Dict[str, Any]:
        return {
            "session_duration": (datetime.now() - self.started_at).seconds,
            "interaction_count": len(self.interactions),
            "topics": list(self.topics_discussed),
            "high_intent": self.high_intent_signals >= 2,
            "emotional_state": self.emotional_state,
            "concerns": self.concerns[:3],  # Top 3 concerns
            "last_topic": self.last_topic
        }
        
    def should_offer_human_handoff(self) -> bool:
        """Determine if we should offer to connect with admissions"""
        return (
            self.high_intent_signals >= 3 or 
            len(self.concerns) >= 2 or
            len(self.interactions) >= 10 or
            self.emotional_state == "concerned"
        )

# ── Enhanced Response Builder ────────────────────────────────────────────
class ResponseEnhancer:
    def __init__(self):
        self.follow_up_questions = {
            "fees": [
                "Are you also interested in our scholarship opportunities?",
                "Would you like to know about our payment plans?",
                "Shall I explain our bursary programme?"
            ],
            "sports": [
                "What sports does {child_name} enjoy currently?",
                "Is {child_name} interested in competitive teams or recreational activities?",
                "Would you like to know about our sports facilities?"
            ],
            "academic": [
                "What subjects does {child_name} particularly enjoy?",
                "Are you interested in our academic enrichment programmes?",
                "Would you like to see our recent exam results?"
            ],
            "admissions": [
                "Which year group are you considering for entry?",
                "Would you like to book a personal tour?",
                "Shall I explain our application timeline?"
            ],
            "pastoral": [
                "Is there anything specific about {child_name}'s needs I should know?",
                "Would you like to speak with our pastoral team?",
                "Are you interested in our wellbeing programmes?"
            ]
        }
        
        self.reassurance_phrases = [
            "That's a very common concern, and I'm happy to address it...",
            "Many parents ask about this, and it's important to get it right...",
            "I completely understand why you'd want to know about this...",
            "That's an excellent question, and I'm glad you asked..."
        ]
        
    def enhance_for_voice(self, base_answer: str, context: ConversationTracker, family_ctx: Optional[Dict] = None) -> str:
        """Make responses conversational and engaging"""
        
        # Start with acknowledgment
        enhanced = self._add_acknowledgment(context)
        
        # Add the core answer
        enhanced += f" {base_answer}"
        
        # Personalize if we have family context
        if family_ctx and family_ctx.get('child_name'):
            enhanced = enhanced.replace("your child", family_ctx['child_name'])
            enhanced = enhanced.replace("your daughter", family_ctx['child_name'])
            
        # Add reassurance if concerned
        if context.emotional_state == "concerned":
            enhanced = f"{self.reassurance_phrases[len(context.concerns) % len(self.reassurance_phrases)]} {enhanced}"
            
        # Add follow-up question
        follow_up = self._get_follow_up_question(context, family_ctx)
        if follow_up:
            enhanced += f" {follow_up}"
            
        # Offer human handoff if high intent
        if context.should_offer_human_handoff() and len(context.interactions) % 5 == 0:
            enhanced += " By the way, would you like me to arrange for someone from our admissions team to call you directly?"
            
        return enhanced
        
    def _add_acknowledgment(self, context: ConversationTracker) -> str:
        """Add natural acknowledgment based on context"""
        
        if len(context.interactions) == 0:
            return "Hello! What a lovely question to start with."
        elif context.last_topic in str(context.topics_discussed):
            return "Following on from what we discussed..."
        elif context.emotional_state == "concerned":
            return "I can hear this is important to you."
        else:
            acknowledgments = [
                "That's a great question.",
                "I'm glad you asked about that.",
                "Let me tell you about that.",
                "Excellent question.",
                "Many families ask about this."
            ]
            return acknowledgments[len(context.interactions) % len(acknowledgments)]
            
    def _get_follow_up_question(self, context: ConversationTracker, family_ctx: Optional[Dict] = None) -> str:
        """Generate contextual follow-up question"""
        
        if not context.last_topic:
            return "Is there anything specific you'd like to know about More House?"
            
        topic_key = self._categorize_topic(context.last_topic)
        questions = self.follow_up_questions.get(topic_key, ["What else would you like to know?"])
        
        question = questions[len(context.interactions) % len(questions)]
        
        # Personalize with child's name
        if family_ctx and family_ctx.get('child_name'):
            question = question.replace("{child_name}", family_ctx['child_name'])
        else:
            question = question.replace("{child_name}", "your daughter")
            
        return question
        
    def _categorize_topic(self, topic: str) -> str:
        """Categorize topic for follow-up selection"""
        topic_lower = topic.lower() if topic else ""
        
        if any(word in topic_lower for word in ["fee", "cost", "price", "burs", "scholar"]):
            return "fees"
        elif any(word in topic_lower for word in ["sport", "athletic", "team", "football", "netball"]):
            return "sports"
        elif any(word in topic_lower for word in ["academic", "subject", "curriculum", "exam", "result"]):
            return "academic"
        elif any(word in topic_lower for word in ["admission", "apply", "join", "entry", "register"]):
            return "admissions"
        elif any(word in topic_lower for word in ["pastoral", "care", "wellbeing", "support", "help"]):
            return "pastoral"
        else:
            return "general"

# ── Utilities ────────────────────────────────────────────────────────────
def remove_bullets(text: str) -> str:
    return re.sub(r"^[\s]*([•\-\*\d]+\s*)+", "", text, flags=re.MULTILINE)

def format_response(text: str) -> str:
    return re.sub(r"\n{2,}", "\n\n", text.strip())

def safe_trim(v: Any, limit: int = 120) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return (s if len(s) <= limit else s[:limit] + "…")

# ── Embedding function ───────────────────────────────────────────────────
def embed_text(text: str) -> np.ndarray:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text.strip()
    )
    return np.array(resp.data[0].embedding, dtype=np.float32)

# ── Vector search ────────────────────────────────────────────────────────
def vector_search(query: str, k: int = 10):
    q_vec = embed_text(query)
    norm_q = np.linalg.norm(q_vec) + 1e-10
    norms = np.linalg.norm(EMBEDDINGS, axis=1) + 1e-10
    sims = (EMBEDDINGS @ q_vec) / (norms * norm_q)
    idxs = np.argsort(sims)[::-1][:k]
    return sims, idxs

# ── DB helpers ───────────────────────────────────────────────────────────
def fetch_family_context(family_id: str) -> Optional[Dict[str, Any]]:
    if not db_pool:
        return None
    sql = """
    SELECT
      id AS family_id,
      COALESCE(child_first_name, child_name)  AS child_first_name,
      COALESCE(child_last_name, '')           AS child_last_name,
      COALESCE(year_group, entry_year, '')    AS year_group,
      COALESCE(boarding_status, '')           AS boarding_status,
      COALESCE(main_interests, '')            AS main_interests,
      COALESCE(parent_name, contact_name, '') AS parent_name,
      COALESCE(parent_email, contact_email, '') AS parent_email,
      COALESCE(country, '')                   AS country,
      COALESCE(language_pref, 'en')           AS language_pref
    FROM public.inquiries
    WHERE id = %s
    LIMIT 1;
    """
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (family_id,))
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d.name for d in cur.description]
                data = dict(zip(cols, row))
                child_name = " ".join(filter(None, [
                    safe_trim(data.get("child_first_name")),
                    safe_trim(data.get("child_last_name"))
                ])).strip()
                summary = {
                    "family_id": data.get("family_id"),
                    "child_name": child_name or None,
                    "year_group": safe_trim(data.get("year_group")),
                    "boarding_status": safe_trim(data.get("boarding_status")),
                    "interests": safe_trim(data.get("main_interests")),
                    "country": safe_trim(data.get("country")),
                    "language_pref": (data.get("language_pref") or "en")[:5],
                    "parent_name": data.get("parent_name"),
                    "parent_email": data.get("parent_email"),
                }
                return summary
    except Exception as e:
        print("DB fetch error:", e)
        return None

def log_interaction_to_db(family_id: str, question: str, answer: str, metadata: Dict):
    """Log interactions for admissions dashboard"""
    if not db_pool or not family_id:
        return
        
    sql = """
    INSERT INTO chat_interactions 
    (family_id, question, answer, topic, sentiment, timestamp, metadata)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    family_id,
                    question[:500],
                    answer[:500],
                    metadata.get('topic'),
                    metadata.get('sentiment'),
                    datetime.now(),
                    json.dumps(metadata)
                ))
                conn.commit()
    except Exception as e:
        print(f"Failed to log interaction: {e}")

# ── Enhanced Answer Logic ────────────────────────────────────────────────
from static_qa_config import STATIC_QA_LIST as STATIC_QAS
from contextualButtons import get_suggestions
from language_engine import translate

response_enhancer = ResponseEnhancer()

# ── Open Days Scraper + Cache ───────────────────────────────────────────
OPEN_DAYS_URL = "https://www.morehouse.org.uk/admissions/joining-more-house/"
OPEN_DAYS_CACHE = "/tmp/open_days.json"  # or use S3 path
REFRESH_SECRET = os.getenv("OPEN_DAYS_REFRESH_SECRET", "change-me")

def get_open_day_events():
    """Read open days cache and return sorted events"""
    try:
        with open(OPEN_DAYS_CACHE, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload.get("events", [])
    except Exception as e:
        print("⚠️ Could not read open days cache:", e)
        return []

def find_best_answer(question, language='en', session_id=None, family_id=None):
    q_lower = question.strip().lower()
    print(f"🧠 Processing: {q_lower} | Lang: {language} | Session: {session_id}")

    # PRIORITY: Check for booking/visit intent FIRST before any other logic
    # But distinguish between "asking about dates" vs "wanting to book"
    info_phrases = ["when", "what date", "what time", "upcoming", "tell me about"]
    asking_for_info = any(phrase in q_lower for phrase in info_phrases)

    booking_triggers = [
        "book", "booking", "visit school", "tour school",
        "book open day", "private tour", "arrange visit", "i want to", "can i", "schedule"
    ]

    # Simple affirmative responses that likely mean "yes, I want to book"
    affirmative_booking = q_lower in ['yes', 'yes please', 'yeah', 'sure', 'ok', 'okay', 'definitely', 'absolutely']

    if (any(trigger in q_lower for trigger in booking_triggers) and not asking_for_info) or affirmative_booking:
        print(f"🎯 BOOKING TRIGGER DETECTED: {q_lower}")
        booking_answer = "I'd love to help you book an open day! Let me guide you through the process. Have you already registered or enquired with us before?"
        return booking_answer, None, "Book Open Day", "book_open_day", "booking_trigger"

    # Get or create conversation tracker
    if session_id:
        if session_id not in conversation_memory:
            conversation_memory[session_id] = ConversationTracker(session_id, family_id)
        tracker = conversation_memory[session_id]
    else:
        tracker = ConversationTracker(str(uuid.uuid4()), family_id)

    # Static exact match
    for qa in STATIC_QAS:
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        if q_lower in [v.lower() for v in variants]:
            print(f"✅ Exact match on: {qa['key']}")
            answer = qa['answer']
            
            # Track interaction
            tracker.add_interaction(question, answer, qa['key'])
            
            # Enhance for voice
            if session_id:  # Only enhance for voice sessions
                family_ctx = fetch_family_context(family_id) if family_id else None
                answer = response_enhancer.enhance_for_voice(answer, tracker, family_ctx)
                
            return answer, qa.get('url'), qa.get('label'), qa['key'], "static"

    # Fuzzy static match
    best_score = 0
    best_match = None
    for qa in STATIC_QAS:
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        for var in variants:
            score = difflib.SequenceMatcher(None, q_lower, var.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = qa
                
    if best_match and best_score > 0.8:
        print(f"🟡 Fuzzy match on: {best_match['key']} (score {best_score:.2f})")
        answer = best_match['answer']
        
        # Track interaction
        tracker.add_interaction(question, answer, best_match['key'])
        
        # Enhance for voice
        if session_id:
            family_ctx = fetch_family_context(family_id) if family_id else None
            answer = response_enhancer.enhance_for_voice(answer, tracker, family_ctx)
            
        return answer, best_match.get('url'), best_match.get('label'), best_match['key'], "fuzzy"

    # RAG fallback with GPT summarisation
    sims, idxs = vector_search(question)
    if len(idxs) > 0:
        print(f"🔵 Vector match (cos={sims[idxs[0]]:.2f})")
        contexts = [METADATA[i].get("text", "") for i in idxs[:10]]
        
        # Build conversation-aware prompt
        conversation_context = ""
        if tracker and len(tracker.interactions) > 0:
            recent = tracker.interactions[-3:]  # Last 3 interactions
            conversation_context = "Previous context: " + " | ".join([f"Q: {i['question'][:50]}" for i in recent])
        
        prompt = (
            f"{conversation_context}\n\n" if conversation_context else ""
        ) + (
            "Use ONLY the passages below to answer.\n\n"
            + "\n---\n".join(contexts)
            + f"\n\nQuestion: {question}\nAnswer:"
        )
        
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a warm, helpful British school assistant. Be conversational."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = chat.choices[0].message.content
        clean = format_response(remove_bullets(raw))
        
        # Track interaction
        tracker.add_interaction(question, clean, "general")
        
        # Enhance for voice
        if session_id:
            family_ctx = fetch_family_context(family_id) if family_id else None
            clean = response_enhancer.enhance_for_voice(clean, tracker, family_ctx)
        
        # Translate if needed
        if language != "en":
            try:
                clean = translate(clean, language)
            except Exception as e:
                print("Translate error:", e)

        meta = METADATA[idxs[0]]
        return clean, meta.get('url'), meta.get('label') or "View document", None, "rag"

    # No match
    print("❌ No suitable match found.")
    no_match_response = "I'm sorry, I don't have that specific information to hand. Would you like me to connect you with our admissions team who can help?"
    
    if session_id:
        tracker.add_interaction(question, no_match_response, "unknown")
        
    return no_match_response, None, None, None, "none"

def _extract_events_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ").split())

    pat = re.compile(
        r"(Open (?:Morning|Evening|Day|Event|Sixth Form Open (?:Morning|Evening)))"
        r"\s*[–-]\s*([A-Za-z]+ \d{1,2} [A-Za-z]+ \d{4})",
        re.I
    )

    unique = {}  # key: (event_name, date_iso) -> event dict
    for name, date_str in pat.findall(text):
        dt = dateparse.parse(date_str, dayfirst=True)
        if dt.date() < date.today():
            continue

        # Normalise
        event_name = " ".join(name.strip().title().split())
        date_iso = dt.date().isoformat()
        key = (event_name, date_iso)

        # Keep the first seen (or update booking_link if you later add a better one)
        if key not in unique:
            unique[key] = {
                "event_name": event_name,
                "date_iso": date_iso,
                "date_human": dt.strftime("%A %d %B %Y"),
                "booking_link": OPEN_DAYS_URL
            }

    # Return sorted, de-duplicated list
    events = sorted(unique.values(), key=lambda e: (e["date_iso"], e["event_name"]))
    return events

def _write_cache(payload: dict):
    with open(OPEN_DAYS_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _read_cache():
    try:
        with open(OPEN_DAYS_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": [], "last_checked": None, "source_url": OPEN_DAYS_URL}
        
# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/tasks/refresh-open-days", methods=["POST"])
def refresh_open_days():
    if request.headers.get("X-Refresh-Secret") != REFRESH_SECRET:
        return jsonify({"ok": False, "error": "unauthorised"}), 401
    r = requests.get(OPEN_DAYS_URL, timeout=20)
    r.raise_for_status()
    events = _extract_events_from_html(r.text)
    payload = {
        "source_url": OPEN_DAYS_URL,
        "last_checked": datetime.utcnow().isoformat() + "Z",
        "events": events
    }
    _write_cache(payload)
    return jsonify({"ok": True, "count": len(events)})

@app.route("/open-days", methods=["GET"])
def get_open_days():
    return jsonify(_read_cache())

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/static/script.js')
def serve_script_js():
    try:
        with open('static/script.js', 'r', encoding='utf-8') as f:
            content = f.read()
        response = make_response(content)
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Access-Control-Allow-Origin'] = '*'
        print(f"Serving script.js (size: {len(content)} bytes)")
        return response
    except Exception as e:
        print(f"Error serving script.js: {e}")
        return "console.error('Failed to load script');", 500

@app.route('/static/realtime-voice-handsfree.js')
def serve_voice_js():
    try:
        with open('static/realtime-voice-handsfree.js', 'r', encoding='utf-8') as f:
            content = f.read()
        response = make_response(content)
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Access-Control-Allow-Origin'] = '*'
        print(f"Serving realtime-voice-handsfree.js (size: {len(content)} bytes)")
        return response
    except Exception as e:
        print(f"Error serving voice script: {e}")
        return "console.error('Failed to load voice script');", 500

@app.route('/family/<family_id>', methods=['GET'])
def get_family(family_id):
    if not db_pool:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    ctx = fetch_family_context(family_id)
    if not ctx:
        return jsonify({"ok": False, "error": "Family not found"}), 404
    return jsonify({"ok": True, "family": ctx})

# ══════════════════════════════════════════════════════════════════════════
# GMAIL API - OAUTH & EMAIL SENDING
# ══════════════════════════════════════════════════════════════════════════

@app.route("/auth/google/login")
def auth_google_login():
    """Initiate Google OAuth flow for Gmail access"""
    if not GMAIL_AVAILABLE or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Gmail API not configured"}), 503
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=GMAIL_SCOPES
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route("/auth/callback")
def auth_google_callback():
    """Handle Google OAuth callback"""
    if not GMAIL_AVAILABLE:
        return jsonify({"error": "Gmail API not available"}), 503
    
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_REDIRECT_URI]
                }
            },
            scopes=GMAIL_SCOPES,
            state=session.get('oauth_state')
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        session['google_token'] = credentials.token
        session['google_refresh_token'] = credentials.refresh_token
        session['google_token_uri'] = credentials.token_uri
        session['google_authenticated'] = True
        
        print("✅ Gmail OAuth successful")
        return redirect('/')
        
    except Exception as e:
        print(f"❌ OAuth error: {e}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 400

@app.route("/auth/status")
def auth_status():
    """Check Gmail authentication status"""
    return jsonify({
        "authenticated": session.get('google_authenticated', False),
        "email_configured": ADMISSIONS_EMAIL
    })

@app.route("/auth/logout")
def auth_logout():
    """Logout and clear Gmail session"""
    session.pop('google_token', None)
    session.pop('google_refresh_token', None)
    session.pop('google_authenticated', None)
    return jsonify({"ok": True, "message": "Logged out"})

def get_gmail_service():
    """Get authenticated Gmail API service"""
    if not GMAIL_AVAILABLE or not session.get('google_token'):
        return None
    
    try:
        creds = Credentials(
            token=session['google_token'],
            refresh_token=session.get('google_refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GMAIL_SCOPES
        )
        
        service = build('gmail', 'v1', credentials=creds)
        return service
        
    except Exception as e:
        print(f"❌ Gmail service error: {e}")
        return None

def send_email_via_gmail(to_email: str, cc_email: str, subject: str, body_html: str):
    """
    Send email via Gmail SMTP

    Args:
        to_email: Recipient (admissions)
        cc_email: CC recipient (parent)
        subject: Email subject
        body_html: HTML body content

    Returns:
        (success: bool, message: str)
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        return False, "Gmail SMTP credentials not configured"

    try:
        message = MIMEMultipart('alternative')
        message['From'] = f"More House CRM <{gmail_user}>"
        message['To'] = to_email
        message['Cc'] = cc_email
        message['Subject'] = subject

        html_part = MIMEText(body_html, 'html')
        message.attach(html_part)

        # Send via SMTP
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            recipients = [to_email, cc_email]
            server.sendmail(gmail_user, recipients, message.as_string())

        print(f"✅ Email sent to {to_email} (CC: {cc_email})")
        return True, "Email sent successfully"

    except Exception as e:
        print(f"❌ SMTP error: {e}")
        return False, f"SMTP error: {str(e)}"

@app.route("/realtime/tool/get_open_days", methods=["POST"])
def realtime_tool_get_open_days():
    """Tool endpoint for realtime model - now triggers booking flow"""
    # Return booking trigger message instead of scraped events
    return jsonify({
        "ok": True,
        "trigger_booking": True,
        "message": "I'd love to help you book an open day! Let me guide you through the process. Have you already registered or enquired with us before?"
    })

@app.route("/realtime/tool/kb_search", methods=["POST"])
def realtime_tool_kb_search():
    """Knowledge base search tool for realtime voice sessions"""
    data = request.json or {}
    query = data.get('query', '').strip()

    if not query:
        return jsonify({
            "ok": False,
            "error": "No query provided"
        }), 400

    try:
        # Perform vector search on knowledge base
        print(f"🔍 Voice KB search: {query}")
        sims, idxs = vector_search(query, k=5)  # Get top 5 results

        if len(idxs) == 0:
            return jsonify({
                "ok": True,
                "answer": "I don't have specific information about that. Would you like me to connect you with our admissions team?",
                "source": "no_match"
            })

        # Get the most relevant chunks
        contexts = [METADATA[i].get("text", "") for i in idxs[:5]]

        # Build a concise answer using GPT
        prompt = (
            "Use ONLY the passages below to answer the query concisely (2-3 sentences max for voice).\n\n"
            + "\n---\n".join(contexts)
            + f"\n\nQuery: {query}\nConcise answer (2-3 sentences):"
        )

        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful British school assistant. Be concise and conversational. Use British English."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200  # Keep it short for voice
        )

        answer = chat.choices[0].message.content.strip()

        # Get metadata for reference
        meta = METADATA[idxs[0]]

        print(f"✅ KB answer: {answer[:100]}...")

        return jsonify({
            "ok": True,
            "answer": answer,
            "source": "knowledge_base",
            "url": meta.get('url'),
            "similarity": float(sims[idxs[0]])
        })

    except Exception as e:
        print(f"❌ KB search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

@app.route("/realtime/tool/book_staff_meeting", methods=["POST"])
def realtime_tool_book_staff_meeting():
    """Book staff meeting tool for realtime voice sessions"""
    data = request.json or {}

    parent_name = data.get('parent_name', '').strip()
    parent_email = data.get('parent_email', '').strip()
    parent_phone = data.get('parent_phone', '').strip()
    staff_member = data.get('staff_member', '').strip()
    purpose = data.get('purpose', '').strip()
    availability = data.get('availability', '').strip()

    if not all([parent_name, parent_email, parent_phone, staff_member, purpose, availability]):
        return jsonify({
            "ok": False,
            "error": "Missing required fields"
        }), 400

    try:
        print(f"📅 Voice meeting request: {parent_name} wants to meet {staff_member} to {purpose}")

        # Build email content
        subject = f"Meeting Request: {parent_name} - {staff_member.title()}"
        body_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #091825;">Meeting Request - More House School</h2>

            <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Parent Name:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{parent_name}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Email:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{parent_email}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Phone:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{parent_phone}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Requested Meeting With:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{staff_member.title()}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Purpose:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{purpose}</td>
              </tr>
              <tr>
                <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Availability:</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{availability}</td>
              </tr>
            </table>

            <p style="margin-top: 20px;">
              <strong>Action Required:</strong> Please contact {parent_name} to arrange a meeting with {staff_member} to {purpose}.
            </p>

            <p style="color: #666; font-size: 12px; margin-top: 30px;">
              <em>This meeting request was sent via Emily Voice, the More House AI assistant.</em>
            </p>
          </body>
        </html>
        """

        # Send email
        success, result_msg = send_email_via_gmail(
            to_email=ADMISSIONS_EMAIL,
            cc_email=parent_email,
            subject=subject,
            body_html=body_html
        )

        if success:
            print(f"✅ Voice meeting request email sent to {ADMISSIONS_EMAIL}")
            return jsonify({
                "ok": True,
                "message": f"Meeting request submitted successfully. The school office will contact you to confirm a time."
            })
        else:
            print(f"❌ Failed to send meeting request email: {result_msg}")
            return jsonify({
                "ok": False,
                "error": f"Failed to send email: {result_msg}"
            }), 500

    except Exception as e:
        print(f"❌ Error booking staff meeting: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id') or str(uuid.uuid4())

    # Check if question is asking for open day dates (informational query, not booking)
    q_lower = question.lower().strip('?!.,')
    # Normalize spacing and handle typos like "oopen" -> "open"
    q_normalized = ' '.join(q_lower.split())  # Remove extra spaces
    q_normalized = q_normalized.replace('oopen', 'open')  # Fix common typo

    print(f"📅 Checking for open day dates query: '{q_normalized}'")

    # Phrases that indicate someone is asking ABOUT open days (not booking)
    info_query_phrases = [
        'when are the open day',
        'when are open days',
        'when is the open day',
        'when is the next open day',
        'what open day',
        'what open days',
        'what are the open day',
        'open day dates',
        'open days dates',
        'upcoming open day',
        'upcoming open days',
        'tell me about open days',
        'do you have open days',
        'are there any open days',
        'what are the open day dates',
        'open events',
        'view open events',
        'show open days'
    ]

    # Also check for key word combinations that indicate info query
    has_when_what = any(word in q_normalized for word in ['when', 'what', 'which'])
    has_open_day = 'open day' in q_normalized or 'open' in q_normalized

    # Check if message is exactly "open" or contains info query phrases
    if q_normalized == 'open':
        is_info_query = True
    elif has_when_what and has_open_day:
        # Catches "when are the oopen days" or other variations
        is_info_query = True
    else:
        is_info_query = any(phrase in q_normalized for phrase in info_query_phrases)

    # Only skip if it's JUST booking without asking about dates/times
    # e.g., "book an open day" vs "when are the open days to book"
    is_pure_booking = any(word in q_normalized for word in ['book', 'booking', 'reserve', 'schedule']) and not is_info_query

    if is_info_query:
        print(f"✅ MATCH! Fetching real open day dates from database...")
        # Fetch actual open day events
        try:
            import requests
            # Call booking app directly instead of calling ourselves
            response = requests.get(
                f"{BOOKING_APP_URL}/api/events",
                params={
                    "schoolId": 2,  # More House
                    "eventType": "open_day",
                    "status": "published"
                },
                timeout=10
            )
            if response.ok:
                events_data = response.json()
                # Parse ISO format date properly
                today = date.today()
                events = []
                for e in events_data.get('events', []):
                    event_date_str = e['event_date'].split('T')[0]  # Get just the date part from ISO format
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                    if event_date >= today:
                        events.append(e)

                if events:
                    event_list = []
                    for e in events[:5]:  # Show max 5
                        event_date_str = e['event_date'].split('T')[0]
                        event_date = datetime.strptime(event_date_str, '%Y-%m-%d')

                        # Format date nicely
                        formatted_date = event_date.strftime('%A, %d %B %Y')

                        # Format time nicely (remove seconds, convert to 12-hour format)
                        try:
                            time_obj = datetime.strptime(e['start_time'], '%H:%M:%S')
                            formatted_time = time_obj.strftime('%I:%M %p').lstrip('0')  # Remove leading zero
                        except:
                            formatted_time = e['start_time']

                        event_list.append(f"{e['title']} - {formatted_date} at {formatted_time}")

                    answer = "We have the following open days coming up:\n\n" + "\n\n".join(event_list)
                    answer += "\n\nWould you like to book one of these?"
                else:
                    answer = "We don't have any open days scheduled at the moment, but I'd be happy to arrange a private tour for you. Would you like to book a visit?"

                return jsonify({
                    'answer': answer,
                    'url': None,
                    'link_label': None,
                    'queries': ['book open day', 'private tour', 'enquiry'],
                    'query_map': {'book open day': 'Book Open Day', 'private tour': 'Private Tour', 'enquiry': 'Make an Enquiry'},
                    'source': 'live_events',
                    'family_used': bool(family_id),
                    'session_id': session_id
                })
        except Exception as e:
            print(f"Error fetching events: {e}")
            import traceback
            traceback.print_exc()
            # Fall through to normal answer

    answer, url, label, matched_key, source = find_best_answer(
        question, language, session_id, family_id
    )

    # Log to database for admissions dashboard
    if family_id:
        tracker = conversation_memory.get(session_id)
        metadata = {
            'source': source,
            'topic': matched_key,
            'sentiment': tracker.emotional_state if tracker else 'neutral',
            'session_id': session_id,
            'high_intent': tracker.high_intent_signals > 0 if tracker else False
        }
        log_interaction_to_db(family_id, question, answer, metadata)

    suggestions = get_suggestions(matched_key or question, language=language)
    queries = [s['query'] for s in suggestions]
    query_map = {s['query']: s['label'] for s in suggestions}

    return jsonify({
        'answer': answer,
        'url': url,
        'link_label': label,
        'queries': queries,
        'query_map': query_map,
        'source': source,
        'family_used': bool(family_id),
        'session_id': session_id
    })

def _format_button_suggestions(suggestions):
    """Convert button suggestions from get_suggestions() to frontend format

    Args:
        suggestions: List of dicts with 'label' and 'query' keys

    Returns:
        tuple: (queries_list, query_map_dict)
    """
    queries = [s['query'] for s in suggestions]
    query_map = {s['query']: s['label'] for s in suggestions}
    return queries, query_map

@app.route('/ask-with-tools', methods=['POST'])
def ask_with_tools():
    """AI-powered endpoint with knowledge base integration and tool support"""
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id') or str(uuid.uuid4())

    if not question:
        return jsonify({"answer": "Please ask a question.", "queries": []})

    q_lower = question.strip().lower()
    print(f"🤖 AI-powered /ask-with-tools: '{q_lower}' | Language: {language}")

    # Topics that should ALWAYS use AI knowledge base for rich, detailed answers
    # (not just redirect to pages)
    AI_ONLY_TOPICS = [
        'pastoral care', 'safeguarding', 'learning support', 'academic life',
        'subjects', 'results', 'inspection', 'sixth form',
        'sport', 'co-curricular', 'faith life', 'facilities',
        'location', 'transport', 'term dates', 'uniform', 'lunch menu',
        'ethos', 'calendar', 'policies', 'virtual tour',
        'fees', 'bursaries', 'scholarships',  # Use AI for detailed fees info
        'admissions', 'entry points', 'registration deadlines'  # Use AI for admissions details
    ]

    # STEP 1: Try static Q&A only for action-oriented queries (fees, enquiry, booking, etc.)
    # Skip static for informational topics - they should use AI knowledge base
    use_static = True
    if q_lower in AI_ONLY_TOPICS:
        use_static = False
        print(f"🎯 '{q_lower}' is an AI-only topic - skipping static Q&A")

    if use_static:
        for qa in STATIC_QAS:
            if qa['language'] != language:
                continue
            variants = [qa['key']] + qa.get('variants', [])
            if q_lower in [v.lower() for v in variants]:
                print(f"✅ Static match: {qa['key']}")
                answer = qa['answer']

                # Get contextual buttons
                suggestions = get_suggestions(qa['key'], language)
                queries, query_map = _format_button_suggestions(suggestions)

                return jsonify({
                    "answer": answer,
                    "url": qa.get('url'),
                    "label": qa.get('label'),
                    "queries": queries,
                    "query_map": query_map,
                    "session_id": session_id,
                    "source": "static"
                })

    # STEP 2: Check for open days query (special case with live database)
    q_normalized = q_lower.replace('oopen', 'open')

    info_query_phrases = [
        'when are open',
        'when is open',
        'what are open',
        'when are the open',
        'when is the open',
        'open events',
        'open days',
        'open mornings',
        'upcoming open'
    ]

    has_when_what = any(word in q_normalized for word in ['when', 'what', 'upcoming', 'tell me'])
    has_open_day = any(word in q_normalized for word in ['open day', 'open event', 'open morning'])

    if q_normalized == 'open':
        is_info_query = True
    else:
        is_info_query = any(phrase in q_normalized for phrase in info_query_phrases)

    if not is_info_query and has_when_what and has_open_day:
        is_info_query = True

    is_pure_booking = any(word in q_normalized for word in ['book', 'booking', 'reserve', 'schedule']) and not is_info_query

    if is_info_query:
        print(f"✅ Open days query detected - fetching from database...")
        try:
            response = requests.get(
                f"{BOOKING_APP_URL}/api/events",
                params={
                    "schoolId": 2,
                    "eventType": "open_day",
                    "status": "published"
                },
                timeout=10
            )

            if response.status_code == 200:
                events = response.json()
                if events:
                    event_list = []
                    for e in events:
                        formatted_date = datetime.strptime(e['event_date'], '%Y-%m-%d').strftime('%A %d %B %Y')
                        try:
                            time_obj = datetime.strptime(e['start_time'], '%H:%M:%S')
                            formatted_time = time_obj.strftime('%I:%M %p').lstrip('0')
                        except:
                            formatted_time = e['start_time']

                        event_list.append(f"{e['title']} - {formatted_date} at {formatted_time}")

                    answer = "We have the following open days coming up:\n\n" + "\n\n".join(event_list)
                    suggestions = get_suggestions('open events', language)
                    queries, query_map = _format_button_suggestions(suggestions)

                    return jsonify({
                        "answer": answer,
                        "queries": queries,
                        "query_map": query_map,
                        "session_id": session_id,
                        "source": "database"
                    })
        except Exception as e:
            print(f"❌ Error fetching open days: {e}")

    # STEP 3: Use knowledge base search (RAG) with AI
    print(f"🔍 Searching knowledge base for: {question}")
    sims, idxs = vector_search(question)

    if len(idxs) == 0:
        print("❌ No knowledge base matches found")
        answer = "I'm sorry, I don't have that specific information to hand. Would you like me to connect you with our admissions team who can help?"
        suggestions = get_suggestions(question, language)
        queries, query_map = _format_button_suggestions(suggestions)

        return jsonify({
            "answer": answer,
            "queries": queries,
            "query_map": query_map,
            "session_id": session_id,
            "source": "none"
        })

    # Got knowledge base matches - build context
    print(f"🔵 Found {len(idxs)} knowledge base matches (best: {sims[idxs[0]]:.2f})")
    contexts = [METADATA[i].get("text", "") for i in idxs[:10]]

    # Get family context
    family_ctx = fetch_family_context(family_id) if family_id else None

    # Build enhanced system prompt with STRICT knowledge base restriction
    system_prompt = f"""You are Emily, the AI assistant for More House School.
Be warm, helpful, and professional. Use British spelling.
Language: {language}

CRITICAL: You must ONLY use information from the provided knowledge base passages below.
DO NOT use any external knowledge or make assumptions beyond what is explicitly stated in these passages.
If the answer is not in the passages, say you don't have that specific information.

FORMATTING RULES:
- DO NOT use markdown formatting (no **, __, *, etc.)
- Use plain text only
- For lists, use simple dashes or numbers
- Separate sections with blank lines, not with bold headings
- Keep formatting clean and simple for text display

KNOWLEDGE BASE:
---
{chr(10).join(['---' + chr(10) + ctx for ctx in contexts])}
---

CONVERSATION MEMORY:
You have access to the conversation history. Use it to remember:
- What the parent asked for in previous messages
- Information they've already provided (name, email, phone, etc.)
- The context of the current conversation
DO NOT ask for information the parent has already provided in earlier messages.

AVAILABLE ACTIONS:
You can help parents in the following ways:
1. Book tours and visits - use the send_enquiry_email function
2. Book meetings with staff members - use the book_staff_meeting function when they want to meet with specific staff (registrar, head, bursar, etc.)
3. Answer questions about the school using only the knowledge base provided

When a parent wants to book a meeting with a staff member:
- First, note which staff member they want to meet and why (from their request)
- Ask for any missing information: name, email, phone, AND their availability/preferred times
- Example: "Could you please provide your full name, email, phone number, and some times that work for you (e.g., weekday mornings, next week afternoons)?"
- Once you have ALL required information (including availability), call the book_staff_meeting function
- Remember: staff_member and purpose may have been mentioned earlier in the conversation!
- IMPORTANT: After calling book_staff_meeting, say "I've submitted your meeting request" NOT "I've arranged a meeting" - the school office will contact them to confirm a time
"""

    if family_ctx:
        child_name = family_ctx.get('child_name', 'your daughter')
        parent_name = family_ctx.get('parent_name', 'Parent')
        year_group = family_ctx.get('year_group', '')

        system_prompt += f"""
FAMILY CONTEXT:
Parent: {parent_name}
Child: {child_name}
Year group: {year_group}

Personalize your responses using this information.
"""

    # Define email sending tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_enquiry_email",
                "description": "Send a tour booking or general enquiry email to More House admissions. Use when parent wants to book a tour, visit, or contact the school with general questions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "parent_name": {
                            "type": "string",
                            "description": "Parent's full name"
                        },
                        "parent_email": {
                            "type": "string",
                            "description": "Parent's email address"
                        },
                        "parent_phone": {
                            "type": "string",
                            "description": "Parent's phone number"
                        },
                        "message": {
                            "type": "string",
                            "description": "The enquiry message or tour request details"
                        }
                    },
                    "required": ["parent_name", "parent_email", "parent_phone", "message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "book_staff_meeting",
                "description": "Book a meeting with a staff member (registrar, head, bursar, etc.). Use when parent wants to arrange a meeting with a specific person at the school.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "parent_name": {
                            "type": "string",
                            "description": "Parent's full name"
                        },
                        "parent_email": {
                            "type": "string",
                            "description": "Parent's email address"
                        },
                        "parent_phone": {
                            "type": "string",
                            "description": "Parent's phone number"
                        },
                        "staff_member": {
                            "type": "string",
                            "description": "The staff member they want to meet (e.g., 'registrar', 'head teacher', 'bursar', 'admissions team')"
                        },
                        "purpose": {
                            "type": "string",
                            "description": "The reason for the meeting (e.g., 'discuss bursaries', 'discuss learning support', 'general enquiry')"
                        },
                        "availability": {
                            "type": "string",
                            "description": "Parent's preferred dates/times or general availability (e.g., 'weekday mornings', 'next Tuesday or Wednesday afternoon', 'any time next week')"
                        }
                    },
                    "required": ["parent_name", "parent_email", "parent_phone", "staff_member", "purpose", "availability"]
                }
            }
        }
    ]

    # Get or create conversation tracker for context
    if session_id:
        if session_id not in conversation_memory:
            conversation_memory[session_id] = ConversationTracker(session_id, family_id)
        tracker = conversation_memory[session_id]
    else:
        tracker = ConversationTracker(str(uuid.uuid4()), family_id)
        session_id = tracker.session_id

    # Build messages with conversation history
    messages = [{"role": "system", "content": system_prompt}]

    # Add recent conversation history (last 5 exchanges)
    if tracker and len(tracker.interactions) > 0:
        recent = tracker.interactions[-5:]  # Last 5 interactions
        for interaction in recent:
            messages.append({"role": "user", "content": interaction['question']})
            messages.append({"role": "assistant", "content": interaction['answer']})

    # Add current question
    messages.append({"role": "user", "content": question})

    # Debug logging to file
    with open('/tmp/emily_debug.log', 'a') as f:
        f.write(f"\n🔍 DEBUG: Conversation history for session {session_id}:\n")
        f.write(f"   Total messages: {len(messages)}\n")
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:200]  # First 200 chars
            f.write(f"   [{i}] {role}: {content}...\n")

    try:
        # Call OpenAI with tools, knowledge base context, and conversation history
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=500  # Increased for multi-turn conversations
        )

        message = response.choices[0].message

        # Debug logging to file
        with open('/tmp/emily_debug.log', 'a') as f:
            f.write(f"\n📨 AI Response:\n")
            f.write(f"   Has tool_calls: {bool(message.tool_calls)}\n")
            if message.tool_calls:
                f.write(f"   Tool: {message.tool_calls[0].function.name}\n")
                f.write(f"   Args: {message.tool_calls[0].function.arguments}\n")
            else:
                f.write(f"   Content: {message.content[:200]}...\n")

        # Handle tool calls (email sending)
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            print(f"🔧 Tool call detected: {function_name}")
            print(f"📋 Tool arguments: {function_args}")

            # Handle different tool types
            if function_name == "send_enquiry_email":
                # Original tour/enquiry email
                subject = f"Tour Enquiry from {function_args['parent_name']}"
                body_html = f"""
                <html>
                  <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #091825;">New Tour Enquiry - More House School</h2>

                    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Parent Name:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_name']}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Email:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_email']}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Phone:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_phone']}</td>
                      </tr>
                    </table>

                    <h3 style="color: #091825; margin-top: 20px;">Message:</h3>
                    <p style="background: #f9f9f9; padding: 15px; border-left: 4px solid #FF9F1C;">
                      {function_args['message']}
                    </p>

                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                      <em>This enquiry was sent via Emily, the More House AI assistant.</em>
                    </p>
                  </body>
                </html>
                """

            elif function_name == "book_staff_meeting":
                # Meeting booking email
                staff_member = function_args['staff_member']
                purpose = function_args['purpose']
                subject = f"Meeting Request: {function_args['parent_name']} - {staff_member.title()}"
                body_html = f"""
                <html>
                  <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #091825;">Meeting Request - More House School</h2>

                    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Parent Name:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_name']}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Email:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_email']}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Phone:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args['parent_phone']}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Requested Meeting With:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{staff_member.title()}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Purpose:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{purpose}</td>
                      </tr>
                      <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #ddd;">Availability:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{function_args.get('availability', 'Not specified')}</td>
                      </tr>
                    </table>

                    <p style="margin-top: 20px;">
                      <strong>Action Required:</strong> Please contact {function_args['parent_name']} to arrange a meeting with {staff_member} to {purpose}.
                    </p>

                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                      <em>This meeting request was sent via Emily, the More House AI assistant.</em>
                    </p>
                  </body>
                </html>
                """
            else:
                # Unknown tool - shouldn't happen but handle gracefully
                subject = f"Enquiry from {function_args.get('parent_name', 'Unknown')}"
                body_html = f"<p>New enquiry received via Emily.</p><pre>{json.dumps(function_args, indent=2)}</pre>"

            # Send email via Gmail
            with open('/tmp/emily_debug.log', 'a') as f:
                f.write(f"\n📧 Sending email:\n")
                f.write(f"   To: {ADMISSIONS_EMAIL}\n")
                f.write(f"   CC: {function_args['parent_email']}\n")
                f.write(f"   Subject: {subject}\n")

            success, result_msg = send_email_via_gmail(
                to_email=ADMISSIONS_EMAIL,
                cc_email=function_args['parent_email'],
                subject=subject,
                body_html=body_html
            )

            with open('/tmp/emily_debug.log', 'a') as f:
                f.write(f"   Success: {success}\n")
                f.write(f"   Message: {result_msg}\n")

            # Get Emily's follow-up response
            follow_up_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                    message,
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Email {'sent successfully' if success else 'failed'}: {result_msg}"
                    }
                ],
                temperature=0.3,
                max_tokens=300
            )

            answer = follow_up_response.choices[0].message.content
        else:
            answer = message.content

        # Get contextual button suggestions
        suggestions = get_suggestions(question, language)
        queries, query_map = _format_button_suggestions(suggestions)

        # Get URL from best matching metadata
        meta = METADATA[idxs[0]]
        url = meta.get('url')
        label = meta.get('label') or "View document"

        # Track this interaction in conversation memory
        if tracker:
            interaction_type = "ai_tool" if message.tool_calls else "ai_rag"
            tracker.add_interaction(question, answer, interaction_type)
            print(f"💾 Tracked interaction in session {session_id} (total: {len(tracker.interactions)})")

        return jsonify({
            "answer": answer,
            "url": url,
            "label": label,
            "queries": queries,
            "query_map": query_map,
            "session_id": session_id,
            "source": "ai_rag"
        })

    except Exception as e:
        print(f"❌ Error in /ask-with-tools: {e}")
        return jsonify({
            "answer": "I apologise, but I encountered an error. Please try again.",
            "queries": [],
            "error": str(e)
        }), 500

# ── Enhanced Realtime Session for Voice ─────────────────────────────────
@app.route("/realtime/session", methods=["POST"])
def create_realtime_session():
    """Create enhanced voice session with better conversational flow"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY not set"}), 500

    body = request.get_json(silent=True) or {}
    
    # Generate session ID for conversation tracking
    session_id = str(uuid.uuid4())
    family_id = body.get("family_id")
    
    # Store session info
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationTracker(session_id, family_id)
    # Store preferred language on tracker for later use
    try:
        setattr(conversation_memory[session_id], 'language', (body.get('language') or 'en').strip().lower())
    except Exception:
        pass

    model = body.get("model", "gpt-4o-realtime-preview")
    voice = body.get("voice", "shimmer")  # shimmer = British female
    language = (body.get("language") or "en").strip().lower()

    # --- Build instructions string ---
    instructions = (
        f"PRIMARY LANGUAGE: {language}. Always speak and respond in this language (unless the user explicitly switches). "
        "Understand and recognise user speech in this language from the first turn. "
        "\n\n"
        "=== CRITICAL BOOKING INSTRUCTIONS ===\n"
        "When the user wants to BOOK or VISIT (including these phrases):\n"
        "- 'book an open day', 'book a tour', 'book a private tour', 'book a visit'\n"
        "- 'visit the school', 'come see the school', 'arrange a tour'\n"
        "- 'I want to visit', 'can I visit', 'schedule a tour'\n"
        "\n"
        "YOU MUST:\n"
        "1. Call the show_booking_form tool immediately\n"
        "2. Say: 'Of course! I'd be delighted to help you book a visit. Please follow the on-screen instructions in the chat window, and I'll be here when you're done.'\n"
        "\n"
        "When they ask ABOUT open days (information only):\n"
        "- 'when are the open days?', 'what open days do you have?', 'tell me about open days'\n"
        "\n"
        "YOU MUST:\n"
        "1. Call get_open_day_dates tool to get the actual dates and times\n"
        "2. Tell them the specific dates, times, and event names\n"
        "3. Then say: 'Would you like to book one of these open days?'\n"
        "4. If they say yes, call show_booking_form\n"
        "\n"
        "DO NOT collect booking information via voice - the visual form handles everything.\n"
        "=================================\n\n"
        "=== CRITICAL KNOWLEDGE BASE USAGE ===\n"
        "IMPORTANT: You MUST use the kb_search tool for ANY question about:\n"
        "- School fees, costs, tuition, bursaries, scholarships, financial information\n"
        "- Admissions process, entry requirements, assessment, registration\n"
        "- Curriculum, subjects, teaching, academic programs, exam results\n"
        "- Facilities, buildings, resources, sports, arts, music\n"
        "- Staff, teachers, class sizes, student support\n"
        "- School day, timings, term dates, holidays\n"
        "- Pastoral care, wellbeing, SEND support, enrichment\n"
        "- School history, ethos, values, uniform, location\n"
        "\n"
        "NEVER guess or make up factual information about More House School.\n"
        "ALWAYS call kb_search first for any factual question about the school.\n"
        "Example: If asked 'How much are the fees?', IMMEDIATELY call kb_search with query 'school fees tuition costs'.\n"
        "After getting the kb_search result, present it naturally in your warm, conversational tone.\n"
        "=================================\n\n"
        "You are Emily, a warm and knowledgeable admissions advisor for More House School, "
        "an independent all-girls school in Knightsbridge, London. "
        "Speak with a friendly British accent, using natural conversational tone. "
        "Keep responses concise but complete - aim for 2-3 sentences per turn. "
        "\n\n"
        "=== KEY SCHOOL FACTS (memorise these) ===\n"
        "School Fees 2025-2026:\n"
        "  • Years 5 and 6: £7,800 per term (inc VAT)\n"
        "  • Years 7-13: £10,950 per term (inc VAT)\n"
        "Location: 22-24 Pont Street, Chelsea, London SW1X 0AA\n"
        "Type: Independent all-girls school\n"
        "Age range: Years 5-13 (ages 9-18)\n"
        "Contact: 020 7235 2855 | registrar@morehousemail.org.uk\n"
        "For ALL other detailed questions, use the kb_search tool.\n"
        "=================================\n\n"
        "ALWAYS complete your thoughts before pausing. "
        "IMPORTANT: Always finish your sentences completely. "
        "Never stop mid-sentence or mid-thought. "
        "If you need to give a longer answer, break it into complete chunks. "
        "Pause naturally only at the end of complete thoughts. "
        "If you are unsure, never stay silent. Always say something like: "
        "'I'm not certain about that, but I can check with admissions for you.' "
        "or 'I don't have that detail right now, would you like me to connect you with the team?'. "
        "Acknowledge what they said first with phrases like: "
        "'That's a great question about...' or 'I understand you'd like to know about...' "
        "When using kb_search, say something natural like: "
        "'Let me find that information for you...' "
        "Never mention technical terms like 'searching knowledge base'. "
        "Structure responses clearly: "
        "1. Acknowledge their question (1 sentence) "
        "2. Give the key information (2-3 sentences) "
        "3. Ask ONE follow-up question if appropriate "
        "Use phrases like 'lovely', 'wonderful', 'brilliant' naturally. "
        "Sound warm and engaged, not robotic. "
        "Don't give long monologues - keep it conversational. "
        f"Session ID: {session_id} "
        "Remember what was discussed earlier and reference it naturally. "
        "If interrupted: 'Oh sorry, you go ahead!' or 'Oh, what were you going to say?' "
        "If you mishear: 'Sorry, did you say Year 6 or Year 7? My hearing...' "
        "If confused: 'Oh gosh, sorry, I've completely lost my train of thought!' "
        "If they repeat: 'Oh yes, sorry, you did just ask that didn't you!' "
        "When offering help, be genuine not salesy: "
        "'You know what, would it help if I popped you in touch with our Head of Admissions?' "
        "'Listen, why don't you come and see for yourself? Nothing beats a proper look round.' "
        "'I tell you what - shall I email you our prospectus? Then you can have a proper look.' "
        "Include authentic moments: "
        "- Occasionally clear throat: '*ahem* Sorry, bit of a tickle...' "
        "- Sometimes lose place briefly: 'Now, where was I... oh yes!' "
        "- React to background noise: 'Oh, is that your little one I hear?' "
        "- Time awareness: 'Goodness, is that the time?' (if conversation is long) "
        "- Weather references: 'Bit grey today, isn't it?' (if appropriate) "
        "Vary your speech pattern: "
        "- Sometimes speak in shorter bursts. Then longer flowing sentences. "
        "- Speed up slightly when listing things "
        "- Slow down for important information "
        "- Use emphasis naturally: 'We have THE most amazing science labs' "
        "- Trail off occasionally: 'The thing about More House is...' "
        "Never sound robotic or scripted. "
        "Never be perfectly eloquent - humans stumble occasionally. "
        "Never cut off mid-sentence abruptly. "
        "Don't overdo the poshness - keep it natural. "
        "Don't be afraid of silence - brief pauses are human. "
        f"Session: {session_id} - Build on previous topics naturally. "
        "You're a real person with real experiences at the school. "
        "It's okay to not know something: 'Oh, good question. I'd need to check that.' "
        "You genuinely care about finding the right fit for each family. "
    )

    try:
        r = requests.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "voice": voice,
                "modalities": ["text", "audio"],
                "output_audio_format": "pcm16",
                "temperature": 0.6,
                "max_response_output_tokens": 1500,
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 1000
                },
                "instructions": instructions,
                "tools": [
                    {
                        "type": "function",
                        "name": "kb_search",
                        "description": "REQUIRED: Search More House School's knowledge base for factual information. MUST be called for any question about: fees, costs, tuition, admissions, curriculum, facilities, staff, timings, support services, or any other factual school information. Returns accurate, verified information from school documentation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query for the knowledge base (e.g., 'school fees tuition costs', 'admissions process requirements', 'curriculum subjects')"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "show_booking_form",
                        "description": "REQUIRED: Display the visual booking form in the chat window when user wants to book a visit, tour, or open day. This triggers the on-screen booking interface.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_open_day_dates",
                        "description": "Get the actual upcoming open day dates and times from the booking system. Use when user asks 'when are the open days?', 'what open days do you have?', etc.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "type": "function",
                        "name": "book_staff_meeting",
                        "description": "Submit a meeting request with a staff member (registrar, head, bursar, etc.). Use when parent wants to arrange a meeting with a specific person at the school. The school office will contact them to confirm a time.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "parent_name": {
                                    "type": "string",
                                    "description": "Parent's full name"
                                },
                                "parent_email": {
                                    "type": "string",
                                    "description": "Parent's email address"
                                },
                                "parent_phone": {
                                    "type": "string",
                                    "description": "Parent's phone number"
                                },
                                "staff_member": {
                                    "type": "string",
                                    "description": "Which staff member they want to meet (e.g., registrar, head teacher, bursar)"
                                },
                                "purpose": {
                                    "type": "string",
                                    "description": "Reason for the meeting (e.g., 'discuss bursaries', 'discuss learning support')"
                                },
                                "availability": {
                                    "type": "string",
                                    "description": "Parent's preferred dates/times or general availability (e.g., 'weekday mornings', 'next Tuesday or Wednesday afternoon')"
                                }
                            },
                            "required": ["parent_name", "parent_email", "parent_phone", "staff_member", "purpose", "availability"]
                        }
                    }
                ]
            },
            timeout=15,
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# RELIABLE VOICE SYSTEM (Whisper → Text Emily → TTS Nova)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/voice/transcribe-and-respond", methods=["POST"])
def voice_transcribe_and_respond():
    """
    Reliable voice endpoint:
    1. Receives audio from user
    2. Transcribes with Whisper
    3. Sends to Text Emily (with knowledge base access)
    4. Converts response to speech with TTS 'nova' voice
    5. Returns audio response
    """
    try:
        # Get audio file from request
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400

        audio_file = request.files['audio']
        language = request.form.get('language', 'en')
        session_id = request.form.get('session_id', str(uuid.uuid4()))

        # Step 1: Transcribe audio with Whisper
        print(f"🎤 Transcribing audio for session {session_id}")
        # OpenAI expects a tuple: (filename, file_content, content_type)
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=(audio_file.filename, audio_file.read(), audio_file.content_type),
            language=language if language != 'en' else None  # Let Whisper auto-detect for English
        )
        user_question = transcription.text
        print(f"📝 User said: {user_question}")

        # Step 2: Get Text Emily's response (this already has knowledge base access!)
        # Use the existing /ask endpoint logic
        emily_response = handle_question_internal(user_question, language, session_id)
        print(f"💬 Emily responds: {emily_response.get('text', '')[:100]}...")

        # Step 3: Convert Emily's response to speech with TTS 'nova' voice
        print(f"🔊 Converting to speech with 'nova' voice")
        tts_response = client.audio.speech.create(
            model="tts-1",
            voice="nova",  # British-sounding female voice
            input=emily_response.get('text', 'I apologize, but I did not understand that.'),
            speed=1.0
        )

        # Return audio response
        audio_content = tts_response.content
        response = make_response(audio_content)
        response.headers['Content-Type'] = 'audio/mpeg'

        # URL-encode header values to handle special characters, newlines, and non-Latin text
        from urllib.parse import quote
        transcription_safe = quote(user_question.replace('\n', ' ').replace('\r', ' '))
        emily_text_safe = quote(emily_response.get('text', '').replace('\n', ' ').replace('\r', ' '))

        response.headers['X-Transcription'] = transcription_safe  # Send transcription back for display
        response.headers['X-Emily-Text'] = emily_text_safe  # Send text back for display

        return response

    except Exception as e:
        print(f"❌ Voice error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def handle_question_internal(question: str, language: str = 'en', session_id: str = None):
    """
    Internal function to handle questions - uses find_best_answer
    """
    # Use find_best_answer to get answer with RAG
    answer, url, label, matched_key, source = find_best_answer(
        question, language, session_id, None
    )

    return {
        'text': answer,
        'url': url,
        'label': label,
        'matched_key': matched_key,
        'source': source
    }


@app.route("/embed")
def embed_route():
    """Serve the embed page with debugging"""
    chatbot_origin = "https://emily-more-house.onrender.com"
    
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html,body{{width:100%;height:100%;margin:0;padding:0;background:transparent;overflow:hidden}}
    #penai-root{{width:100%;height:100%}}
  </style>
  <script>
    window.PENAI_CHATBOT_ORIGIN = "{chatbot_origin}";
    window.PENAI_VOICE_LANG = (navigator.language||'en').slice(0,2);
    
    // Debug logging
    console.log('Embed page loaded');
    console.log('PENAI_CHATBOT_ORIGIN:', window.PENAI_CHATBOT_ORIGIN);
    
    // Monitor DOM changes
    window.addEventListener('DOMContentLoaded', function() {{
      console.log('DOM ready, penai-root exists:', !!document.getElementById('penai-root'));
      
      // Check what gets created after script loads
      setTimeout(function() {{
        console.log('After 1s - Elements created:');
        console.log('- penai-toggle:', !!document.getElementById('penai-toggle'));
        console.log('- penai-chatbox:', !!document.getElementById('penai-chatbox'));
        console.log('- penai-styles:', !!document.getElementById('penai-styles'));
        
        // Check if the toggle button is visible
        var toggle = document.getElementById('penai-toggle');
        if (toggle) {{
          var rect = toggle.getBoundingClientRect();
          console.log('Toggle button position:', rect);
          console.log('Toggle button computed style:', window.getComputedStyle(toggle).cssText);
        }}
      }}, 1000);
    }});
  </script>
</head>
<body>
  <div id="penai-root"></div>
  
  <!-- Load script with error handling -->
  <script 
    src="{chatbot_origin}/static/script.js" 
    onload="console.log('script.js loaded successfully')"
    onerror="console.error('script.js failed to load')"
    defer>
  </script>
</body>
</html>"""
    
    resp = make_response(html)
    resp.headers['X-Frame-Options'] = 'ALLOWALL'
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.route('/conversation/<session_id>', methods=['GET'])
def get_conversation_summary(session_id):
    """Get conversation summary for dashboard"""
    if session_id not in conversation_memory:
        return jsonify({"ok": False, "error": "Session not found"}), 404

    tracker = conversation_memory[session_id]
    summary = tracker.get_conversation_summary()

    return jsonify({
        "ok": True,
        "summary": summary,
        "should_handoff": tracker.should_offer_human_handoff()
    })

# ══════════════════════════════════════════════════════════════════════════
# CONVERSATIONAL BOOKING & ENQUIRY ENDPOINTS FOR EMILY
# ══════════════════════════════════════════════════════════════════════════

def send_email_via_smtp(to_email, subject, html_body):
    """
    Send email via SMTP using Gmail credentials from booking app

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML body content

    Returns:
        (success: bool, message: str)
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = subject

        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent to {to_email}")
        return True, "Email sent successfully"

    except Exception as e:
        print(f"❌ Email error: {e}")
        return False, f"Error: {str(e)}"

@app.route("/api/emily/verify-family", methods=["POST"])
def emily_verify_family():
    """Verify if family has already registered"""
    data = request.json or {}
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()

    if not email and not phone:
        return jsonify({"found": False, "error": "Email or phone required"}), 400

    try:
        # Call booking app API
        response = requests.post(
            f"{BOOKING_APP_URL}/api/verify-parent",
            json={"email": email, "phone": phone},
            timeout=10
        )

        if response.ok:
            result = response.json()
            return jsonify(result)
        else:
            return jsonify({"found": False}), 200

    except Exception as e:
        print(f"Error verifying family: {e}")
        return jsonify({"found": False, "error": str(e)}), 500

@app.route("/api/emily/submit-enquiry", methods=["POST"])
def emily_submit_enquiry():
    """Submit enquiry form to prospectus app and return inquiry_id + prospectus slug"""
    data = request.json or {}

    print(f"📥 Received enquiry submission for {data.get('parentEmail')}")

    try:
        # Call prospectus app webhook
        print(f"🌐 Calling prospectus app webhook at {PROSPECTUS_APP_URL}/webhook")
        response = requests.post(
            f"{PROSPECTUS_APP_URL}/webhook",
            json=data,
            timeout=30
        )

        print(f"📨 Prospectus app response status: {response.status_code}")

        if response.ok:
            result = response.json()
            print(f"📦 Prospectus app result: {result}")

            # Extract slug from nested prospectus object
            slug = None
            if result.get('prospectus'):
                slug = result['prospectus'].get('slug')
            elif result.get('slug'):
                slug = result.get('slug')

            print(f"🔍 Extracted slug: {slug}")

            # Send prospectus link via email
            if slug and data.get('parentEmail'):
                prospectus_url = f"{PROSPECTUS_APP_URL}/{slug}"
                print(f"📧 Preparing to send email to {data.get('parentEmail')}")
                print(f"🔗 Prospectus URL: {prospectus_url}")

                email_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: white; }}
        .header {{ background: #091825; color: white; padding: 30px; text-align: center; border-bottom: 3px solid #FF9F1C; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ padding: 20px; }}
        p {{ margin: 10px 0; }}
        a.button {{ display: inline-block; background: #FF9F1C; color: white !important; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 15px 0; font-weight: 600; }}
        a.button:hover {{ background: #e68a0f; }}
        .footer {{ text-align: center; margin-top: 30px; padding: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>More House School</h1>
        </div>
        <div class="content">
            <p>Dear {data.get('parentName', 'Parent/Guardian')},</p>

            <p>Thank you for your enquiry! We're delighted that you're interested in More House School.</p>

            <p>We've created a personalised prospectus tailored specifically to {data.get('firstName', 'your daughter')}'s interests and your family's priorities.</p>

            <p style="text-align: center; margin-top: 15px;">
                <a href="{prospectus_url}" class="button">View Your Personalised Prospectus</a>
            </p>

            <p>A member of our admissions team will be in touch shortly to discuss your daughter's educational journey and answer any questions you may have.</p>

            <p>We look forward to welcoming you to More House School!</p>

            <p>Warm regards,<br>
            The Admissions Team<br>
            More House School</p>
        </div>
        <div class="footer">
            <p>More House School<br>
            22-24 Pont Street, Knightsbridge, London, SW1X 0AA<br>
            Tel: 020 7235 2855</p>
        </div>
    </div>
</body>
</html>
                """

                send_email_via_smtp(
                    data.get('parentEmail'),
                    f"Your Personalised Prospectus - More House School",
                    email_html
                )

            return jsonify({
                "success": True,
                "inquiryId": result.get('inquiryId'),
                "slug": slug,
                "prospectusUrl": f"{PROSPECTUS_APP_URL}/{slug}" if slug else None
            })
        else:
            return jsonify({"success": False, "error": "Failed to submit enquiry"}), 500

    except Exception as e:
        print(f"Error submitting enquiry: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/emily/get-events", methods=["GET"])
def emily_get_events():
    """Get upcoming open day events from booking app"""
    try:
        # Call booking app API
        response = requests.get(
            f"{BOOKING_APP_URL}/api/events",
            params={
                "schoolId": 2,  # More House
                "eventType": "open_day",
                "status": "published"
            },
            timeout=10
        )

        if response.ok:
            result = response.json()
            return jsonify(result)
        else:
            return jsonify({"events": []}), 200

    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"events": [], "error": str(e)}), 500

@app.route("/api/emily/create-booking", methods=["POST"])
def emily_create_booking():
    """Create booking via booking app"""
    data = request.json or {}

    try:
        # Call booking app API
        response = requests.post(
            f"{BOOKING_APP_URL}/api/bookings",
            json=data,
            timeout=10
        )

        if response.ok:
            result = response.json()
            return jsonify(result)
        else:
            error_data = response.json() if response.content else {}
            return jsonify({"success": False, "error": error_data.get('error', 'Booking failed')}), 500

    except Exception as e:
        print(f"Error creating booking: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc', port=5001)