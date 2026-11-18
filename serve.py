#!/usr/bin/env python3
"""
FitFindr over HTTP. ← UNIT 9

    python serve.py                       run it on your machine
    gunicorn serve:app                    run it the way a host runs it

Everything else in this repo exits after one command. A host has nothing to
keep running, so a command line cannot be deployed. This file is the smallest
thing that can: it starts a web server, waits, and hands each request to the
same `run_agent()` your CLI calls. **No new agent logic lives here.** If your
loop works from `python app.py ask`, it works from here; if it doesn't, fix it
there, not in this file.

Three routes:

    POST /ask       {"query": "vintage graphic tee under $30",
                     "wardrobe": {...}}     ← wardrobe is optional
    GET  /health    is it awake?
    GET  /logs?n=50 the last n structured log records (capstone)

`/ask` returns the session dict from `run_agent()` as JSON, unchanged — the
same keys you print from the command line, including `error`. Read
`session["error"]` first, exactly as you do everywhere else.

It runs **one request at a time**, and one route is deliberately slower than a
web server has to be. The reason is worth reading before you deploy: see the
note above `_one_at_a_time` below — it also decides which gunicorn worker you
can use.

Capstone instrumentation: every /ask request — accepted, rejected or crashed —
appends one JSON record to logs/requests.jsonl (and prints it to stdout) with
timestamp, query, outcome, status, timings (total / lock wait / agent), the
model calls and tokens that request spent, and what came back.
"""

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# config first, and before anything that talks to the model: it loads your .env
# and fixes the Windows console encoding for every module that imports it.
import config  # noqa: F401

from flask import Flask, jsonify, request

import generate
from agent import run_agent
from utils.data_loader import get_example_wardrobe

app = Flask(__name__)


# ── structured log ────────────────────────────────────────────────────────────
# One JSON object per line, one line per request — including the ones that
# were rejected (400) or crashed (500). A failure that leaves no record is a
# failure nobody finds.
#
# The file lives on the instance's disk, and a free host wipes that disk when
# it sleeps. So every record is ALSO printed to stdout (the host's log viewer
# keeps that for a while), and GET /logs hands the file back so the records
# can be copied into the README the same session they're made.

LOG_PATH = Path(os.getenv("AI201_LOG_PATH", config.ROOT / "logs" / "requests.jsonl"))
_log_lock = threading.Lock()


def _write_log(record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False)
    print(f"[log] {line}", flush=True)
    try:
        with _log_lock:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError as exc:  # logging must never take a working request down
        print(f"[log] could not write {LOG_PATH}: {exc}", file=sys.stderr, flush=True)


def _base_record(route: str) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "request_id": uuid.uuid4().hex[:8],
        "route": route,
        "model": config.MODEL,
        "cache_enabled": config.CACHE_ENABLED,
    }


def _summarise_session(session: dict) -> dict:
    """The parts of a session worth keeping in a log line — not the wardrobe."""
    item = session.get("selected_item") or {}
    return {
        "parsed": session.get("parsed"),
        "results_count": len(session.get("search_results") or []),
        "selected_item": {k: item.get(k) for k in ("id", "title", "price", "size", "condition")}
        if item else None,
        "outfit_chars": len(session.get("outfit_suggestion") or ""),
        "fit_card": session.get("fit_card"),
    }


# ── one request at a time ─────────────────────────────────────────────────────
# Here's why this exists.
#
# A web server will happily run two requests at once. Two things in this repo
# assume otherwise:
#
#   • If you moved a tool onto MCP in unit 4, `mcp_client.call_tool` starts
#     `mcp_server.py` as a separate process over stdio, one per call. Two
#     overlapping requests means two extra Python interpreters, and the free
#     tier you're deploying to has 512 MB for all of it. That is the reason
#     that would still be here even if everything else were perfect.
#   • `generate.py`'s pacing window and its call counter are plain module
#     globals — deliberately, because that file is teaching pacing and quota,
#     not locking. Two threads sharing them means the per-minute limiter is
#     counting something that isn't true.
#
# What the lock covers is exactly the agent run: the part that spawns
# processes and calls the model. Reading the request, rejecting a bad one, and
# turning the answer into JSON all happen outside it — so a request with a
# malformed body comes straight back with a 400 instead of queueing behind
# somebody else's agent.
#
# Serialising the runs costs you nothing here — this is one user asking one
# question — and it keeps the deployed behaviour identical to the CLI's. When
# that stops being an acceptable trade, the fix is a real queue, not a bigger
# lock.
#
# The same constraint decides your start command, and this is the part that
# bites in deployment rather than on your machine. `mcp_client.call_tool`
# wraps `asyncio.run()`, and `asyncio.run()` refuses to start when an event
# loop is already running. An async worker always has one running. So under
# `gunicorn -k gevent` (or `-k eventlet`, or `serve:app` wrapped for an ASGI
# server like uvicorn) EVERY MCP call fails with "asyncio.run() cannot be
# called from a running event loop" — not some of them under load, all of
# them, every time, in a place your laptop never showed you.
#
#     gunicorn serve:app              ← right: the DEFAULT sync worker
#     gunicorn -k gevent serve:app    ← breaks every MCP call you make

