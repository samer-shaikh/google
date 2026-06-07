<![CDATA[<div align="center">

# 🎬 AI Content Studio

### Multi-Agent YouTube Content Creation Platform

*Built for the Google Cloud Rapid Agent Hackathon*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-blue?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)](https://python.org)
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
- **Provider Abstraction** — YouTube MCP or Data API, the workflow doesn't care which
- **Generation History** — Every workflow run saved to DB; browse, reload, and republish past content
- **Upload History** — Full audit trail of every YouTube publish attempt
- **Plan-Based Model Routing** — Normal/Pro routes to `qwen-plus`; Plus routes heavy tasks to `qwen-max`
- **Dual Auth** — Email/password + Google OAuth; JWT access + refresh token pattern
- **Production-Ready** — CORS, session middleware, Pydantic validation, structured error handling, 30-check health suite

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph Client["Client (Next.js Frontend)"]
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

    subgraph Graphs["LangGraph Orchestration"]
        CG[Content Generation Graph]
        UG[Upload Graph]
        CPG[Creator Profile Graph]
    end

    subgraph Storage["PostgreSQL"]
        Users[(users)]
        Profiles[(creator_profiles)]
        Videos[(youtube_videos)]
        Gens[(generations)]
        Uploads[(upload_records)]
        Checkpoints[(langgraph_checkpoints)]
    end

    subgraph YouTube["YouTube Integration"]
        YTAPI[Data API v3]
        Provider[Provider Abstraction]
    end

    subgraph LLM["LLM Layer"]
        QwenPlus[Qwen-Plus]
        QwenMax[Qwen-Max]
    end

    UI --> API
    Auth --> Users
    YT --> YTAPI
    WF --> CG
    WF --> UG
    CP --> CPG
    CG --> Agents
    CG --> Checkpoints
    UG --> Provider
    Provider --> YTAPI
    Agents --> LLM
    CG --> Gens
    UG --> Uploads
    CPG --> Profiles
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
    LangGraph->>Agents: Script Agent
    LangGraph->>Agents: Thumbnail Agent
    LangGraph->>DB: save generation (completed)
    API-->>User: {script, thumbnail, generation_id}
```

---

## 🚀 Upload Workflow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant LangGraph
    participant YouTube

    User->>API: POST /workflow/upload/start {generation_id}
    LangGraph->>LangGraph: load_generation
    LangGraph->>LangGraph: seo_title → seo_description → tags
    LangGraph-->>API: PAUSE (metadata_review)
    API-->>User: {seo_title, description, tags, hashtags}

    User->>API: POST /workflow/upload/review {approved: true}
    LangGraph->>YouTube: upload_video (MediaFileUpload)
    LangGraph->>YouTube: upload_thumbnail
    LangGraph->>DB: save upload_record
    API-->>User: {youtube_video_id, youtube_video_url, published_at}
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | FastAPI 0.115 | REST API, Swagger UI, dependency injection |
| **Orchestration** | LangGraph | Stateful multi-agent graph with HITL |
| **Checkpointing** | langgraph-checkpoint-postgres | HITL state persistence across restarts |
| **LLM** | Qwen-Plus / Qwen-Max | Content generation via LangChain OpenAI compat |
| **LLM (alt)** | Gemini 2.5 Flash | Available, switchable via model router |
| **Database** | PostgreSQL 16 | All application + checkpoint state |
| **ORM** | SQLAlchemy 2.0 | Models, migrations, session management |
| **Auth** | JWT + Google OAuth2 | Dual auth with refresh tokens |
| **YouTube** | Data API v3 + OAuth2 PKCE | Channel connection, video upload, thumbnail upload |
| **Validation** | Pydantic v2 | Request/response models, LLM output validation |
| **Security** | bcrypt + python-jose | Password hashing, JWT signing |

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── agents/              # AI agents (one per responsibility)
│   │   ├── README.md
│   │   ├── research_agent.py
│   │   ├── video_idea_agent.py
│   │   ├── script_agent.py
│   │   ├── thumbnail_agent.py
│   │   ├── seo_agent.py
│   │   ├── creator_profile_agent.py
│   │   └── youtube_research_agent.py
│   ├── graph/               # LangGraph workflow definitions
│   │   ├── workflow.py          # Content generation pipeline
│   │   ├── upload_workflow.py   # Publishing pipeline
│   │   ├── creator_profile_workflow.py
│   │   ├── state.py             # TypedDict state schemas
│   │   └── checkpointer.py      # PostgreSQL checkpointer singleton
│   ├── models/              # SQLAlchemy ORM models
│   ├── routes/              # FastAPI route handlers
│   ├── services/            # Business logic services
│   ├── youtube_provider/    # Provider abstraction layer
│   │   ├── base.py              # Abstract interface
│   │   ├── youtube_api_provider.py  # Data API v3
│   │   └── youtube_mcp_provider.py  # MCP stub
│   ├── core/                # Security, exceptions
│   ├── dependencies/        # FastAPI dependencies (auth)
│   ├── prompts/             # Prompt templates
│   │   └── README.md
│   └── schemas/             # Pydantic request/response schemas
├── docs/                    # Architecture and workflow docs
│   ├── architecture.md
│   ├── content_workflow.md
│   ├── upload_workflow.md
│   ├── database_schema.md
│   └── mcp_integration.md
├── check.py                 # 30-check automated health suite
├── migrate.py               # Safe schema migration script
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- A [Qwen API key](https://dashscope-intl.aliyuncs.com) (free tier available)
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
pip install langgraph-checkpoint-postgres psycopg[binary]
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM
QWEN_API_KEY=your_qwen_api_key

# Database
DATABASE_URl=postgresql://postgres:password@localhost:5432/ai_content_studio

# Auth
SECRET_KEY_FOR_LOGIN=your_64_char_hex_secret
SECRET_KEY=your_session_secret
ALGORITHM=HS256

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/youtube/callback
```

### 5. Create database & run migrations

```bash
# Create the database first in PostgreSQL:
# CREATE DATABASE ai_content_studio;

python migrate.py
```

### 6. Start the server

```bash
uvicorn app.main:app --reload
```

### 7. Verify everything works

```bash
python check.py
# Expected: 30 passed, 0 failed
```

### 8. Open Swagger UI

```
http://localhost:8000/docs
```

Click **Authorize** → paste your `access_token` from `POST /auth/login`.

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
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| GET | `/auth/me` | Current authenticated user |
| GET | `/auth/google/login` | Google OAuth login redirect |

### YouTube
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/youtube/connect` | Get Google OAuth URL (PKCE) for channel connection |
| GET | `/youtube/callback` | OAuth callback — saves tokens + channel info |
| GET | `/youtube/me` | Connection status |
| POST | `/youtube/research` | Fetch recent videos → save to DB |

### Creator Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/creator-profile/generate` | Run profile workflow → analyze channel with LLM |
| GET | `/creator-profile/me` | Get saved creator profile |

### Content Generation Workflow
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/workflow/run` | Start pipeline → returns research + thread_id |
| POST | `/workflow/resume` | Approve/reject research (HITL #1) → returns ideas |
| POST | `/workflow/select-idea` | Select idea (HITL #2) → returns script + thumbnail |
| GET | `/workflow/status/{thread_id}` | Check workflow pause state |
| GET | `/workflow/history` | List all past generations |
| GET | `/workflow/history/{id}` | Full generation detail |

### Upload / Publishing Workflow
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/workflow/upload/start` | Generate SEO → pause for review |
| POST | `/workflow/upload/review` | Approve metadata → upload to YouTube |
| GET | `/workflow/uploads` | List all past uploads |
| GET | `/workflow/uploads/{id}` | Full upload record detail |

---

## 🗺️ Roadmap

### ✅ Phase 1 — Core Pipeline (Complete)
- [x] Multi-agent LangGraph content generation
- [x] Human-in-the-loop at research + idea selection
- [x] Creator profile from real YouTube channel data
- [x] PostgreSQL state persistence
- [x] JWT + Google OAuth auth

### 🔄 Phase 2 — Publishing (In Progress)
- [x] Separate upload workflow
- [x] SEO generation (title, description, tags)
- [x] YouTube Data API v3 upload
- [x] Upload history tracking
- [x] Provider abstraction (MCP / API)
- [ ] Real video file binary upload via frontend
- [ ] Thumbnail image generation (text → image)
- [ ] Scheduled publishing

### 📅 Phase 3 — Intelligence (Planned)
- [ ] YouTube MCP server integration
- [ ] MongoDB MCP for vector search
- [ ] Multi-channel support
- [ ] A/B title testing suggestions
- [ ] Analytics feedback loop
- [ ] Automatic re-profiling on channel growth

### 🚀 Phase 4 — Scale (Planned)
- [ ] Celery background task queue
- [ ] Multi-worker PostgreSQL checkpointing
- [ ] Next.js frontend
- [ ] SaaS billing (Stripe)
- [ ] Team workspaces

---

## 🏆 Hackathon — Google Cloud Rapid Agent

This project was built for the **Google Cloud Rapid Agent Hackathon**, demonstrating:

- **Real agentic AI** — not a chatbot, but a coordinated multi-agent system with persistent state
- **Google Cloud integration** — YouTube Data API v3, Google OAuth2, Gemini (available)
- **Production thinking** — checkpointing, error handling, migration scripts, 30-check health suite
- **Human-AI collaboration** — HITL at every critical decision point; AI proposes, human decides
- **Provider abstraction** — MCP-ready architecture, switchable without changing workflow logic

**Key technical achievements:**
- LangGraph HITL with PostgreSQL persistence (zero state loss on restart)
- PKCE OAuth2 for YouTube channel connection
- Pydantic-validated LLM output (no silent garbage in DB)
- Creator profile personalization injected into every agent prompt
- Decoupled content generation and publishing pipelines

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run the health check: `python check.py` — must pass 30/30
4. Commit: `git commit -m "feat: describe your change"`
5. Push and open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with ❤️ by **Samer** · [Learn with Samer](https://youtube.com/@LearnWithSamer)

*Self-taught developer · Mumbai, India*

</div>
]]>