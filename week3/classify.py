"""python classify.py qwen/laya"""
import json, re, sys
from functools import cache
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "week2"))
import pipeline

pipeline.PROMPT = pipeline.PROMPT.replace("}]}", '}], "confidence_basis": how you chose the confidence numbers}') \
    + "\nOnly use the GICS sector names listed above, never tag values."
SECTORS = re.findall(r"^- ([^:]+):", pipeline.PROMPT, re.M)
HERE = Path(__file__).parent


@cache
def router():  # needs: pip install laya
    from laya import Router
    return Router(vega=False)


def laya(text):  # one yes/no question per sector -> real probabilities, not self-reported
    qs = {s: {"type": "noul", "instructions": f"Does this threat target the {s} sector?"} for s in SECTORS}
    a = router().predict(text, qs, model="multilingual", max_len=4096)["answers"]
    return {"sectors": [{"sector": s, "confidence": round(a[s]["noul"], 3)} for s in SECTORS if a[s]["noul"] >= 0.5]}


MODELS = {"qwen": pipeline.classify, "laya": laya}
out = HERE / "results.json"
results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
for path in sorted((HERE / "sample" / "events").glob("*.json")):
    text = pipeline.shrink(json.loads(path.read_text(encoding="utf-8")))
    row = results.setdefault(path.stem, {"title": text.splitlines()[0][7:]})
    for m in (m for m in sys.argv[1:] if m not in row):
        try:
            row[m] = MODELS[m](text)
            print(f"{m:7} {row['title'][:60]:60} {[s['sector'] for s in row[m]['sectors']]}")
        except Exception as e:
            print(f"{m:7} {row['title'][:60]:60} FAILED: {e!r}")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
