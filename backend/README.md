<div align="center">

# 🎬 AI Content Studio

### Multi-Agent YouTube Content Creation Platform

*Built for the Google Cloud Rapid Agent Hackathon*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-blue?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)](https://python.org)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-4285F4?style=for-the-badge&logo=google)](https://aistudio.google.com)
[![Qwen](https://img.shields.io/badge/LLM-Qwen--Plus%20%2F%20Max-orange?style=for-the-badge)](https://qwenlm.github.io)

---

**AI Content Studio** is a production-grade, multi-agent AI platform that transforms a single topic into a complete, publish-ready YouTube video — with full Human-in-the-Loop control at every critical decision point.

From research to script to SEO to YouTube upload, every step is handled by a specialized AI agent, coordinated by a stateful LangGraph workflow that persists across server restarts via PostgreSQL checkpointing.

[📖 Architecture](docs/architecture.md) · [⚡ Content Workflow](docs/content_workflow.md) · [🚀 Upload Workflow](docs/upload_workflow.md) · [🗄️ Database](docs/database_schema.md) · [🔌 MCP Integration](docs/mcp_integration.md)

</div>

---

## ✨ Features

- **Multi-Agent Pipeline** — Six specialized AI agents working in sequence, each with a single responsibility
- **Human-in-the-Loop (HITL)** — Workflow pauses at research approval and idea selection; resumes without data loss
- **Creator Profile Intelligence** — LLM analyzes your real YouTube channel to build a profile; every agent personalizes output to your niche, audience, and style
- **Real YouTube Integration** — OAuth2 + PKCE flow connects your channel; videos and thumbnails upload directly via Data API v3
- **Persistent Checkpointing** — PostgreSQL-backed LangGraph state survives server restarts; HITL sessions never lost
- **Separate Publishing Pipeline** — Content generation and publishing are decoupled; SEO is generated at upload time, not content time
- **Multi-LLM Support** — Gemini 2.5 Flash (default) and Qwen via a unified provider interface; switch with one env var
- **Generation History** — Every workflow run saved to DB; browse, reload, and republish past content
- **Upload History** — Full audit trail of every YouTube publish attempt
- **Plan-Based Model Routing** — Normal/Pro/Plus plans map to the right model tier automatically
- **Dual Auth** — Email/password + Google OAuth; JWT access + refresh token pattern
- **Production-Ready** — CORS, session middleware, Pydantic validation, structured error handling, 30-check health suite

---

## 🤖 LLM Provider Architecture

AI Content Studio uses a **unified provider interface** — all LLM calls go through a single entry point regardless of which model is active.

```
agents / routes
      │
      ▼
app/services/llm_provider.py   ← single entry point
      │
      ├── model="gemini"  ──▶  gemini_service.py  ──▶  Gemini 2.5 Flash
      │
      └── model="qwen"    ──▶  qwen_service.py    ──▶  Qwen-Plus / Qwen-Max
                                                        via DashScope
```

### Switching providers

Set `DEFAULT_MODEL` in `.env`:

```env
DEFAULT_MODEL=gemini   # ← default (Google Gemini 2.5 Flash)
DEFAULT_MODEL=qwen     # ← Alibaba Qwen via DashScope
```

No code changes needed. Restart the server and all agents switch automatically.

### Per-request model override

Any API endpoint that generates content accepts an optional `model` field:

```json
// Use Gemini (or omit — same result since Gemini is default)
{ "topic": "Python async explained", "model": "gemini" }

// Use Qwen for this specific request only
{ "topic": "Python async explained", "model": "qwen" }
```

### Supported model values

| Value | Provider | Notes |
|-------|----------|-------|
| `"gemini"` | Google Gemini 2.5 Flash | **Default** — fast, capable, free tier available |
| `"qwen"` | Alibaba Qwen-Plus | Good balance of speed and quality |
| `"qwen-plus"` | Alibaba Qwen-Plus | Same as `"qwen"` |
| `"qwen-max"` | Alibaba Qwen-Max | Highest quality Qwen; used for heavy tasks in Plus plan |

### Adding a new provider

1. Create `app/services/<name>_service.py` with `generate_response(prompt: str) -> str`
2. Add detection logic in `llm_provider._resolve_provider()`
3. Add a dispatch branch in `llm_provider._dispatch()`
4. Add key validation in `llm_provider._check_api_key()`
5. Update `.env.example` and this README

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph Client["Client (React Frontend)"]
        UI[User Interface]
    end

    subgraph API["FastAPI Backend"]
        Auth[Auth Routes]
        YT[YouTube Routes]
        WF[Workflow Routes]
        CP[Creator Profile Routes]
    end

    subgraph Agents["Agent Layer"]
        RA[Research Agent]
        VIA[Video Idea Agent]
        SA[Script Agent]
        TA[Thumbnail Agent]
        SEOA[SEO Agent]
    end

    subgraph LLMLayer["LLM Provider Layer"]
        LLP[llm_provider.py]
        GEM[Gemini 2.5 Flash]
        QWN[Qwen-Plus / Max]
    end

    subgraph Graphs["LangGraph Orchestration"]
        CG[Content Generation Graph]
        UG[Upload Graph]
    end

    subgraph Storage["PostgreSQL"]
        Users[(users)]
        Profiles[(creator_profiles)]
        Gens[(generations)]
        Uploads[(upload_records)]
        Checkpoints[(langgraph_checkpoints)]
    end

    subgraph YouTube["YouTube Integration"]
        YTAPI[Data API v3]
    end

    UI --> API
    WF --> CG
    WF --> UG
    CG --> Agents
    Agents --> LLP
    LLP --> GEM
    LLP --> QWN
    CG --> Checkpoints
    UG --> YTAPI
    CG --> Gens
    UG --> Uploads
```

---

## ⚡ Content Generation Workflow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant LangGraph
    participant Agents
    participant DB

    User->>API: POST /workflow/run {topic}
    API->>DB: Create generation record (pending)
    API->>LangGraph: invoke graph
    LangGraph->>Agents: Research Agent
    Agents-->>LangGraph: research output
    LangGraph->>DB: save research
    LangGraph-->>API: PAUSE (human_approval)
    API-->>User: {thread_id, research}

    User->>API: POST /workflow/resume {approved: true}
    LangGraph->>Agents: Video Idea Agent (5 ideas)
    LangGraph-->>API: PAUSE (idea_selection)
    API-->>User: {ideas: [...]}

    User->>API: POST /workflow/select-idea {selected_idea}
    LangGraph->>Agents: Script Agent → Critic → Thumbnail
    LangGraph->>DB: save generation (completed)
    API-->>User: {script, thumbnail, generation_id}
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | FastAPI 0.115 | REST API, Swagger UI, dependency injection |
| **Orchestration** | LangGraph | Stateful multi-agent graph with HITL |
| **Checkpointing** | langgraph-checkpoint-postgres | HITL state persistence across restarts |
| **LLM (default)** | Gemini 2.5 Flash | Fast, capable; free tier at aistudio.google.com |
| **LLM (alt)** | Qwen-Plus / Qwen-Max | Via DashScope; switchable with DEFAULT_MODEL=qwen |
| **LLM Interface** | llm_provider.py | Unified provider abstraction; zero agent coupling |
| **Database** | PostgreSQL 16 | All application + checkpoint state |
| **ORM** | SQLAlchemy 2.0 | Models, migrations, session management |
| **Auth** | JWT + Google OAuth2 | Dual auth with refresh tokens |
| **YouTube** | Data API v3 + OAuth2 PKCE | Channel connection, video upload, thumbnail upload |
| **Validation** | Pydantic v2 | Request/response models, LLM output validation |

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── agents/              # AI agents (one per responsibility)
│   │   ├── research_agent.py
│   │   ├── video_idea_agent.py
│   │   ├── script_agent.py
│   │   ├── thumbnail_agent.py
│   │   ├── seo_agent.py
│   │   ├── critic_agent.py
│   │   ├── content_gap_agent.py
│   │   ├── creator_profile_agent.py
│   │   └── youtube_research_agent.py
│   ├── graph/               # LangGraph workflow definitions
│   │   ├── workflow.py          # Content generation pipeline
│   │   ├── upload_workflow.py   # Publishing pipeline
│   │   ├── state.py             # TypedDict state schemas
│   │   └── checkpointer.py      # PostgreSQL checkpointer singleton
│   ├── services/            # Business logic + LLM providers
│   │   ├── llm_provider.py      # ← Unified LLM interface (all calls go here)
│   │   ├── gemini_service.py    # Gemini 2.5 Flash implementation
│   │   ├── qwen_service.py      # Qwen via DashScope implementation
│   │   └── model_router.py      # Maps (plan, task) → model identifier
│   ├── models/              # SQLAlchemy ORM models
│   ├── routes/              # FastAPI route handlers
│   ├── mcp/                 # MCP integrations (MongoDB, Elastic)
│   ├── memory/              # Creator memory service layer
│   ├── core/                # Security, exceptions
│   ├── dependencies/        # FastAPI dependencies (auth)
│   └── prompts/             # Prompt templates
├── test_llm_providers.py    # Smoke test for both LLM providers
├── check.py                 # 30-check automated health suite
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- A **Gemini API key** (free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) **or** a **Qwen API key** ([dashscope-intl.aliyuncs.com](https://dashscope-intl.aliyuncs.com))
- A [Google Cloud project](https://console.cloud.google.com) with YouTube Data API v3 enabled

### 1. Clone

```bash
git clone https://github.com/your-username/ai-content-studio.git
cd ai-content-studio/backend
```

### 2. Virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — minimum required fields:

```env
# LLM — choose one (or both)
DEFAULT_MODEL=gemini
GEMINI_API_KEY=your_gemini_api_key_here
QWEN_API_KEY=your_qwen_api_key_here   # optional if using Gemini only

# Database
DATABASE_URl=postgresql://postgres:password@localhost:5432/ai_content_studio

# Auth
SECRET_KEY_FOR_LOGIN=your_64_char_hex_secret
SECRET_KEY=your_session_secret
ALGORITHM=HS256

# Google OAuth + YouTube
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/youtube/callback
```

### 5. Create database & run migrations

```bash
# In psql: CREATE DATABASE ai_content_studio;
python migrate.py
```

### 6. Test LLM providers

```bash
python test_llm_providers.py
```

Expected output:
```
✅ Gemini response: LLM provider test passed.
✅ Qwen response: LLM provider test passed.
✅ Default response: LLM provider test passed.
✅ model_router working (provider: gemini)
✅ Correctly raised ValueError: Unsupported model 'gpt-99'...
6/6 tests passed
```

### 7. Start the server

```bash
uvicorn app.main:app --reload
```

### 8. Verify everything works

```bash
python check.py
# Expected: 30 passed, 0 failed
```

### 9. Open Swagger UI

```
http://localhost:8000/docs
```

Click **Authorize** → paste your `access_token` from `POST /auth/login`.

---

## 🔑 Getting API Keys

### Gemini (Recommended — Free)
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with Google
3. Click **Create API Key**
4. Copy the key into `.env` as `GEMINI_API_KEY=...`
5. Make sure `DEFAULT_MODEL=gemini` in `.env`

> ⚠️ **Important**: The key must be on a **single line** with no backslash (`\`) at the end.

### Qwen (Alternative)
1. Go to [dashscope-intl.aliyuncs.com](https://dashscope-intl.aliyuncs.com)
2. Register → Console → API Keys → Create
3. Copy the key into `.env` as `QWEN_API_KEY=...`
4. Set `DEFAULT_MODEL=qwen` to make Qwen the default

---

## 🔑 Google Cloud Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. **APIs & Services → Credentials** → Create **OAuth 2.0 Client ID** (Web application)
4. Add to **Authorized redirect URIs**:
   ```
   http://localhost:8000/youtube/callback
   http://localhost:8000/auth/google/callback
   ```
5. **OAuth consent screen → Test users** → add your Gmail account

---

## 📡 API Overview

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/signup` | Register with email + password |
| POST | `/auth/login` | Login → JWT access + refresh token |
| GET | `/auth/me` | Current authenticated user |

### Content Generation Workflow
| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/workflow/run` | `{topic, plan?, model?}` | Start pipeline → research + thread_id |
| POST | `/workflow/resume` | `{thread_id, approved}` | Approve research → ideas |
| POST | `/workflow/select-idea` | `{thread_id, selected_idea}` | Select idea → script + thumbnail |
| GET | `/workflow/history` | — | List all past generations |

### Per-endpoint model selection
All content endpoints accept an optional `model` field:
```json
{ "topic": "Python decorators", "plan": "normal", "model": "gemini" }
{ "topic": "Python decorators", "plan": "normal", "model": "qwen" }
{ "topic": "Python decorators", "plan": "normal" }   // uses DEFAULT_MODEL
```

---

## 🗺️ Roadmap

### ✅ Phase 1 — Core Pipeline (Complete)
- [x] Multi-agent LangGraph content generation
- [x] Human-in-the-loop at research + idea selection
- [x] Creator profile from real YouTube channel data
- [x] PostgreSQL state persistence
- [x] JWT + Google OAuth auth
- [x] Gemini + Qwen unified provider architecture
- [x] Per-request model selection via API

### 🔄 Phase 2 — Publishing (In Progress)
- [x] Separate upload workflow
- [x] SEO generation (title, description, tags)
- [x] YouTube Data API v3 upload
- [x] Upload history tracking
- [ ] Real video file binary upload via frontend
- [ ] Scheduled publishing

### 📅 Phase 3 — Intelligence (Planned)
- [ ] MongoDB MCP memory layer (partially implemented)
- [ ] Elasticsearch trend intelligence (indexes written)
- [ ] Multi-channel support
- [ ] Analytics feedback loop

---

## 🏆 Hackathon — Google Cloud Rapid Agent

Built for the **Google Cloud Rapid Agent Hackathon**, demonstrating:

- **Real agentic AI** — coordinated multi-agent system with persistent state
- **Google Cloud integration** — YouTube Data API v3, Google OAuth2, Gemini 2.5 Flash (default LLM)
- **Production thinking** — checkpointing, error handling, migration scripts, 30-check health suite
- **Human-AI collaboration** — HITL at every critical decision point
- **Provider abstraction** — swap LLMs with one env var, zero agent code changes

---

<div align="center">

Built with ❤️ by **Samer** · [Learn with Samer](https://youtube.com/@LearnWithSamer)

*Self-taught developer · Mumbai, India*

</div>
