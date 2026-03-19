"""Async Jira REST API v3 client.

Used by cli/dblcheck.py for ticket creation and commenting on failure incidents.

All functions check for required env vars — if absent, log a warning and
return gracefully so the workflow continues unchanged.
"""

import base64
import logging
import os
import re

import httpx

from core.vault import get_secret

log = logging.getLogger("dblcheck.jira")

_JIRA_TIMEOUT = httpx.Timeout(timeout=15.0, connect=5.0)


def _config() -> dict:
    """Read Jira config from env vars at call time (not cached at import)."""
    return {
        "base_url":    os.getenv("JIRA_BASE_URL", "").rstrip("/"),
        "email":       os.getenv("JIRA_EMAIL", ""),
        "api_token":   get_secret("dblcheck/jira", "token", fallback_env="JIRA_API_TOKEN", quiet=True) or "",
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


def _inline_to_adf(text: str) -> list[dict]:
    """Parse inline Markdown (bold, inline code) into ADF text-run nodes."""
    nodes: list[dict] = []
    last = 0
    for m in re.finditer(r"\*\*(.+?)\*\*|`([^`]+)`", text):
        if m.start() > last:
            nodes.append({"type": "text", "text": text[last:m.start()]})
        if m.group(1) is not None:  # **bold**
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "strong"}]})
        else:                        # `code`
            nodes.append({"type": "text", "text": m.group(2), "marks": [{"type": "code"}]})
        last = m.end()
    if last < len(text):
        nodes.append({"type": "text", "text": text[last:]})
    return nodes or [{"type": "text", "text": " "}]


def _to_adf(text: str) -> dict:
    """Convert Markdown-formatted text to Atlassian Document Format (ADF).

    Handles the subset the diagnosis agent produces:
    ## headings, **bold**, `inline code`, ``` code blocks, plain paragraphs.
    """
    nodes: list[dict] = []
    lines = text.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            nodes.append({
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            })
            continue

        # Heading
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            nodes.append({
                "type": "heading",
                "attrs": {"level": len(m.group(1))},
                "content": _inline_to_adf(m.group(2)),
            })
            i += 1
            continue

        # Empty line
        if not stripped:
            i += 1
            continue

        # Paragraph
        nodes.append({"type": "paragraph", "content": _inline_to_adf(line)})
        i += 1

    if not nodes:
        nodes = [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]
    return {"version": 1, "type": "doc", "content": nodes}


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
    """Add a comment to a Jira issue."""
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


async def resolve_issue(issue_key: str, comment_text: str) -> None:
    """Transition a Jira issue to Done/Resolved and post a resolution comment.

    Queries available transitions and picks the first one whose name contains
    'done', 'resolve', or 'close' (case-insensitive), or matches JIRA_RESOLVE_TRANSITION
    if set. Falls back to add_comment() if no matching transition is found.
    """
    if not _is_configured():
        return

    cfg = _config()
    target_name = os.getenv("JIRA_RESOLVE_TRANSITION", "").strip().lower()

    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=_JIRA_TIMEOUT) as client:
            # Query available transitions
            t_url = f"{cfg['base_url']}/rest/api/3/issue/{issue_key}/transitions"
            t_resp = await client.get(t_url)
            if t_resp.status_code != 200:
                log.warning(
                    "Jira: could not fetch transitions for %s (%s) — falling back to comment",
                    issue_key, t_resp.status_code,
                )
                await add_comment(issue_key, comment_text)
                return

            transitions = t_resp.json().get("transitions", [])
            _RESOLVE_KEYWORDS = {"done", "resolve", "close"}
            transition_id = None
            for t in transitions:
                name_lower = t.get("name", "").lower()
                if target_name:
                    if name_lower == target_name:
                        transition_id = t["id"]
                        break
                else:
                    if any(kw in name_lower for kw in _RESOLVE_KEYWORDS):
                        transition_id = t["id"]
                        break

            if not transition_id:
                log.warning(
                    "Jira: no matching resolve transition found for %s (available: %s) "
                    "— falling back to comment",
                    issue_key,
                    [t.get("name") for t in transitions],
                )
                await add_comment(issue_key, comment_text)
                return

            # Perform the transition with the resolution comment attached
            body = {
                "transition": {"id": transition_id},
                "update": {
                    "comment": [{"add": {"body": _to_adf(comment_text)}}],
                },
            }
            resp = await client.post(t_url, json=body)
            if resp.status_code not in (200, 204):
                log.error(
                    "Jira: transition failed for %s: %s %s — falling back to comment",
                    issue_key, resp.status_code, resp.text[:200],
                )
                await add_comment(issue_key, comment_text)
            else:
                log.info("Jira: resolved issue %s", issue_key)

    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.error("Jira resolve_issue failed on %s (connection error): %s", issue_key, exc)
        await add_comment(issue_key, comment_text)
