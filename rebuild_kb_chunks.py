import os
import pickle
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load original metadata
with open("metadata.pkl", "rb") as f:
    metadata = pickle.load(f)

print(f"🔄 Generating embeddings for {len(metadata)} chunks...")

# Add embeddings to each chunk
kb_chunks = []
for i, chunk in enumerate(metadata):
    text = chunk.get("text") or chunk.get("chunk")
    if not text:
        continue
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text.strip()
        )
        embedding = response.data[0].embedding
        chunk["embedding"] = embedding
        kb_chunks.append(chunk)
        if i % 100 == 0:
            print(f"  🔹 Embedded chunk {i}/{len(metadata)}")
    except Exception as e:
        print(f"  ❌ Error embedding chunk {i}: {e}")

# Save to kb_chunks.pkl
with open("kb_chunks/kb_chunks.pkl", "wb") as f:
    pickle.dump(kb_chunks, f)

print(f"✅ Rebuilt kb_chunks.pkl with embeddings: {len(kb_chunks)} chunks saved.")
