import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ORDER = sys.argv[2] if len(sys.argv) > 2 else "typo-first"

PAIRS = [
    ("my phone batery drainz so fast", "my phone battery drains so fast"),
    ("wifi keps disconecting", "wifi keeps disconnecting"),
    ("my screen is flikering alot", "my screen is flickering a lot"),
    ("blutooth wont pair with my car", "bluetooth won't pair with my car"),
    ("my camra photos are blury", "my camera photos are blurry"),
    ("phone overheting while chargng", "phone overheating while charging"),
    ("my phone storge is ful", "my phone storage is full"),
    ("speker not wroking on calls", "speaker not working on calls"),
    ("apps keep crashng and freezng", "apps keep crashing and freezing"),
    ("my phone tiem is in 24 hr", "my phone time is in 24 hrs"),
    ("turn of blutooth", "turn off bluetooth"),
    ("mobil data not wrking", "mobile data not working"),
]


def ask(query: str) -> dict:
    request = urllib.request.Request(
        BASE + "/v1/troubleshoot", data=json.dumps({"query": query}).encode(), headers={"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body, headers, status = json.loads(response.read()), response.headers, response.status
    except urllib.error.HTTPError as exc:
        return {"query": query, "status": exc.code, "answer": None, "cache": None, "ms": 0}
    answer = body["contexts"][0]["title"] if body["contexts"] else body["fallback"]
    return {"query": query, "status": status, "answer": answer, "cache": headers.get("X-Cache"),
            "ms": round((time.perf_counter() - started) * 1000)}


def main() -> None:
    rows = []
    for typo, clean in PAIRS:
        first, second = (typo, clean) if ORDER == "typo-first" else (clean, typo)
        a, b = ask(first), ask(second)
        rows.append({"first": a, "second": b, "same_answer": a["answer"] == b["answer"]})
        print(f"{'SAME' if rows[-1]['same_answer'] else 'DIFFERENT':9} | {first[:34]:34} -> {a['answer']} | {second[:34]:34} -> {b['answer']} ({b['cache']})")
    errors = sum(r[k]["status"] != 200 for r in rows for k in ("first", "second"))
    summary = {"order": ORDER, "pairs": len(rows), "same_answer": sum(r["same_answer"] for r in rows), "http_errors": errors}
    print(summary)
    print(json.dumps({"summary": summary, "rows": rows}, indent=1), file=sys.stderr)


if __name__ == "__main__":
    main()
