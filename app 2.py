print("✅ Flask server is running")

from flask import Flask, request, jsonify, send_from_directory
from static_qa_config import STATIC_QA_LIST as STATIC_QAS
from contextualButtons import get_suggestions
import difflib

app = Flask(__name__, static_url_path='/static')


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


def find_best_answer(question, language='en'):
    question_lower = question.strip().lower()
    print(f"🧠 Received question: {question_lower} | Language: {language}")

    # Step 1: Direct match to any variant
    for qa in STATIC_QAS:
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        if question_lower in [v.lower() for v in variants]:
            print(f"✅ Exact match on: {qa['key']}")
            return qa['answer'], qa.get('url'), qa.get('label'), qa['key']

    # Step 2: Fuzzy fallback
    best_score = 0
    best_match = None
    for qa in STATIC_QAS:
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        for variant in variants:
            score = difflib.SequenceMatcher(None, question_lower, variant.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = qa

    if best_match and best_score > 0.6:
        print(f"🟡 Fuzzy match on: {best_match['key']} (score {best_score:.2f})")
        return best_match['answer'], best_match.get('url'), best_match.get('label'), best_match['key']

    print("❌ No suitable match found.")
    return "I'm sorry, I couldn't find an answer to that.", None, None, None


@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question', '')
    language = data.get('language', 'en')

    print(f"🧠 Received question: {question} | Lang: {language}")
    
    answer, url, label, matched_key = find_best_answer(question, language)
    print("🔎 Answer returned:", answer)
    print("🔗 URL returned:", url)
    print("🏷️ Label returned:", label)

    # Generate related buttons based on matched key
    suggestions = get_suggestions(matched_key or question, language=language)
    print("📌 Suggestions returned:", suggestions)
    
    queries = [s['query'] for s in suggestions]
    query_map = {s['query']: s['label'] for s in suggestions}


    print("✅ Returning chatbot response...")

    return jsonify({
        'answer': answer,
        'url': url,
        'link_label': label,
        'queries': queries,
        'query_map': query_map
    })


if __name__ == '__main__':
    app.run(debug=True)
