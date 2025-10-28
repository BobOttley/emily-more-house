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

# Email imports
import base64
import smtplib
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


# ── Boot ──────────────────────────────────────────────────────────────────
print("✅ Flask server is starting")
load_dotenv()

# ── OpenAI client ────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Gmail API Configuration (Legacy - OAuth) ─────────────────────────────
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

# ── SMTP Configuration (Primary email method) ────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")  # School's Gmail address
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # App password (not regular password)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Emily - More House School")

if SMTP_USER and SMTP_PASSWORD:
    print("✅ SMTP email configured")
else:
    print("⚠️ SMTP not configured (SMTP_USER, SMTP_PASSWORD required)")


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
        self.parent_email = None  # For collecting contact info during conversation
        self.parent_phone = None  # For collecting contact info during conversation
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
    
    # Special case: Open Days / Visits
    open_day_keywords = ["open day", "open morning", "open evening", "visit", "tour"]
    if any(kw in q_lower for kw in open_day_keywords):
        events = get_open_day_events()
        if events:
            next_event = sorted(events, key=lambda e: e["date_iso"])[0]
            answer = (
                f"Our next {next_event['event_name']} is on "
                f"{next_event['date_human']}. "
                f"You can find more details and register here: "
                f"{next_event['booking_link']}"
            )
            return answer, next_event["booking_link"], "Open Days", "open_days", "open_days"
        else:
            answer = (
                "We don't currently have any upcoming Open Days listed. "
                f"You can check back soon on our [Admissions page]({OPEN_DAYS_URL})."
            )
            return answer, OPEN_DAYS_URL, "Admissions", "open_days", "open_days"

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

def send_email_via_smtp(to_email: str, cc_email: str, subject: str, body_html: str):
    """
    Send email via SMTP (no OAuth required)

    Args:
        to_email: Recipient (admissions)
        cc_email: CC recipient (parent)
        subject: Email subject
        body_html: HTML body content

    Returns:
        (success: bool, message: str)
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "SMTP not configured (set SMTP_USER and SMTP_PASSWORD in .env)"

    try:
        # Create message
        message = MIMEMultipart('alternative')
        message['From'] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        message['To'] = to_email
        message['Cc'] = cc_email
        message['Subject'] = subject

        # Attach HTML body
        html_part = MIMEText(body_html, 'html')
        message.attach(html_part)

        # Connect to SMTP server and send
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()  # Upgrade to secure connection
            server.login(SMTP_USER, SMTP_PASSWORD)

            # Send to both TO and CC recipients
            recipients = [to_email]
            if cc_email:
                recipients.append(cc_email)

            server.sendmail(SMTP_USER, recipients, message.as_string())

        print(f"✅ Email sent via SMTP to {to_email} (CC: {cc_email})")
        return True, "Email sent successfully"

    except smtplib.SMTPAuthenticationError:
        print(f"❌ SMTP authentication failed - check SMTP_USER and SMTP_PASSWORD")
        return False, "Email authentication failed"
    except smtplib.SMTPException as e:
        print(f"❌ SMTP error: {e}")
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False, f"Error: {str(e)}"

def send_email_via_gmail(to_email: str, cc_email: str, subject: str, body_html: str):
    """
    Legacy Gmail API method (requires OAuth - not used by default)
    Use send_email_via_smtp() instead for automatic sending

    Args:
        to_email: Recipient (admissions)
        cc_email: CC recipient (parent)
        subject: Email subject
        body_html: HTML body content

    Returns:
        (success: bool, message: str)
    """
    service = get_gmail_service()
    if not service:
        return False, "Not authenticated with Gmail"

    try:
        message = MIMEMultipart('alternative')
        message['To'] = to_email
        message['Cc'] = cc_email
        message['Subject'] = subject

        html_part = MIMEText(body_html, 'html')
        message.attach(html_part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        result = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        print(f"✅ Email sent: {result.get('id')}")
        return True, "Email sent successfully"

    except HttpError as error:
        print(f"❌ Gmail API error: {error}")
        return False, f"Gmail API error: {str(error)}"
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False, f"Error: {str(e)}"

@app.route("/realtime/tool/get_open_days", methods=["POST"])
def realtime_tool_get_open_days():
    """Tool endpoint for realtime model to fetch open days"""
    events = get_open_day_events()
    if not events:
        return jsonify({
            "ok": True,
            "events": [],
            "message": "No upcoming open days are currently listed."
        })

    return jsonify({
        "ok": True,
        "events": events
    })

@app.route("/realtime/tool/send_enquiry_email", methods=["POST"])
def realtime_tool_send_enquiry_email():
    """Tool endpoint for realtime model to send enquiry emails"""
    data = request.json or {}

    parent_name = data.get('parent_name')
    parent_email = data.get('parent_email')
    parent_phone = data.get('parent_phone')
    message = data.get('message', 'Tour enquiry from voice conversation')

    # Validate required fields
    if not all([parent_name, parent_email, parent_phone]):
        return jsonify({
            "ok": False,
            "error": "Missing required fields: parent_name, parent_email, or parent_phone"
        }), 400

    # Send email via SMTP
    success, result_msg = send_email_via_smtp(
        to_email=ADMISSIONS_EMAIL,
        cc_email=parent_email,
        subject=f"Tour Enquiry from {parent_name}",
        body_html=f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #091825;">New Tour Enquiry - More House School</h2>

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
            </table>

            <h3 style="color: #091825; margin-top: 20px;">Message:</h3>
            <p style="background: #f9f9f9; padding: 15px; border-left: 4px solid #FF9F1C;">
              {message}
            </p>

            <p style="color: #666; font-size: 12px; margin-top: 30px;">
              <em>This enquiry was sent via Emily, the More House AI assistant (voice conversation).</em>
            </p>
          </body>
        </html>
        """
    )

    if success:
        return jsonify({
            "ok": True,
            "message": f"Email sent successfully to {ADMISSIONS_EMAIL}"
        })
    else:
        return jsonify({
            "ok": False,
            "error": result_msg
        }), 500

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id')  # For voice sessions
    
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

