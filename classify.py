import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from threading import Lock
from pathlib import Path

import pipeline
from pipeline import CONFIG, SetupError
from vote import VOTERS

pipeline.PROMPT = pipeline.PROMPT.replace("}]}", '}], "confidence_basis": how you chose the confidence numbers}') \
    + "\nOnly use the GICS sector names listed above, never tag values."
SECTORS = re.findall(r"^- ([^:]+):", pipeline.PROMPT, re.M)
HERE = Path(__file__).parent
LAYA = Lock()  # laya's model is shared, so only one laya question at a time


@cache
def router():  
    try:
        from laya import Router
    except ImportError as e:
        raise SetupError(f"laya could not be loaded ({e}). Run: pip install -r requirements.txt")
    return Router(vega=False)


def laya(text):  
    qs = {s: {"type": "noul", "instructions": f"Does this threat target the {s} sector?"} for s in SECTORS}
    with LAYA:
        a = router().predict(text, qs, model=CONFIG["laya"]["model"], max_len=4096)["answers"]
    best = max(SECTORS, key=lambda s: a[s]["noul"])  # only the main sector, if laya is sure enough
    return {"sectors": [{"sector": best if a[best]["noul"] >= CONFIG["laya"].getfloat("threshold") else "Not sector-specific", "confidence": round(a[best]["noul"], 3)}]}


def laya_choice(text):
    criteria = dict(re.findall(r"^- ([^:]+): (.*)$", pipeline.PROMPT, re.M)) | {"Not sector-specific": "no particular industry"}
    qs = {"sector": {"type": "choice", "instructions": "Which industry sector does this threat target?", "criteria": criteria}}
    with LAYA:
        a = router().predict(text, qs, model=CONFIG["laya"]["model"], max_len=4096)["answers"]["sector"]
    return {"sectors": [{"sector": a["choice"], "confidence": round(a["probabilities"][a["choice"]], 3)}]}


CLAUDE = max(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
             key=lambda p: p.stat().st_mtime, default="claude")


def claude(text):  # with an API key: the Anthropic API, without one: the Claude Code CLI (subscription)
    key = CONFIG["claude"].get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        import anthropic
        try:
            r = anthropic.Anthropic(api_key=key).beta.messages.create(
                model=CONFIG["claude"]["model"], max_tokens=16000, system=pipeline.PROMPT,
                messages=[{"role": "user", "content": text}],
                betas=["server-side-fallback-2026-07-01"], fallbacks="default")  # if Claude refuses (cyber text), another model answers
        except anthropic.AuthenticationError:
            raise SetupError("The Claude API key is not valid. Check api_key under [claude] in config.cfg or ANTHROPIC_API_KEY")
        if r.stop_reason == "refusal":
            raise RuntimeError("Claude refused to answer")
        reply = next(b.text for b in r.content if b.type == "text")
    else:
        try:
            r = subprocess.run([str(CLAUDE), "-p", "--system-prompt", pipeline.PROMPT, "--tools", "", "--model", CONFIG["claude"]["model"],
                                "--no-session-persistence", "--output-format", "json"], input=text, capture_output=True, encoding="utf-8", timeout=300)
        except FileNotFoundError:
            raise SetupError("Claude Code is not installed. Install it and log in with a paid Claude plan, "
                             "or put a Claude API key in config.cfg (see README.md)")
        out = json.loads(r.stdout or "{}")
        if out.get("is_error") or "result" not in out:
            raise SetupError(f"Claude Code failed ({out.get('result') or r.stderr.strip()}). "
                             "Log in by running: claude, or put a Claude API key in config.cfg")
        reply = out["result"]
    return json.loads(re.search(r"\{.*\}", reply, re.S).group())


def chatgpt(text):  # OpenAI API; needs an API key (config or OPENAI_API_KEY)
    import openai
    key = CONFIG["chatgpt"].get("api_key") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SetupError("ChatGPT needs an OpenAI API key. Set api_key under [chatgpt] in config.cfg or OPENAI_API_KEY")
    try:
        r = openai.OpenAI(api_key=key).chat.completions.create(
            model=CONFIG["chatgpt"]["model"], response_format={"type": "json_object"},
            messages=[{"role": "system", "content": pipeline.PROMPT}, {"role": "user", "content": text}])
    except openai.AuthenticationError:
        raise SetupError("The OpenAI API key is not valid. Check api_key under [chatgpt] in config.cfg or OPENAI_API_KEY")
    return json.loads(r.choices[0].message.content)


MODELS = {"qwen": pipeline.classify, "laya": laya, "laya_choice": laya_choice, "claude": claude, "chatgpt": chatgpt}
if not VOTERS:
    raise SystemExit(f"No models chosen in config.cfg. Set for example: models = laya, laya_choice (supported: {', '.join(MODELS)})")
if unknown := [m for m in VOTERS if m not in MODELS]:
    raise SystemExit(f"Unknown model(s) {unknown} in config.cfg. Supported: {', '.join(MODELS)}")


def run(m, text, tries=3):  # retry, because Qwen sometimes returns an error instead of an answer
    for i in range(tries):
        try:
            answer = MODELS[m](text)
            answer["sectors"] = [max((s for s in answer["sectors"] if isinstance(s, dict) and "sector" in s),
                                     key=lambda s: s.get("confidence", 0))]
            return answer
        except SetupError:
            raise
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
        return path.stem, row, run_all(text, [m for m in sys.argv[1:] or VOTERS if m not in row])

    with ThreadPoolExecutor(4) as ex:  
        for stem, row, answers in ex.map(do, sorted((HERE / CONFIG["general"]["events_folder"]).glob("*.json"))):
            for m, a in answers.items():
                if isinstance(a, Exception):
                    print(f"{m:11} {row['title'][:60]:60} FAILED: {a or repr(a)}")
                else:
                    row[m] = a
                    print(f"{m:11} {row['title'][:60]:60} {a['sectors'][0]['sector']}")
            results[stem] = row
            out.write_text(json.dumps(results, indent=2), encoding="utf-8")
