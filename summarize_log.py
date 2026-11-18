#!/usr/bin/env python3
"""
Summarise serve.py's structured log: per-request rows plus averages.

    python summarize_log.py                         local logs/requests.jsonl
    python summarize_log.py path/to/requests.jsonl  a saved copy
    python summarize_log.py https://<your-app>/logs?n=500
                                                    the live log from the host

    --since 2026-11-16T20:00     only records at or after this timestamp
    --save results/name.jsonl    also write the records it read to a file

The averages are taken over successful agent runs (status 200, outcome "ok")
with the cache off, because a cached run spends no tokens and would drag the
per-run cost down to something that isn't true.
"""

import argparse
import json
import ssl
import statistics
import sys
import urllib.request
from pathlib import Path

DEFAULT = Path(__file__).parent / "logs" / "requests.jsonl"


def load(source: str) -> list[dict]:
    if source.startswith("http://") or source.startswith("https://"):
        # python.org's macOS Python has no CA certificates; use certifi's.
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        with urllib.request.urlopen(source, timeout=120, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    records = []
    for line in Path(source).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", default=str(DEFAULT))
    ap.add_argument("--since")
    ap.add_argument("--save")
    args = ap.parse_args()

    records = load(args.source)
    if args.since:
        records = [r for r in records if r.get("ts", "") >= args.since]
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )

    print("| ts | id | status | outcome | query | total ms | agent ms | wait ms | calls | tokens |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in records:
        q = str(r.get("query"))[:40].replace("|", "\\|")
        print(f"| {r.get('ts')} | {r.get('request_id')} | {r.get('status')} | "
              f"{r.get('outcome')} | {q} | {r.get('duration_ms')} | "
              f"{r.get('agent_ms', '')} | {r.get('lock_wait_ms', '')} | "
              f"{r.get('model_calls', '')} | {r.get('total_tokens', '')} |")

    ok = [r for r in records
          if r.get("status") == 200 and r.get("outcome") == "ok"
          and not r.get("cache_hits")]
    print()
    print(f"{len(records)} records: "
          + ", ".join(f"{o}={sum(1 for r in records if r.get('outcome') == o)}"
                      for o in sorted({str(r.get('outcome')) for r in records})))
    if not ok:
        print("No uncached successful runs to average.")
        return 0

    def avg(key):
        return statistics.mean(r.get(key) or 0 for r in ok)

    durations = [r["duration_ms"] for r in ok]
    print(f"Uncached successful runs: {len(ok)}")
    print(f"  model calls / run:   {avg('model_calls'):.2f}")
    print(f"  prompt tokens / run: {avg('prompt_tokens'):.1f}")
    print(f"  output tokens / run: {avg('output_tokens'):.1f}")
    print(f"  total tokens / run:  {avg('total_tokens'):.1f}")
    print(f"  duration ms: mean {statistics.mean(durations):.0f}, "
          f"median {statistics.median(durations):.0f}, "
          f"p90 {pct(durations, 90):.0f}, max {max(durations):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
