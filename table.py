"""Compare models with manual labels (and with Claude). First run creates manual_labels.csv to fill in."""
import csv, html, json
from pathlib import Path

HERE = Path(__file__).parent
results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
labels = HERE / "manual_labels.csv"
if not labels.exists():
    with open(labels, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["uuid", "title", "manual"]] + [[u, r["title"], ""] for u, r in results.items()])
    raise SystemExit(f"fill in the manual column of {labels} (sectors separated by ;) and run again")

for row in csv.DictReader(open(labels, encoding="utf-8")):
    if row["manual"].strip():
        results[row["uuid"]]["manual"] = {"sectors": [{"sector": s.strip()} for s in row["manual"].split(";")]}

models = [m for m in ("manual", "qwen", "claude", "laya", "laya_choice", "vote") if any(m in r for r in results.values())]
get = lambda r, m: {s["sector"] for s in r[m]["sectors"]} - {"Not sector-specific"}


def stats(m, ref):  # how well model m matches reference ref, on events that have both
    pairs = [(get(r, m), get(r, ref)) for r in results.values() if m in r and ref in r]
    tp, pred, gold = (sum(len(x) for x in xs) for xs in zip(*[(p & g, p, g) for p, g in pairs]))
    return [f"{m} vs {ref}", len(pairs), f"{sum(p == g for p, g in pairs) / len(pairs):.0%}",
            f"{tp / (pred or 1):.2f}", f"{tp / (gold or 1):.2f}"]


rows = [stats(m, ref) for ref in ("manual", "claude") for m in models
        if m not in (ref, "manual") and ref in models and any(m in r and ref in r for r in results.values())]
cell = lambda r, m: "; ".join(sorted(get(r, m))) or "none" if m in r else "-"
mark = lambda r, m: "" if m == "manual" or "manual" not in r or m not in r else "ok" if get(r, m) == get(r, "manual") else "bad"
table = lambda head, body: ("<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + "".join(
    "<tr>" + "".join(f'<td class="{c}">{html.escape(str(t))}</td>' for t, c in row) + "</tr>" for row in body) + "</table>")
page = f"""<!doctype html><meta charset="utf-8"><title>Sector classification results</title>
<style>body{{font-family:sans-serif;margin:2em}} table{{border-collapse:collapse;margin-bottom:2em}}
td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}} th{{background:#eee}} .ok{{background:#d4f4d4}} .bad{{background:#f8d4d4}}</style>
<h1>Sector classification: {" vs ".join(models)}</h1>
<h2>Scores</h2>{table(["comparison", "n", "exact match", "precision", "recall"], [[(v, "") for v in r] for r in rows])}
<h2>Per event</h2><p>Green = same sectors as the manual label, red = different.</p>
{table(["event", *models], [[(r["title"], "")] + [(cell(r, m), mark(r, m)) for m in models] for r in results.values()])}"""
(HERE / "table.html").write_text(page, encoding="utf-8")
print("open", HERE / "table.html")
