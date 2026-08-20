import os
import re
import requests
# pyrefly: ignore [missing-import]
from huggingface_hub import InferenceClient
# pyrefly: ignore [missing-import]
from pypdf import PdfReader
# pyrefly: ignore [missing-import]
from supabase import create_client
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
GITHUB_USERNAME = os.environ["GITHUB_USERNAME"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RESUME_PATH = os.environ["RESUME_PATH"]
HF_TOKEN = os.environ["HF_TOKEN"]


CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


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


def extract_resume_text(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def ingest_resume():
    print("Extracting resume text...")
    text = extract_resume_text(RESUME_PATH)
    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks")

    supabase.table("resume_chunks").delete().neq("id", 0).execute()

    embeddings = embed_batch(chunks)
    rows = [
        {"content": chunk, "embedding": emb}
        for chunk, emb in zip(chunks, embeddings)
    ]
    supabase.table("resume_chunks").insert(rows).execute()
    print("Resume ingested.")


def get_github_repos() -> list[dict]:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos"
    params = {"per_page": 100, "type": "owner"}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def get_readme_content(repo_name: str) -> str | None:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    headers["Accept"] = "application/vnd.github.raw+json"
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/readme"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return None
    return resp.text


def ingest_readmes():
    print("Fetching repo list...")
    repos = get_github_repos()
    print(f"  {len(repos)} repos found")

    supabase.table("readme_chunks").delete().neq("id", 0).execute()

    all_rows = []
    for repo in repos:
        name = repo["name"]
        readme = get_readme_content(name)
        if not readme:
            print(f"  {name}: no README, skipping")
            continue

        chunks = chunk_text(readme)
        if not chunks:
            continue

        embeddings = embed_batch(chunks)
        for chunk, emb in zip(chunks, embeddings):
            all_rows.append({
                "project_slug": name,
                "content": chunk,
                "embedding": emb,
            })
        print(f"  {name}: {len(chunks)} chunks")

    if all_rows:
        supabase.table("readme_chunks").insert(all_rows).execute()
    print("READMEs ingested.")


if __name__ == "__main__":
    ingest_resume()
    ingest_readmes()