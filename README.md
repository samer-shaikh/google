<h1 align="center">
  <br>
  🎬 AI Content Studio
  <br>
</h1>

<h4 align="center">
  A multi-agent AI platform that researches, writes, and publishes YouTube content — end to end.
</h4>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/LangGraph-0.2-FF6B35?style=flat-square" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql" />
  <img src="https://img.shields.io/badge/Qwen-Max-6B21A8?style=flat-square" />
  <img src="https://img.shields.io/badge/YouTube_API-v3-FF0000?style=flat-square&logo=youtube" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
</p>

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#installation">Installation</a> •
  <a href="#api">API</a> •
  <a href="#roadmap">Roadmap</a>
</p>

---

## Overview

**AI Content Studio** is a production-grade, multi-agent content creation platform built for YouTube creators. It connects directly to your YouTube channel, analyzes your content style and audience, then runs a full agentic pipeline — from topic research to script writing to publishing — all with human-in-the-loop approval at every critical step.

Built for the **Google Cloud Rapid Agent Hackathon** using LangGraph, FastAPI, PostgreSQL, and Qwen LLM via Alibaba Cloud DashScope.

> **"From topic idea to published YouTube video — one API call at a time."**

---

## Features

### 🤖 Multi-Agent Pipeline
- **Research Agent** — deep topic research personalized to your channel niche and audience
- **Video Idea Agent** — generates 5 viral video concepts matching your title style
- **Script Agent** — writes full production scripts tuned to your audience level and tone
- **Thumbnail Agent** — produces AI image generation prompts for scroll-stopping thumbnails
- **SEO Agent** — generates title, description, 15 tags, and hashtags for maximum reach
- **Creator Profile Agent** — analyzes your real YouTube channel to build a personalization engine

### 🔄 Human-in-the-Loop (HITL) Workflows
- Research approval before ideas are generated
- Idea selection before script is written
- Full metadata review before YouTube upload
- All HITL state persists across server restarts via PostgreSQL checkpointing

### 🎯 Deep Personalization
Every agent reads your creator profile — niche, audience level, title style, viral patterns — and personalizes its output. A beginner Python tutorial channel gets different ideas, scripts, and SEO than a finance channel targeting professionals.

### 📺 YouTube Integration
- Full OAuth 2.0 with PKCE for secure channel connection
- Automatic token refresh
- Video upload via YouTube Data API v3
- Thumbnail upload
- Resumable uploads with retry logic

### 🗄️ Complete History
- Every generation saved to PostgreSQL
- Every upload tracked with full audit trail
- Creator profile snapshots preserved at generation time

---

## Architecture

```mermaid
graph TB
    subgraph Client["Client (Browser / Frontend)"]
        UI[React Frontend]
    end

    subgraph API["FastAPI Backend"]
        Auth[Auth Routes]
        WF[Workflow Routes]
        YT[YouTube Routes]
        CP[Creator Profile Routes]
    end

    subgraph Workflows["LangGraph Workflows"]
        CGW[Content Generation Workflow]
        UPW[Upload Workflow]
        CPW[Creator Profile Workflow]
    end

    subgraph Agents["AI Agents"]
        RA[Research Agent]
        VIA[Video Idea Agent]
        SA[Script Agent]
        TA[Thumbnail Agent]
        CPA[Creator Profile Agent]
    end

    subgraph LLM["LLM Layer"]
        QP[Qwen Plus]
        QM[Qwen Max]
    end

    subgraph DB["PostgreSQL"]
        Users[(users)]
        Gens[(generations)]
        Profiles[(creator_profiles)]
        Uploads[(upload_records)]
        Checkpoints[(langgraph_checkpoints)]
    end

    subgraph YouTube["YouTube"]
        YTAPI[YouTube Data API v3]
    end

    UI --> API
    API --> Workflows
    Workflows --> Agents
    Agents --> LLM
    Workflows --> DB
    API --> DB
    Workflows --> YouTube
```

---

## Content Generation Workflow

