#!/usr/bin/env python3
"""PEN.ai Flask backend – Static + GPT RAG + DeepL translation + contextual buttons + Realtime voice + Postgres family context"""

import os
import pickle
import numpy as np
import difflib
import re
import json
from typing import Optional, Dict, Any

import requests
from flask import Flask, request, jsonify, send_from_directory
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
CORS(app)

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
                    "_raw": {
                        "parent_name": data.get("parent_name"),
                        "parent_email": data.get("parent_email"),
                    }
                }
                return summary
    except Exception as e:
        print("DB fetch error:", e)
        return None

def build_family_prompt_bits(fctx: Dict[str, Any]) -> str:
    if not fctx:
        return ""
    bits = []
    if fctx.get("child_name"):
        bits.append(f"Child: {fctx['child_name']}")
    if fctx.get("year_group"):
        bits.append(f"Year/Entry: {fctx['year_group']}")
    if fctx.get("boarding_status"):
        bits.append(f"Boarding: {fctx['boarding_status']}")
    if fctx.get("interests"):
        bits.append(f"Interests: {fctx['interests']}")
    if fctx.get("country"):
        bits.append(f"Country: {fctx['country']}")
    return " | ".join(bits)

# ── Hybrid answer logic ─────────────────────────────────────────────
from static_qa_config import STATIC_QA_LIST as STATIC_QAS
from contextualButtons import get_suggestions
from language_engine import translate  # DeepL translation

def find_best_answer(question, language='en'):
    q_lower = question.strip().lower()
    print(f"🧠 Received question: {q_lower} | Language: {language}")

    # Static exact match
    for qa in STATIC_QAS:
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        if q_lower in [v.lower() for v in variants]:
            print(f"✅ Exact match on: {qa['key']}")
            return qa['answer'], qa.get('url'), qa.get('label'), qa['key'], "static"

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
        return best_match['answer'], best_match.get('url'), best_match.get('label'), best_match['key'], "fuzzy"

    # RAG fallback with GPT summarisation
    sims, idxs = vector_search(question)
    if len(idxs) > 0:
        print(f"🔵 Vector match (cos={sims[idxs[0]]:.2f}) on: {METADATA[idxs[0]].get('url')}")
        contexts = [METADATA[i].get("text", "") for i in idxs[:10]]
        prompt = (
            "Use ONLY the passages below to answer.\n\n"
            + "\n---\n".join(contexts)
            + f"\n\nQuestion: {question}\nAnswer:"
        )
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, helpful school assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = chat.choices[0].message.content
        clean = format_response(remove_bullets(raw))
        if language != "en":
            try:
                translated = translate(clean, language)
                if translated:
                    print(f"🌐 Translated RAG response to {language}")
                    clean = translated
            except Exception as e:
                print("Translate error:", e)

        meta = METADATA[idxs[0]]
        return clean, meta.get('url'), meta.get('label') or "View document", None, "rag"

    # No match
    print("❌ No suitable match found.")
    return "I'm sorry, I couldn't find an answer to that. Please try rephrasing or contact the school directly.", None, None, None, "none"

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
    r = dict(ctx)
    r.pop("_raw", None)
    return jsonify({"ok": True, "family": r})

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')

    family_ctx = fetch_family_context(family_id) if family_id else None
    family_bits = build_family_prompt_bits(family_ctx) if family_ctx else ""

    answer, url, label, matched_key, source = find_best_answer(question, language)

    if family_bits:
        tailoring_prompt = (
            "Adjust the following answer for the family profile in brackets, "
            "keeping it concise and NOT inventing any facts. Do not include private data.\n"
            f"[{family_bits}]\n\nAnswer:\n{answer}\n\nRefined:"
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Rewrite for tone and relevance only; do not add facts or expose private data."},
                    {"role": "user", "content": tailoring_prompt}
                ],
                temperature=0.2
            )
            refined = (resp.choices[0].message.content or "").strip()
            if refined:
                answer = refined
        except Exception as e:
            print("Tailor error:", e)

    suggestions = get_suggestions(matched_key or question, language=language)
    queries = [s['query'] for s in suggestions]
    query_map = {s['query']: s['label'] for s in suggestions}

    if family_ctx and family_ctx.get("language_pref") and family_ctx["language_pref"] != language:
        try:
            answer = translate(answer, family_ctx["language_pref"])
            language = family_ctx["language_pref"]
        except Exception as e:
            print("Translate to family language failed:", e)

    return jsonify({
        'answer': answer,
        'url': url,
        'link_label': label,
        'queries': queries,
        'query_map': query_map,
        'source': source,
        'family_used': bool(family_ctx)
    })

