"""python vote.py -> adds a "vote" to every event in results.json (then run table.py to compare it)"""
import json
from collections import Counter
from pathlib import Path

VOTERS = ["claude", "qwen", "laya", "laya_choice"]  # claude first: it breaks ties
out = Path(__file__).parent / "results.json"
results = json.loads(out.read_text(encoding="utf-8"))

for row in results.values():
    votes = {m: row[m]["sectors"][0]["sector"] for m in VOTERS if m in row}  # classify.py keeps one sector per model
    counts = Counter(votes.values())
    tied = [s for s, n in counts.items() if n == max(counts.values())]
    winner = next(s for s in votes.values() if s in tied)  # tie -> the first voter's (claude's) choice
    row["vote"] = {"sectors": [{"sector": winner}], "votes": votes}
    print(f"{row['title'][:60]:60} -> {winner:24} {votes}")
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
