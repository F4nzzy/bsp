import json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from threading import Lock
from pathlib import Path

import pipeline

pipeline.PROMPT = pipeline.PROMPT.replace("}]}", '}], "confidence_basis": how you chose the confidence numbers}') \
    + "\nOnly use the GICS sector names listed above, never tag values."
SECTORS = re.findall(r"^- ([^:]+):", pipeline.PROMPT, re.M)
HERE = Path(__file__).parent
LAYA = Lock()  # laya's model is shared, so only one laya question at a time


@cache
def router():  
    from laya import Router
    return Router(vega=False)


def laya(text):  
    qs = {s: {"type": "noul", "instructions": f"Does this threat target the {s} sector?"} for s in SECTORS}
    with LAYA:
        a = router().predict(text, qs, model="multilingual", max_len=4096)["answers"]
    best = max(SECTORS, key=lambda s: a[s]["noul"])  # only the main sector, if laya is sure enough
    return {"sectors": [{"sector": best if a[best]["noul"] >= 0.8 else "Not sector-specific", "confidence": round(a[best]["noul"], 3)}]}


def laya_choice(text):
    criteria = dict(re.findall(r"^- ([^:]+): (.*)$", pipeline.PROMPT, re.M)) | {"Not sector-specific": "no particular industry"}
    qs = {"sector": {"type": "choice", "instructions": "Which industry sector does this threat target?", "criteria": criteria}}
    with LAYA:
        a = router().predict(text, qs, model="multilingual", max_len=4096)["answers"]["sector"]
    return {"sectors": [{"sector": a["choice"], "confidence": round(a["probabilities"][a["choice"]], 3)}]}


CLAUDE = max(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
             key=lambda p: p.stat().st_mtime, default="claude")


def claude(text):  
    r = subprocess.run([str(CLAUDE), "-p", "--system-prompt", pipeline.PROMPT, "--tools", "", "--model", "claude-opus-5-5",
                        "--no-session-persistence", "--output-format", "json"], input=text, capture_output=True, encoding="utf-8")
    return json.loads(re.search(r"\{.*\}", json.loads(r.stdout)["result"], re.S).group())


MODELS = {"qwen": pipeline.classify, "laya": laya, "laya_choice": laya_choice, "claude": claude}


def run(m, text, tries=3):  # retry, because Qwen sometimes returns an error instead of an answer
    for i in range(tries):
        try:
            answer = MODELS[m](text)
            answer["sectors"] = [max((s for s in answer["sectors"] if isinstance(s, dict) and "sector" in s),
                                     key=lambda s: s.get("confidence", 0))]
            return answer
        except Exception:
            if i == tries - 1:
                raise


def run_all(text, models):  # all models at the same time -> {model: answer, or the exception if it failed}
    with ThreadPoolExecutor() as ex:
        jobs = {m: ex.submit(run, m, text) for m in models}
    return {m: j.exception() or j.result() for m, j in jobs.items()}


if __name__ == "__main__":
    out = HERE / "results.json"
    results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

    def do(path):
        text = pipeline.shrink(json.loads(path.read_text(encoding="utf-8")))
        row = results.get(path.stem, {"title": text.splitlines()[0][7:]})
        return path.stem, row, run_all(text, [m for m in sys.argv[1:] if m not in row])

    with ThreadPoolExecutor(4) as ex:  # 4 events at the same time
        for stem, row, answers in ex.map(do, sorted((HERE / "events").glob("*.json"))):
            for m, a in answers.items():
                if isinstance(a, Exception):
                    print(f"{m:11} {row['title'][:60]:60} FAILED: {a!r}")
                else:
                    row[m] = a
                    print(f"{m:11} {row['title'][:60]:60} {a['sectors'][0]['sector']}")
            results[stem] = row
            out.write_text(json.dumps(results, indent=2), encoding="utf-8")
