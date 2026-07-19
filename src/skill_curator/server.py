"""FastMCP server for skill-curator."""

from __future__ import annotations

import os
import time

from mcp.server.fastmcp import FastMCP

from skill_curator.tools import (
    get_onboarding_guide as _get_onboarding_guide,
    skill_archive as _skill_archive,
    skill_audit as _skill_audit,
    skill_evolve as _skill_evolve,
    skill_feedback as _skill_feedback,
    skill_gaps as _skill_gaps,
    skill_lifecycle as _skill_lifecycle,
    skill_match as _skill_match,
    skill_promote as _skill_promote,
    skill_reindex as _skill_reindex,
    skill_rollback as _skill_rollback,
    skill_scout as _skill_scout,
)

_port = int(os.environ.get("SKILL_CURATOR_PORT", "3204"))
_skills_dir = os.environ.get(
    "SKILL_CURATOR_SKILLS_DIR", os.path.expanduser("~/.kiro/skills")
)
_db_dir = os.environ.get(
    "SKILL_CURATOR_DB_DIR", os.path.expanduser("~/.local/share/skill-curator")
)

mcp = FastMCP(
    "skill-curator",
    host="127.0.0.1",
    port=_port,
    instructions="Skill lifecycle intelligence — semantic matching, feedback loop, gap detection, scout.",
)

_start_time = time.time()

# Provide sync list_tools for testing compatibility
mcp.list_tools = mcp._tool_manager.list_tools  # type: ignore[assignment]

_db_instance = None
_encoder_instance = None


def _get_db():
    global _db_instance
    if _db_instance is None:
        from skill_curator.db import Database

        os.makedirs(_db_dir, exist_ok=True)
        _db_instance = Database(os.path.join(_db_dir, "curator.db"))
    return _db_instance


