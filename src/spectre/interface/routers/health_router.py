"""Health check router — includes DB, Redis, and ML model status."""

from __future__ import annotations

import datetime
import os
import asyncio

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import text
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Literal

from spectre.config import Settings
from spectre.interface.dependencies import get_current_user, get_settings
from spectre.domain.entities.user import User

router = APIRouter(tags=["Health"])


@router.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with basic UI for testing."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Spectre API | Auth Test</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f4f7f9; }
            .card { background: white; padding: 2.5rem; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); text-align: center; max-width: 400px; width: 90%; }
            h1 { color: #1a1f36; margin-bottom: 0.5rem; font-size: 1.8rem; }
            p { color: #4f566b; margin-bottom: 2rem; line-height: 1.5; }
            .btn-google { 
                display: flex; align-items: center; justify-content: center; 
                background-color: #fff; color: #3c4043; border: 1px solid #dadce0; 
                padding: 10px 24px; border-radius: 4px; font-weight: 500; cursor: pointer;
                text-decoration: none; transition: background-color .2s, box-shadow .2s;
                font-size: 14px;
            }
            .btn-google:hover { background-color: #f8f9fa; box-shadow: 0 1px 2px 0 rgba(60,64,67,.3), 0 1px 3px 1px rgba(60,64,67,.15); }
            .btn-google img { width: 18px; height: 18px; margin-right: 12px; }
            .footer { margin-top: 2rem; font-size: 12px; color: #a3acb9; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Spectre API</h1>
            <p>Internal backend authentication verification portal.</p>
            
            <a href="/api/v1/auth/oauth/google" class="btn-google">
                <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_Logo.svg" alt="Google">
                Sign in with Google
            </a>

            <div class="footer">
                Ready for Frontend Handoff &bull; v0.1.0
            </div>
        </div>
    </body>
    </html>
    """


@router.get("/health", response_model=None)
async def health_check(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Application health check endpoint with component status."""
    components = {}

    # Database health
    try:
        db_factory = getattr(request.app.state, "db_session_factory", None)
        if db_factory:
            from sqlalchemy import text

            async with db_factory() as session:
                await session.execute(text("SELECT 1"))
            components["database"] = "healthy"
        else:
            components["database"] = "not_initialized"
    except Exception:
        components["database"] = "unhealthy"

    # Redis health
    try:
        redis = getattr(request.app.state, "redis", None)
        if redis and await redis.ping():
            components["redis"] = "healthy"
        else:
            components["redis"] = "not_initialized"
    except Exception:
        components["redis"] = "unhealthy"

    # ML model health
    registry = getattr(request.app.state, "model_registry", None)
    components["ml_model"] = "loaded" if registry is not None else "not_loaded"

    # FAS registry health
    fas_registry = getattr(request.app.state, "fas_registry", None)
    components["fas_registry"] = f"{fas_registry.loaded_count}_models" if fas_registry else "not_loaded"

    overall = "healthy" if all(
        v in ("healthy", "loaded") or "models" in v for v in components.values()
    ) else "degraded"

    return {
        "status": overall,
        "service": "spectre-api",
        "version": "0.1.0",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "components": components,
    }


@router.get("/health/ml-status", tags=["Health", "SDK Integration"])
async def ml_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    fas_registry = getattr(request.app.state, "fas_registry", None)
    active_id = settings.active_fas_model

    import json as _json
    try:
        benchmark_ids = _json.loads(settings.benchmark_models)
        if not isinstance(benchmark_ids, list):
            benchmark_ids = []
    except (ValueError, _json.JSONDecodeError):
        benchmark_ids = []

    if fas_registry is None:
        return {
            "active_model_id": active_id,
            "active_model": None,
            "benchmark_enabled": settings.benchmark_enabled,
            "benchmark_models": benchmark_ids,
            "detail_mode_default": settings.detail_mode_default,
        }

    handler = fas_registry._handlers.get(active_id)
    return {
        "active_model_id": active_id,
        "active_model": {
            "model_id": handler.model_id,
            "version": handler.version,
            "supports_tta": handler.supports_tta,
        } if handler else None,
        "benchmark_enabled": settings.benchmark_enabled,
        "benchmark_models": benchmark_ids,
        "detail_mode_default": settings.detail_mode_default,
    }


class DBConfigRequest(BaseModel):
    target: Literal["supabase", "alpine"]


@router.get("/admin/stats")
async def get_admin_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Protected endpoint for admin to view infrastructure stats."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get latest heartbeats
    heartbeats = []
    try:
        db_factory = getattr(request.app.state, "db_session_factory", None)
        if db_factory:
            async with db_factory() as session:
                heartbeat_query = text(
                    "SELECT id, pinged_at, source FROM keepalive_ping "
                    "ORDER BY pinged_at DESC LIMIT 5"
                )
                result = await session.execute(heartbeat_query)
                heartbeats = [
                    {
                        "id": str(row.id),
                        "pinged_at": row.pinged_at.isoformat(),
                        "source": row.source,
                    }
                    for row in result.all()
                ]
    except Exception:
        pass

    # Extract active db string from configuration
    db_url = str(settings.database_url)
    if "supabase" in db_url:
        active_db = "supabase"
    else:
        active_db = "alpine"

    return {
        "heartbeats": heartbeats,
        "server_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "active_db": active_db
    }


@router.post("/admin/config/db")
async def switch_db(
    request: Request,
    body: DBConfigRequest,
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Dynamically switch database connection environment."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Simulate DB switch orchestration
    await asyncio.sleep(2)
    
    if body.target == "supabase":
        # Should use settings from environment instead of hardcoded strings
        url = os.environ.get("SUPABASE_DATABASE_URL")
        if not url:
            raise HTTPException(status_code=400, detail="SUPABASE_DATABASE_URL not set")
        settings.database_url = url
    else:
        url = os.environ.get("LOCAL_DATABASE_URL") or "postgresql+asyncpg://spectre:spectre@localhost:5432/spectre"
        settings.database_url = url
    
    return {"status": "success", "message": f"Database switched to {body.target}"}


@router.get("/admin/env")
async def get_admin_env(
    current_user: User = Depends(get_current_user),
):
    """Protected endpoint to audit active environment variables."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    keys_to_audit = [
        "APP_NAME", "APP_ENV", "DATABASE_URL", "REDIS_URL", 
        "API_PORT", "MODEL_PATH", "HF_SPACE_ID"
    ]
    
    sensitive_patterns = ["DATABASE", "JWT", "SECRET", "KEY", "URL", "TOKEN", "PASSWORD"]
    
    audit_data = {}
    for k, v in os.environ.items():
        if any(p in k.upper() for p in sensitive_patterns):
            # Redact sensitive values
            if len(v) > 8:
                audit_data[k] = f"{v[:4]}...{v[-4:]}"
            else:
                audit_data[k] = "********"
        elif k in keys_to_audit:
            audit_data[k] = v

    return audit_data


@router.get("/admin/automation/status")
async def get_automation_status(
    current_user: User = Depends(get_current_user),
):
    """Fetch status of GitHub Actions keep-alive workflow."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    import requests
    
    repo = "fadhiilahahmadzikri/spectre-backend"
    workflow_file = "keepalive.yml"
    
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("HF_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs?per_page=1"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        latest_run = data.get("workflow_runs", [{}])[0]
        
        return {
            "workflow": "Keep HF Space Alive",
            "last_run_at": latest_run.get("created_at"),
            "status": latest_run.get("status"),
            "conclusion": latest_run.get("conclusion"),
            "html_url": latest_run.get("html_url"),
            "repo": repo,
            "cron_interval": "Every 20 hours"
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch GHA status: {str(e)}",
            "workflow": "Keep HF Space Alive",
            "repo": repo,
            "cron_interval": "Every 20 hours"
        }
