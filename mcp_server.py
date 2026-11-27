import json, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp.server.mcpserver import MCPServer

import pipeline
from classify import run_all
from vote import VOTERS, agreement, vote

server = MCPServer("sector-classifier")
HERE = Path(__file__).parent


@server.tool()
def classify_event(event: dict, models: list[str] = VOTERS) -> dict:
    """Classify one MISP event JSON into one GICS sector with each model, then majority vote."""
    answers = run_all(pipeline.shrink(event), models)
    votes = {m: a["sectors"][0]["sector"] for m, a in answers.items() if not isinstance(a, Exception)}
    errors = {m: str(a) or repr(a) for m, a in answers.items() if isinstance(a, Exception)}
    winner = vote(votes) if votes else None
    return {"title": event["Event"]["info"], "votes": votes, "vote": winner,
            "agreement": agreement(votes, winner) if votes else None, "errors": errors}


@server.tool()
def classify_file(path: str, models: list[str] = VOTERS) -> dict:
    """Same as classify_event, but reads the MISP event JSON from a file path."""
    return classify_event(json.loads(Path(path).read_text(encoding="utf-8")), models)


def saved_or_classify(event, saved):  # reuse classify.py's saved answers if every model already answered this event
    row = saved.get(event["Event"].get("uuid"), {})
    if not all(m in row for m in VOTERS):
        return classify_event(event)
    votes = {m: row[m]["sectors"][0]["sector"] for m in VOTERS}
    winner = vote(votes)
    return {"title": event["Event"]["info"], "votes": votes, "vote": winner, "agreement": agreement(votes, winner), "errors": {}}


def threat_reasons(event, result, profile):  # why this event is a threat to the company ([] = not a threat)
    text = pipeline.shrink(event).lower()
    mentioned = lambda word: word and re.search(rf"\b{re.escape(word.lower())}\b", text)
    reasons = [f"targets the {result['vote']} sector"] if result["vote"] and result["vote"] == profile.get("sector") else []
    reasons += [f"mentions {w}" for w in [profile.get("name"), profile.get("country")] if mentioned(w)]
    reasons += [f"mentions {s.strip()}" for s in profile.get("software", "").split(",") if mentioned(s.strip())]  # optional field
    return reasons


@server.tool()
def check_events(events: list[dict], profile: dict | None = None) -> dict:
    """Classify a batch of MISP events and say which ones are a threat to the company profile
    (same sector, or the event mentions the company, its country or its software). Without a profile, uses profile.json."""
    profile = profile or json.loads((HERE / "profile.json").read_text(encoding="utf-8"))
    saved = json.loads((HERE / "results.json").read_text(encoding="utf-8")) if (HERE / "results.json").exists() else {}
    with ThreadPoolExecutor(4) as ex:  # 4 events at the same time
        results = list(ex.map(lambda e: saved_or_classify(e, saved), events))
    return {"events": [r | {"reasons": threat_reasons(e, r, profile)} for e, r in zip(events, results)]}


if __name__ == "__main__":
    server.run("stdio")
