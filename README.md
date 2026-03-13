# MCP Marketplace Backend

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API will be live at: http://localhost:8000
Interactive docs at: http://localhost:8000/docs

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /models | All running models + their connected tools |
| GET | /catalog?q=&category= | Browse/search MCP catalog |
| POST | /connect | Connect an MCP tool to a model |
| POST | /disconnect | Disconnect an MCP tool from a model |
| GET | /registry | Full model→tools map (for orchestrator) |
| GET | /processes | All running MCP server processes |
| DELETE | /processes/{id} | Force-kill an MCP process |

## Connect Example

```bash
curl -X POST http://localhost:8000/connect \
  -H "Content-Type: application/json" \
  -d '{"model_id": "model_a", "mcp_id": "brave-search", "api_key": "YOUR_KEY"}'
```

## Wiring to the React Frontend

In your React app, replace the hardcoded mock data with API calls:

```js
// Get models
const models = await fetch("http://localhost:8000/models").then(r => r.json());

// Get catalog
const catalog = await fetch("http://localhost:8000/catalog?q=search").then(r => r.json());

// Connect a tool
await fetch("http://localhost:8000/connect", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ model_id: "model_a", mcp_id: "brave-search", api_key: "..." })
});
```

## TODO: Wire to real vLLM/Ollama

In main.py, replace MOCK_MODELS with real API calls:

```python
# vLLM
resp = requests.get("http://<spark-ip>:8000/v1/models")
models = resp.json()["data"]

# Ollama
resp = requests.get("http://<spark-ip>:11434/api/tags")
models = resp.json()["models"]
```
