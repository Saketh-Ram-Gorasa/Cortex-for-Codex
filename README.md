<div align="center">
<img src="logo%20kit/Group%202.png" alt="SecondCortex" width="512">

<h1>SecondCortex: AI-Powered Developer Memory System</h1>

<h3>Capture Context · Resurrect Workspaces · Remember Everything</h3>

<p>
    <img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white" alt="TypeScript">
    <img src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Next.js-000000?style=flat&logo=next.js&logoColor=white" alt="Next.js">
    <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <br>
    <a href="https://github.com/SuhaanSyed/SecondCortex"><img src="https://img.shields.io/badge/GitHub-Repository-black?style=flat&logo=github&logoColor=white" alt="GitHub"></a>
    <a href="https://marketplace.visualstudio.com/items?itemName=cortex-team.secondcortex"><img src="https://img.shields.io/badge/VS%20Code-Extension-007ACC?style=flat&logo=visual-studio-code&logoColor=white" alt="VS Code"></a>
</p>

**English** | [中文](READMECN.md)

</div>

---

> **SecondCortex** is an AI-powered developer memory system that captures your coding context, protects sensitive data locally, and helps you resume complex work in seconds. Never lose development context again.

## 🎯 The Problem

You're deep in a complex feature after hours of work. You close your laptop. Days later, you return. The context is gone.

- _"What branch was I on?"_
- _"What was the git conflict I was debugging?"_
- _"How did I solve this 3 months ago?"_
- _"What terminal commands was I running?"_

Without this context, developers lose 30-60 minutes per context switch. With distributed teams and long-running projects, this multiplies quickly.

**SecondCortex solves this** with:
- ✅ **Automatic context capture** — Every file, branch, terminal output, and decision is logged
- ✅ **Privacy-first redaction** — Sensitive data (passwords, keys, SSNs) is scrubbed locally before leaving your machine
- ✅ **Semantic search** — Ask natural-language questions and get answers from your work history
- ✅ **Workspace resurrection** — Restore your exact IDE state with a single click
- ✅ **Decision archaeology** — Understand _why_ code was written, not just _what_ it does
- ✅ **Team collaboration** — Share snapshots and insights across your development team

---

## ✨ Key Features

🧠 **Developer Memory Graph**
- Automatic capture of code snapshots, git history, terminal commands, and decisions
- Semantic search across months of context using vector embeddings
- Privacy-first: sensitive values are redacted locally before backend sync

🔄 **Workspace Resurrection Engine**
- Restore your exact IDE state: open files, branch, terminal intent
- Reconstructed in seconds, not hours
- One-click "resume" from any prior snapshot

🛡️ **Semantic Firewall**
- AST-based redaction for code secrets (API keys, credentials, PII)
- Regex pattern matching for payment cards, SSNs, emails (optional)
- All redaction happens locally—backend never sees raw secrets

📊 **AI-Powered Dashboard**
- Real-time team activity timeline
- Project evolution tracking
- Snapshot summaries and evolution insights
- Git decision archaeology with confidence scoring

🔍 **Decision Archaeology**
- Hover over any function to see historical reasoning
- Linked to original commits, snapshots, and terminal context
- Understand contradictions and disproof in incident response

🤖 **Multi-Agent Orchestration**
- **Retriever Agent**: Decides whether to add/update/delete snapshots
- **Planner Agent**: Decomposes user queries into semantic searches
- **Executor Agent**: Synthesizes answers with confidence scoring
- **Simulator Agent**: Pre-flight safety analysis for workspace resurrection

🔌 **Model Context Protocol (MCP)**
- Expose your private developer memory to external AI clients
- Custom `search_memory()` tool for integration with other AI systems
- Secure API key management and rate limiting

📱 **Multi-Channel Integration**
- Chat directly in VS Code sidebar
- Web dashboard for team insights
- CLI tools for automation and scripting
- MCP server for external agent access

🌍 **Cross-Platform Support**
- VS Code extension (Windows, macOS, Linux)
- Self-hosted FastAPI backend
- Docker deployment with docker-compose
- Fully privacy-preserving (all sensitive data stays on-device)

---

## 🏗️ Architecture

SecondCortex is built as a distributed system with three main layers:

### Layer 1: VS Code Extension (TypeScript)
- **Event Capture**: Monitors editor events, terminal output, git changes
- **Debouncer**: Time-gates events to reduce noise (configurable intervals)
- **Semantic Firewall**: AST-based scrubbing of secrets before leaving your machine
- **Snapshot Cache**: Queues snapshots for reliable backend delivery
- **Decision Archaeology**: Hover analysis linking code to historical context
- **Workspace Resurrector**: Executes commands to restore your prior IDE state

