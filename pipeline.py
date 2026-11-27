import configparser, json, requests
from pathlib import Path

SAMPLE = Path(__file__).parent / "week2_sample"
CONFIG = configparser.ConfigParser(inline_comment_prefixes=("#",)) 
CONFIG.read(Path(__file__).parent / "config.cfg", encoding="utf-8")

PROMPT = """You classify cyber threat intelligence events by the industry sector of the victims they target.
GICS sectors (with examples):
- Energy: oil, gas, coal, petroleum
- Materials: chemicals, mining, metals
- Industrials: aerospace, defense, manufacturing, construction, airlines, logistics
- Consumer Discretionary: retail, hotels, restaurants, cars, entertainment
- Consumer Staples: food, beverages, household products, supermarkets
- Health Care: hospitals, pharmaceuticals, medical devices
- Financials: banks, central banks, insurance, payments, ATMs, cryptocurrency exchanges
- Information Technology: software, hardware, IT services, semiconductors
- Communication Services: telecoms, media, internet platforms, gaming
- Utilities: electricity, water, gas distribution
- Real Estate: property companies, REITs
Give only the ONE main sector of the victims. Answer "Not sector-specific" if nothing in the text points to an industry.
Reply in JSON with exactly one entry: {"sectors": [{"sector": ..., "confidence": 0-1, "evidence": ...}]}"""


def shrink(event):
    """Keep the title, tags and written descriptions; drop hashes, IPs, domains."""
    e = event["Event"]
    tags = [t["name"] for t in e.get("Tag", []) if not t["name"].startswith("tlp:")]
    texts = [a["value"] for a in e.get("Attribute", []) if a["type"] in ("comment", "text")]
    return f"Title: {e['info']}\nTags: {tags}\nDescription: {' '.join(texts)}"[:3000]


class SetupError(RuntimeError):
    """A model is not installed or set up; retrying will not help."""


def classify(text, options={"temperature": 0}):
    model = CONFIG["qwen"]["model"]
    try:
        r = requests.post(CONFIG["qwen"]["url"], json={
            "model": model,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
            "format": "json",
            "options": options,
            "stream": False,
        }, timeout=120).json()  # never wait forever (e.g. Ollama half started)
    except requests.ConnectionError:
        raise SetupError("Ollama is not running. Install it from https://ollama.com and start it (ollama serve)")
    if "error" in r and "not found" in r["error"]:
        raise SetupError(f"Ollama does not have the model {model}. Run: ollama pull {model}")
    if "error" in r and "repeat_penalty" not in options:  # Qwen sometimes gets stuck repeating itself
        return classify(text, {"temperature": 0, "repeat_penalty": 1.2})
    if "error" in r:
        raise RuntimeError(r["error"])
    return json.loads(r["message"]["content"])


if __name__ == "__main__":
    results = []
    for path in sorted((SAMPLE / "events").glob("*.json")):
        text = shrink(json.loads(path.read_text()))
        answer = classify(text)
        results.append({"file": path.name, "input": text, "output": answer})
        print(text.splitlines()[0], "->", answer)

    (SAMPLE / "results.json").write_text(json.dumps(results, indent=2))
