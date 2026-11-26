""" run:
ollama serve
python web.py
Other ways to use the same pipeline:
    python classify.py qwen laya laya_choice claude   
    python vote.py                                     
    python table.py              
"""

import asyncio, html, json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent
PAGE = """<!doctype html><meta charset="utf-8"><title>Sector classifier</title>
<style>body{{font-family:sans-serif;margin:2em;max-width:900px}} textarea{{width:100%;height:12em}}
table{{border-collapse:collapse;margin-top:1em}} td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}</style>
<h1>Sector classifier</h1>
<form method="post" onsubmit="this.querySelector('button').textContent='Classifying...'">
<p><input type="file" accept=".json" onchange="this.files[0].text().then(t => this.form.event.value = t)"></p>
<textarea name="event" placeholder="...or paste a MISP event JSON here">{event}</textarea>
<p><button>Classify</button></p></form>{result}"""

loop, client, ready = asyncio.new_event_loop(), None, threading.Event()


async def connect():
    global client
    async with Client(stdio_client(StdioServerParameters(command=sys.executable, args=["mcp_server.py"], cwd=HERE))) as client:
        ready.set()
        await asyncio.Event().wait()

threading.Thread(target=loop.run_until_complete, args=(connect(),), daemon=True).start()


def classify(event_text):
    try:
        event = json.loads(event_text)
    except ValueError as e:
        return f"<p>Not valid JSON: {html.escape(str(e))}</p>"
    ready.wait()
    r = asyncio.run_coroutine_threadsafe(client.call_tool("classify_event", {"event": event}), loop).result()
    if r.is_error:
        return f"<p>Error: {html.escape(r.content[0].text)}</p>"
    r = json.loads(r.content[0].text)
    rows = [*r["votes"].items(), *((m, f"FAILED: {e}") for m, e in r["errors"].items()), ("<b>vote</b>", f"<b>{r['vote']}</b>")]
    return f"<h2>{html.escape(r['title'])}</h2><table><tr><th>model</th><th>sector</th></tr>" + "".join(
        f"<tr><td>{m}</td><td>{s if m.startswith('<b>') else html.escape(s)}</td></tr>" for m, s in rows) + "</table>"


class Handler(BaseHTTPRequestHandler):
    def page(self, event="", result=""):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.format(event=html.escape(event), result=result).encode())

    def do_GET(self):
        self.page()

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        event = parse_qs(body).get("event", [""])[0]
        self.page(event, classify(event))


print("open http://localhost:8000")
HTTPServer(("localhost", 8000), Handler).serve_forever()