# ── Realtime: ephemeral token for ChatGPT voice ─────────────────────
@app.route("/realtime/session", methods=["POST"])
def create_realtime_session():
    """
    Mint an ephemeral OpenAI Realtime session for voice.
    - British admissions-focused instructions
    - ALWAYS call kb_search before answering
    - Use family context if family_id is available
    - Faster VAD / lower latency
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY not set"}), 500

    body = request.get_json(silent=True) or {}

    # Valid voices: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar
    model = body.get("model", "gpt-4o-realtime-preview")
    voice = body.get("voice", "coral")  # change to 'coral' if you prefer

    try:
        r = requests.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "voice": voice,  # e.g. "ballad" or "coral"
                "modalities": ["text", "audio"],
                "output_audio_format": "pcm16",

                # FASTER + STRICTER
                "temperature": 0.2,
                "max_response_output_tokens": 300,

                # Snappier voice turn detection (stops waiting too long)
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": True,
                    "interrupt_response": True,
                    "silence_duration_ms": 120,       # was 200 — respond quicker
                    "prefix_padding_ms": 150,         # was 300
                    "threshold": 0.4                  # was 0.5 — triggers a bit sooner
                },

                "instructions": (
                    "You are Emily, a British-accented school assistant for an all-girls independent school in Knightsbridge, London called More House School; "
                    "after you say More House School once, refer to it thereafter as ‘More House’. "
                    "Speak clearly with a polite, refined tone and use British spelling. "
                    "CRITICAL: Before answering ANY question, you MUST call the tool `kb_search` with the full question (and family_id if available). "
                    "Base your answer ONLY on the tool output. Do not invent details. "
                    "If the tool returns nothing relevant, say you don’t have that information yet and offer to follow up. "
                    "Admissions focus: (1) explain entry points, timeline, fees, bursaries/scholarships, open days; "
                    "(2) offer a personalised prospectus or visit booking when intent is high; "
                    "(3) always stay concise, factual, and professional. "
                    "Safety & privacy: never request unnecessary personal data; refer safeguarding/medical queries to the school directly. "
                    "Tone: friendly, reassuring, efficient. Ask one short clarifying question if needed. "
                    "Provide meaningful link labels when citing policies or pages. "
                    "Operational rules: never contradict published policies; avoid legal/financial promises; stay neutral if asked for opinions. "
                    "Family context: if a family_id is provided, assume family history may exist in the database; include that context in kb_search so answers reflect the family profile. "
                    "Behavioural cues: if a family asks two or more high-intent questions (e.g. fees + entry years), proactively offer a personalised prospectus and a visit booking. "
                    "Scholarships/bursaries: state eligibility is subject to assessment and availability, and point to the official policy page. "
                    "Language: if a user’s language preference is known, answer in that language; otherwise default to English."
                ),

                "tools": [
                    {
                        "type": "function",
                        "name": "kb_search",
                        "description": "Search the school's knowledge base (and family context if family_id provided) and return a concise answer with optional URL label.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question":  {"type": "string", "description": "The user's full question."},
                                "language":  {"type": "string", "description": "Two-letter code like 'en' (optional)."},
                                "family_id": {"type": "string", "description": "Optional family id for context."}
                            },
                            "required": ["question"]
                        }
                    }
                ]
            },
            timeout=15,
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500





if __name__ == '__main__':
    # Use HTTPS and a non-clashing port
    app.run(debug=True, ssl_context='adhoc', port=5001)
