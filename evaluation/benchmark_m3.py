import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.main import app, warm_up
from backend.services import cache as cache_module
from backend.services import telemetry
from backend.services.cache import SemanticCache
from backend.services.contract_validator import validate_and_repair
from backend.services.query_processor import process_query

for key in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(key, None)

DATASET = ROOT / "evaluation" / "m3_paraphrase_set.json"
INPUT_FILE = ROOT / "data" / "input.txt"
RESULTS = ROOT / "evaluation" / "benchmark_m3_results.json"

CONFIGS = {
    "A_exact_baseline": dict(semantic_enabled=False, seed_variations=False),
    "B_semantic_unguarded": dict(domain_guard=False, facet_guard=False, seed_variations=False),
    "C_semantic_guarded": dict(seed_variations=False),
    "D_full_guarded_seeded": dict(),
}


def percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, -(-pct * len(ordered) // 100) - 1))
    return round(ordered[int(index)], 3)


def split(items, part):
    return [x for i, x in enumerate(items) if i % 2 == (0 if part == "dev" else 1)]


def seed_responses(intents):
    seeded = {}
    for intent in intents:
        repaired, _ = validate_and_repair(process_query(intent["seed"]))
        seeded[intent["id"]] = repaired
    return seeded


def evaluate(config, intents, probes, seeded, part, threshold, variation_threshold, simulated_variations=False):
    cache = SemanticCache(threshold=threshold, variation_threshold=variation_threshold, **config)
    owner = {}
    for intent in intents:
        response = seeded[intent["id"]]
        variations = split(intent["paraphrases"], "dev") if simulated_variations else response.get("query_variations")
        cache.store(intent["seed"], response, variations)
        owner[id(response)] = intent["id"]

    correct = wrong = total = 0
    tiers = {"exact": 0, "semantic": 0, "variation": 0}
    misses = []
    for intent in intents:
        for query in split(intent["paraphrases"], part):
            total += 1
            hit = cache.lookup(query)
            if hit.response is None:
                misses.append(query)
                continue
            tiers[hit.tier] += 1
            if owner[id(hit.response)] == intent["id"]:
                correct += 1
            else:
                wrong += 1

    probe_set = split(probes, part)
    false_probe_hits = [p["query"] for p in probe_set if cache.lookup(p["query"]).response is not None]
    return {
        "paraphrases": total,
        "correct_hits": correct,
        "wrong_hits": wrong,
        "hit_rate": round(correct / total, 4) if total else 0.0,
        "wrong_hit_rate": round(wrong / total, 4) if total else 0.0,
        "probes": len(probe_set),
        "probe_false_hits": len(false_probe_hits),
        "probe_false_hit_queries": false_probe_hits,
        "hits_by_tier": tiers,
        "missed_queries": misses,
    }


def tune(config, intents, probes, seeded):
    best, grid = None, []
    for t in [round(0.30 + 0.05 * i, 2) for i in range(12)]:
        for delta in (0.0, 0.05, 0.10):
            vt = round(t + delta, 2)
            r = evaluate(config, intents, probes, seeded, "dev", t, vt)
            safe = r["wrong_hits"] == 0 and r["probe_false_hits"] == 0
            grid.append({"threshold": t, "variation_threshold": vt, "hit_rate": r["hit_rate"],
                         "wrong_hits": r["wrong_hits"], "probe_false_hits": r["probe_false_hits"], "safe": safe})
            if safe and (best is None or r["hit_rate"] > best[2] or (r["hit_rate"] == best[2] and t > best[0])):
                best = (t, vt, r["hit_rate"])
    return best, grid


def api_latency(intents):
    client = TestClient(app)
    cache_module.clear()
    telemetry.metrics.reset()
    cold, hot = [], []
    for intent in intents:
        start = time.perf_counter()
        client.post("/v1/troubleshoot", json={"query": intent["seed"]})
        cold.append((time.perf_counter() - start) * 1000)
    for intent in intents:
        for query in split(intent["paraphrases"], "test"):
            start = time.perf_counter()
            response = client.post("/v1/troubleshoot", json={"query": query})
            elapsed = (time.perf_counter() - start) * 1000
            (cold if response.headers["X-Cache"] == "miss" else hot).append(elapsed)
    return {
        "cold_ms": {"count": len(cold), "p50": percentile(cold, 50), "p95": percentile(cold, 95),
                    "mean": round(statistics.mean(cold), 3)},
        "hit_ms": {"count": len(hot), "p50": percentile(hot, 50), "p95": percentile(hot, 95),
                   "mean": round(statistics.mean(hot), 3) if hot else 0.0},
        "server_metrics": client.get("/v1/metrics").json(),
    }


def official_contract_audit():
    queries = [q.strip() for q in INPUT_FILE.read_text(encoding="utf-8").splitlines()
               if q.strip() and not q.startswith("#")]
    codes, quarantined, repaired, passed = {}, 0, 0, 0
    for query in queries:
        output, report = validate_and_repair(process_query(query))
        for v in report.violations:
            codes[v.code] = codes.get(v.code, 0) + 1
        quarantined += report.count("quarantined")
        repaired += report.count("repaired")
        passed += bool(output["contexts"]) and output.get("fallback") is None
    return {"queries": len(queries), "responses_delivered": passed, "repairs": repaired,
            "quarantined": quarantined, "violation_codes": codes}


def main():
    warm_up()
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    intents, probes = data["intents"], data["probes"]
    seeded = seed_responses(intents)

    tuned, grids = {}, {}
    for name, cfg in CONFIGS.items():
        best, grids[name] = tune(cfg, intents, probes, seeded)
        tuned[name] = best or (0.85, 0.95, 0.0)
    t, vt, dev_rate = tuned["D_full_guarded_seeded"]
    test = {name: evaluate(cfg, intents, probes, seeded, "test", tuned[name][0], tuned[name][1])
            for name, cfg in CONFIGS.items()}
    test["E_full_seeded_simulated_llm_variations"] = evaluate(
        CONFIGS["D_full_guarded_seeded"], intents, probes, seeded, "test", t, vt, simulated_variations=True)
    shared = {name: evaluate(cfg, intents, probes, seeded, "test", t, vt) for name, cfg in CONFIGS.items()}
    results = {
        "selected_thresholds": {"semantic": t, "variation": vt, "dev_hit_rate": dev_rate},
        "per_config_thresholds": {n: {"semantic": v[0], "variation": v[1], "dev_hit_rate": v[2]} for n, v in tuned.items()},
        "dev_grid": grids,
        "test": test,
        "test_shared_threshold": shared,
        "dev": {name: evaluate(cfg, intents, probes, seeded, "dev", tuned[name][0], tuned[name][1])
                for name, cfg in CONFIGS.items()},
        "api_latency": api_latency(intents),
        "official_contract_audit": official_contract_audit(),
        "environment": {"python": sys.version.split()[0], "llm_provider": "disabled (deterministic M1 fallback)"},
    }
    RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"selected thresholds: semantic={t} variation={vt} (dev hit rate {dev_rate})")
    print(f"{'config':40} {'split':5} {'thr':>5} {'hit':>7} {'wrong':>6} {'probeFP':>8}")
    for part in ("dev", "test"):
        for name, r in results[part].items():
            thr = tuned.get(name, (t,))[0]
            print(f"{name:40} {part:5} {thr:5} {r['hit_rate']:7.2%} {r['wrong_hits']:6d} {r['probe_false_hits']:4d}/{r['probes']}")
    lat = results["api_latency"]
    print(f"api cold p50={lat['cold_ms']['p50']}ms p95={lat['cold_ms']['p95']}ms | "
          f"hit p50={lat['hit_ms']['p50']}ms p95={lat['hit_ms']['p95']}ms")
    print("official contract audit:", results["official_contract_audit"])


if __name__ == "__main__":
    main()
