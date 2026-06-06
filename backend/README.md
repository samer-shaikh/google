# AI Content Studio — Backend

Multi-agent content creation platform for YouTube creators.
Built with FastAPI, LangGraph, PostgreSQL, and Gemini/Qwen LLM.

---

## Tech Stack

- **FastAPI** — REST API
- **LangGraph** — Multi-agent workflow with HITL (Human-in-the-Loop)
- **PostgreSQL** — Database
- **SQLAlchemy** — ORM
- **Google OAuth2** — Auth + YouTube API
- **Gemini / Qwen** — LLM for content generation

---

## Agent Pipeline

```
FetchVideosAgent → CreatorProfileAgent → VideoIdeaAgent → ScriptAgent → ThumbnailAgent → SEOAgent
```

---

## Local Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd backend
```

### 2. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

You need:
- A PostgreSQL database (local or [Neon](https://neon.tech) free tier)
- A Google Cloud project with YouTube Data API v3 enabled
- A Gemini or Qwen API key

### 5. Run database migration

```bash
python migrate.py
```

### 6. Start the server

```bash
uvicorn app.main:app --reload
```

### 7. Open Swagger UI

```
http://localhost:8000/docs
```

---

## Authentication Flow (Swagger UI)

1. `POST /auth/signup` — create an account
2. `POST /auth/login` — get your `access_token`
3. Click **Authorize** (top right in Swagger) → paste the token
4. All protected routes now work

---

## YouTube Connection Flow

1. `GET /youtube/connect` — get Google OAuth URL
2. Paste the URL in your browser → sign in with your YouTube account
3. You'll be redirected back with a success message
4. `POST /youtube/research` — fetch and save your videos
5. `POST /creator-profile/generate` — generate your creator profile
6. `GET /creator-profile/me` — view your profile

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/auth/signup` | Register |
| POST | `/auth/login` | Login → JWT |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Current user |
| GET | `/auth/google/login` | Google OAuth login |
| GET | `/youtube/connect` | Connect YouTube channel |
| GET | `/youtube/me` | YouTube connection status |
| POST | `/youtube/research` | Fetch and save videos |
| POST | `/creator-profile/generate` | Generate creator profile |
| GET | `/creator-profile/me` | Get creator profile |
| POST | `/workflow/start` | Start content generation workflow |
| POST | `/workflow/resume` | Resume after HITL |
| POST | `/workflow/select-idea` | Select a video idea |

---

## Google Cloud Setup (Required)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project
3. Enable **YouTube Data API v3**
4. Go to **APIs & Services → Credentials**
5. Create an **OAuth 2.0 Client ID** (Web application type)
6. Add `http://localhost:8000/youtube/callback` to **Authorized redirect URIs**
7. Add `http://localhost:8000/auth/google/callback` to **Authorized redirect URIs**
8. Go to **OAuth consent screen → Test users** → add your Gmail

---

## Frontend Integration Notes

The API is fully documented at `http://localhost:8000/docs`.

All protected routes require:
```
Authorization: Bearer <access_token>
```

CORS is configured for local development. For production, update the allowed origins in `main.py`.

Base URL for API calls: `http://localhost:8000`

Key response formats are available in Swagger — use the **Schemas** section at the bottom of the docs page.

---

## Health Check

```bash
python check.py
```

Verifies server, auth, DB schema, and all routes are working correctly.
