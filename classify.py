"""python classify.py qwen/laya"""
import json, re, subprocess, sys
from functools import cache
from pathlib import Path

import pipeline

pipeline.PROMPT = pipeline.PROMPT.replace("}]}", '}], "confidence_basis": how you chose the confidence numbers}') \
    + "\nOnly use the GICS sector names listed above, never tag values."
SECTORS = re.findall(r"^- ([^:]+):", pipeline.PROMPT, re.M)
HERE = Path(__file__).parent


@cache
def router():  
    from laya import Router
    return Router(vega=False)


def laya(text):  
    qs = {s: {"type": "noul", "instructions": f"Does this threat target the {s} sector?"} for s in SECTORS}
    a = router().predict(text, qs, model="multilingual", max_len=4096)["answers"]
    best = max(SECTORS, key=lambda s: a[s]["noul"])  # only the main sector, if laya is sure enough
    return {"sectors": [{"sector": best if a[best]["noul"] >= 0.8 else "Not sector-specific", "confidence": round(a[best]["noul"], 3)}]}


def laya_choice(text):  # one question, laya picks one of the sectors
    criteria = dict(re.findall(r"^- ([^:]+): (.*)$", pipeline.PROMPT, re.M)) | {"Not sector-specific": "no particular industry"}
    qs = {"sector": {"type": "choice", "instructions": "Which industry sector does this threat target?", "criteria": criteria}}
    a = router().predict(text, qs, model="multilingual", max_len=4096)["answers"]["sector"]
    return {"sectors": [{"sector": a["choice"], "confidence": round(a["probabilities"][a["choice"]], 3)}]}


CLAUDE = max(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
             key=lambda p: p.stat().st_mtime, default="claude")


def claude(text):  
    r = subprocess.run([str(CLAUDE), "-p", "--system-prompt", pipeline.PROMPT, "--tools", "", "--model", "claude-opus-5-5",
                        "--no-session-persistence", "--output-format", "json"], input=text, capture_output=True, encoding="utf-8")
    return json.loads(re.search(r"\{.*\}", json.loads(r.stdout)["result"], re.S).group())


MODELS = {"qwen": pipeline.classify, "laya": laya, "laya_choice": laya_choice, "claude": claude}
out = HERE / "results.json"
results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
for path in sorted((HERE / "events").glob("*.json")):
    text = pipeline.shrink(json.loads(path.read_text(encoding="utf-8")))
    row = results.setdefault(path.stem, {"title": text.splitlines()[0][7:]})
    for m in (m for m in sys.argv[1:] if m not in row):
        try:
            answer = MODELS[m](text)  # keep only the one main sector (qwen sometimes adds junk entries)
            answer["sectors"] = [max((s for s in answer["sectors"] if isinstance(s, dict) and "sector" in s),
                                     key=lambda s: s.get("confidence", 0))]
            row[m] = answer
            print(f"{m:7} {row['title'][:60]:60} {[s['sector'] for s in row[m]['sectors']]}")
        except Exception as e:
            print(f"{m:7} {row['title'][:60]:60} FAILED: {e!r}")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
