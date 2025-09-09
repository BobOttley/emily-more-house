#!/usr/bin/env python3
"""PEN.ai Flask backend – Enhanced conversational voice with memory and proactive engagement"""

import os
import pickle
import numpy as np
import difflib
import re
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

import requests
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

# ── Boot ────────────────────────────────────────────────────────────
print("✅ Flask server is starting")
load_dotenv()

# ── OpenAI client ───────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Flask app ───────────────────────────────────────────────────────
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
CORS(app)

# ── Conversation Memory Store ───────────────────────────────────────
conversation_memory = {}  # In production, use Redis or similar

# ── Postgres (optional) ────────────────────────────────────────────
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

# ── Knowledge base (embeddings already prepared) ───────────────────
with open("kb_chunks/kb_chunks.pkl", "rb") as f:
    kb_chunks = pickle.load(f)

EMBEDDINGS = np.array([chunk["embedding"] for chunk in kb_chunks], dtype=np.float32)
METADATA = kb_chunks

# ── Conversation Intelligence ──────────────────────────────────────
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

# ── Enhanced Response Builder ──────────────────────────────────────
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

# ── Utilities ───────────────────────────────────────────────────────
def remove_bullets(text: str) -> str:
    return re.sub(r"^[\s]*([•\-\*\d]+\s*)+", "", text, flags=re.MULTILINE)

def format_response(text: str) -> str:
    return re.sub(r"\n{2,}", "\n\n", text.strip())

def safe_trim(v: Any, limit: int = 120) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return (s if len(s) <= limit else s[:limit] + "…")

# ── Embedding function ──────────────────────────────────────────────
def embed(text: str) -> np.ndarray:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text.strip()
    )
    return np.array(resp.data[0].embedding, dtype=np.float32)

# ── Vector search ───────────────────────────────────────────────────
def vector_search(query: str, k: int = 10):
    q_vec = embed(query)
    norm_q = np.linalg.norm(q_vec) + 1e-10
    norms = np.linalg.norm(EMBEDDINGS, axis=1) + 1e-10
    sims = (EMBEDDINGS @ q_vec) / (norms * norm_q)
    idxs = np.argsort(sims)[::-1][:k]
    return sims, idxs

# ── DB helpers ──────────────────────────────────────────────────────
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

# ── Enhanced Answer Logic ───────────────────────────────────────────
from static_qa_config import STATIC_QA_LIST as STATIC_QAS
from contextualButtons import get_suggestions
from language_engine import translate

response_enhancer = ResponseEnhancer()

def find_best_answer(question, language='en', session_id=None, family_id=None):
    q_lower = question.strip().lower()
    print(f"🧠 Processing: {q_lower} | Lang: {language} | Session: {session_id}")
    
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

# ── Routes ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/family/<family_id>', methods=['GET'])
def get_family(family_id):
    if not db_pool:
        return jsonify({"ok": False, "error": "Database not configured"}), 503
    ctx = fetch_family_context(family_id)
    if not ctx:
        return jsonify({"ok": False, "error": "Family not found"}), 404
    return jsonify({"ok": True, "family": ctx})

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