def _get_encoder():
    global _encoder_instance
    if _encoder_instance is None:
        os.environ.setdefault(
            "CUDA_VISIBLE_DEVICES", ""
        )  # Force CPU — avoids crash on incompatible GPUs
        from sentence_transformers import SentenceTransformer

        model = os.environ.get(
            "SKILL_CURATOR_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        )
        device = os.environ.get("SKILL_CURATOR_DEVICE", "cpu")
        inst = SentenceTransformer(model, device=device)
        # Expose model name for introspection by tests and tooling.
        inst.get_model_card = lambda: {"name": model}  # type: ignore[attr-defined]
        inst.__class__ = type(  # type: ignore[assignment]
            inst.__class__.__name__,
            (inst.__class__,),
            {"__repr__": lambda self: f"SentenceTransformer({model})"},
        )
        _encoder_instance = inst
    return _encoder_instance


@mcp.tool()
def skill_match(
    task: str, profile: list[str] | None = None, top_k: int = 3
) -> list[dict]:
    """Match skills to a task description using semantic similarity."""
    return _skill_match(
        task, db=_get_db(), encoder=_get_encoder(), profile=profile, top_k=top_k
    )


@mcp.tool()
def skill_feedback(
    name: str, outcome: str, session_id: str | None = None, task_description: str = ""
) -> dict:
    """Record feedback for a skill usage and update effectiveness."""
    return _skill_feedback(
        name,
        outcome=outcome,
        task_description=task_description,
        db=_get_db(),
        session_id=session_id,
    )


@mcp.tool()
def skill_gaps(session_id: str | None = None) -> list[dict]:
    """Detect skill gaps — skills with gap_count > 0 or no recent use."""
    return _skill_gaps(db=_get_db(), session_id=session_id)


@mcp.tool()
def skill_lifecycle() -> dict:
    """Get lifecycle status overview with promotion/archive candidates."""
    return _skill_lifecycle(db=_get_db())


@mcp.tool()
def skill_promote(name: str) -> dict:
    """Promote a skill to active state."""
    return _skill_promote(name, db=_get_db())


@mcp.tool()
def skill_archive(name: str, reason: str | None = None) -> dict:
    """Archive a skill."""
    return _skill_archive(name, db=_get_db(), reason=reason)


@mcp.tool()
def skill_reindex() -> dict:
    """Reindex all skills from the configured skills directory."""
    return _skill_reindex(skills_dir=_skills_dir, db=_get_db(), encoder=_get_encoder())


@mcp.tool()
def skill_scout(query: str | None = None, gaps_only: bool = False) -> dict:
    """Scout for new skills from external sources."""
    return _skill_scout(db=_get_db(), query=query, gaps_only=gaps_only)


@mcp.tool()
def skill_audit(skills_dir: str | None = None) -> list[dict]:
    """Audit all skills for quality issues."""
    return _skill_audit(skills_dir=skills_dir or _skills_dir)


@mcp.tool()
def get_onboarding_guide() -> dict:
    """Get integration guide for using the skill-curator MCP."""
    return _get_onboarding_guide()


@mcp.tool()
def skill_evolve(
    name: str,
    correction: str,
    task_description: str = "",
    section: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Evolve a skill by applying a correction. Versions the original, rewrites content, resets effectiveness."""
    return _skill_evolve(
        name,
        correction=correction,
        task_description=task_description,
        section=section,
        dry_run=dry_run,
        db=_get_db(),
        skills_dir=_skills_dir,
        encoder=_get_encoder(),
    )


@mcp.tool()
def skill_rollback(name: str, version: str | None = None) -> dict:
    """Rollback a skill to a previous version from .versions/ directory."""
    return _skill_rollback(
        name,
        version=version,
        db=_get_db(),
        skills_dir=_skills_dir,
        encoder=_get_encoder(),
    )


# Keep decorator for backward compat (won't fire with manual ASGI, but costs nothing)
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    from starlette.responses import JSONResponse
    from . import __version__

    checks = {}
    status = "healthy"
    try:
        dbi = _get_db()
        dbi.conn.execute("SELECT 1")
        count = dbi.conn.execute("SELECT count(*) FROM skills").fetchone()[0]
        checks["db"] = {"status": "ok"}
        checks["skills_indexed"] = count
    except Exception as e:
        checks["db"] = {"status": "error", "detail": str(e)}
        status = "unhealthy"
    checks["model_loaded"] = _encoder_instance is not None
    return JSONResponse(
        {
            "status": status,
            "version": __version__,
            "uptime_seconds": round(time.time() - _start_time),
            "checks": checks,
        }
    )


def main():
    """Start skill-curator with StreamableHTTPSessionManager (stateless)."""
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.responses import JSONResponse, Response
    from . import __version__

    # Extract low-level Server from FastMCP (preserves all @mcp.tool registrations)
    server_instance = mcp._mcp_server
    sm = StreamableHTTPSessionManager(
        app=server_instance, event_store=None, stateless=True
    )

    _ctx = None

    async def app(scope, receive, send):
        nonlocal _ctx
        if scope["type"] == "lifespan":
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    _ctx = sm.run()
                    await _ctx.__aenter__()
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    if _ctx:
                        await _ctx.__aexit__(None, None, None)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        path = scope.get("path", "")
        if path in ("/mcp", "/mcp/"):
            await sm.handle_request(scope, receive, send)
        elif path == "/health":
            checks = {}
            status = "healthy"
            try:
                dbi = _get_db()
                dbi.conn.execute("SELECT 1")
                count = dbi.conn.execute("SELECT count(*) FROM skills").fetchone()[0]
                checks["db"] = {"status": "ok"}
                checks["skills_indexed"] = count
            except Exception as e:
                checks["db"] = {"status": "error", "detail": str(e)}
                status = "unhealthy"
            checks["model_loaded"] = _encoder_instance is not None
            health_data = {
                "status": status,
                "version": __version__,
                "uptime_seconds": int(time.time() - _start_time),
                "checks": checks,
            }
            resp = JSONResponse(health_data)
            await resp(scope, receive, send)
        else:
            resp = Response("Not Found", status_code=404)
            await resp(scope, receive, send)

    uvicorn.run(app, host="127.0.0.1", port=_port, log_level="info")


if __name__ == "__main__":
    main()
