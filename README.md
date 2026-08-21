<div align="center">

# Flamolina

**The AI assistant behind [shivambuilds.dev](https://shivambuilds.dev)**

Retrieval-augmented · Confident · Grounded in real data

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-service-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![Groq](https://img.shields.io/badge/Groq-chat%20completions-F55036)](https://groq.com/)

</div>

---

Flamolina is a retrieval-augmented chatbot built to answer questions about Shivam Tamboli — his projects, engineering experience, writing, and relevant technology topics. Its persona is intentionally **confident, dry, and slightly cocky**; off-topic questions get redirected rather than answered like a general-purpose assistant.

Under the hood, it combines a FastAPI service, Supabase-backed vector search, Hugging Face embeddings, Groq chat completions, and a small set of live web-data tools. The repository also ships ingestion scripts for a resume PDF, GitHub repository READMEs, blog posts, project records, and optional personal Markdown files.

> **Design philosophy:** useful on-topic, concise in its answers, grounded in retrieved data, and unwilling to invent facts about Shivam.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Database Setup](#database-setup)
- [Ingesting Knowledge](#ingesting-knowledge)
- [Running the API](#running-the-api)
- [Command-Line Conversation Mode](#command-line-conversation-mode)
- [Live Tools](#live-tools)
- [Automated Re-ingestion](#automated-re-ingestion)
- [Security & Deployment Notes](#security--deployment-notes)
- [Project Layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [References](#references)

---

## Features

| Capability | Description |
| --- | --- |
| **Portfolio-aware chat** | Answers questions about Shivam's resume, projects, GitHub READMEs, blog posts, and personal context. |
| **Retrieval-augmented generation** | Embeds each query with `sentence-transformers/all-MiniLM-L6-v2`, then searches multiple Supabase vector collections in parallel. |
| **Live technology searches** | Searches recent news, Hacker News discussions, and AI job listings when a question needs current information. |
| **Structured portfolio lookups** | Uses direct Supabase queries for exact blog like/comment counts and project ratings instead of guessing from semantic context. |
| **Conversation history** | Accepts prior user/assistant turns and returns updated history so the client can persist multi-turn conversations. |
| **FastAPI endpoints** | Health check and a JSON chat endpoint with request validation and configurable CORS. |
| **Automated content refresh** | GitHub Actions workflow re-ingests blog and project content every six hours, with manual dispatch support. |

## Architecture

The request path is intentionally simple:

```text
Client
  │
  ├── GET /health
  └── POST /chat
          │
          ▼
    FastAPI application
          │
          ├── Embed user query with Hugging Face
          ├── Retrieve resume, README, blog, project, and personal chunks from Supabase
          ├── Ask Groq for an answer with optional tool calls
          │       ├── GNews search
          │       ├── Hacker News search
          │       ├── AI jobs search
          │       ├── Exact blog statistics
          │       └── Exact project ratings
          └── Return answer and updated conversation history
```

| Layer | Location |
| --- | --- |
| FastAPI app (`app`) | [`api/server.py`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/server.py) |
| Retrieval | [`api/retrieve.py`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/retrieve.py) |
| Orchestration & tool calls | [`api/router.py`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/router.py) |
| External integrations | [`api/tools.py`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/tools.py) |

## Requirements

| Requirement | Purpose |
| --- | --- |
| Python 3.11+ | Runs the FastAPI service and ingestion modules. |
| Supabase project with `pgvector` | Stores embedded chunks and serves similarity-search RPCs. |
| Groq API key | Generates chatbot responses with the configured `openai/gpt-oss-120b` model. |
| Hugging Face token | Generates 384-dimensional embeddings via the HF Inference API. |
| Resume PDF | Source document for resume ingestion. |
| GitHub username + optional token | Allows ingestion of the owner's repository READMEs. |
| GNews API key | Intended for current-news search — see the [security note](#security--deployment-notes) before deploying. |

Install the dependencies in a virtual environment:

```bash
git clone https://github.com/LordCrateis/flamolina-chatbot.git
cd flamolina-chatbot

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuration

Create a local environment file from the provided template:

```bash
cp .env.example .env
```

Then fill in the values below. **Never commit** `.env`, service-role keys, API tokens, or private source documents.

| Variable | Required | Used by | Description |
| --- | --- | --- | --- |
| `SUPABASE_URL` | Yes | API & ingestion | URL of the Supabase project. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | API & ingestion | Server-side Supabase key with read/write access to ingestion tables. Keep it private. |
| `HF_TOKEN` | Yes | API & ingestion | Hugging Face token used with `sentence-transformers/all-MiniLM-L6-v2`. |
| `GROQ_API_KEY` | Yes for chat | API | Groq credential used by the chat orchestration layer. |
| `GNEWS_API_KEY` | Intended | API tools | Credential intended for GNews search. |
| `GITHUB_USERNAME` | Yes for README ingestion | `ingest.ingest` | GitHub account whose owned repositories should be indexed. |
| `GITHUB_TOKEN` | Optional | `ingest.ingest` | Optional token for higher API limits or private-access scenarios. |
| `RESUME_PATH` | Yes for resume ingestion | `ingest.ingest` | Path to the resume PDF. Relative paths resolve from the process working directory. |
| `FLAMOLINA_ALLOWED_ORIGINS` | Optional | API | Comma-separated additional browser origins allowed by CORS. Local Vite origins on port 5173 are allowed by default. |

A minimal `.env` for starting the API:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
HF_TOKEN=your-hugging-face-token
GROQ_API_KEY=your-groq-api-key
GNEWS_API_KEY=your-gnews-api-key
FLAMOLINA_ALLOWED_ORIGINS=http://localhost:3000,https://your-frontend.example.com
```

## Database Setup

The repository includes [`db/schema.sql`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/db/schema.sql), which enables the `vector` extension and creates:

| Provisioned object | Purpose |
| --- | --- |
| `resume_chunks` | Embedded resume passages. |
| `readme_chunks` | Embedded GitHub README passages keyed by `project_slug`. |
| `match_resume_chunks(...)` | Similarity search over resume chunks. |
| `match_readme_chunks(...)` | Similarity search over README chunks. |

Run the SQL in the Supabase SQL editor before the first ingestion. Embedding columns are `vector(384)`, matching the configured MiniLM model's output size.

> **Schema prerequisite**
>
> The API retrieves five knowledge categories through these RPCs:
> ```text
> match_resume_chunks
> match_readme_chunks
> match_blog_chunks
> match_project_chunks
> match_personal_chunks
> ```
> The checked-in `db/schema.sql` currently defines **only** the resume and README tables/RPCs. The blog, project, and personal ingestion scripts also expect `blog_chunks`, `project_chunks`, and `personal_chunks` plus their matching functions. Before enabling those paths, add the missing tables and RPCs to Supabase and confirm their vector columns also use 384-dimensional embeddings.
>
> The source database is expected to already contain the application's `blogs`, `projects`, `blog_comments`, and `project_ratings` tables — these are **not** created by this repo's schema file.

## Ingesting Knowledge

Run all ingestion commands from the repository root with the virtual environment activated.

### Resume & GitHub READMEs

Set `RESUME_PATH`, `GITHUB_USERNAME`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `HF_TOKEN`, then run:

```bash
python -m ingest.ingest
```

This extracts text from the resume PDF, chunks it into ~500-character passages with 100-character overlap, creates embeddings, and replaces the contents of `resume_chunks`. It then lists repositories owned by `GITHUB_USERNAME`, fetches each available README via the GitHub API, embeds the README chunks, and replaces the contents of `readme_chunks`.

### Blogs & Projects

To index published blog posts and visible projects already stored in Supabase:

```bash
python -m ingest.ingest_content
```

Blog ingestion strips HTML and includes title, category, publication date, and like-count metadata before embedding. Project ingestion includes title, category, year, status, description, technology stack, and live URL metadata.

### Optional Personal Markdown Files

The optional personal ingestion module reads every `*.md` file from a repository-root `personal/` directory and stores the resulting chunks in `personal_chunks`:

```bash
mkdir -p personal
# Add private Markdown source files to personal/.
python -m ingest.ingest_personal
```

> The `personal/` directory is **not** part of the tracked repository tree. Treat its contents as private and keep it excluded from version control.

## Running the API

Start the development server from the repository root:

```bash
uvicorn api.server:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive docs live at [`/docs`](http://127.0.0.1:8000/docs), and the OpenAPI schema is at [`/openapi.json`](http://127.0.0.1:8000/openapi.json).

### Health Check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "flamolina"
}
```

### Chat Request

`POST /chat` accepts a non-empty message of up to 12,000 characters and an optional conversation history. History entries must use the roles `user` or `assistant`; invalid roles and blank content are ignored before the model request.

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are Shivam'\''s strongest engineering projects?",
    "history": []
  }'
```

Response shape:

```json
{
  "answer": "...",
  "history": [
    {
      "role": "user",
      "content": "What are Shivam's strongest engineering projects?"
    },
    {
      "role": "assistant",
      "content": "..."
    }
  ]
}
```

## Command-Line Conversation Mode

The orchestration module also contains a simple terminal chat loop:

```bash
python -m api.router
```

Type `exit` or `quit` to stop the session. This mode still requires the same model, embedding, Supabase, and tool configuration as the API server.

## Live Tools

When appropriate, the model can call the following functions:

| Function | Data source | Typical use |
| --- | --- | --- |
| `search_news` | GNews | Recent news and time-sensitive technology topics. |
| `search_hackernews` | Algolia Hacker News Search API | Community discussions and technology stories. |
| `search_ai_jobs` | artificialintelligencejobs.co | Current AI/ML job listings, with optional remote, region, and city filters. |
| `get_blog_stats` | Supabase | Exact blog like and comment counts. |
| `get_project_ratings` | Supabase | Average project ratings and rating counts. |

The persona instructs Flamolina to use structured lookups for exact counts and to state clearly when a live search returns no results.

## Automated Re-ingestion

[`reingest.yml`](https://github.com/LordCrateis/flamolina-chatbot/blob/main/.github/workflows/reingest.yml) schedules `python -m ingest.ingest_content` every six hours and also supports manual execution through GitHub Actions. The workflow expects `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as repository secrets.

> Before relying on this workflow in production, update its dependency installation and environment configuration to match the current ingestion code. In particular, `ingest.ingest_content` uses Hugging Face Inference and reads `HF_TOKEN`, while the workflow currently installs a different embedding dependency set and passes only the two Supabase secrets.

## Security & Deployment Notes

- The service uses a Supabase **service-role key** for server-side retrieval and ingestion. It must remain on the backend and must **never** be exposed to a browser client. Configure the frontend to call the FastAPI service rather than placing Supabase service credentials in frontend code.
- The current `api/tools.py` implementation declares `GNEWS_API_KEY`, but the GNews request URL contains a credential directly in source code. **Before publishing or deploying:** remove any hardcoded credential, construct the request with the environment-provided key, rotate the exposed key, and keep all secrets in environment variables or a secret manager.
- Because the chatbot can call live external services, production deployments should also add request authentication, rate limiting, structured logging, timeouts at the edge, and monitoring for upstream failures. The included API currently exposes `/chat` **without authentication**.

## Project Layout

```text
.
├── api/
│   ├── retrieve.py          # Embedding and parallel Supabase retrieval
│   ├── router.py            # Groq orchestration, tool calls, and CLI loop
│   ├── server.py            # FastAPI app, validation, CORS, and endpoints
│   └── tools.py             # News, Hacker News, jobs, and exact-stat tools
├── db/
│   └── schema.sql           # pgvector tables and initial match functions
├── ingest/
│   ├── ingest.py            # Resume and GitHub README ingestion
│   ├── ingest_content.py    # Blog and project ingestion
│   └── ingest_personal.py   # Optional local Markdown ingestion
├── prompts/
│   └── persona.py           # Flamolina system prompt
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── README.md
```

## Troubleshooting

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `GROQ_API_KEY` or another variable is missing | `.env` is absent, incomplete, or loaded from the wrong working directory | Copy `.env.example` to `.env`, fill in required values, and run commands from the repository root. |
| Retrieval fails on `match_blog_chunks`, `match_project_chunks`, or `match_personal_chunks` | The corresponding tables or RPC functions aren't present in Supabase | Provision the missing vector tables/functions and run the appropriate ingestion script. |
| Embedding requests fail | `HF_TOKEN` is missing or invalid | Confirm the token is set and that the Hugging Face Inference API is available. |
| Resume ingestion fails | `RESUME_PATH` doesn't point to a readable PDF | Use an absolute path or a valid path relative to the repository root. |
| Browser requests are rejected by CORS | The frontend origin isn't in the default local origins or `FLAMOLINA_ALLOWED_ORIGINS` | Add the exact frontend origin as a comma-separated value in `FLAMOLINA_ALLOWED_ORIGINS`. |
| Live search returns no results | The upstream service returned no matching data or is unavailable | Check the service response and avoid presenting guessed information as current data. |

## Contributing

Contributions should preserve Flamolina's core guarantees: answers about Shivam must be grounded in retrieved data, exact numerical facts should come from structured lookups, and secrets must not be committed. When changing the retrieval or embedding model, update the Supabase vector dimensions and all related ingestion and matching functions together.

## References

1. [Flamolina Chatbot repository](https://github.com/LordCrateis/flamolina-chatbot)
2. [FastAPI server](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/server.py)
3. [Retrieval module](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/retrieve.py)
4. [Chat orchestration module](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/router.py)
5. [External and structured data tools](https://github.com/LordCrateis/flamolina-chatbot/blob/main/api/tools.py)
6. [Supabase pgvector schema](https://github.com/LordCrateis/flamolina-chatbot/blob/main/db/schema.sql)
7. [Resume and GitHub README ingestion](https://github.com/LordCrateis/flamolina-chatbot/blob/main/ingest/ingest.py)
8. [Blog and project ingestion](https://github.com/LordCrateis/flamolina-chatbot/blob/main/ingest/ingest_content.py)
9. [Personal Markdown ingestion](https://github.com/LordCrateis/flamolina-chatbot/blob/main/ingest/ingest_personal.py)
10. [Automated re-ingestion workflow](https://github.com/LordCrateis/flamolina-chatbot/blob/main/.github/workflows/reingest.yml)
11. [Flamolina persona prompt](https://github.com/LordCrateis/flamolina-chatbot/blob/main/prompts/persona.py)
