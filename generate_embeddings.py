#!/usr/bin/env python3
import os
import pickle
import numpy as np
import openai
import tiktoken
from dotenv import load_dotenv

# ─── Load OpenAI API key ─────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

# ─── Embedding model and config ──────────────────────────────────────
EMB_MODEL = "text-embedding-3-small"
KB_FOLDER = "kb_chunks"
MAX_TOKENS = 8192
tokenizer = tiktoken.encoding_for_model(EMB_MODEL)

# ─── Count tokens ────────────────────────────────────────────────────
def count_tokens(text):
    return len(tokenizer.encode(text))

# ─── Generate embeddings ─────────────────────────────────────────────
def generate_embeddings(chunks):
    enriched_chunks = []
    for chunk in chunks:
        token_count = count_tokens(chunk["text"])
        if token_count > MAX_TOKENS:
            print(f"Skipping (too long: {token_count} tokens): {chunk['text'][:50]}...")
            continue
        try:
            response = openai.embeddings.create(model=EMB_MODEL, input=[chunk["text"]])
            embedding = response.data[0].embedding
            chunk["embedding"] = embedding
            enriched_chunks.append(chunk)
        except Exception as e:
            print(f"⚠️ Embedding error for chunk: {chunk['text'][:50]}... → {e}")
    return enriched_chunks

# ─── Load and chunk .txt or .pdf files ───────────────────────────────
def load_and_chunk_text(folder=KB_FOLDER):
    text_chunks = []
    for filename in os.listdir(folder):
        if filename.startswith(".") or not filename.endswith(".txt"):
            print(f"Skipping: {filename}")
            continue
        filepath = os.path.join(folder, filename)
        print(f"Reading: {filepath}")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(filepath, "r", encoding="latin-1") as f:
                text = f.read()

        # Split into ~600-word chunks
        paragraphs = text.split("\n\n")
        chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(chunk.split()) + len(para.split()) <= 600:
                chunk += "\n\n" + para if chunk else para
            else:
                text_chunks.append({
                    "text": chunk.strip(),
                    "source_url": "https://www.morehouse.org.uk"
                })
                chunk = para
        if chunk:
            text_chunks.append({
                "text": chunk.strip(),
                "source_url": "https://www.morehouse.org.uk"
            })
    return text_chunks

# ─── Run main workflow ───────────────────────────────────────────────
if __name__ == "__main__":
    print("🔍 Loading and chunking...")
    raw_chunks = load_and_chunk_text()

    print("💡 Generating embeddings...")
    enriched_chunks = generate_embeddings(raw_chunks)

    print("💾 Saving metadata.pkl and embeddings.pkl...")
    with open("metadata.pkl", "wb") as f:
        pickle.dump(enriched_chunks, f)

    embeddings = [chunk["embedding"] for chunk in enriched_chunks]
    with open("embeddings.pkl", "wb") as f:
        pickle.dump(np.array(embeddings, dtype="float32"), f)

    print(f"✅ Done: {len(enriched_chunks)} chunks saved.")
