"""
Small read-only status web interface.
Shows which documents are queued, being processed, done or failed.
"""

import html
import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from job_store import JobStore, STATUSES, STATUS_FAILED

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "queued": "Queued",
    "processing": "Processing",
    "done": "Done",
    "failed": "Failed",
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Documenter</title>
<style>
:root {{
  --bg: #f6f7f9; --card: #ffffff; --text: #1d2330; --muted: #5d6676; --border: #dde1e7;
  --queued: #6b7280; --processing: #1d6fd6; --done: #1f8a4c; --failed: #c4322f;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #14171c; --card: #1d2128; --text: #e6e9ee; --muted: #9aa3b2; --border: #313742;
    --queued: #9aa3b2; --processing: #5aa2ff; --done: #4cc27e; --failed: #ff6b66;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 16px; }}
h1 {{ font-size: 20px; margin: 4px 0 16px; }}
h1 small {{ color: var(--muted); font-weight: normal; font-size: 13px; margin-left: 8px; }}
nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
nav a {{ display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px;
  border: 1px solid var(--border); border-radius: 22px; background: var(--card);
  color: var(--text); text-decoration: none; }}
nav a.active {{ border-color: var(--text); font-weight: 600; }}
nav b {{ font-variant-numeric: tabular-nums; }}
.job {{ background: var(--card); border: 1px solid var(--border); border-left-width: 4px;
  border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; overflow-wrap: anywhere; }}
.job.queued {{ border-left-color: var(--queued); }}
.job.processing {{ border-left-color: var(--processing); }}
.job.done {{ border-left-color: var(--done); }}
.job.failed {{ border-left-color: var(--failed); }}
.head {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; }}
.name {{ font-weight: 600; }}
.badge {{ font-size: 13px; font-weight: 600; }}
.queued .badge {{ color: var(--queued); }}
.processing .badge {{ color: var(--processing); }}
.done .badge {{ color: var(--done); }}
.failed .badge {{ color: var(--failed); }}
.meta {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
.error {{ color: var(--failed); margin-top: 6px; white-space: pre-wrap; }}
.step {{ color: var(--processing); margin-top: 6px; }}
ul {{ margin: 6px 0 0; padding-left: 18px; }}
li {{ font-size: 14px; }}
li span {{ color: var(--muted); }}
.empty {{ color: var(--muted); padding: 24px 0; }}
</style>
</head>
<body>
<main>
<h1>Documenter<small>{version} · refreshes every 10 s</small></h1>
<nav>{nav}</nav>
{jobs}
</main>
<script>
for (const el of document.querySelectorAll("time[datetime]")) {{
  el.textContent = new Date(el.getAttribute("datetime")).toLocaleString();
}}
</script>
</body>
</html>
"""


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _time_html(ts: Optional[float]) -> str:
    iso = _iso(ts)
    if iso is None:
        return ""
    return f'<time datetime="{iso}">{html.escape(iso)}</time>'


def _duration(job: Dict) -> str:
    if job["started_at"] is None or job["finished_at"] is None:
        return ""
    seconds = int(job["finished_at"] - job["started_at"])
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60} min {seconds % 60} s"


def render_job(job: Dict) -> str:
    status = job["status"]
    name = html.escape(os.path.basename(job["source"]))
    meta = [f"received {_time_html(job['queued_at'])}"]
    if job["finished_at"] is not None:
        meta.append(f"finished {_time_html(job['finished_at'])}")
    duration = _duration(job)
    if duration:
        meta.append(f"took {duration}")
    if job["size"]:
        meta.append(f"{job['size'] / 1024 / 1024:.1f} MB")

    parts = [
        f'<div class="job {status}">',
        '<div class="head">',
        f'<span class="name">{name}</span>',
        f'<span class="badge">{STATUS_LABELS.get(status, status)}</span>',
        '</div>',
        f'<div class="meta">{" · ".join(meta)}</div>',
    ]
    if job.get("step"):
        parts.append(f'<div class="step">{html.escape(job["step"])}</div>')
    if job.get("error"):
        error = html.escape(job["error"])
        if status == STATUS_FAILED:
            if os.path.exists(job["source"]):
                error += "\n(The file is still in the input folder.)"
            parts.append(f'<div class="error">{error}</div>')
        else:
            parts.append(f'<div class="meta">Note: {error}</div>')
    if job["outputs"]:
        parts.append("<ul>")
        for output in job["outputs"]:
            targets = ", ".join(output["targets"]) or "no target"
            parts.append(
                f'<li>{html.escape(output["filename"])} <span>→ {html.escape(targets)}</span></li>'
            )
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


def render_page(store: JobStore, status: Optional[str], version: str) -> str:
    counts = store.counts()
    nav = [f'<a href="/" class="{"active" if status is None else ""}">All</a>']
    for key in STATUSES:
        active = "active" if status == key else ""
        nav.append(
            f'<a href="/?status={key}" class="{active}">{STATUS_LABELS[key]} <b>{counts[key]}</b></a>'
        )
    jobs = store.list_jobs(status=status)
    if jobs:
        body = "".join(render_job(job) for job in jobs)
    else:
        body = '<p class="empty">No documents yet.</p>'
    return _PAGE.format(version=html.escape(version), nav="".join(nav), jobs=body)


def jobs_as_json(store: JobStore, status: Optional[str]) -> str:
    jobs = store.list_jobs(status=status)
    for job in jobs:
        for key in ("queued_at", "started_at", "finished_at"):
            job[key] = _iso(job[key])
    return json.dumps({"counts": store.counts(), "jobs": jobs}, indent=2)


def _make_handler(store: JobStore, version: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, content_type: str, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            status = parse_qs(url.query).get("status", [None])[0]
            if status not in STATUSES:
                status = None
            try:
                if url.path == "/":
                    self._send(200, "text/html; charset=utf-8", render_page(store, status, version))
                elif url.path == "/api/jobs":
                    self._send(200, "application/json", jobs_as_json(store, status))
                elif url.path == "/healthz":
                    self._send(200, "text/plain", "ok\n")
                else:
                    self._send(404, "text/plain", "not found\n")
            except Exception:
                logger.exception("Status page failed")
                self._send(500, "text/plain", "internal error\n")

        def log_message(self, format, *args):
            logger.debug("web: " + format, *args)

    return Handler


def start_web_server(store: JobStore, port: int, version: str) -> ThreadingHTTPServer:
    """Start the status web server in a daemon thread."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(store, version))
    thread = threading.Thread(target=server.serve_forever, name="web", daemon=True)
    thread.start()
    logger.info(f"Status web interface listening on port {port}")
    return server
