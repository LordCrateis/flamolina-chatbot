import os
import json
# pyrefly: ignore [missing-import]
from groq import Groq
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

from api.tools import *
from api.retrieve import retrieve_context
from prompts.persona import build_prompt

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = "openai/gpt-oss-120b"

client = Groq(api_key=GROQ_API_KEY)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search recent news articles on any current topic. Use this when the user asks about current events, recent tech developments, or anything time-sensitive that isn't covered by Shivam's own data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query for news articles."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hackernews",
            "description": "Search Hacker News for tech/startup community discussions and stories on a topic. Use this for tech-community sentiment, discussions, or notable tech stories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query for Hacker News stories."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ai_jobs",
            "description": "Search live AI/ML job listings. Use this when the user asks about the AI job market, hiring trends, or specific AI roles available right now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Job search keywords, e.g. 'llm', 'computer vision'."},
                    "remote_only": {"type": "boolean", "description": "Whether to filter to remote-only roles."},
                    "region": {"type": ["string", "null"], "description": "Filter by region/country, e.g. 'India', 'Europe'."},
                    "city": {"type": ["string", "null"], "description": "Filter by city, e.g. 'Bengaluru', 'London'."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_blog_stats",
            "description": "Look up exact like count and comment count for a specific blog post by title keyword. Use this whenever the user asks about likes, comments, or engagement numbers on a blog post — do not guess these from retrieved context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title_keyword": {"type": "string", "description": "A keyword from the blog post title, e.g. 'Akshar'."}
                },
                "required": ["title_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_ratings",
            "description": "Get average rating and rating count for one or all projects. Use this for any 'highest rated', 'best project', or rating-count question — do not guess ratings from retrieved context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title_keyword": {"type": ["string", "null"], "description": "Optional keyword to filter to one project. Leave empty to get all projects' ratings."}
                },
                "required": [],
            },
        },
    },
]

AVAILABLE_FUNCTIONS = {
    "search_news": lambda args: search_news(args.get("query", "")),
    "search_hackernews": lambda args: search_hackernews(args.get("query", "")),
    "search_ai_jobs": lambda args: search_ai_jobs(
        args.get("query") or "",
        remote_only=args.get("remote_only", False),
        region=args.get("region") or "",
        city=args.get("city") or "",
    ),
    "get_blog_stats": lambda args: get_blog_stats(args.get("title_keyword", "")),
    "get_project_ratings": lambda args: get_project_ratings(args.get("title_keyword") or ""),
}


def get_flamolina_response(user_query: str, conversation_history: list, max_tool_rounds: int = 3) -> tuple[str, list]:
    """
    Full pipeline with conversation memory:
    - retrieves fresh RAG context for this specific query
    - appends it + the user query to the existing conversation history
    - resolves any tool calls
    - returns (answer, updated_history) so the caller can persist it across turns
    """
    retrieval = retrieve_context(user_query)

    context_block = (
        f"RETRIEVED CONTEXT (about Shivam — use this to ground your answer if relevant):\n{retrieval['context']}"
        if retrieval["context"].strip()
        else "RETRIEVED CONTEXT: (none relevant found — don't invent specifics about Shivam if asked)"
    )

    # Fresh context is injected as a system message right before this user turn,
    # so it's relevant to THIS question without permanently polluting history.
    messages = conversation_history + [
        {"role": "system", "content": context_block},
        {"role": "user", "content": user_query},
    ]

    for _ in range(max_tool_rounds):
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.8,
            max_tokens=500,
        )

        response_message = completion.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            # Persist only the clean user turn + final answer to history —
            # not the per-turn retrieved context or tool-call noise.
            updated_history = conversation_history + [
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": response_message.content},
            ]
            return response_message.content, updated_history

        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            function_to_call = AVAILABLE_FUNCTIONS.get(function_name)
            if function_to_call:
                function_response = function_to_call(function_args)
            else:
                function_response = f"Unknown tool: {function_name}"

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            })

    final_completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=300,
    )
    final_answer = final_completion.choices[0].message.content
    updated_history = conversation_history + [
        {"role": "user", "content": user_query},
        {"role": "assistant", "content": final_answer},
    ]
    return final_answer, updated_history


if __name__ == "__main__":
    from prompts.persona import FLAMOLINA_SYSTEM_PROMPT

    history = [{"role": "system", "content": FLAMOLINA_SYSTEM_PROMPT}]

    while True:
        query = input("\nYou: ")
        if query.lower() in ("exit", "quit"):
            break
        answer, history = get_flamolina_response(query, history)
        print(f"\nFlamolina: {answer}")
if __name__ == "__main__":
    from prompts.persona import FLAMOLINA_SYSTEM_PROMPT

    history = [{"role": "system", "content": FLAMOLINA_SYSTEM_PROMPT}]

    while True:
        query = input("\nYou: ")
        if query.lower() in ("exit", "quit"):
            break
        answer, history = get_flamolina_response(query, history)
        print(f"\nFlamolina: {answer}")