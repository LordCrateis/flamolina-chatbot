import os
import re
from pathlib import Path
import requests
# pyrefly: ignore [missing-import]
from huggingface_hub import InferenceClient
# pyrefly: ignore [missing-import]
from supabase import create_client
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HF_TOKEN = os.environ["HF_TOKEN"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
PERSONAL_DIR = Path(__file__).parent.parent / "personal"


client_hf = InferenceClient(
    token=HF_TOKEN,
    provider="hf-inference"
)


def embed_batch(texts: list[str]) -> list[list[float]]:
    embeddings = client_hf.feature_extraction(
        text=texts,
        model="sentence-transformers/all-MiniLM-L6-v2"
    )

    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()

    return embeddings


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c for c in chunks if len(c.strip()) > 20]


def ingest_personal():
    print(f"Reading personal files from {PERSONAL_DIR}...")
    md_files = list(PERSONAL_DIR.glob("*.md"))
    print(f"  {len(md_files)} files found")

    supabase.table("personal_chunks").delete().neq("id", 0).execute()

    all_rows = []
    for file_path in md_files:
        text = file_path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        if not chunks:
            continue

        embeddings = embed_batch(chunks)
        for chunk, emb in zip(chunks, embeddings):
            all_rows.append({
                "source_file": file_path.stem,
                "content": chunk,
                "embedding": emb,
            })
        print(f"  {file_path.name}: {len(chunks)} chunks")

    if all_rows:
        supabase.table("personal_chunks").insert(all_rows).execute()
    print("Personal files ingested.")


if __name__ == "__main__":
    ingest_personal()