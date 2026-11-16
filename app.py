"""Lead Generation Tool - Flask backend (web scraping edition, no API keys)."""
import io
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

from scrapers import BusinessSiteScraper, ScraperError, build_sources
from utils.data_cleaning import clean_lead, deduplicate, finalize
from utils.export import to_csv_bytes, to_xlsx_bytes

load_dotenv()
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
# Render puts a proxy in front of the app: trust exactly one proxy hop so request.remote_addr
# is the real visitor IP (and visitors can't fake it with their own X-Forwarded-For header).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "5"))
DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))
COUNTRY_CC = os.getenv("DEFAULT_COUNTRY_CODE", "92")

SOURCES = build_sources(CONTACT_EMAIL, DELAY)
JOBS, JOBS_LOCK = {}, threading.Lock()   # in-memory jobs (run gunicorn with ONE worker)
HITS = defaultdict(deque)                # ip -> recent search timestamps
TEXT_RE = re.compile(r"^[\w\s&'.,()/-]{2,100}$", re.UNICODE)


def client_ip():
    return request.remote_addr or "?"


def rate_limited(ip):
    now, q = time.time(), HITS[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    if len(HITS) > 5000:                     # keep memory small on a free instance
        for k in [k for k, v in HITS.items() if not v or now - v[-1] > 60]:
            HITS.pop(k, None)
    return False


def run_job(job_id, source_keys, keyword, location, limit, enrich):
    """Runs in a background thread so long scrapes don't block the web server."""
    job = JOBS[job_id]
    try:
        raw, errors = [], []
        for key in source_keys:
            job["message"] = f"Searching {SOURCES[key].label}…"
            try:
                raw += SOURCES[key].search(keyword, location, limit)
            except ScraperError as e:
                errors.append(str(e))
        if not raw:
            raise ScraperError(" ".join(errors) or "No results found.")
        raw = raw[:limit]
        if enrich:
            def progress(done, total):
                job["message"] = f"Checking business websites for contact info ({done}/{total})…"
            cleaned = [l for l in (clean_lead(r, COUNTRY_CC) for r in raw) if l]
            BusinessSiteScraper(CONTACT_EMAIL, DELAY).enrich_many(cleaned, progress=progress)
            cleaned = [clean_lead(l, COUNTRY_CC) for l in cleaned]   # re-validate enriched data
        else:
            cleaned = [clean_lead(r, COUNTRY_CC) for r in raw]
        leads = finalize(deduplicate([l for l in cleaned if l]))
        job.update(status="done", results=leads, warnings=errors,
                   message=f"Found {len(leads)} unique businesses.")
    except ScraperError as e:
        job.update(status="error", error=str(e))
    except Exception:
        logging.exception("Unexpected scraper failure")
        job.update(status="error", error="Something went wrong while scraping. Please try again.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Used by Render's health check."""
    return jsonify(status="ok")


@app.route("/api/sources")
def sources():
    return jsonify(sources=[{"key": k, "label": s.label} for k, s in SOURCES.items()])


@app.route("/api/search", methods=["POST"])
def search():
    d = request.get_json(silent=True) or {}
    keyword, location = str(d.get("keyword", "")).strip(), str(d.get("location", "")).strip()
    source = str(d.get("source", "all"))
    try:
        limit = min(max(int(d.get("limit", 50)), 10), 100)
    except (TypeError, ValueError):
        limit = 50
    if not (TEXT_RE.match(keyword) and TEXT_RE.match(location)):
        return jsonify(error="Enter a keyword and a location (2-100 letters/numbers)."), 400
    if source != "all" and source not in SOURCES:
        return jsonify(error="Unknown source selected."), 400
    if rate_limited(client_ip()):
        return jsonify(error=f"Too many searches. Limit is {RATE_LIMIT} per minute - please wait."), 429

    with JOBS_LOCK:
        for jid in [j for j, v in JOBS.items() if time.time() - v["created"] > 3600]:
            del JOBS[jid]                              # forget old jobs
        if sum(v["status"] == "running" for v in JOBS.values()) >= 3:
            return jsonify(error="The server is busy with other searches. Try again shortly."), 429
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"status": "running", "message": "Starting…", "created": time.time()}
    keys = list(SOURCES) if source == "all" else [source]
    threading.Thread(target=run_job, daemon=True,
                     args=(job_id, keys, keyword, location, limit, bool(d.get("enrich", True)))).start()
    return jsonify(job_id=job_id)


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="Search not found or expired."), 404
    return jsonify({k: v for k, v in job.items() if k != "created"})


@app.route("/api/export/<fmt>", methods=["POST"])
def export(fmt):
    rows = (request.get_json(silent=True) or {}).get("results", [])
    if not isinstance(rows, list) or not rows:
        return jsonify(error="Nothing to export. Run a search first."), 400
    rows = rows[:5000]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "csv":
        return send_file(io.BytesIO(to_csv_bytes(rows)), mimetype="text/csv", as_attachment=True,
                         download_name=f"leads_{stamp}.csv")
    if fmt == "xlsx":
        return send_file(io.BytesIO(to_xlsx_bytes(rows)), as_attachment=True, download_name=f"leads_{stamp}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return jsonify(error="Unsupported format."), 400


if __name__ == "__main__":
    # Local development only. On Render, gunicorn runs the app (see README / render.yaml).
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG", "1") == "1")