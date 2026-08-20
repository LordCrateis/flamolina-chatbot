import os
from concurrent.futures import ThreadPoolExecutor
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from huggingface_hub import InferenceClient
# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")

# Initialize Hugging Face Inference Client
client_hf = InferenceClient(token=HF_TOKEN)


def embed_query(query: str) -> list[float]:
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN is missing or not loaded from environment variables.")

    # Calls the feature-extraction pipeline cleanly via official client
    embeddings = client_hf.feature_extraction(
        text=query,
        model="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # Flatten if returned as nested list
    if isinstance(embeddings, list) and isinstance(embeddings[0], list):
        return embeddings[0]
    return embeddings.tolist() if hasattr(embeddings, "tolist") else list(embeddings)


def _rpc_call(function_name: str, query_embedding: list, match_count: int):
    # Fresh client per call avoids sharing HTTP/2 connection pool across threads
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.rpc(
        function_name,
        {"query_embedding": query_embedding, "match_count": match_count},
    ).execute()
    return result.data or []


def retrieve_context(query: str, match_count: int = 4) -> dict:
    query_embedding = embed_query(query)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            "resume": executor.submit(_rpc_call, "match_resume_chunks", query_embedding, match_count),
            "readme": executor.submit(_rpc_call, "match_readme_chunks", query_embedding, match_count),
            "blog": executor.submit(_rpc_call, "match_blog_chunks", query_embedding, match_count),
            "project": executor.submit(_rpc_call, "match_project_chunks", query_embedding, match_count),
            "personal": executor.submit(_rpc_call, "match_personal_chunks", query_embedding, match_count),
        }
        results = {k: f.result() for k, f in futures.items()}

    resume_chunks = results["resume"]
    readme_chunks = results["readme"]
    blog_chunks = results["blog"]
    project_chunks = results["project"]
    personal_chunks = results["personal"]

    context_parts = []

    if personal_chunks:
        context_parts.append("--- PERSONAL CONTEXT (about Shivam as a person) ---")
        for c in personal_chunks:
            context_parts.append(c["content"])

    if resume_chunks:
        context_parts.append("--- RESUME ---")
        for c in resume_chunks:
            context_parts.append(c["content"])

    if project_chunks:
        context_parts.append("--- PROJECTS ---")
        for c in project_chunks:
            context_parts.append(f"[{c['title']}] {c['content']}")

    if readme_chunks:
        context_parts.append("--- PROJECT READMEs ---")
        for c in readme_chunks:
            context_parts.append(f"[{c['project_slug']}] {c['content']}")

    if blog_chunks:
        context_parts.append("--- BLOG POSTS ---")
        for c in blog_chunks:
            context_parts.append(f"[{c['title']}] {c['content']}")

    context_str = "\n\n".join(context_parts)

    return {
        "context": context_str,
        "resume_chunks": resume_chunks,
        "readme_chunks": readme_chunks,
        "blog_chunks": blog_chunks,
        "project_chunks": project_chunks,
        "personal_chunks": personal_chunks,
    }