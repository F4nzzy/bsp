# Threat event sector classifier

Takes MISP threat-intelligence events (JSON), lets several AI models classify each event into one GICS sector, and returns the majority vote.

## 1. Install (do this first)

You need **Python 3.11+**. Then, in this folder, run:

```
pip install -r requirements.txt
```

This installs every Python package the pipeline uses (laya, the MCP library, and the Claude and ChatGPT API libraries).

## 2. Set up the models you want

Choose the models in `config.cfg` (`models = ...`). Each model needs its own setup:

| Model | Cost | What you need |
|---|---|---|
| `qwen` | free | Install **Ollama** from https://ollama.com, then run `ollama pull qwen2.5:7b` (about 5 GB). Ollama must be running while you classify. |
| `laya`, `laya_choice` | free | Nothing more. On the first run laya downloads its model from Hugging Face, so you need internet once. |
| `claude` | paid | **Either** Claude Code installed and logged in with a paid Claude plan, **or** an Anthropic API key. |
| `chatgpt` | paid | An OpenAI API key. |

A completely free setup: `models = qwen, laya`

`laya_choice` is still supported but not in the defaults: in our test it answered Information Technology for most events (4/30 correct).

**API keys:** put them in `config.cfg` (`api_key =` under `[claude]` or `[chatgpt]`), or in the environment variables `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. Do not commit `config.cfg` with a key in it.

If a model is not set up, it shows as `FAILED` with a message saying what to install, and the vote uses the other models.

## 3. Run

**Webpage:** `python web.py`, then open http://localhost:8000, upload or paste a MISP event JSON and click Classify.

**A whole folder of events:** put the JSON files in `events/` (or change `events_folder` in `config.cfg`), then:

```
python classify.py    # every model classifies every event -> results.json (already classified events are skipped)
python vote.py        # majority vote -> results.json
python table.py       # compare with manual_labels.csv -> table.html
```

**From Claude Code (MCP):** `claude mcp add sector-classifier -- python mcp_server.py`, then ask Claude to classify an event file.

## Settings

All settings are in `config.cfg`: which models vote (the first one breaks ties), model names, the Ollama address, laya's threshold and the events folder.
