import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

import pipeline
from classify import run_all
from vote import VOTERS, vote

server = MCPServer("sector-classifier")


@server.tool()
def classify_event(event: dict, models: list[str] = VOTERS) -> dict:
    """Classify one MISP event JSON into one GICS sector with each model, then majority vote."""
    answers = run_all(pipeline.shrink(event), models)
    votes = {m: a["sectors"][0]["sector"] for m, a in answers.items() if not isinstance(a, Exception)}
    errors = {m: repr(a) for m, a in answers.items() if isinstance(a, Exception)}
    return {"title": event["Event"]["info"], "votes": votes, "vote": vote(votes) if votes else None, "errors": errors}


@server.tool()
def classify_file(path: str, models: list[str] = VOTERS) -> dict:
    """Same as classify_event, but reads the MISP event JSON from a file path."""
    return classify_event(json.loads(Path(path).read_text(encoding="utf-8")), models)


if __name__ == "__main__":
    server.run("stdio")
