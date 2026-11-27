import json
from collections import Counter
from pathlib import Path

from pipeline import CONFIG

VOTERS = [m.strip() for m in CONFIG["general"]["models"].split(",") if m.strip()]  # in config order, so the first model breaks ties


def vote(votes): 
    counts = Counter(votes.values())
    tied = [s for s, n in counts.items() if n == max(counts.values())]
    return next(s for s in votes.values() if s in tied)


def agreement(votes, winner): 
    n = sum(s == winner for s in votes.values())
    return f"{n} of {len(votes)} models agree" + ("" if n * 2 > len(votes) else " - check by hand")


if __name__ == "__main__":
    out = Path(__file__).parent / "results.json"
    results = json.loads(out.read_text(encoding="utf-8"))
    for row in results.values():
        votes = {m: row[m]["sectors"][0]["sector"] for m in VOTERS if m in row}
        if not votes:
            print(f"{row['title'][:60]:60} -> no model answered (see the FAILED messages from classify.py)")
            continue
        winner = vote(votes)
        row["vote"] = {"sectors": [{"sector": winner}], "votes": votes, "agreement": agreement(votes, winner)}
        print(f"{row['title'][:60]:60} -> {winner:24} {row['vote']['agreement']}")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    check = [r["title"] for r in results.values() if "check by hand" in r.get("vote", {}).get("agreement", "")]
    print(f"\n{len(check)} of {len(results)} events need checking by hand" + "".join(f"\n  - {t}" for t in check))