@app.route('/ask-with-tools', methods=['POST'])
def ask_with_tools():
    """Enhanced /ask endpoint that supports email sending via function calls"""
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id') or str(uuid.uuid4())

    if not question:
        return jsonify({"answer": "Please ask a question.", "queries": []})

    # Get or create conversation tracker
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationTracker(session_id, family_id)
    tracker = conversation_memory[session_id]

    # Get family context
    family_ctx = fetch_family_context(family_id) if family_id else None

    # Build system prompt
    system_prompt = f"""You are Emily, the AI assistant for More House School.
Be warm, helpful, and professional. Use British spelling.
Language: {language}

PROACTIVE ENGAGEMENT - Suggesting Visits:
When parents show interest in the school (asking about curriculum, facilities, admissions, fees),
naturally suggest they visit. Use phrases like:
- "Would you like to visit us? I can arrange a private tour that fits your schedule."
- "Many parents find it helpful to see the school in person. Shall I arrange a tour for you?"
- "We have upcoming open days if you'd like to see the school with other families, or I can arrange a private tour just for you."
- "The best way to get a feel for More House is to visit! Would you prefer a private tour or one of our open days?"

WHEN TO SUGGEST:
- After answering 2-3 questions about the school
- When parents ask about admissions, fees, or year groups
- When they express concerns or want more details
- At the end of any detailed explanation

IMPORTANT - Email Sending Process:
When parents want to book a tour or contact admissions:
1. First, warmly acknowledge their request
2. Then ask for their details if you don't have them:
   - Their full name
   - Their email address
   - Their phone number
3. ONLY call the send_enquiry_email function when you have ALL three details
4. Don't send the email until the parent has confirmed their information

Be conversational and friendly when collecting information. For example:
"I'd be delighted to arrange that for you! May I have your name, email address, and phone number so I can send this enquiry to our admissions team?"
"""

    if family_ctx:
        child_name = family_ctx.get('child_name', 'your daughter')
        parent_name = family_ctx.get('parent_name', 'Parent')
        parent_email = family_ctx.get('parent_email', None)
        parent_phone = family_ctx.get('parent_phone', None)
        year_group = family_ctx.get('year_group', '')

        system_prompt += f"""

FAMILY CONTEXT:
Parent: {parent_name}
Child: {child_name}
Year group: {year_group}"""

        if parent_email:
            system_prompt += f"\nEmail: {parent_email}"
        if parent_phone:
            system_prompt += f"\nPhone: {parent_phone}"

        system_prompt += "\n\nPersonalize your responses using this information."

        # Pre-populate tracker with family context
        if not tracker.parent_name:
            tracker.parent_name = parent_name
        if parent_email and not tracker.parent_email:
            tracker.parent_email = parent_email
        if parent_phone and not tracker.parent_phone:
            tracker.parent_phone = parent_phone

    
    # Define email sending tool
    tools = [{
        "type": "function",
        "function": {
            "name": "send_enquiry_email",
            "description": "Send a tour booking or enquiry email to More House admissions. Use when parent wants to book a tour, visit, or contact the school.",
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
    }]
    
    try:
        # Build conversation messages with history
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 5 interactions to keep context manageable)
        for interaction in tracker.interactions[-5:]:
            messages.append({"role": "user", "content": interaction['question']})
            messages.append({"role": "assistant", "content": interaction['answer']})

        # Add current question
        messages.append({"role": "user", "content": question})

        # Call OpenAI with tools
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=500
        )

        message = response.choices[0].message
        
        # Handle tool call (email sending)
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            function_args = json.loads(tool_call.function.arguments)
            
            # Send email via SMTP
            success, result_msg = send_email_via_smtp(
                to_email=ADMISSIONS_EMAIL,
                cc_email=function_args['parent_email'],
                subject=f"Tour Enquiry from {function_args['parent_name']}",
                body_html=f"""
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
            )
            
            # Get Emily's follow-up response
            follow_up_messages = messages + [
                message,
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"Email {'sent successfully' if success else 'failed'}: {result_msg}"
                }
            ]

            follow_up_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=follow_up_messages,
                temperature=0.7,
                max_tokens=300
            )

            answer = follow_up_response.choices[0].message.content
        else:
            answer = message.content

        # Store interaction in tracker
        tracker.add_interaction(question, answer)

        return jsonify({
            "answer": answer,
            "queries": ["fees", "admissions", "open days", "curriculum"],
            "session_id": session_id
        })
        
    except Exception as e:
        print(f"❌ Error in /ask-with-tools: {e}")
        return jsonify({
            "answer": "I apologize, but I encountered an error. Please try again.",
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

    # --- Build Open Days context ---
    events = get_open_day_events()
    if events:
        events_str = "Upcoming Open Days: " + "; ".join(
            [f"{e['event_name']} on {e['date_human']}" for e in events]
        ) + ". "
    else:
        events_str = "No upcoming Open Days are currently listed. "

    # --- Build instructions string ---
    instructions = (
        f"{events_str}"
        f"PRIMARY LANGUAGE: {language}. Always speak and respond in this language (unless the user explicitly switches). "
        "Understand and recognise user speech in this language from the first turn. "
        "When asked about open days, visits, or tours, ALWAYS call the tool `get_open_days` and use only its response. Never guess dates. "
        "PROACTIVE ENGAGEMENT - Suggesting Visits: "
        "When parents show interest in the school (asking about curriculum, facilities, admissions, fees), naturally suggest they visit. "
        "After answering 2-3 questions, use phrases like: "
        "'Would you like to come and see us? I can arrange a private tour that fits your schedule.' "
        "'Many parents find it really helpful to see the school in person. Shall I arrange a tour for you?' "
        "'The best way to get a feel for More House is to visit! Would you prefer a private tour or one of our open days?' "
        "'Listen, why don't you come and see for yourself? I can set that up for you if you'd like.' "
        "Be natural and conversational - don't push, just offer warmly. "
        "IMPORTANT - Email Sending: When parents want to book a tour or contact admissions: "
        "1. First, warmly acknowledge their request "
        "2. Then ask for their contact details conversationally: 'Lovely! Can I take your name, email address, and phone number so I can send this through to our admissions team?' "
        "3. ONLY call send_enquiry_email when you have ALL three: name, email, and phone "
        "4. After sending, confirm: 'Perfect! I've sent that through to admissions. They'll be in touch with you shortly.' "
        "You are Emily, a warm and knowledgeable admissions advisor for More House School, "
        "an independent all-girls school in Knightsbridge, London. "
        "Speak with a friendly British accent, using natural conversational tone. "
        "Keep responses concise but complete - aim for 2-3 sentences per turn. "
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
                        "description": "Search school knowledge base with conversation context",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "The search query string"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "book_tour",
                        "description": "Offer to book a school tour when high intent detected",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "Requested tour date"},
                                "time": {"type": "string", "description": "Requested tour time"}
                            },
                            "required": []
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_open_days",
                        "description": "Retrieve upcoming open day events from the school's admissions page",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "type": "function",
                        "name": "send_enquiry_email",
                        "description": "Send a tour booking or enquiry email to More House admissions. ONLY use this when you have collected ALL required information: parent name, email, and phone number. Ask for these details first if you don't have them.",
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
                ]
            },
            timeout=15,
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True, ssl_context='adhoc', port=5001)