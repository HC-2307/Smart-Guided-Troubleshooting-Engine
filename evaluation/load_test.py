import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 16
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 10
RESULTS = ROOT / "evaluation" / "load_test_results.json"

official = [q.strip() for q in open(ROOT / "data" / "input.txt", encoding="utf-8") if q.strip()]
paraphrases = json.loads((ROOT / "evaluation" / "m3_paraphrase_set.json").read_text(encoding="utf-8"))
QUERIES = official[:10] + [q for it in paraphrases["intents"] for q in [it["seed"], *it["paraphrases"][:2]]] + [
    "turn on bluetooth", "my phone time is in 24 hrs", "change to light mode", "what is the capital of france",
    "tell me a joke", "my galaxy has a problem",
]


def one(client: httpx.Client, query: str) -> dict:
    started = time.perf_counter()
    try:
        response = client.post(f"{BASE}/v1/troubleshoot", json={"query": query})
        return {"query": query, "status": response.status_code, "cache": response.headers.get("x-cache"),
                "body": response.text, "ms": (time.perf_counter() - started) * 1000}
    except httpx.HTTPError as exc:
        return {"query": query, "status": "error", "cache": None, "body": repr(exc), "ms": (time.perf_counter() - started) * 1000}


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(p / 100 * len(ordered)))], 1) if ordered else 0.0


def main() -> None:
    jobs = QUERIES * ROUNDS
    with httpx.Client(timeout=30) as client, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        started = time.perf_counter()
        results = list(pool.map(lambda q: one(client, q), jobs))
        wall = time.perf_counter() - started
    by_tier: dict[str, list[float]] = defaultdict(list)
    bodies: dict[str, set[str]] = defaultdict(set)
    for r in results:
        by_tier["hit" if r["cache"] not in (None, "miss") else "miss"].append(r["ms"])
        if r["status"] == 200:
            bodies[r["query"]].add(r["body"])
    report = {
        "requests": len(results), "workers": WORKERS, "wall_seconds": round(wall, 2),
        "throughput_rps": round(len(results) / wall, 1),
        "status_codes": dict(Counter(str(r["status"]) for r in results)),
        "latency_ms": {tier: {"count": len(v), "p50": pct(v, 50), "p95": pct(v, 95), "max": round(max(v), 1)}
                       for tier, v in by_tier.items()},
        "queries_with_inconsistent_answers": [q for q, b in bodies.items() if len(b) > 1],
    }
    RESULTS.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
