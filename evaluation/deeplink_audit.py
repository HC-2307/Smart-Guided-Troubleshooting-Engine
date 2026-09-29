import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CACHE_PERSIST_PATH"] = ""
os.environ["CACHE_PREWARM"] = "false"
os.environ["LLM_FREE_TIER"] = "false"

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import cache
from backend.services.contract_validator import catalog_by_deeplink, entry_polarity, polarity

for key in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(key, None)

client = TestClient(app)
RESULTS = ROOT / "evaluation" / "deeplink_audit_results.json"


def queries() -> dict[str, list[str]]:
    official = [line.strip() for line in (ROOT / "data" / "input.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    paraphrase_set = json.loads((ROOT / "evaluation" / "m3_paraphrase_set.json").read_text(encoding="utf-8"))
    seeds = [intent["seed"] for intent in paraphrase_set["intents"]]
    settings_set = json.loads((ROOT / "evaluation" / "m3_settings_set.json").read_text(encoding="utf-8"))
    settings = [item["query"] for item in settings_set.get("requests", settings_set.get("settings", [])) if isinstance(item, dict) and "query" in item]
    return {"official": official, "domain_seeds": seeds, "settings_requests": settings}


def audit(group: list[str]) -> dict:
    catalog = catalog_by_deeplink()
    counts = Counter()
    problems = []
    for query in group:
        cache.clear()
        body = client.post("/v1/troubleshoot", json={"query": query}).json()
        for goal in body.get("contexts", []):
            actions = goal.get("actions", [])
            categories = [a.get("category") for a in actions]
            if "critical" in categories and any(c != "critical" for c in categories[categories.index("critical"):]):
                problems.append({"query": query, "problem": "critical action not last"})
            for action in actions:
                category = action.get("category")
                counts[f"actions_{category}"] += 1
                links = [g.get("actionableDeeplink") for g in action.get("stepGroups", []) if g.get("actionableDeeplink")]
                if not links:
                    continue
                counts[f"with_deeplink_{category}"] += 1
                for link in links:
                    counts["deeplinks"] += 1
                    entry = catalog.get(link.get("deeplink"))
                    if entry is None:
                        problems.append({"query": query, "problem": "deeplink not in catalog", "deeplink": link.get("deeplink")})
                        continue
                    counts["deeplinks_in_catalog"] += 1
                    if category == "manual":
                        problems.append({"query": query, "problem": "manual action has a deeplink"})
                    wanted, offered = polarity(action.get("actionName", "")), entry_polarity(entry)
                    if wanted and offered and wanted != offered:
                        problems.append({"query": query, "problem": "toggle polarity conflict", "action": action.get("actionName")})
    auto = counts["actions_auto"]
    return {
        "queries": len(group),
        "actions": {c: counts[f"actions_{c}"] for c in ("auto", "manual", "critical")},
        "auto_actions_with_deeplink": f"{counts['with_deeplink_auto']}/{auto}",
        "deeplinks_in_catalog": f"{counts['deeplinks_in_catalog']}/{counts['deeplinks']}",
        "manual_actions_with_deeplink": counts["with_deeplink_manual"],
        "problems": problems,
    }


def main() -> None:
    report = {"environment": {"llm": "disabled", "python": sys.version.split()[0]}}
    for name, group in queries().items():
        report[name] = audit(group)
        summary = {k: v for k, v in report[name].items() if k != "problems"}
        print(f"{name:18} {summary} problems={len(report[name]['problems'])}")
    RESULTS.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
