import os
import io
import time
import pickle
import requests
import numpy as np
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from openai import OpenAI
from dotenv import load_dotenv
import tiktoken

# ─── Setup ──────────────────────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_DOMAIN = "www.morehouse.org.uk"
START_URLS = [
    "https://www.morehouse.org.uk/",
    "https://www.morehouse.org.uk/admissions/",
    "https://www.morehouse.org.uk/our-school/",
    "https://www.morehouse.org.uk/information/school-policies/#filter-content"  # ✅ This is the correct policies page
]

tokenizer = tiktoken.encoding_for_model("text-embedding-ada-002")
MAX_TOKENS = 7000

visited = set()
all_chunks = []
all_embeddings = []

# ─── Token-Safe Chunking ───────────────────────────────
def chunk_text_by_tokens(text, max_tokens=MAX_TOKENS):
    tokens = tokenizer.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i + max_tokens]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
    return chunks

# ─── Clean HTML ───────────────────────────────────────
def extract_clean_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav", "form"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)

# ─── Embed a Chunk ─────────────────────────────────────
def get_embedding(text):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[text]
    )
    return response.data[0].embedding

# ─── URL Validity Check ────────────────────────────────
def is_valid_url(url):
    parsed = urlparse(url)
    return (
        parsed.netloc == BASE_DOMAIN and
        url not in visited and
        parsed.scheme in ["http", "https"] and
        not url.endswith(".jpg") and
        not url.endswith(".png") and
        not "#" in url
    )

# ─── Main Crawl Logic ──────────────────────────────────
def crawl(url):
    try:
        print(f"🌐 Crawling: {url}")
        visited.add(url)
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        if url.lower().endswith(".pdf"):
            pdf = PdfReader(io.BytesIO(response.content))
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            chunks = chunk_text_by_tokens(text)

            for chunk in chunks:
                try:
                    embedding = get_embedding(chunk)
                    all_chunks.append({
                        "text": chunk,
                        "source": url,
                        "label": os.path.basename(url).replace(".pdf", "").replace("-", " ").title()
                    })
                    all_embeddings.append(embedding)
                    print(f"📄 Embedded from PDF: {url}")
                except Exception as e:
                    print(f"⚠️  Skipped a PDF chunk from {url} – {e}")
                time.sleep(1)
            return

        # HTML route
        html = response.text
        text = extract_clean_text(html)
        chunks = chunk_text_by_tokens(text)

        for chunk in chunks:
            try:
                embedding = get_embedding(chunk)
                all_chunks.append({
                    "text": chunk,
                    "source": url,
                    "label": url.split("/")[-2].replace("-", " ").title()
                })
                all_embeddings.append(embedding)
                print(f"🔹 Embedded from {url}")
            except Exception as e:
                print(f"⚠️  Skipped an HTML chunk from {url} – {e}")
            time.sleep(1)

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)
        for link in links:
            absolute_url = urljoin(url, link["href"])
            if is_valid_url(absolute_url):
                crawl(absolute_url)

    except Exception as e:
        print(f"❌ Failed to crawl {url} – {e}")

# ─── Start Crawling ────────────────────────────────────
for url in START_URLS:
    crawl(url)

# ─── Save Files ────────────────────────────────────────
with open("metadata.pkl", "wb") as f:
    pickle.dump(all_chunks, f)

with open("embeddings.pkl", "wb") as f:
    pickle.dump(np.array(all_embeddings), f)

# Combine and save to kb_chunks.pkl
kb_chunks = []
for i in range(len(all_chunks)):
    chunk = all_chunks[i]
    chunk["embedding"] = all_embeddings[i]
    kb_chunks.append(chunk)

os.makedirs("kb_chunks", exist_ok=True)
with open("kb_chunks/kb_chunks.pkl", "wb") as f:
    pickle.dump(kb_chunks, f)

print(f"\n✅ Done: {len(kb_chunks)} total chunks embedded and saved.")
