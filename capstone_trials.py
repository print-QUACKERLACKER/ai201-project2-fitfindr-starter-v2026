#!/usr/bin/env python3
"""
Run the five capstone criteria (criteria.md → "Capstone criteria") once against
the deployed app, and save every raw response.

    python capstone_trials.py --label before --trial 1
    python capstone_trials.py --label before --trial 1 --only 4
    python capstone_trials.py --url http://localhost:5000 ...   (local instead)

Writes results/capstone_<label>_trial<N>.jsonl (one line per request: the
criterion, the input, status, the full response, pass/fail and why) and prints
the score per criterion.

The cases are fixed so every trial sends the same inputs. Each case was chosen
because it meets the criterion's condition (e.g. #5: no search result matches
any survey answer) — checked against search_listings before any trial ran.
"""

import argparse
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "https://ai201-project2-fitfindr-starter-v2026-bsqi.onrender.com"

# python.org's macOS Python ships without CA certificates, so HTTPS fails with
# CERTIFICATE_VERIFY_FAILED. certifi comes in with google-genai's dependencies.
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()
RESULTS = Path(__file__).parent / "results"

# 1 — first result doesn't match the style answer, but some other result does.
C1 = [
    ("top under $40", {"style": "grunge"}),
    ("vintage", {"style": "cottagecore"}),
    ("shoes", {"style": "streetwear"}),
    ("vintage jacket", {"style": "y2k"}),
    ("denim", {"style": "grunge"}),
]

# 2 — at least one result matches every answer (score == max_score possible).
C2 = [
    ("top under $40", {"style": "y2k", "colors": "bright", "condition": "like_new"}),
    ("vintage", {"style": "grunge", "colors": "dark", "condition": "any"}),
    ("jeans", {"style": "grunge", "colors": "dark", "condition": "any"}),
    ("graphic tee", {"style": "streetwear", "colors": "neutral", "condition": "any"}),
    ("vintage jacket", {"style": "vintage", "colors": "neutral", "condition": "like_new"}),
    ("black", {"style": "grunge", "colors": "dark", "condition": "any"}),
]

# 3 — no survey at all.
C3 = ["top under $40", "vintage", "jacket under $60", "jeans", "shoes",
      "dress", "shirt", "tee", "graphic tee", "denim"]

# 4 — bad surveys: 3 unknown answers, 3 unknown questions, 3 not an object.
C4 = [
    {"style": "punk"}, {"colors": "rainbow"}, {"condition": "brand_new"},
    {"vibe": "dark"}, {"size": "M"}, {"budget": "30"},
    "grunge", ["grunge"], 5,
]

# 5 — no search result matches ANY survey answer.
C5 = [
    ("jeans", {"style": "cottagecore", "colors": "neutral"}),
    ("jeans", {"style": "y2k", "colors": "bright"}),
    ("boots", {"style": "streetwear", "colors": "dark"}),
    ("boots", {"style": "grunge", "colors": "bright"}),
    ("bag", {"style": "cottagecore", "colors": "dark"}),
    ("hoodie", {"style": "minimal", "colors": "neutral"}),
    ("shirt", {"style": "y2k", "colors": "neutral"}),
    ("pants", {"style": "grunge", "colors": "dark"}),
    ("cardigan", {"style": "vintage", "colors": "bright"}),
    ("sneakers", {"style": "cottagecore", "colors": "dark"}),
]


def post(url: str, body: dict) -> tuple[int, dict, float]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{url}/ask", data=data,
                                 headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300, context=_SSL) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    secs = time.perf_counter() - started
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {"_raw": raw.decode("utf-8", "replace")}
    return status, payload, secs


def judge(criterion: int, status: int, r: dict, survey) -> tuple[bool, str]:
    why = r.get("selection_reason") or {}
    item = r.get("selected_item") or {}
    results = r.get("search_results") or []
    first = results[0]["id"] if results else None
    if criterion == 1:
        style = f"style={survey['style']}"
        ok = (status == 200 and item.get("id") not in (None, first)
              and style in why.get("matched", []))
        return ok, f"picked {item.get('id')} (first {first}), matched {why.get('matched')}"
    if criterion == 2:
        ok = status == 200 and why.get("score") is not None and why.get("score") == why.get("max_score")
        return ok, f"score {why.get('score')}/{why.get('max_score')} for {item.get('id')}"
    if criterion == 3:
        ok = status == 200 and why.get("by") == "first_result" and item.get("id") == first
        return ok, f"by={why.get('by')}, picked {item.get('id')}, first {first}"
    if criterion == 4:
        msg = r.get("error") or ""
        names_problem_and_allowed = any(s in msg for s in
                                        ("Choose one of:", "Questions are:", "must be an object like"))
        ran_agent = "selected_item" in r or "search_results" in r
        ok = status == 400 and names_problem_and_allowed and not ran_agent
        return ok, f"status {status}, agent ran={ran_agent}, error={msg!r}"
    if criterion == 5:
        note = why.get("note") or ""
        ok = status == 200 and note.startswith("None of the")
        return ok, f"note={note!r}"
    raise ValueError(criterion)


def cases(only: set[int]):
    if 1 in only:
        for q, s in C1:
            yield 1, {"query": q, "survey": s}, s
    if 2 in only:
        for q, s in C2:
            yield 2, {"query": q, "survey": s}, s
    if 3 in only:
        for q in C3:
            yield 3, {"query": q}, None
    if 4 in only:
        for s in C4:
            yield 4, {"query": "top under $40", "survey": s}, s
    if 5 in only:
        for q, s in C5:
            yield 5, {"query": q, "survey": s}, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="before / after")
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--only", default="1,2,3,4,5")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",")}

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"capstone_{args.label}_trial{args.trial}.jsonl"
    tally: dict[int, list[bool]] = {}
    with out.open("a", encoding="utf-8") as fh:
        for criterion, body, survey in cases(only):
            status, payload, secs = post(args.url, body)
            ok, detail = judge(criterion, status, payload, survey)
            tally.setdefault(criterion, []).append(ok)
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "label": args.label, "trial": args.trial, "criterion": criterion,
                "input": body, "status": status, "seconds": round(secs, 2),
                "pass": ok, "detail": detail,
                "run_error": payload.get("error") if status == 200 else None,
                "response": payload,
            }, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  #{criterion} {'PASS' if ok else 'FAIL'} {secs:5.1f}s  {body}  → {detail}",
                  flush=True)

    print(f"\n{args.label} trial {args.trial}:")
    for c in sorted(tally):
        print(f"  criterion {c}: {sum(tally[c])}/{len(tally[c])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
