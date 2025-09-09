#!/usr/bin/env python3
"""PEN.ai Flask backend – Static + GPT RAG + DeepL translation + contextual buttons"""

import os
import pickle
import numpy as np
import difflib
import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

from static_qa_config import STATIC_QA_LIST as STATIC_QAS
from contextualButtons import get_suggestions
from language_engine import translate  # ✅ DeepL translation

print("✅ Flask server is running")
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = Flask(__name__, static_url_path='/static')
CORS(app)

# ─── Load Embeddings ────────────────────────────────────────────────
with open("kb_chunks/kb_chunks.pkl", "rb") as f:
    kb_chunks = pickle.load(f)

EMBEDDINGS = np.array([chunk["embedding"] for chunk in kb_chunks], dtype=np.float32)
METADATA = kb_chunks

# ─── Utilities ──────────────────────────────────────────────────────
def remove_bullets(text: str) -> str:
    return re.sub(r"^[\s]*([•\-\*\d]+\s*)+", "", text, flags=re.MULTILINE)

def format_response(text: str) -> str:
    return re.sub(r"\n{2,}", "\n\n", text.strip())

# ─── Embedding Function ─────────────────────────────────────────────
def embed(text: str) -> np.ndarray:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text.strip()
    )
    return np.array(resp.data[0].embedding, dtype=np.float32)

# ─── Vector Search ─────────────────────────────────────────────────
def vector_search(query: str, k: int = 10, threshold: float = 0.25):
    q_vec = embed(query)
    norm_q = np.linalg.norm(q_vec) + 1e-10
    norms = np.linalg.norm(EMBEDDINGS, axis=1) + 1e-10
    sims = (EMBEDDINGS @ q_vec) / (norms * norm_q)
    idxs = np.argsort(sims)[::-1][:k]
    return sims, idxs

# ─── Hybrid Answer Logic ────────────────────────────────────────────
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

        # Translate if language is not English
        if language != "en":
            translated = translate(clean, language)
            if translated != clean:
                print(f"🌐 Translated RAG response to {language}")
                clean = translated

        meta = METADATA[idxs[0]]
        return clean, meta.get('url'), meta.get('label') or "View document", None, "rag"

    # No match
    print("❌ No suitable match found.")
    return "I'm sorry, I couldn't find an answer to that. Please try rephrasing or contact the school directly.", None, None, None, "none"

# ─── Routes ────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')

    answer, url, label, matched_key, source = find_best_answer(question, language)

    seed = matched_key or question
    suggestions = get_suggestions(seed, language=language)
    queries = [s['query'] for s in suggestions]
    query_map = {s['query']: s['label'] for s in suggestions}

    return jsonify({
        'answer': answer,
        'url': url,
        'link_label': label,
        'queries': queries,
        'query_map': query_map,
        'source': source
    })

if __name__ == '__main__':
    app.run(debug=True)