_one_at_a_time = threading.Lock()


@app.get("/health")
def health():
    """Is the server awake? A host pings something like this to find out."""
    return jsonify({"status": "ok"})


@app.post("/ask")
def ask():
    """
    Run the agent on one query.

    In:   {"query": "...", "wardrobe": {...}}   wardrobe optional — leave it
                                                out and you get the same
                                                example wardrobe the CLI uses.
    Out:  the session dict from run_agent(), as JSON.
    """
    started = time.perf_counter()
    record = _base_record("/ask")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    raw_query = payload.get("query")
    query = raw_query.strip() if isinstance(raw_query, str) else ""
    record["query"] = query if query else raw_query
    record["wardrobe_supplied"] = isinstance(payload.get("wardrobe"), dict)

    if not query:
        # 400 rather than a stack trace: the caller can act on this one.
        message = ("Send JSON with a 'query' field, e.g. "
                   '{"query": "vintage graphic tee under $30"}')
        record.update(status=400, outcome="rejected", error=message,
                      duration_ms=round((time.perf_counter() - started) * 1000, 1))
        _write_log(record)
        return jsonify({"error": message}), 400

    wardrobe = payload.get("wardrobe")
    if not isinstance(wardrobe, dict):
        wardrobe = get_example_wardrobe()

    # A queued request should look like a queued request. Without this the
    # second caller just sits there, and "slow" and "waiting its turn" are
    # indistinguishable from the outside — which is how people conclude the
    # deployment is broken when it is behaving exactly as designed.
    #
    # This is NOT the logging you add in the follow-along. It prints nothing
    # on the normal path, carries no timing and counts nothing; it says only
    # that this request had to wait. `locked()` can be a moment out of date,
    # so the note is occasionally missed — which costs nothing, because
    # nothing depends on it.
    if _one_at_a_time.locked():
        print(
            "  [serve] another request is still running. This one is waiting "
            "its turn — serve.py handles one at a time, on purpose.",
            file=sys.stderr,
            flush=True,
        )

    failure = None
    session = None
    queued_at = time.perf_counter()
    with _one_at_a_time:
        # Inside the lock nobody else is calling the model, so the change in
        # generate.py's session counters is exactly what THIS request spent.
        lock_wait_ms = (time.perf_counter() - queued_at) * 1000
        calls_before = generate.call_count()
        tokens_before = generate.token_counts()
        cache_before = generate._cache_hits
        agent_started = time.perf_counter()
        try:
            session = run_agent(query, wardrobe)
        except Exception as exc:  # noqa: BLE001 — a 500 with a sentence beats a hang
            failure = f"{type(exc).__name__}: {exc}"
        agent_ms = (time.perf_counter() - agent_started) * 1000
        tokens_after = generate.token_counts()
        record.update(
            lock_wait_ms=round(lock_wait_ms, 1),
            agent_ms=round(agent_ms, 1),
            model_calls=generate.call_count() - calls_before,
            cache_hits=generate._cache_hits - cache_before,
            prompt_tokens=tokens_after["prompt"] - tokens_before["prompt"],
            output_tokens=tokens_after["output"] - tokens_before["output"],
            total_tokens=tokens_after["total"] - tokens_before["total"],
            process_model_calls=generate.call_count(),
        )

    # Outside the lock: building a response is not work the next caller should
    # be waiting on.
    if failure is not None:
        record.update(status=500, outcome="crashed", error=failure,
                      duration_ms=round((time.perf_counter() - started) * 1000, 1))
        _write_log(record)
        return jsonify({"error": failure}), 500

    record.update(_summarise_session(session))
    record.update(
        status=200,
        outcome="error" if session.get("error") else "ok",
        error=session.get("error"),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    _write_log(record)
    return jsonify(session)


@app.get("/logs")
def logs():
    """
    The last N log records (default 50, max 500), newest last.

    On a free host this file disappears when the instance sleeps — fetch it
    and commit it the same session you produce it.
    """
    try:
        n = max(1, min(int(request.args.get("n", 50)), 500))
    except ValueError:
        n = 50
    if not LOG_PATH.exists():
        return jsonify([])
    with _log_lock:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return jsonify(out)


if __name__ == "__main__":
    # PORT and 0.0.0.0 are not decoration. A host tells you which port to
    # listen on through PORT, and it reaches your process from outside the
    # container — bind 127.0.0.1 and nothing but the container itself can
    # connect, which looks exactly like a broken app from the browser.
    port = int(os.getenv("PORT", "5000"))

    # Never on by default. Flask's debugger executes code typed into a browser,
    # and a deployed app with it on is a stranger's shell. Set AI201_DEBUG=1 in
    # your own terminal when you want the reloader.
    debug = os.getenv("AI201_DEBUG", "0") == "1"

    print(f"\nFitFindr is listening on http://localhost:{port}")
    print("It runs one request at a time — a second one waits for the first.")
    print("Ask it something (single quotes, as always):\n")
    print(
        f"  curl -X POST http://localhost:{port}/ask \\\n"
        f"    -H 'Content-Type: application/json' \\\n"
        f"    -d '{{\"query\": \"vintage graphic tee under $30\"}}'\n"
    )
    print("Ctrl-C to stop.\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