### Layer 2: FastAPI Backend (Python)
- **Auth Layer**: JWT verification + MCP API key management
- **Retriever Agent**: Decides ADD/UPDATE/DELETE/NOOP on incoming snapshots
- **Planner Agent**: Interprets user queries and generates search decompositions
- **Executor Agent**: Synthesizes answers from retrieved context with confidence scoring
- **Simulator Agent**: Pre-flight safety analysis (git conflicts, risk levels)
- **Services Layer**: VectorDB, Rate Limiter, LLM Client, Git Ingest, Auth

### Layer 3: Frontend (Next.js + React)
- **Dashboard**: Team timeline, project evolution, snapshot insights
- **Shadow Graph**: Interactive visualization of context relationships
- **Incident Debug Graph**: Three-column view for incident archaeology
- **Chat Interface**: Real-time conversation with agent

### Storage & Integrations
- **ChromaDB**: Vector database for semantic search (SQLite backend)
- **Git API**: Retroactive commit mining and PR ingestion
- **LLM APIs**: OpenAI (embeddings), Groq (fast inference)
- **Auth DB**: User sessions, MCP keys, chat history

```
┌─────────────────────────────┐
│   VS Code Extension         │
│  (Context Capture)          │
├─────────────────────────────┤
│   Semantic Firewall         │
│  (Local Redaction)          │
├─────────────────────────────┤
│                             │
└──────────────┬──────────────┘
               │ HTTPS + JWT
               ↓
┌────────────────────────────────┐
│    FastAPI Backend             │
│  (Multi-Agent Orchestration)   │
├────────────────────────────────┤
│  Retriever | Planner |         │
│  Executor  | Simulator         │
├────────────────────────────────┤
└──────────────┬─────────────────┘
               │
        ┌──────┴──────┐
        ↓             ↓
    ChromaDB      Git API
    (Search)      (History)
```

---

## 🚀 Quick Start

### Prerequisites
- **Node.js** 18+ (for VS Code extension and web frontend)
- **Python** 3.10+ (for backend)
- **Docker** & **Docker Compose** (recommended for backend)
- **VS Code** 1.80+ (for extension)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/SuhaanSyed/SecondCortex.git
cd SecondCortex

# Start backend + frontend + database
docker compose up -d

