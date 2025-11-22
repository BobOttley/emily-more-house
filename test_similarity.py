import pickle
import numpy as np
from numpy import dot
from numpy.linalg import norm
from openai import OpenAI
from dotenv import load_dotenv
import os

# ─── Load OpenAI API key ─────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Load Embedded Chunks ─────────────────────────────
with open("kb_chunks/kb_chunks.pkl", "rb") as f:
    chunks = pickle.load(f)

print(f"✅ Loaded {len(chunks)} embedded chunks")

# ─── Create Embedding for Test Question ───────────────
query = "Who are the governors?"
resp = client.embeddings.create(
    model="text-embedding-3-small",
    input=query
)
q_vec = np.array(resp.data[0].embedding)

# ─── Score Chunks by Similarity ───────────────────────
scores = []
for chunk in chunks:
    c_vec = np.array(chunk["embedding"])
    similarity = dot(q_vec, c_vec) / (norm(q_vec) * norm(c_vec))
    scores.append((similarity, chunk["source"], chunk["text"][:200]))

# ─── Show Top Matches ─────────────────────────────────
scores.sort(reverse=True)
print("\n🔍 Top 5 Similar Chunks:")
for sim, url, preview in scores[:5]:
    print(f"\n🔹 Similarity: {sim:.3f}")
    print(f"🌐 URL: {url}")
    print(f"📄 Preview: {preview.strip()}")