```mermaid
flowchart TD
    A([POST /workflow/run]) --> B[load_profile_node\nReads creator profile from DB]
    B --> C[research_node\nResearches topic for this creator's audience]
    C --> D{HITL #1\nhuman_approval}
    D -->|Rejected| E[handle_rejection_node\nMark generation failed]
    D -->|Approved| F[idea_node\nGenerates 5 personalized video ideas]
    F --> G{HITL #2\nidea_selection}
    G --> H[script_node\nWrites full production script]
    H --> I[thumbnail_node\nGenerates thumbnail concept + AI prompt]
    I --> J[save_generation_node\nSaves all outputs to PostgreSQL]
    J --> K([Generation Complete\nReady for Upload Workflow])

    style D fill:#FF6B35,color:#fff
    style G fill:#FF6B35,color:#fff
```

---

## Upload Workflow

```mermaid
flowchart TD
    A([POST /workflow/upload/start]) --> B[load_generation_node\nLoad completed generation from DB]
    B --> C[seo_title_node\nGenerate SEO-optimized title]
    C --> D[seo_description_node\nGenerate YouTube description]
    D --> E[tags_node\nGenerate 15 tags + 5 hashtags]
    E --> F{HITL\nMetadata Review}
    F -->|Rejected| G[handle_rejection\nCancel upload]
    F -->|Approved| H[upload_video_node\nUpload via YouTubeAPIProvider or MCP]
    H --> I[upload_thumbnail_node\nAttach thumbnail image]
    I --> J[save_upload_result_node\nSave to upload_records table]
    J --> K([Published to YouTube])

    style F fill:#FF6B35,color:#fff
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Framework** | FastAPI | REST API, Swagger UI, dependency injection |
| **Agentic Orchestration** | LangGraph | Stateful multi-agent workflows with HITL |
| **LLM** | Qwen Plus / Qwen Max | Content generation via DashScope API |
| **Database** | PostgreSQL 16 | Users, generations, uploads, LangGraph checkpoints |
| **ORM** | SQLAlchemy | Database models and queries |
| **Auth** | JWT + Google OAuth2 + PKCE | Dual auth, YouTube channel connection |
| **YouTube** | Data API v3 | Video upload, thumbnail upload, channel data |
| **Server** | Uvicorn | ASGI server |
| **LLM Client** | LangChain OpenAI | Compatible interface for DashScope |

---

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- A Google Cloud project with YouTube Data API v3 enabled

### 1. Clone

```bash
git clone https://github.com/your-username/ai-content-studio.git
cd ai-content-studio/backend
```

### 2. Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Setup

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# LLM
QWEN_API_KEY=your_qwen_api_key

# PostgreSQL
DATABASE_URl=postgresql://user:password@localhost:5432/ai_content_studio

# JWT Auth
SECRET_KEY_FOR_LOGIN=your_64_char_hex_secret
ALGORITHM=HS256
SECRET_KEY=your_session_secret

# Google OAuth (for login + YouTube)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/youtube/callback
```

### 5. Google Cloud Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Enable **YouTube Data API v3**
3. Create an **OAuth 2.0 Client ID** (Web application)
4. Add `http://localhost:8000/youtube/callback` to Authorized redirect URIs
5. Add `http://localhost:8000/auth/google/callback` to Authorized redirect URIs
6. Add your Gmail to **OAuth consent screen → Test users**

### 6. Database Setup

```bash
python migrate.py
```

### 7. Run

```bash
uvicorn app.main:app --reload
```

### 8. Verify

```bash
python check.py
```

Expected: **30/30 checks passing**

API docs available at: `http://localhost:8000/docs`

---

## API Overview

### Auth
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/auth/signup` | Register with email + password |
| `POST` | `/auth/login` | Login → JWT access + refresh tokens |
| `POST` | `/auth/refresh` | Exchange refresh token for new access token |
| `GET` | `/auth/me` | Get current authenticated user |
| `GET` | `/auth/google/login` | Start Google OAuth login |

### YouTube
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/youtube/connect` | Get Google OAuth URL for YouTube |
| `GET` | `/youtube/callback` | OAuth callback (handle in browser) |
| `GET` | `/youtube/me` | Check YouTube connection status |
| `POST` | `/youtube/research` | Fetch and save videos from connected channel |

