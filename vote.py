import json
from collections import Counter
from pathlib import Path

VOTERS = ["claude", "qwen", "laya", "laya_choice"]


def vote(votes): 
    counts = Counter(votes.values())
    tied = [s for s, n in counts.items() if n == max(counts.values())]
    return next(s for s in votes.values() if s in tied)


if __name__ == "__main__":
    out = Path(__file__).parent / "results.json"
    results = json.loads(out.read_text(encoding="utf-8"))
    for row in results.values():
        votes = {m: row[m]["sectors"][0]["sector"] for m in VOTERS if m in row}
        winner = vote(votes)
        row["vote"] = {"sectors": [{"sector": winner}], "votes": votes}
        print(f"{row['title'][:60]:60} -> {winner:24} {votes}")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
