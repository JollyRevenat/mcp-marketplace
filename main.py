"""
MCP Marketplace Backend
Run with: python -m uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import json
import os
import requests
from typing import Optional

app = FastAPI(title="MCP Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Registry (persists to disk) ─────────────────────────────────────────────

REGISTRY_FILE = "registry.json"
PROCESSES_FILE = "processes.json"

def load_registry() -> dict:
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {}

def save_registry(registry: dict):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)

def load_processes() -> dict:
    if os.path.exists(PROCESSES_FILE):
        with open(PROCESSES_FILE) as f:
            return json.load(f)
    return {}

def save_processes(processes: dict):
    with open(PROCESSES_FILE, "w") as f:
        json.dump(processes, f, indent=2)


# ─── Mock Models (swap for real vLLM/Ollama API calls later) ─────────────────

MOCK_MODELS = [
    {"id": "model_a", "name": "Llama 3.1 70B",  "engine": "vLLM",   "status": "running"},
    {"id": "model_b", "name": "Mistral 7B",      "engine": "vLLM",   "status": "running"},
    {"id": "model_c", "name": "Qwen2.5 72B",     "engine": "vLLM",   "status": "running"},
    {"id": "model_d", "name": "Phi-3 Mini",      "engine": "Ollama", "status": "running"},
    {"id": "model_e", "name": "DeepSeek R1",     "engine": "Ollama", "status": "idle"},
]

# ─── Smithery API ─────────────────────────────────────────────────────────────

SMITHERY_BASE = "https://registry.smithery.ai"

def fetch_smithery_catalog(q: str = "", page: int = 1, page_size: int = 50) -> dict:
    """Fetch servers from Smithery registry. Returns normalized list."""
    try:
        params = {"q": q, "page": page, "pageSize": page_size}
        resp = requests.get(
            f"{SMITHERY_BASE}/servers",
            params=params,
            timeout=8,
            headers={"Accept": "application/json", "User-Agent": "mcp-marketplace/1.0"}
        )
        resp.raise_for_status()
        data = resp.json()

        servers = []
        # Smithery returns { servers: [...], pagination: {...} }
        raw_list = data.get("servers", data if isinstance(data, list) else [])

        for s in raw_list:
            servers.append(normalize_smithery_server(s))

        return {"servers": servers, "total": data.get("pagination", {}).get("totalCount", len(servers))}

    except Exception as e:
        print(f"[Smithery] Failed to fetch catalog: {e}")
        return None


def normalize_smithery_server(s: dict) -> dict:
    """Normalize a raw Smithery server object into our frontend format."""
    # Map categories to our icons
    icon_map = {
        "search": "🔍", "browser": "🌐", "file": "📁", "filesystem": "📁",
        "database": "🗄️", "code": "⚙️", "memory": "🧠", "communication": "💬",
        "network": "📡", "maps": "🗺️", "github": "🐙", "git": "🐙",
        "slack": "💬", "email": "📧", "calendar": "📅", "storage": "📦",
        "ai": "🤖", "image": "🖼️", "video": "🎬", "audio": "🎵",
        "weather": "🌤️", "finance": "💰", "news": "📰", "social": "👥",
        "security": "🔒", "analytics": "📊", "automation": "⚡",
    }

        # Try to pick a good icon based on name/description
    name_lower = s.get("displayName", s.get("qualifiedName", "")).lower()
    desc_lower = s.get("description", "").lower()
    combined = name_lower + " " + desc_lower

    icon = "🔧"  # default
    for keyword, emoji in icon_map.items():
        if keyword in combined:
            icon = emoji
            break

    # Guess category
    cat = "Tools"
    if any(w in combined for w in ["search", "browse", "web", "brave", "google"]):
        cat = "Search"
    elif any(w in combined for w in ["file", "filesystem", "storage", "drive", "s3"]):
        cat = "Storage"
    elif any(w in combined for w in ["database", "sql", "postgres", "mysql", "mongo", "redis", "sqlite"]):
        cat = "Database"
    elif any(w in combined for w in ["code", "execute", "run", "shell", "terminal", "python", "javascript"]):
        cat = "Code"
    elif any(w in combined for w in ["github", "git", "jira", "linear", "gitlab"]):
        cat = "Dev Tools"
    elif any(w in combined for w in ["slack", "email", "discord", "telegram", "message", "chat"]):
        cat = "Communication"
    elif any(w in combined for w in ["browser", "puppeteer", "playwright", "chrome", "scrape"]):
        cat = "Browser"
    elif any(w in combined for w in ["http", "fetch", "api", "network", "request"]):
        cat = "Network"
    elif any(w in combined for w in ["memory", "knowledge", "remember", "context"]):
        cat = "Storage"

    qualified_name = s.get("qualifiedName", "")
    server_id = qualified_name.replace("/", "-").replace("@", "").lower() if qualified_name else s.get("displayName", "unknown").lower().replace(" ", "-")

    return {
        "id": server_id,
        "qualifiedName": qualified_name,
        "name": s.get("displayName", qualified_name or "Unknown"),
        "author": qualified_name.split("/")[0].lstrip("@") if "/" in qualified_name else "unknown",
        "description": s.get("description", "No description available."),
        "category": cat,
        "installs": s.get("useCount", 0),
        "requiresKey": False,  # Smithery doesn't always expose this — assume false
        "icon": icon,
        "command": f"npx {qualified_name}" if qualified_name else "",
        "homepage": s.get("homepage", ""),
    }


# ─── Large fallback catalog (used if Smithery is unreachable) ─────────────────

FALLBACK_CATALOG = [
    {"id": "brave-search",       "name": "Brave Search",        "author": "modelcontextprotocol", "description": "Web search via Brave's privacy-focused search API. Returns rich results with snippets.", "category": "Search",        "installs": 48200, "requiresKey": True,  "icon": "🔍", "command": "npx @modelcontextprotocol/server-brave-search"},
    {"id": "filesystem",         "name": "Filesystem",          "author": "modelcontextprotocol", "description": "Read and write files on the local filesystem with full path control and safety sandboxing.", "category": "Storage",   "installs": 61000, "requiresKey": False, "icon": "📁", "command": "npx @modelcontextprotocol/server-filesystem"},
    {"id": "code-exec",          "name": "Code Executor",       "author": "e2b",                  "description": "Run Python, JS, and shell commands in a secure sandboxed environment with output streaming.", "category": "Code",     "installs": 29400, "requiresKey": True,  "icon": "⚙️", "command": "npx @e2b/mcp-server"},
    {"id": "postgres",           "name": "PostgreSQL",          "author": "modelcontextprotocol", "description": "Query and manage PostgreSQL databases. Supports schema inspection, reads, and writes.", "category": "Database",    "installs": 33100, "requiresKey": False, "icon": "🗄️", "command": "npx @modelcontextprotocol/server-postgres"},
    {"id": "github",             "name": "GitHub",              "author": "modelcontextprotocol", "description": "Interact with GitHub repos, issues, PRs, and Actions. Full API coverage.", "category": "Dev Tools",              "installs": 44800, "requiresKey": True,  "icon": "🐙", "command": "npx @modelcontextprotocol/server-github"},
    {"id": "slack",              "name": "Slack",               "author": "modelcontextprotocol", "description": "Send messages, read channels, and manage Slack workspaces via the Slack Web API.", "category": "Communication", "installs": 21700, "requiresKey": True,  "icon": "💬", "command": "npx @modelcontextprotocol/server-slack"},
    {"id": "puppeteer",          "name": "Puppeteer",           "author": "modelcontextprotocol", "description": "Control a headless Chrome browser. Scrape pages, take screenshots, fill forms.", "category": "Browser",       "installs": 18900, "requiresKey": False, "icon": "🌐", "command": "npx @modelcontextprotocol/server-puppeteer"},
    {"id": "memory",             "name": "Memory",              "author": "modelcontextprotocol", "description": "Persistent key-value memory store for agents. Survives across sessions.", "category": "Storage",                "installs": 52300, "requiresKey": False, "icon": "🧠", "command": "npx @modelcontextprotocol/server-memory"},
    {"id": "sqlite",             "name": "SQLite",              "author": "modelcontextprotocol", "description": "Create and query SQLite databases. Perfect for lightweight structured data.", "category": "Database",               "installs": 27600, "requiresKey": False, "icon": "🗃️", "command": "npx @modelcontextprotocol/server-sqlite"},
    {"id": "fetch",              "name": "Fetch",               "author": "modelcontextprotocol", "description": "Make HTTP requests to any API or webpage. Supports GET, POST, headers, and auth.", "category": "Network",    "installs": 39800, "requiresKey": False, "icon": "📡", "command": "npx @modelcontextprotocol/server-fetch"},
    {"id": "google-maps",        "name": "Google Maps",         "author": "modelcontextprotocol", "description": "Geocoding, directions, places search, and distance matrix via Google Maps API.", "category": "Search",        "installs": 15400, "requiresKey": True,  "icon": "🗺️", "command": "npx @modelcontextprotocol/server-google-maps"},
    {"id": "redis",              "name": "Redis",               "author": "upstash",              "description": "Fast in-memory cache and pub/sub for agents. Great for shared state across models.", "category": "Database",    "installs": 12800, "requiresKey": False, "icon": "⚡", "command": "npx @upstash/mcp-server-redis"},
    {"id": "playwright",         "name": "Playwright",          "author": "executeautomation",    "description": "Browser automation using Playwright. Supports Chromium, Firefox, and WebKit.", "category": "Browser",        "installs": 14200, "requiresKey": False, "icon": "🌐", "command": "npx @executeautomation/playwright-mcp-server"},
    {"id": "aws-kb",             "name": "AWS Knowledge Base",  "author": "modelcontextprotocol", "description": "Retrieve data from AWS Knowledge Base via Bedrock Agent Runtime.", "category": "Storage",                    "installs": 8900,  "requiresKey": True,  "icon": "☁️", "command": "npx @modelcontextprotocol/server-aws-kb-retrieval"},
    {"id": "gdrive",             "name": "Google Drive",        "author": "modelcontextprotocol", "description": "Browse, read, and search files stored in Google Drive.", "category": "Storage",                            "installs": 19300, "requiresKey": True,  "icon": "📁", "command": "npx @modelcontextprotocol/server-gdrive"},
    {"id": "gitlab",             "name": "GitLab",              "author": "modelcontextprotocol", "description": "Manage GitLab repos, merge requests, issues, and CI/CD pipelines.", "category": "Dev Tools",                "installs": 11200, "requiresKey": True,  "icon": "🦊", "command": "npx @modelcontextprotocol/server-gitlab"},
    {"id": "linear",             "name": "Linear",              "author": "modelcontextprotocol", "description": "Create and manage Linear issues, projects, and cycles for engineering teams.", "category": "Dev Tools",        "installs": 9800,  "requiresKey": True,  "icon": "📋", "command": "npx @modelcontextprotocol/server-linear"},
    {"id": "sentry",             "name": "Sentry",              "author": "modelcontextprotocol", "description": "Query and triage Sentry error reports, issues, and performance data.", "category": "Dev Tools",                "installs": 7600,  "requiresKey": True,  "icon": "🔥", "command": "npx @modelcontextprotocol/server-sentry"},
    {"id": "everart",            "name": "EverArt",             "author": "modelcontextprotocol", "description": "Generate images using EverArt AI models directly from your agent.", "category": "Tools",                     "installs": 5400,  "requiresKey": True,  "icon": "🎨", "command": "npx @modelcontextprotocol/server-everart"},
    {"id": "sequentialthinking", "name": "Sequential Thinking", "author": "modelcontextprotocol", "description": "Dynamic and reflective problem-solving through structured thought sequences.", "category": "Tools",             "installs": 31000, "requiresKey": False, "icon": "🧠", "command": "npx @modelcontextprotocol/server-sequential-thinking"},
    {"id": "time",               "name": "Time",                "author": "modelcontextprotocol", "description": "Get current time and perform timezone conversions across the world.", "category": "Tools",                     "installs": 22100, "requiresKey": False, "icon": "🕐", "command": "npx @modelcontextprotocol/server-time"},
    {"id": "mongodb",            "name": "MongoDB",             "author": "mongodb",              "description": "Query, insert, and manage MongoDB databases and collections.", "category": "Database",                        "installs": 10500, "requiresKey": False, "icon": "🍃", "command": "npx @mongodb-js/mongodb-mcp-server"},
    {"id": "mysql",              "name": "MySQL",               "author": "benborla",             "description": "Execute queries and manage MySQL/MariaDB databases.", "category": "Database",                               "installs": 8300,  "requiresKey": False, "icon": "🐬", "command": "npx @benborla29/mcp-server-mysql"},
    {"id": "notion",             "name": "Notion",              "author": "makenotion",           "description": "Read and write Notion pages, databases, and blocks.", "category": "Tools",                                  "installs": 16700, "requiresKey": True,  "icon": "📓", "command": "npx @makenotion/notion-mcp-server"},
    {"id": "discord",            "name": "Discord",             "author": "community",            "description": "Send messages and interact with Discord servers and channels.", "category": "Communication",                  "installs": 9100,  "requiresKey": True,  "icon": "💬", "command": "npx discord-mcp-server"},
    {"id": "twitter",            "name": "Twitter / X",         "author": "community",            "description": "Post tweets, search content, and interact with the Twitter/X API.", "category": "Communication",              "installs": 7800,  "requiresKey": True,  "icon": "🐦", "command": "npx twitter-mcp-server"},
    {"id": "jira",               "name": "Jira",                "author": "community",            "description": "Create, update, and search Jira issues and projects.", "category": "Dev Tools",                             "installs": 12400, "requiresKey": True,  "icon": "📋", "command": "npx jira-mcp-server"},
    {"id": "kubernetes",         "name": "Kubernetes",          "author": "community",            "description": "Manage Kubernetes clusters, pods, deployments, and services.", "category": "Dev Tools",                      "installs": 6700,  "requiresKey": False, "icon": "⎈",  "command": "npx kubernetes-mcp-server"},
    {"id": "docker",             "name": "Docker",              "author": "community",            "description": "Manage Docker containers, images, and compose stacks.", "category": "Dev Tools",                            "installs": 8900,  "requiresKey": False, "icon": "🐳", "command": "npx docker-mcp-server"},
    {"id": "openai",             "name": "OpenAI",              "author": "community",            "description": "Call OpenAI models (GPT-4, DALL-E, Whisper) from within your agents.", "category": "Tools",                  "installs": 14300, "requiresKey": True,  "icon": "🤖", "command": "npx openai-mcp-server"},
]


# ─── Request Models ───────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    model_id: str
    mcp_id: str
    api_key: Optional[str] = None

class DisconnectRequest(BaseModel):
    model_id: str
    mcp_id: str


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "MCP Marketplace API running"}


@app.get("/models")
def get_models():
    registry = load_registry()
    return [{**m, "tools": registry.get(m["id"], [])} for m in MOCK_MODELS]


@app.get("/catalog")
def get_catalog(
    q: str = Query(default=""),
    category: str = Query(default=""),
    page: int = Query(default=1),
    pageSize: int = Query(default=50),
):
    """
    Returns MCP catalog. Tries Smithery live API first, falls back to local list.
    """
    # Try Smithery live
    smithery_result = fetch_smithery_catalog(q=q, page=page, page_size=pageSize)

    if smithery_result and smithery_result["servers"]:
        servers = smithery_result["servers"]
        # Apply category filter if provided
        if category and category != "All":
            servers = [s for s in servers if s["category"] == category]
        return {
            "source": "smithery",
            "total": smithery_result["total"],
            "servers": servers,
        }

    # Fallback to local catalog
    print("[Catalog] Falling back to local catalog")
    results = FALLBACK_CATALOG
    if q:
        q_lower = q.lower()
        results = [m for m in results if q_lower in m["name"].lower() or q_lower in m["description"].lower()]
    if category and category != "All":
        results = [m for m in results if m["category"] == category]

    return {
        "source": "fallback",
        "total": len(results),
        "servers": results,
    }


@app.post("/connect")
def connect_tool(req: ConnectRequest):
    model = next((m for m in MOCK_MODELS if m["id"] == req.model_id), None)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{req.model_id}' not found")

    # Look up in fallback catalog or accept any mcp_id from Smithery
    mcp = next((m for m in FALLBACK_CATALOG if m["id"] == req.mcp_id), None)
    # If not in fallback, create a minimal entry (came from Smithery live)
    if not mcp:
        mcp = {"id": req.mcp_id, "name": req.mcp_id, "command": f"npx {req.mcp_id}"}

    registry = load_registry()
    tools = registry.get(req.model_id, [])
    if req.mcp_id not in tools:
        tools.append(req.mcp_id)
    registry[req.model_id] = tools
    save_registry(registry)

    # Attempt to start the MCP process
    processes = load_processes()
    process_status = "already_running"

    if req.mcp_id not in processes:
        try:
            env = os.environ.copy()
            if req.api_key:
                key_map = {
                    "brave-search": "BRAVE_API_KEY",
                    "github": "GITHUB_TOKEN",
                    "slack": "SLACK_BOT_TOKEN",
                    "code-exec": "E2B_API_KEY",
                    "google-maps": "GOOGLE_MAPS_API_KEY",
                }
                env_key = key_map.get(req.mcp_id, "MCP_API_KEY")
                env[env_key] = req.api_key

            proc = subprocess.Popen(
                mcp["command"].split(),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes[req.mcp_id] = {"pid": proc.pid, "command": mcp["command"], "status": "running", "mcp_name": mcp["name"]}
            save_processes(processes)
            process_status = "started"

        except FileNotFoundError:
            processes[req.mcp_id] = {"pid": None, "command": mcp.get("command", ""), "status": "failed_no_npx", "mcp_name": mcp["name"]}
            save_processes(processes)
            process_status = "registered_only_npx_missing"

    return {"success": True, "model": model["name"], "tool": mcp["name"], "process_status": process_status, "registry": registry}


@app.post("/disconnect")
def disconnect_tool(req: DisconnectRequest):
    registry = load_registry()
    tools = registry.get(req.model_id, [])
    if req.mcp_id in tools:
        tools.remove(req.mcp_id)
    registry[req.model_id] = tools
    save_registry(registry)

    still_used = any(req.mcp_id in v for k, v in registry.items() if k != req.model_id)
    if not still_used:
        processes = load_processes()
        proc_info = processes.pop(req.mcp_id, None)
        if proc_info and proc_info.get("pid"):
            try:
                os.kill(proc_info["pid"], 15)
            except ProcessLookupError:
                pass
        save_processes(processes)

    return {"success": True, "registry": registry}


@app.get("/registry")
def get_registry():
    return load_registry()


@app.get("/processes")
def get_processes():
    return load_processes()


@app.delete("/processes/{mcp_id}")
def kill_process(mcp_id: str):
    processes = load_processes()
    proc_info = processes.pop(mcp_id, None)
    if not proc_info:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc_info.get("pid"):
        try:
            os.kill(proc_info["pid"], 9)
        except ProcessLookupError:
            pass
    save_processes(processes)
    return {"success": True, "killed": mcp_id}