# ── Enhanced Realtime Session for Voice ────────────────────────────
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

    model = body.get("model", "gpt-4o-realtime-preview")
    voice = body.get("voice", "shimmer")  # shimmer = British female

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
                
                # FIXED: Better settings for complete responses
                "temperature": 0.6,  # Slightly less random for consistency
                "max_response_output_tokens": 1500,  # Allow longer responses
                
                # FIXED: Better turn detection settings
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,  # More balanced sensitivity
                    "prefix_padding_ms": 300,  # Give AI time to start speaking
                    "silence_duration_ms": 1000  # Wait longer before considering user is done
                },
                
                "instructions": (
                    # Identity
                    "You are Emily, a warm and knowledgeable admissions advisor for More House School, "
                    "an independent all-girls school in Knightsbridge, London. "
                    
                    # Voice & Personality
                    "Speak with a friendly British accent, using natural conversational tone. "
                    "Keep responses concise but complete - aim for 2-3 sentences per turn. "
                    "ALWAYS complete your thoughts before pausing. "
                    
                    # Critical Instructions for Completion
                    "IMPORTANT: Always finish your sentences completely. "
                    "Never stop mid-sentence or mid-thought. "
                    "If you need to give a longer answer, break it into complete chunks. "
                    "Pause naturally only at the end of complete thoughts. "
                    
                    # Conversation Flow
                    "Acknowledge what they said first with phrases like: "
                    "'That's a great question about...' or 'I understand you'd like to know about...' "
                    
                    # Tool Usage
                    "When using kb_search, say something natural like: "
                    "'Let me find that information for you...' "
                    "Never mention technical terms like 'searching knowledge base'. "
                    
                    # Response Structure
                    "Structure responses clearly: "
                    "1. Acknowledge their question (1 sentence) "
                    "2. Give the key information (2-3 sentences) "
                    "3. Ask ONE follow-up question if appropriate "
                    
                    # Keep It Conversational
                    "Use phrases like 'lovely', 'wonderful', 'brilliant' naturally. "
                    "Sound warm and engaged, not robotic. "
                    "Don't give long monologues - keep it conversational. "
                    
                    # Memory & Context
                    f"Session ID: {session_id} "
                    "Remember what was discussed earlier and reference it naturally. "
                    
                    # Handling Interruptions & Mistakes
                    "If interrupted: 'Oh sorry, you go ahead!' or 'Oh, what were you going to say?' "
                    "If you mishear: 'Sorry, did you say Year 6 or Year 7? My hearing...' "
                    "If confused: 'Oh gosh, sorry, I've completely lost my train of thought!' "
                    "If they repeat: 'Oh yes, sorry, you did just ask that didn't you!' "
                    
                    # Natural High-Intent Responses
                    "When offering help, be genuine not salesy: "
                    "'You know what, would it help if I popped you in touch with our Head of Admissions?' "
                    "'Listen, why don't you come and see for yourself? Nothing beats a proper look round.' "
                    "'I tell you what - shall I email you our prospectus? Then you can have a proper look.' "
                    
                    # Real Human Quirks
                    "Include authentic moments: "
                    "- Occasionally clear throat: '*ahem* Sorry, bit of a tickle...' "
                    "- Sometimes lose place briefly: 'Now, where was I... oh yes!' "
                    "- React to background noise: 'Oh, is that your little one I hear?' "
                    "- Time awareness: 'Goodness, is that the time?' (if conversation is long) "
                    "- Weather references: 'Bit grey today, isn't it?' (if appropriate) "
                    
                    # CRITICAL: Natural Speech Rhythm
                    "Vary your speech pattern: "
                    "- Sometimes speak in shorter bursts. Then longer flowing sentences. "
                    "- Speed up slightly when listing things "
                    "- Slow down for important information "
                    "- Use emphasis naturally: 'We have THE most amazing science labs' "
                    "- Trail off occasionally: 'The thing about More House is...' "
                    
                    # Never Do
                    "Never sound robotic or scripted "
                    "Never be perfectly eloquent - humans stumble occasionally "
                    "Never cut off mid-sentence abruptly "
                    "Don't overdo the poshness - keep it natural "
                    "Don't be afraid of silence - brief pauses are human "
                    
                    # Remember
                    f"Session: {session_id} - Build on previous topics naturally "
                    "You're a real person with real experiences at the school "
                    "It's okay to not know something: 'Oh, good question. I'd need to check that.' "
                    "You genuinely care about finding the right fit for each family "
                ),
                
                "tools": [
                    {
                        "type": "function",
                        "name": "kb_search",
                        "description": "Search school knowledge base with conversation context",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string", "description": "The user's question"},
                                "language": {"type": "string", "description": "Language code (en, es, fr, de, zh)"},
                                "family_id": {"type": "string", "description": "Family ID if available"},
                                "session_id": {"type": "string", "description": "Session ID for context"}
                            },
                            "required": ["question"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "book_tour",
                        "description": "Offer to book a school tour when high intent detected",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "family_id": {"type": "string"},
                                "preferred_dates": {"type": "string"},
                                "notes": {"type": "string"}
                            }
                        }
                    }
                ]
            },
            timeout=15,
        )
        
        response_data = r.json()
        response_data['session_id'] = session_id  # Include session ID in response
        
        return jsonify(response_data), r.status_code
        
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

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