""" run:
ollama serve
python web.py
Settings (models, model names, Ollama address, events folder): edit config.cfg
The company profile is edited on the webpage and saved in profile.json
Other ways to use the same pipeline:
    python classify.py   (or name the models: python classify.py qwen claude)
    python vote.py                                     
    python table.py              
"""

import asyncio, html, json, re, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

import pipeline

HERE = Path(__file__).parent
PROFILE = HERE / "profile.json"
SECTORS = re.findall(r"^- ([^:]+):", pipeline.PROMPT, re.M)
FIELDS = {"name": "Company name", "siren": "SIREN (registration number)", "sector": "Sector (GICS)", "country": "Country",
          "employees": "Number of employees", "website": "Website", "software": "Software used (optional, comma separated)"}
PAGE = """<!doctype html><meta charset="utf-8"><title>Sector classifier</title>
<style>body{{font-family:sans-serif;margin:2em;max-width:900px}} textarea{{width:100%;height:12em}}
table{{border-collapse:collapse;margin-top:1em}} td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
.threat{{color:#c00;font-weight:bold}} .check{{color:#d46b00;font-weight:bold}}</style>
<h1>Sector classifier</h1>
{profile}
<h2>Classify an event</h2>
<form method="post" onsubmit="this.querySelector('button').textContent='Classifying...'">
<p><input type="file" accept=".json" onchange="this.files[0].text().then(t => this.form.event.value = t)"></p>
<textarea name="event" placeholder="...or paste a MISP event JSON here">{event}</textarea>
<p><button>Classify</button></p></form>{result}
<h2>Check event files against the profile</h2>
<form method="post" action="/check" onsubmit="this.querySelector('button').textContent='Checking...'">
<p><input type="file" accept=".json" multiple onchange="Promise.all([...this.files].map(f => f.text().then(text => ({{name: f.name, text}}))))
  .then(files => this.form.files.value = JSON.stringify(files))"><input type="hidden" name="files"></p>
<p><button>Check files</button></p></form>{check}"""

loop, client, ready = asyncio.new_event_loop(), None, threading.Event()


async def connect():
    global client
    try:
        async with Client(stdio_client(StdioServerParameters(command=sys.executable, args=["mcp_server.py"], cwd=HERE))) as client:
            ready.set()
            await asyncio.Event().wait()
    except Exception:  # e.g. a mistake in config.cfg: the server prints why, above
        client = None
        print("The MCP server could not start, see the message above. Fix it and restart web.py")
        ready.set()

threading.Thread(target=loop.run_until_complete, args=(connect(),), daemon=True).start()


def classify(event_text):
    try:
        event = json.loads(event_text)
    except ValueError as e:
        return f"<p>Not valid JSON: {html.escape(str(e))}</p>"
    r, error = call("classify_event", {"event": event})
    if error:
        return f"<p>Error: {html.escape(error)}</p>"
    rows =[*r["votes"].items(), *((m, f"FAILED: {e}") for m, e in r["errors"].items()), ("<b>vote</b>", f"<b>{r['vote'] or 'no model answered'}</b>"),
            *([("<b>agreement</b>", f"<b>{agree(r['agreement'])}</b>")] if r["agreement"] else [])]
    return f"<h2>{html.escape(r['title'])}</h2><table><tr><th>model</th><th>sector</th></tr>" + "".join(
        f"<tr><td>{m}</td><td>{s if m.startswith('<b>') else html.escape(s)}</td></tr>" for m, s in rows) + "</table>"


def agree(text):  # "check by hand" in orange so it stands out
    return f'<span class="check">{html.escape(text)}</span>' if "check by hand" in text else html.escape(text)


def call(tool, args):  # call a tool on the MCP server -> (result, error message)
    ready.wait()
    if client is None:
        return None, "The classifier could not start. See the message in the terminal where web.py runs."
    r = asyncio.run_coroutine_threadsafe(client.call_tool(tool, args), loop).result()
    return (None, r.content[0].text) if r.is_error else (json.loads(r.content[0].text), None)


def check(files_json):
    files, events, skipped = json.loads(files_json or "[]"), [], []
    for f in files:
        try:
            event = json.loads(f["text"])
            event["Event"]["info"]
            events.append((f["name"], event))
        except (ValueError, KeyError, TypeError):
            skipped.append(f["name"])
    if not events:
        return "<p>No MISP event files chosen.</p>"
    r, error = call("check_events", {"events": [e for _, e in events]})
    if error:
        return f"<p>Error: {html.escape(error)}</p>"
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    rows = sorted(zip([n for n, _ in events], r["events"]), key=lambda x: not x[1]["reasons"])  # threats first
    threats = sum(bool(e["reasons"]) for _, e in rows)
    cell = lambda e: f'<span class="threat">THREAT</span>: {html.escape("; ".join(e["reasons"]))}' if e["reasons"] else "no"
    return (f"<p><b>{threats} of {len(rows)} events are a threat to {html.escape(profile.get('name', 'the company'))}.</b>"
            + (f" Skipped (not MISP event JSON): {html.escape(', '.join(skipped))}" if skipped else "") + "</p>"
            + "<table><tr><th>file</th><th>event</th><th>sector (vote)</th><th>agreement</th><th>threat?</th></tr>"
            + "".join(f"<tr><td>{html.escape(n)}</td><td>{html.escape(e['title'])}</td><td>{html.escape(e['vote'] or 'no model answered')}</td>"
                      f"<td>{agree(e['agreement'] or '')}</td><td>{cell(e)}</td></tr>"
                      for n, e in rows) + "</table>")


def profile_form(message=""):
    p = json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else {}

    def field(k):
        if k == "sector":
            return '<select name="sector">' + "".join(
                f'<option{" selected" * (s == p.get("sector"))}>{s}</option>' for s in SECTORS) + "</select>"
        return f'<input name="{k}" value="{html.escape(p.get(k, ""))}" size="50">'

    return ('<h2>Company profile</h2><form method="post" action="/profile"><table>'
            + "".join(f"<tr><td>{label}</td><td>{field(k)}</td></tr>" for k, label in FIELDS.items())
            + f"</table><p><button>Save profile</button> {message}</p></form>")


class Handler(BaseHTTPRequestHandler):
    def page(self, event="", result="", message="", checked=""):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.format(profile=profile_form(message), event=html.escape(event), result=result, check=checked).encode())

    def do_GET(self):
        self.page()

    def do_POST(self):
        form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        if self.path == "/profile":  # save the company profile
            PROFILE.write_text(json.dumps({k: form.get(k, [""])[0].strip() for k in FIELDS}, indent=2), encoding="utf-8")
            return self.page(message="Saved.")
        if self.path == "/check":  # many event files against the profile
            return self.page(checked=check(form.get("files", [""])[0]))
        event = form.get("event", [""])[0]
        self.page(event, classify(event))


print("open http://localhost:8000")
HTTPServer(("localhost", 8000), Handler).serve_forever()
