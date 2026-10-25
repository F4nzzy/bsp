import requests, json
from pathlib import Path

SAMPLE = Path(__file__).parent / "sample"

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
Several sectors are allowed. Answer "Not sector-specific" if nothing in the text points to an industry.
Reply in JSON: {"sectors": [{"sector": ..., "confidence": 0-1, "evidence": ...}]}"""


def shrink(event):
    """Keep the title, tags and written descriptions; drop hashes, IPs, domains."""
    e = event["Event"]
    tags = [t["name"] for t in e.get("Tag", []) if not t["name"].startswith("tlp:")]
    texts = [a["value"] for a in e.get("Attribute", []) if a["type"] in ("comment", "text")]
    return f"Title: {e['info']}\nTags: {tags}\nDescription: {' '.join(texts)}"[:3000]


def classify(text):
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:7b",
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
        "format": "json",
        "options": {"temperature": 0},
        "stream": False,
    })
    return json.loads(r.json()["message"]["content"])


results = []
for path in sorted((SAMPLE / "events").glob("*.json")):
    text = shrink(json.loads(path.read_text()))
    answer = classify(text)
    results.append({"file": path.name, "input": text, "output": answer})
    print(text.splitlines()[0], "->", answer)

(SAMPLE / "results.json").write_text(json.dumps(results, indent=2))