# Backend available at http://localhost:8000
# Frontend available at http://localhost:3000
# MCP server runs on localhost:5000
```

See [Docker Setup](docs/docker.md) for advanced configuration.

### Option 2: Local Development

#### Backend Setup
```bash
cd secondcortex-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start backend (defaults to http://localhost:8000)
python main.py
```

#### Frontend Setup
```bash
cd secondcortex-web

# Install dependencies
npm install

# Start development server (defaults to http://localhost:3000)
npm run dev
```

#### VS Code Extension Setup
```bash
cd secondcortex-vscode

# Install dependencies
npm install

# Build extension
npm run build

# For development with debugging:
# Open in VS Code, press F5 to start debug instance
```

### Configure the Extension

1. **Install VS Code Extension**
   - From Marketplace: search for "SecondCortex"
   - Or load locally: `code --install-extension ./secondcortex-vscode`

2. **Authenticate Backend**
   - Open VS Code Command Palette (`Ctrl+Shift+P`)
   - Run: `SecondCortex: Authenticate`
   - Enter backend URL (e.g., `http://localhost:8000`)
   - Provide your API token or create new user account

3. **Configure Redaction Rules** (Optional)
   - Open settings: `Ctrl+,` → Search "SecondCortex"
   - Configure sensitivity levels (High/Medium/Low)
   - Add custom regex patterns for sensitive values

4. **Start Capturing**
   - Open a project folder in VS Code
   - Extension automatically starts capturing context
   - View captured snapshots in the SecondCortex sidebar

---

## 📊 Usage Examples

### Example 1: Resume a Complex Feature After a Break

**Scenario**: You were debugging a database indexing issue. After two days away, you return.

```
👤 Me: "What was I working on with the database?"

🤖 SecondCortex:
  ✅ Found 8 snapshots from last session
  📋 Context:
     - Branch: fix/db-indexing-performance
     - Terminal: $ psql -c "CREATE INDEX idx_user_projects..."
     - Files open: schema.sql, migration.py, test_perf.py
     - Error: "Index creation timeout on 5M rows"
  
  💡 Decision: In snapshot 2026-03-15 14:23, you discovered compound indices 
     reduced query time from 850ms to 12ms. Solution: Use CONCURRENTLY flag.

[Click: Restore Workspace] → Opens exact files, branch, terminal history
```

### Example 2: Search Your Work History

```
👤 Me: "Show me all incidents where we crashed the API gateway"

🤖 SecondCortex (via Planner + Executor agents):
  🔍 Searching: "api gateway crash", "gateway error", "503 timeout"
  📍 Found 3 related snapshots:
     1. 2026-02-12: Rate limiter misconfiguration → Fixed with circuit breaker
     2. 2026-02-28: Memory leak in event loop → Fixed with pooling
     3. 2026-03-10: DNS cache TTL too high → Fixed with shorter TTL
  
  📊 Pattern: All three involved external service timeout handling
  💡 Recommendation: Add integration tests for service degradation scenarios
```

### Example 3: Team Collaboration

Alice opens the SecondCortex dashboard and sees:

```
📊 Team Timeline (Last 7 days)
├─ Alice: Fixed OAuth token refresh logic
│  └─ Branch: fix/oauth-refresh → 3 snapshots → 4 files changed
├─ Bob: Added webhook retry mechanism
│  └─ Branch: feat/webhook-retry → 8 snapshots → 2 files changed
├─ Charlie: Refactored search service
│  └─ Branch: refactor/search-service → 12 snapshots → 5 files changed
└─ David: Deployed schema migration v3.2
   └─ Branch: release/3.2 → Production snapshot

📈 Project Evolution:
   Week 1: 120 commits, 45 files changed, 3 hotfixes
   Week 2: 156 commits, 62 files changed, 1 hotfix (improving!)
   
🎯 Next: Click any snapshot to see full context, diffs, and decisions
```

---

## 🔒 Privacy & Security

### How SecondCortex Protects Your Data

**Data Flow:**
1. ✅ VS Code Extension captures context locally
2. ✅ **Semantic Firewall scrubs secrets** (API keys, credentials, PII)
3. ✅ Safe snapshot sent to backend over HTTPS
4. ✅ Backend stores encrypted data (ChromaDB)
5. ✅ Vectors are searchable but non-reversible

**What Gets Redacted:**
- AWS keys, GitHub tokens, database passwords
- Payment card numbers (PCI compliance)
- Social Security Numbers, email addresses (optional)
- Custom patterns (user-defined regex)

**What You Control:**
- Choose backend location (self-hosted or cloud)
- Define redaction sensitivity (High/Medium/Low)
- Add custom sensitive patterns
- Export or delete your data anytime
- Fine-grained access controls per team member

**OpenAI Model Privacy:**
- Embeddings use `text-embedding-3-small` from OpenAI
- Text is sent to OpenAI only for embedding (never for model inference)
- Configure to use local embeddings or alternative providers

See [Security Documentation](docs/security.md) for detailed threat model and compliance (SOC2, HIPAA considerations).

---

## 📦 Installation Options

### VS Code Marketplace (Easiest)

1. Open VS Code → Extensions Marketplace
2. Search for "SecondCortex"
3. Click Install
4. Reload VS Code

### Manual Installation

```bash
# Clone and build locally
git clone https://github.com/SuhaanSyed/SecondCortex.git
cd secondcortex-vscode
npm install
npm run build

# Install locally
code --install-extension ./dist/secondcortex-*.vsix
```

### Development Mode

```bash
cd secondcortex-vscode
npm install

# Opens new VS Code window with extension running
npm run watch  # Auto-rebuild on changes
# or press F5 in VS Code to launch debug instance
```

---

## ⚙️ Configuration

### Backend Configuration

**Environment Variables:**
```bash
# Backend
Backend_URL=http://localhost:8000
BACKEND_JWT_SECRET=your-secret-key
BACKEND_DB_PATH=./chroma_db

# LLM Providers
GROQ_API_KEY=your-groq-api-key
OPENAI_API_KEY=your-openai-api-key

# Feature Flags
MCP_EXTERNAL_INGESTION_ENABLED=true
MCP_EXTERNAL_DOCUMENT_ENABLED=false
```

See [Configuration Guide](docs/configuration.md) for full reference.

### Extension Configuration

Open VS Code Settings (`Ctrl+,`), search "SecondCortex":

| Setting | Default | Description |
|---------|---------|-------------|
| `secondcortex.backend.url` | `http://localhost:8000` | Backend API URL |
| `secondcortex.redaction.level` | `medium` | Sensitivity: `high`, `medium`, `low` |
| `secondcortex.capture.interval` | `5000` | Snapshot frequency (ms) |
| `secondcortex.git.enabled` | `true` | Enable git history ingestion |
| `secondcortex.mcp.port` | `5000` | MCP server port |

---

## 🔌 MCP Server Integration

SecondCortex exposes a **Model Context Protocol (MCP)** server that allows external AI clients to query your private developer memory.

### Enable MCP Server

```bash
# In VS Code settings, enable:
secondcortex.mcp.enabled: true
secondcortex.mcp.port: 5000
```

### Query from External Agents

```python
import asyncio
from mcp.client.session import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def query_memory():
    async with stdio_client(
        StdioServerParameters(
            command="npm",
            args=["exec", "secondcortex-mcp-server"]
        )
    ) as (read, write):
        session = ClientSession(read, write)
        
        # Query your memory
        result = await session.call_tool(
            "search_memory",
            {
                "query": "database indexing performance",
                "limit": 5
            }
        )
        
        print(result)

asyncio.run(query_memory())
```

See [MCP Integration Guide](docs/mcp-integration.md) for details.

---

## 🛠️ Development

### Project Structure

```
.
├── secondcortex-vscode/        # VS Code extension (TypeScript)
│   ├── src/
│   │   ├── extension.ts        # Extension entry point
│   │   ├── capture/            # Event capture & debouncing
│   │   ├── firewall/           # Semantic redaction
│   │   ├── sidebar/            # Chat & UI
│   │   └── services/           # Backend client, auth
│   └── package.json
│
├── secondcortex-backend/       # FastAPI backend (Python)
│   ├── main.py                 # Entry point
│   ├── agents/                 # Retriever, Planner, Executor, Simulator
│   ├── services/               # VectorDB, LLM, Auth
│   ├── models/                 # Data models & schemas
│   ├── database/               # ChromaDB integration
│   └── requirements.txt
│
├── secondcortex-web/           # Next.js frontend (TypeScript)
│   ├── src/
│   │   ├── app/                # Next.js app router
│   │   ├── components/         # React components
│   │   │   ├── Dashboard.tsx   # Main dashboard
│   │   │   ├── Timeline.tsx    # Snapshot timeline
│   │   │   └── Chat.tsx        # Chat interface
│   │   └── lib/                # Utilities, API clients
│   └── package.json
│
├── docker-compose.yml           # Local orchestration
└── docs/                        # Documentation
    ├── docker.md
    ├── configuration.md
    ├── security.md
    ├── mcp-integration.md
    └── architecture.md
```

### Contributing

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feat/your-feature`
3. **Make** your changes and add tests
4. **Run** linting: `npm run lint` (extension/web), `pylint` (backend)
5. **Commit** with clear messages: `git commit -m "feat: add new feature"`
6. **Push** and create a **Pull Request**

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Local Development Workflow

```bash
# Terminal 1: Backend
cd secondcortex-backend
python main.py

# Terminal 2: Frontend
cd secondcortex-web
npm run dev  # Runs on http://localhost:3000

# Terminal 3: VS Code Extension
cd secondcortex-vscode
npm run watch
# Then press F5 in VS Code to launch debug instance
```

### Testing

```bash
# Backend
cd secondcortex-backend
pytest tests/ -v

# Extension & Web
cd secondcortex-vscode
npm test

cd secondcortex-web
npm test
```

---

## 📚 Documentation

| Topic | Location |
|-------|----------|
| Full Architecture | [docs/architecture.md](docs/architecture.md) |
| Docker & Deployment | [docs/docker.md](docs/docker.md) |
| Configuration Reference | [docs/configuration.md](docs/configuration.md) |
| Security & Privacy | [docs/security.md](docs/security.md) |
| MCP Integration | [docs/mcp-integration.md](docs/mcp-integration.md) |
| API Reference | [docs/api.md](docs/api.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |

---

## 🤝 Community

**Have questions?** Open an issue or discussion on [GitHub](https://github.com/SuhaanSyed/SecondCortex/issues).

**Want to contribute?** Read [CONTRIBUTING.md](CONTRIBUTING.md) and submit a PR!

**Report Security Issues?** Email: `security@secondcortex.dev` (responsible disclosure)

---

## 📊 Status

- ✅ **v0.3.1** Released — HAX transparency, Incident packets, Document ingestion
- 🔄 **In Development** — Team collaboration features, Mobile support, Analytics
- 🚀 **Roadmap** — End-to-end encryption, GDPR compliance, Offline mode

See [ROADMAP.md](ROADMAP.md) for detailed plans.

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ by the SecondCortex team**

[⭐ Star on GitHub](https://github.com/SuhaanSyed/SecondCortex) · [📧 Email us](mailto:team@secondcortex.dev) · [🐦 Follow us](https://twitter.com/secondcortex)

</div>
