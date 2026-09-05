"""Scripty, the agent. Google ADK + Gemini; its only data access is ClickHouse through the official
mcp-clickhouse MCP server (runtime, load-bearing), plus one tool that can look at two frames."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from mcp import StdioServerParameters

from .verify import verify_pair

INSTRUCTION = """You are Scripty, a continuity assistant for a film's script supervisor. Your data is a ClickHouse
database `scripty` with tables:
- scripty.frames (project, scene, take, shot, t_s, frame_id, image_path)
- scripty.inventory (project, scene, take, shot, t_s, frame_id, entity, entity_kind, attribute, value, confidence, region)
- scripty.findings (project, scene, finding_id, category, entity, attribute, take_a, frame_a, value_a, take_b, frame_b, value_b, sql_score, verified, verdict, confidence, explanation)
- scripty.eval_labels (planted ground truth for evaluation scenes)
Use run_query (read-only SQL, always add FINAL after ReplacingMergeTree tables and LIMIT) to answer questions
like "what changed on the desk between take 2 and take 4", "which findings are confirmed continuity errors",
"what does take 3 hold in the left hand". Cite the rows you used (take, shot, t_s, value). When a user asks
you to double-check a specific pair, call look_at_pair with the two frame_ids. Be concise and concrete; a
supervisor reads this at call time."""


def look_at_pair(frame_a_id: str, frame_b_id: str, entity: str, attribute: str, value_a: str, value_b: str) -> dict:
    """Look at two frames (by frame_id) and rule whether the candidate difference is a continuity error."""
    from . import db
    pa = db.query("SELECT image_path FROM scripty.frames FINAL WHERE frame_id = {f:String} LIMIT 1", {"f": frame_a_id})
    pb = db.query("SELECT image_path FROM scripty.frames FINAL WHERE frame_id = {f:String} LIMIT 1", {"f": frame_b_id})  # thread-local client
    if not pa or not pb:
        return {"error": "unknown frame_id"}
    v = verify_pair(Path(pa[0]["image_path"]), Path(pb[0]["image_path"]), entity, attribute, value_a, value_b)
    return v.model_dump()


def clickhouse_toolset() -> McpToolset:
    env = {k: v for k, v in os.environ.items()}
    env.setdefault("CLICKHOUSE_USER", "default")
    import shutil
    exe = shutil.which("mcp-clickhouse")
    params = StdioServerParameters(command=exe, args=[], env=env) if exe else StdioServerParameters(command="uvx", args=["--from", "mcp-clickhouse", "mcp-clickhouse"], env=env)
    return McpToolset(connection_params=StdioConnectionParams(server_params=params, timeout=90), tool_filter=["run_query", "list_tables", "list_databases"])


def build_agent(model: str | None = None) -> tuple[LlmAgent, McpToolset]:
    ts = clickhouse_toolset()
    agent = LlmAgent(name="scripty", model=model or os.getenv("SCRIPTY_AGENT_MODEL", "gemini-2.5-flash"), instruction=INSTRUCTION, tools=[ts, look_at_pair])
    return agent, ts


async def ask_async(question: str, session_state: dict | None = None) -> tuple[str, list[str]]:
    agent, ts = build_agent()
    sessions = InMemorySessionService()
    runner = Runner(agent=agent, app_name="scripty", session_service=sessions)
    session = await sessions.create_session(app_name="scripty", user_id="supervisor", state=session_state or {})
    msg = types.Content(role="user", parts=[types.Part(text=question)])
    final, calls = "", []
    try:
        async for ev in runner.run_async(user_id="supervisor", session_id=session.id, new_message=msg):
            if ev.content and ev.content.parts:
                for part in ev.content.parts:
                    fc = getattr(part, "function_call", None)
                    if fc is not None:
                        calls.append(fc.name)
                    if ev.is_final_response() and getattr(part, "text", None):
                        final += part.text
    finally:
        try:
            await ts.close()
        except Exception:
            pass
    return final, calls


def ask(question: str) -> tuple[str, list[str]]:
    return asyncio.run(ask_async(question))
