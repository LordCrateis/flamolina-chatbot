from api.retrieve import SUPABASE_URL
from api.retrieve import SUPABASE_KEY
import os
import requests
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

GNEWS_API_KEY = os.environ["GNEWS_API_KEY"]


def search_news(query: str, max_results: int = 5) -> str:
    """Searches GNews for recent articles matching the query."""
    url = "https://gnews.io/api/v4/search?q=AI&apikey=7409d1002485daa226ff544a1c0beb2d"
    params = {"q": query, "lang": "en", "max": max_results}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return f"News search failed: {e}"

    articles = data.get("articles", [])
    if not articles:
        return "No recent news articles found for that query."

    lines = []
    for a in articles:
        title = a.get("title", "")
        source = a.get("source", {}).get("name", "Unknown source")
        published = a.get("publishedAt", "")
        description = a.get("description", "")
        lines.append(f"- [{source}, {published}] {title}: {description}")
    return "\n".join(lines)


def search_hackernews(query: str, max_results: int = 5) -> str:
    """Searches Hacker News (via Algolia HN Search API) for stories matching the query."""
    url = "https://hn.algolia.com/api/v1/search"
    params = {"query": query, "tags": "story", "hitsPerPage": max_results}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return f"Hacker News search failed: {e}"

    hits = data.get("hits", [])
    if not hits:
        return "No relevant Hacker News stories found."

    lines = []
    for h in hits:
        title = h.get("title", "")
        points = h.get("points", 0)
        author = h.get("author", "")
        url_link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        lines.append(f"- {title} ({points} pts, by {author}) — {url_link}")
    return "\n".join(lines)


def search_ai_jobs(query: str = "", max_results: int = 5, remote_only: bool = False, region: str = "", city: str = "") -> str:
    """Searches live AI job listings via artificialintelligencejobs.co (free, no-key API)."""
    url = "https://artificialintelligencejobs.co/api/jobs"
    params = {"limit": max_results}
    if query:
        params["q"] = query
    if remote_only:
        params["remote"] = "true"
    if region:
        params["region"] = region
    if city:
        params["city"] = city

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return f"AI jobs search failed: {e}"

    jobs = data.get("jobs", [])
    if not jobs:
        return "No matching AI job listings found for that search."

    lines = []
    for j in jobs:
        title = j.get("title", "")
        company = j.get("company", "")
        location = j.get("location", "")
        remote = "Remote" if j.get("remote") else location
        salary = j.get("salary", "")
        job_url = j.get("url", "")
        salary_part = f" | {salary}" if salary else ""
        lines.append(f"- {title} at {company} ({remote}){salary_part} — {job_url}")
    return "\n".join(lines) + "\n\n(Source: artificialintelligencejobs.co)"


def get_blog_stats(title_keyword: str) -> str:
    """Looks up exact like/comment counts for a blog post by matching its title directly in Supabase — not via vector search, since these are exact structured facts."""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = client.table("blogs").select("id, title, like_count").ilike("title", f"%{title_keyword}%").execute()
    blogs = result.data or []

    if not blogs:
        return f"No blog post found matching '{title_keyword}'."

    lines = []
    for b in blogs:
        comment_result = client.table("blog_comments").select("id", count="exact").eq("blog_id", b["id"]).execute()
        comment_count = comment_result.count or 0
        lines.append(f"- '{b['title']}': {b['like_count']} likes, {comment_count} comments")

    return "\n".join(lines)

def get_project_ratings(title_keyword: str = "") -> str:
    """Looks up average rating and rating count for projects, optionally filtered by title keyword. Use for 'highest rated', 'best rated', or rating-count questions."""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    proj_query = client.table("projects").select("id, title")
    if title_keyword:
        proj_query = proj_query.ilike("title", f"%{title_keyword}%")
    projects = proj_query.execute().data or []

    if not projects:
        return f"No project found matching '{title_keyword}'." if title_keyword else "No projects found."

    lines = []
    for p in projects:
        ratings_result = client.table("project_ratings").select("value").eq("project_uuid", p["id"]).execute()
        values = [r["value"] for r in (ratings_result.data or [])]
        if values:
            avg = sum(values) / len(values)
            lines.append(f"- '{p['title']}': {avg:.1f}/5 average ({len(values)} ratings)")
        else:
            lines.append(f"- '{p['title']}': no ratings yet")

    return "\n".join(lines)

if __name__ == "__main__":
    print("=== GNews ===")
    print(search_news("AI models 2026"))
    print("\n=== Hacker News ===")
    print(search_hackernews("machine learning"))
    print("\n=== AI Jobs ===")
    print(search_ai_jobs("llm"))