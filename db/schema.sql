-- Enable pgvector
create extension if not exists vector;

-- Resume chunks
create table resume_chunks (
  id bigserial primary key,
  content text not null,
  embedding vector(384),
  created_at timestamptz default now()
);

-- README / project doc chunks
create table readme_chunks (
  id bigserial primary key,
  project_slug text not null, -- ties chunk back to a project in your existing projects table
  content text not null,
  embedding vector(384),
  created_at timestamptz default now()
);

-- Row level security — locked down, only service role key can access
alter table resume_chunks enable row level security;
alter table readme_chunks enable row level security;

-- Similarity search functions
create or replace function match_resume_chunks(
  query_embedding vector(384),
  match_count int default 5
)
returns table (id bigint, content text, similarity float)
language sql stable
as $$
  select id, content, 1 - (embedding <=> query_embedding) as similarity
  from resume_chunks
  order by embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_readme_chunks(
  query_embedding vector(384),
  match_count int default 5
)
returns table (id bigint, project_slug text, content text, similarity float)
language sql stable
as $$
  select id, project_slug, content, 1 - (embedding <=> query_embedding) as similarity
  from readme_chunks
  order by embedding <=> query_embedding
  limit match_count;
$$;