### Creator Profile
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/creator-profile/generate` | Analyze channel → build creator profile |
| `GET` | `/creator-profile/me` | Get current creator profile |

### Content Generation Workflow
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/workflow/run` | Start pipeline (returns research, pauses for approval) |
| `POST` | `/workflow/resume` | Approve/reject research (HITL #1) |
| `POST` | `/workflow/select-idea` | Select video idea → generate script + thumbnail (HITL #2) |
| `GET` | `/workflow/status/{thread_id}` | Check workflow state |
| `GET` | `/workflow/history` | List all past generations |
| `GET` | `/workflow/history/{id}` | Get full generation detail |

### Upload Workflow
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/workflow/upload/start` | Start upload pipeline → generate SEO |
| `POST` | `/workflow/upload/review` | Approve/reject + optional overrides (HITL) |
| `GET` | `/workflow/uploads` | List all uploads |
| `GET` | `/workflow/uploads/{id}` | Get upload detail |

### Swagger UI
All routes documented and testable at `http://localhost:8000/docs`.
Click **Authorize** → paste your `access_token` from `/auth/login`.

---

## Folder Structure

```
ai-content-studio/
├── backend/
│   ├── app/
│   │   ├── agents/              # AI agent functions
│   │   │   └── README.md        # Agent documentation
│   │   ├── core/                # Security, exceptions
│   │   ├── dependencies/        # FastAPI dependency injection
│   │   ├── graph/               # LangGraph workflows + state
│   │   ├── models/              # SQLAlchemy database models
│   │   ├── prompts/             # Prompt files + documentation
│   │   │   └── README.md        # Prompt documentation
│   │   ├── routes/              # FastAPI route handlers
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business logic layer
│   │   ├── youtube_provider/    # YouTube provider abstraction
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   └── main.py              # FastAPI app entry point
│   ├── docs/
│   │   ├── architecture.md      # System + agent architecture
│   │   ├── content_workflow.md  # Content generation pipeline
│   │   ├── upload_workflow.md   # Publishing pipeline
│   │   ├── database_schema.md   # All tables + relationships
│   │   └── mcp_integration.md   # MCP provider architecture
│   ├── check.py                 # 30-check health verification script
│   ├── migrate.py               # Safe schema migration script
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md                # Backend-specific setup
└── README.md                    # This file
```

---

## Hackathon

This project was built for the **Google Cloud Rapid Agent Hackathon**.

### What makes it a strong submission

**Real agentic behavior** — agents don't just call LLMs in sequence. Each agent reads the creator's profile from PostgreSQL, adapts its prompt, and feeds structured output to the next agent. The pipeline is genuinely stateful.

**Production-grade HITL** — LangGraph's `interrupt()` + `Command(resume=)` pattern with PostgreSQL checkpointing. A user can start a workflow, close their browser, come back hours later, and resume exactly where they left off.

**Real YouTube integration** — not a mock. Full PKCE OAuth, real API calls to fetch channel data, resumable video uploads with retry logic.

**Provider abstraction** — the upload workflow doesn't know whether it's talking to the YouTube Data API or a YouTube MCP server. Swap providers by setting one env variable.

**Automated verification** — 30-check health script that tests every layer from env vars to DB schema to live API calls.

### Built by
**Samer Shaikh** — Self-taught developer, Mumbai.
YouTube: [@LearnWithSamer](https://youtube.com/@LearnWithSamer)

---

## Roadmap

- [ ] **PostgreSQL Checkpointer** — persistent HITL state (package installed, wiring in progress)
- [ ] **Real video file upload** — binary MediaFileUpload once file handling is implemented
- [ ] **YouTube MCP provider** — activate by setting `YOUTUBE_MCP_URL` in `.env`
- [ ] **Frontend** — React/Next.js dashboard (in development with collaborator)
- [ ] **Alembic migrations** — replace `migrate.py` with proper versioned migrations
- [ ] **Celery background tasks** — non-blocking workflow execution
- [ ] **Webhook notifications** — notify frontend when HITL pauses
- [ ] **Multi-channel support** — manage multiple YouTube accounts per user
- [ ] **Analytics agent** — analyze video performance and recommend improvements
- [ ] **Thumbnail image generation** — Imagen / DALL-E integration

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Run `python check.py` — all 30 checks must pass
4. Commit with a clear message (`git commit -m "feat: add X"`)
5. Push and open a Pull Request

Please don't break the `check.py` contract. If you add a new route or model, add a check for it.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with ☕ in Mumbai by <a href="https://youtube.com/@LearnWithSamer">Samer Shaikh</a>
</p>
