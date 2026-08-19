import os
import re
from html import unescape
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer
# pyrefly: ignore [missing-import]
from supabase import create_client
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = SentenceTransformer("all-MiniLM-L6-v2")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c for c in chunks if len(c.strip()) > 20]


def ingest_blogs():
    print("Fetching blogs...")
    result = supabase.table("blogs").select(
        "id, title, content, published, like_count, category, published_at"
    ).eq("published", True).execute()
    blogs = result.data or []
    print(f"  {len(blogs)} published blogs")

    supabase.table("blog_chunks").delete().neq("id", 0).execute()

    all_rows = []
    for blog in blogs:
        text = strip_html(blog.get("content") or "")

        # Prepend structured metadata so it's part of the searchable/retrievable text
        meta_line = (
            f"Blog post: {blog['title']}. Category: {blog.get('category', 'N/A')}. "
            f"Published: {blog.get('published_at', 'N/A')}. Likes: {blog.get('like_count', 0)}."
        )
        full_text = f"{meta_line} {text}"

        chunks = chunk_text(full_text)
        if not chunks:
            continue

        embeddings = model.encode(chunks)
        for chunk, emb in zip(chunks, embeddings):
            all_rows.append({
                "blog_id": blog["id"],
                "title": blog["title"],
                "content": chunk,
                "embedding": emb.tolist(),
            })
        print(f"  {blog['title']}: {len(chunks)} chunks")

    if all_rows:
        supabase.table("blog_chunks").insert(all_rows).execute()
    print("Blogs ingested.")

def ingest_projects():
    print("Fetching projects...")
    result = supabase.table("projects").select(
        "id, title, category, year, description, tech_stack, status, live_url"
    ).eq("visible", True).execute()
    projects = result.data or []
    print(f"  {len(projects)} visible projects")

    supabase.table("project_chunks").delete().neq("id", 0).execute()

    all_rows = []
    for proj in projects:
        tech = ", ".join(proj.get("tech_stack") or [])
        full_text = (
            f"{proj['title']} ({proj.get('category', '')}, {proj.get('year', '')}). "
            f"Status: {proj.get('status', '')}. "
            f"{proj.get('description', '')} "
            f"Tech stack: {tech}. "
            f"Live at: {proj.get('live_url', '')}"
        )
        chunks = chunk_text(full_text)
        if not chunks:
            continue

        embeddings = model.encode(chunks)
        for chunk, emb in zip(chunks, embeddings):
            all_rows.append({
                "project_id": proj["id"],
                "title": proj["title"],
                "content": chunk,
                "embedding": emb.tolist(),
            })
        print(f"  {proj['title']}: {len(chunks)} chunks")

    if all_rows:
        supabase.table("project_chunks").insert(all_rows).execute()
    print("Projects ingested.")


if __name__ == "__main__":
    ingest_blogs()
    ingest_projects()