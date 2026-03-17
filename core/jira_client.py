"""Async Jira REST API v3 client.

Used by cli/dblcheck.py for ticket creation and commenting on failure incidents.

All functions check for required env vars — if absent, log a warning and
return gracefully so the workflow continues unchanged.
"""

import base64
import logging
import os

import httpx

from core.vault import get_secret

log = logging.getLogger("dblcheck.jira")

_JIRA_TIMEOUT = httpx.Timeout(timeout=15.0, connect=5.0)


def _config() -> dict:
    """Read Jira config from env vars at call time (not cached at import)."""
    return {
        "base_url":    os.getenv("JIRA_BASE_URL", "").rstrip("/"),
        "email":       os.getenv("JIRA_EMAIL", ""),
        "api_token":   get_secret("dblcheck/jira", "token", fallback_env="JIRA_API_TOKEN") or "",
        "project_key": os.getenv("JIRA_PROJECT_KEY", ""),
        "issue_type":  os.getenv("JIRA_ISSUE_TYPE", "[System] Incident"),
    }


def _is_configured() -> bool:
    cfg = _config()
    missing = [k for k in ("base_url", "email", "api_token", "project_key") if not cfg[k]]
    if missing:
        log.warning("Jira not configured — missing: %s", ", ".join(missing))
        return False
    return True


def _headers() -> dict:
    cfg = _config()
    creds = base64.b64encode(f"{cfg['email']}:{cfg['api_token']}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _to_adf(text: str) -> dict:
    """Convert a plain-text string to minimal Atlassian Document Format (ADF)."""
    paragraphs = []
    for line in text.strip().split("\n"):
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": line or " "}],
        })
    return {"version": 1, "type": "doc", "content": paragraphs}


async def create_issue(
    summary:     str,
    description: str,
    priority:    str = "High",
    labels:      list[str] | None = None,
) -> str | None:
    """Create a Jira issue. Returns the issue key (e.g. 'NET-12') or None on failure.

    Tries JIRA_ISSUE_TYPE first; falls back to 'Task' if the configured type is rejected.
    """
    if not _is_configured():
        return None

    cfg = _config()
    if labels is None:
        labels = ["dblcheck", "automated"]

    body = {
        "fields": {
            "project":     {"key": cfg["project_key"]},
            "summary":     summary,
            "description": _to_adf(description),
            "issuetype":   {"name": cfg["issue_type"]},
            "priority":    {"name": priority},
            "labels":      labels,
        }
    }

    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=_JIRA_TIMEOUT) as client:
            url = f"{cfg['base_url']}/rest/api/3/issue"
            resp = await client.post(url, json=body)

            if resp.status_code == 201:
                return resp.json()["key"]

            # Fall back to Task if the configured issue type is rejected
            if resp.status_code == 400:
                body["fields"]["issuetype"] = {"name": "Task"}
                resp2 = await client.post(url, json=body)
                if resp2.status_code == 201:
                    key = resp2.json()["key"]
                    log.warning(
                        "Jira: issue type '%s' rejected, created as Task: %s",
                        cfg["issue_type"], key,
                    )
                    return key
                log.error(
                    "Jira create_issue failed (fallback): %s %s",
                    resp2.status_code, resp2.text[:200],
                )
                return None

            log.error("Jira create_issue failed: %s %s", resp.status_code, resp.text[:200])
            return None

    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.error("Jira create_issue failed (connection error): %s", exc)
        return None


async def add_comment(issue_key: str, comment_text: str) -> None:
    """Add a plain-text comment to a Jira issue."""
    if not _is_configured():
        return

    cfg = _config()
    body = {"body": _to_adf(comment_text)}
    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=_JIRA_TIMEOUT) as client:
            url = f"{cfg['base_url']}/rest/api/3/issue/{issue_key}/comment"
            resp = await client.post(url, json=body)
            if resp.status_code not in (200, 201):
                log.error(
                    "Jira add_comment failed on %s: %s %s",
                    issue_key, resp.status_code, resp.text[:200],
                )
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.error("Jira add_comment failed on %s (connection error): %s", issue_key, exc)
