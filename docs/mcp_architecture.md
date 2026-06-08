# MCP-Native Architecture Design
## AI Content Studio — Google Cloud Rapid Agent Hackathon

---

# TASK 1 — Architecture Review

## What's genuinely strong

**The LangGraph HITL implementation is production-grade.** The `interrupt()` + `Command(resume=)` pattern with PostgreSQL checkpointing is correct and non-trivial. Most hackathon submissions use MemorySaver and lose state on restart. You don't.

**The provider abstraction is MCP-ready.** `youtube_provider/base.py` + factory pattern means activating a YouTube MCP server is a one-line env change. This is the right foundation.

**The agent personalization layer is real.** `_profile_context()` injected into every agent prompt is a genuine personalization mechanism, not a fake one.

**The DB design is solid.** Six tables, proper FKs, JSONB for evolving schemas, upload audit trail. This is better than 90% of hackathon backends.

## Architectural weaknesses

### 1. Creator profile is loaded from a relational table — not a memory system

`load_profile_node` reads `creator_profiles` from PostgreSQL. That table has: topics (JSONB list), audience (JSONB), title_style (JSONB), description_style (JSONB). That's it.

What's missing: **research history**, **topic history**, **what worked**, **what didn't work**, **competitor context**, **trending signals**. The profile is static. It's the same every run. There is no learning.

### 2. Agents have no memory of previous runs

Every workflow run starts cold. The Research Agent doesn't know what this creator researched last week. The Script Agent doesn't know what scripts performed well. The Idea Agent generates ideas without knowing which of the last 20 ideas the creator actually used.

This is the single biggest weakness. It's not a personalization system. It's a personalized one-shot generator.

### 3. No content intelligence layer

There is no trending signal. No competitor awareness. No duplicate detection. The system can generate the exact same 5 ideas it generated 3 weeks ago with no awareness it already did that.

### 4. No evaluation loop

Scripts and ideas are generated and saved. Nothing evaluates whether they're good. There's no critic, no quality gate, no feedback mechanism. The creator's only signal is human approval at HITL checkpoints.

### 5. `content_strengths` and `viral_patterns` are always empty

In `load_profile_node`:
```python
"content_strengths": [],
"viral_patterns":    [],
```

These fields are defined in the state but never populated. The Thumbnail Agent and Research Agent both try to use `viral_patterns` from the profile but always get an empty list. This is a silent bug that degrades output quality on every single run.

### 6. The Upload Workflow has no memory of past uploads

`upload_records` table exists. But when generating SEO for a new video, the SEO agents don't look at what tags/titles worked in previous uploads. Every upload is as naive as the first.

### 7. MongoDB MCP — 0% usage. Elastic MCP — 0% usage.

The hackathon "strongly rewards MCP integration." The current codebase has zero MCP integration beyond the YouTube provider stub. This is the primary risk.

---

# TASK 2 — MCP-First Architecture

## Why MongoDB MCP here

MongoDB is a document database. Creator memory is document-shaped: each research session is a document, each content piece is a document, each performance record is a document. Querying "give me all research this creator did on Python topics in the last 6 months" is a natural MongoDB aggregation, not a SQL join chain.

More importantly: **MongoDB MCP gives the LLM direct tool-calling access to the memory system.** The LLM doesn't receive a formatted context blob — it calls `find_similar_research(topic, creator_id)` as a tool and decides what to do with the result. This is what MCP-native means.

## Why Elastic MCP here

Elasticsearch is a search engine. Trend intelligence, competitor analysis, and content similarity are fundamentally search problems. "Find content similar to this script," "find trending topics in this niche," "find what keywords competitors rank for" — these are Elastic queries, not MongoDB queries and not SQL queries.

Elastic MCP gives agents semantic search capability. Without it, you'd have to send all competitor content to the LLM context window. With it, the LLM calls `search_trending_topics(niche, timeframe)` and gets back the top 10 results.

## Architecture diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Content Studio                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              LangGraph Workflow Layer                   │    │
│  │                                                         │    │
│  │  load_memory → research → ideas → script → thumbnail   │    │
│  │       ↑            ↓         ↓       ↓         ↓       │    │
│  │       │        [Elastic]  [Mongo] [Mongo]   [Mongo]    │    │
│  │       │            ↓         ↓       ↓         ↓       │    │
│  │  [Mongo MCP]   trends    history  scripts  patterns     │    │
│  │  creator memory                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │   MongoDB MCP    │    │   Elastic MCP    │                   │
│  │                  │    │                  │                   │
│  │ creator_memory   │    │ trending_topics  │                   │
│  │ research_history │    │ competitor_intel │                   │
│  │ content_history  │    │ content_search   │                   │
│  │ performance_data │    │ keyword_index    │                   │
│  │ audience_intel   │    │ duplicate_detect │                   │
│  └──────────────────┘    └──────────────────┘                   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  PostgreSQL (existing)                   │   │
│  │  users · creator_profiles · generations · upload_records │   │
│  │  youtube_accounts · youtube_videos · lg_checkpoints      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Data flow per MCP

### MongoDB MCP — what flows through it

| Collection | Written by | Read by | Purpose |
|---|---|---|---|
| `creator_memory` | CreatorProfileAgent | load_memory_node, all agents | Persistent creator profile with history |
| `research_sessions` | ResearchAgent | ResearchAgent | Avoid duplicate research, build knowledge base |
| `content_pieces` | ScriptAgent, IdeaAgent | IdeaAgent | Track what was generated, find patterns |
| `performance_signals` | (future) PerformanceAgent | ResearchAgent, IdeaAgent | What actually worked on YouTube |
| `audience_intelligence` | YouTubeResearchAgent | ResearchAgent | Real audience data from channel analytics |

### Elastic MCP — what flows through it

| Index | Written by | Read by | Purpose |
|---|---|---|---|
| `trending_topics` | TrendAgent (background) | ResearchAgent | What's trending in the creator's niche |
| `competitor_content` | CompetitorAgent | IdeaAgent, SEOAgent | What competitors are publishing |
| `content_index` | SaveGenerationNode | IdeaAgent | Semantic search across all past content |
| `keyword_performance` | UploadResultSaver | SEOAgent | Which keywords drove views |
| `audience_questions` | YouTubeCommentAnalyzer | ResearchAgent | What audiences actually ask about |

---

# TASK 3 — Creator Memory System

## MongoDB collections design

### `creator_memory` — the root document

```json
{
  "_id": "user_6",
  "user_id": 6,
  "channel_id": "UCY5DQxlBO5MLReyrhnRB0tA",
  "channel_name": "Learn with Samer",
  "updated_at": "2026-06-06T10:30:00Z",

  "profile": {
    "niche": "General Learning, Study Skills",
    "main_topics": ["Python", "Data Science", "Machine Learning"],
    "audience_type": "students and self-learners seeking foundational knowledge",
    "audience_level": "beginner",
    "content_goals": ["grow subscribers", "establish authority in ML education"],
    "preferred_tone": "neutral and aspirational",
    "title_style": "neutral and aspirational (e.g. 'Learn with Samer')",
    "description_style": "minimal",
    "prompt_version": "v1"
  },

  "content_strengths": [
    "breaking down complex topics for beginners",
    "step-by-step explanations",
    "relatable analogies"
  ],

  "viral_patterns": [
    "titles that frame learning as surprisingly simple",
    "thumbnails with text overlay showing the end result"
  ],

  "topic_history": [
    "How to learn Python fast",
    "SVMs explained simply",
    "What is machine learning"
  ],

  "successful_hooks": [
    "What if learning Python was as easy as learning a new word every day?",
    "Stop watching tutorials. Do this instead."
  ],

  "successful_title_patterns": [
    "Learn X Like You're Learning Y",
    "The X-Minute Y Reset",
    "Stop Doing X. Do This Instead."
  ],

  "audience_intelligence": {
    "common_questions": [
      "How long does it take to learn Python?",
      "Do I need math for machine learning?"
    ],
    "content_gaps": [
      "practical projects for beginners",
      "how to get first data science job"
    ],
    "frustrations": [
      "too many conflicting tutorials",
      "don't know what to learn next"
    ]
  },

  "performance_summary": {
    "avg_views_last_10": 0,
    "best_performing_topic": null,
    "best_performing_format": null,
    "avg_engagement_rate": 0
  }
}
```

### `research_sessions` — one document per research run

```json
{
  "_id": "res_20260606_user6_python",
  "user_id": 6,
  "session_id": "uuid",
  "topic": "How to learn Python fast",
  "created_at": "2026-06-06T10:00:00Z",

  "research_output": "... full research text ...",
  "key_insights": [
    "Beginners are overwhelmed by conflicting advice",
    "Language-learning analogy resonates with this audience",
    "5-minute micro-learning format is trending"
  ],
  "pain_points_identified": [
    "time anxiety",
    "isolation from learner community",
    "unclear progress milestones"
  ],
  "trending_angles": [
    "spaced repetition for code",
    "learn by building not watching"
  ],
  "topics_suggested": [
    "Python basics in 30 days",
    "First Python project in 1 hour"
  ],

  "generation_id": 1,
  "ideas_generated": 5,
  "idea_selected": "The 5-Minute Python Reset"
}
```

### `content_pieces` — one document per completed generation

```json
{
  "_id": "gen_1",
  "user_id": 6,
  "generation_id": 1,
  "topic": "How to learn Python fast",
  "selected_idea": "The 5-Minute Python Reset — ...",
  "created_at": "2026-06-06T10:38:00Z",

  "script_summary": "Hook: stop watching tutorials...",
  "script_length_words": 847,
  "thumbnail_concept": "Text: PYTHON IN 5 MIN. Visual: timer countdown...",

  "seo": {
    "title": "How to Learn Python Fast in 2025",
    "tags": ["python", "learn python", "..."],
    "category": "Education"
  },

  "upload_record_id": null,
  "youtube_video_id": null,
  "performance": null
}
```

## Memory service design

```
app/memory/
├── __init__.py
├── mongo_client.py          # singleton MongoDB connection via MCP
├── creator_memory_service.py # CRUD for creator_memory collection
├── research_memory_service.py # save/query research sessions
├── content_memory_service.py  # save/query content pieces
└── performance_memory_service.py # update performance signals
```

### `mongo_client.py`

```python
"""
MongoDB connection via MCP tool-calling interface.
The LLM calls MongoDB tools through this client.
"""
import os
from anthropic import Anthropic

_client = None

def get_mongo_mcp_client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client

MONGO_MCP_URL = os.getenv("MONGODB_MCP_URL", "")
```

### `creator_memory_service.py` — key methods

```python
async def get_creator_memory(user_id: int) -> dict:
    """Retrieve full creator memory document."""

async def update_creator_memory(user_id: int, updates: dict) -> None:
    """Upsert creator memory with new insights."""

async def add_successful_hook(user_id: int, hook: str) -> None:
    """Append a hook that performed well."""

async def add_topic_to_history(user_id: int, topic: str) -> None:
    """Track researched topics to avoid repetition."""

async def get_audience_intelligence(user_id: int) -> dict:
    """Get aggregated audience questions and gaps."""

async def update_viral_patterns(user_id: int, pattern: str) -> None:
    """Add a newly discovered viral pattern."""
```

## How memory flows through the workflow

```
load_memory_node (NEW — replaces load_profile_node)
  → calls MongoDB MCP: find_one({user_id})
  → returns full creator_memory document
  → state["creator_memory"] = full document
  → state["creator_profile"] = memory["profile"]  (backward compat)
  → state["viral_patterns"] = memory["viral_patterns"]  (NOW POPULATED)
  → state["successful_hooks"] = memory["successful_hooks"]
  → state["topic_history"] = memory["topic_history"]

research_node
  → checks state["topic_history"] — avoids repeating last 10 topics
  → calls Elastic MCP: search_trending_topics(niche, last_30_days)
  → injects trends + topic history into research prompt
  → saves research session to MongoDB via research_memory_service

save_generation_node (updated)
  → saves content piece to MongoDB content_pieces collection
  → updates creator_memory.topic_history
  → updates creator_memory.performance_summary
```

---

# TASK 4 — Elastic MCP Intelligence Layer

## Index design

### `trending_topics` index

```json
{
  "niche": "Python programming",
  "topic": "vibe coding with AI",
  "search_volume_trend": "rising",
  "score": 0.94,
  "region": "global",
  "timeframe": "last_7_days",
  "related_keywords": ["cursor ai", "github copilot", "ai pair programming"],
  "indexed_at": "2026-06-06T00:00:00Z"
}
```

**Used by:** ResearchAgent at the start of every research session.

**Query:** `search_trending_topics(niche="Python programming", days=30, limit=10)`

**Business value:** Every research session is informed by what's actually trending right now, not just what the creator already knows. A beginner Python channel discovers "vibe coding" is trending before their competitors do.

### `competitor_content` index

```json
{
  "channel_id": "UCcompetitor123",
  "channel_name": "Competitor Channel",
  "video_id": "abc123",
  "title": "Python for Beginners in 2025",
  "views": 450000,
  "published_at": "2026-05-15",
  "topics": ["python", "beginners", "2025"],
  "hook_pattern": "question-based",
  "thumbnail_style": "face + text overlay",
  "engagement_rate": 0.047
}
```

**Used by:** IdeaAgent before generating ideas.

**Query:** `search_competitor_content(niche="Python", audience_level="beginner", min_views=100000)`

**Business value:** Ideas are generated with awareness of what's already performing well in the niche. The agent avoids suggesting ideas competitors have saturated, and identifies underserved angles.

### `content_index` — all creator's own past content

```json
{
  "user_id": 6,
  "generation_id": 1,
  "topic": "How to learn Python fast",
  "selected_idea": "The 5-Minute Python Reset",
  "script_embedding": "[768-dim vector]",
  "topic_embedding": "[768-dim vector]",
  "created_at": "2026-06-06"
}
```

**Used by:** IdeaAgent for duplicate detection.

**Query:** `search_similar_content(user_id=6, query="Python learning speed", threshold=0.85)`

**Business value:** Prevents generating near-duplicate content. If the creator already made "How to learn Python fast" last month, the system detects semantic similarity and suggests a different angle.

### `keyword_performance` index

```json
{
  "user_id": 6,
  "keyword": "learn python",
  "used_in_video_id": "dQw4w9WgXcQ",
  "title_position": 2,
  "views_30_days": 12400,
  "click_through_rate": 0.068,
  "avg_watch_percentage": 0.54
}
```

**Used by:** SEO agents in the upload workflow.

**Query:** `search_performing_keywords(user_id=6, niche="Python", min_ctr=0.05)`

**Business value:** SEO recommendations are based on what actually drove views for this specific channel, not generic advice. The system learns which keywords work for this creator's audience.

## Which agents use Elastic, when, and what they retrieve

| Agent | When | Query | Retrieved |
|---|---|---|---|
| ResearchAgent | Start of every run | `trending_topics` | Top 10 trends in niche |
| IdeaAgent | Before idea generation | `competitor_content` | Top competitor videos |
| IdeaAgent | Before idea generation | `content_index` | Similar past content (dedup) |
| SEOAgent (upload) | Before title generation | `keyword_performance` | Best-performing keywords |
| SEOAgent (upload) | Before tag generation | `competitor_content` | Competitor tags in niche |

---

# TASK 5 — Redesigned Agents

## ResearchAgent

**Inputs:** `topic`, `plan`, `creator_profile`, `creator_memory` (NEW), `trending_topics` (NEW), `topic_history` (NEW)

**MongoDB MCP usage:**
- Reads: `creator_memory.topic_history` — prevents researching same topic twice
- Reads: `creator_memory.audience_intelligence.common_questions` — known audience pain points
- Writes: `research_sessions` — saves full research output with key insights extracted

**Elastic MCP usage:**
- Reads: `trending_topics` where `niche matches creator niche` — injects into prompt
- Reads: `audience_questions` — what questions real audiences ask about this topic

**Memory updates:**
- Appends topic to `creator_memory.topic_history`
- Saves research session to `research_sessions` collection

**What changes in the prompt:** The research prompt goes from "research this topic for this creator" to "research this topic for this creator, given that trending angles in their niche right now are X, Y, Z, and their audience frequently asks Q1, Q2, Q3, and they already covered these related topics: T1, T2, T3."

---

## IdeaAgent

**Inputs:** `topic`, `research`, `plan`, `creator_profile`, `creator_memory` (NEW), `competitor_content` (NEW), `similar_past_content` (NEW)

**MongoDB MCP usage:**
- Reads: `creator_memory.successful_title_patterns` — patterns that worked before
- Reads: `creator_memory.viral_patterns` — visual/content patterns
- Reads: `content_pieces` — last 20 ideas generated (to avoid repetition)

**Elastic MCP usage:**
- Reads: `competitor_content` — top 10 competitor videos in niche with high engagement
- Reads: `content_index` — semantic similarity check against past content

**Data saved:**
- Generated ideas are embedded and indexed in `content_index` (even before selection)

**Key improvement:** Ideas are now generated with explicit awareness of: (a) what competitors are doing, (b) what this creator already covered, (c) which title patterns worked before. The prompt becomes dramatically richer.

---

## ScriptAgent

**Inputs:** `topic`, `research`, `selected_idea`, `plan`, `creator_profile`, `successful_hooks` (NEW), `script_patterns` (NEW)

**MongoDB MCP usage:**
- Reads: `creator_memory.successful_hooks` — inject 2-3 hooks that performed well for this creator
- Reads: `content_pieces` where `topic similar` — look at how related topics were scripted before

**Elastic MCP usage:**
- Reads: `audience_questions` — real questions to address in the script

**Data saved:**
- Script word count, hook text, and structure to `content_pieces`
- Successful hook patterns extracted and offered for `creator_memory` update

---

## ThumbnailAgent

**Inputs:** `topic`, `script`, `plan`, `creator_profile`, `viral_patterns` (NOW POPULATED), `successful_thumbnail_concepts` (NEW)

**MongoDB MCP usage:**
- Reads: `creator_memory.viral_patterns` — NOW ACTUALLY POPULATED (currently always empty)
- Reads: `content_pieces.thumbnail_concept` — past thumbnail concepts for consistency

**Elastic MCP usage:**
- Reads: `competitor_content.thumbnail_style` — what thumbnail styles work in the niche

**Key fix:** `viral_patterns` is currently always `[]` because `load_profile_node` hardcodes it. With MongoDB memory, this is populated from real data.

---

## SEO Agents (Upload Workflow)

**Inputs:** `topic`, `script`, `seo_title`, `plan`, `creator_memory` (NEW), `keyword_performance` (NEW)

**MongoDB MCP usage:**
- Reads: `creator_memory.successful_title_patterns` — title structure that worked
- Reads: `content_pieces.seo` — past SEO metadata

**Elastic MCP usage:**
- Reads: `keyword_performance` — which specific keywords drove views for this channel
- Reads: `competitor_content` — competitor tags and titles in this niche

**Data saved:**
- After upload: SEO metadata + YouTube performance metrics saved to `keyword_performance` index

---

## UploadAgent

**Data saved after successful upload:**
- Updates `content_pieces` with `youtube_video_id`
- Schedules performance polling job (views, CTR, watch time after 7 days)
- Queues `keyword_performance` update when analytics come in

---

# TASK 6 — New Agents

## Recommended: Yes

### Trend Intelligence Agent

**Should it exist:** Yes. This is the entry point for Elastic MCP visibility to judges.

**Where it belongs:** Background job that runs on a schedule (daily or weekly), not in the real-time content generation graph.

**What it does:** Queries trending topics from Elastic, compares against the creator's niche and topic history, identifies gaps and opportunities, and saves a "trend brief" to MongoDB that ResearchAgent reads on next run.

**Expected impact:** Every content generation session starts with current trend awareness. Judges see Elastic MCP being used for genuine intelligence, not just search.

**Implementation complexity:** Medium. The agent itself is simple — it's mostly Elastic queries and a MongoDB write. The complexity is setting up the scheduler (APScheduler or Celery beat) and the Elastic index population pipeline.

---

### Content Gap Agent

**Should it exist:** Yes. This is the most impressive demo-able feature.

**Where it belongs:** Runs once after `load_memory_node`, before ResearchAgent. Or as a standalone endpoint `POST /agent/content-gap-analysis`.

**What it does:** Reads the creator's topic history (MongoDB) + audience questions (Elastic) + competitor content (Elastic). Identifies: topics the audience asks about that the creator hasn't covered, topics competitors cover that the creator doesn't, topics that are trending but underserved in the niche.

**Output:** A ranked list of content opportunities, written to `creator_memory.content_gaps`.

**Expected impact:** This is a genuinely useful feature for real creators. It's also exactly what a hackathon judge wants to see — a system that gets smarter over time by learning from multiple data sources.

**Implementation complexity:** Medium-high. Requires Elastic to have populated competitor content. But the demo can be seeded with mock competitor data.

---

### Critic Agent

**Should it exist:** Yes, but scoped correctly.

**Where it belongs:** After ScriptAgent, as a quality gate before save_generation.

**What it does:** Reviews the generated script against: (a) the creator's quality standards from past content, (b) known weak patterns (too long, weak hook, no CTA), (c) factual consistency with research. Returns a structured critique with a quality score. If score < threshold, routes back to ScriptAgent with the critique.

**Expected impact:** Prevents saving obviously weak content. Creates a visible quality loop that judges can see in the graph.

**Implementation complexity:** Low. One LLM call with a structured output schema. The graph routing (conditional edge back to ScriptAgent) is slightly more complex but manageable.

---

### Competitor Analysis Agent

**Should it exist:** As a background job, yes. As a real-time agent in the content workflow, no.

**Reason:** Competitor data ingestion is too slow for real-time. Running it in the background and having the data ready in Elastic for all other agents is the right architecture.

**Where it belongs:** `app/jobs/competitor_ingestion.py` — runs on schedule, writes to `competitor_content` Elastic index.

---

### Performance Prediction Agent

**Should it exist:** Not in v1. Save for v2 after real performance data exists.

**Reason:** Predictions require historical data. With 0 videos on the channel currently, any "prediction" is hallucinated. Build this when you have 10+ uploaded videos with real view data.

---

### Audience Insight Agent

**Should it exist:** Yes, but as part of YouTubeResearchAgent's extended capability, not a separate agent.

**What it does:** Analyzes YouTube comments from existing videos (YouTube Data API v3 has a `commentThreads().list()` endpoint). Extracts questions, frustrations, and topic requests. Saves to `creator_memory.audience_intelligence` and indexes to `audience_questions` Elastic index.

**Where it belongs:** Extend `YouTubeResearchAgent.run()` to also fetch and analyze comments when available.

---

# TASK 7 — Redesigned LangGraph Workflow

## New content generation graph

```
load_memory_node
  ↓ [MongoDB MCP: read creator_memory]

content_gap_check_node (NEW)
  ↓ [Elastic MCP: check what topics are uncovered]
  ↓ [MongoDB MCP: read topic_history]

research_node (enhanced)
  ↓ [Elastic MCP: trending_topics in niche]
  ↓ [MongoDB MCP: read audience_intelligence]
  ↓ LLM call with enriched context
  ↓ [MongoDB MCP: write research_session]

HITL #1 — human_approval_node
  ↓ (approved)

idea_node (enhanced)
  ↓ [Elastic MCP: competitor_content in niche]
  ↓ [Elastic MCP: content_index similarity check]
  ↓ [MongoDB MCP: read successful_title_patterns]
  ↓ LLM call with enriched context

HITL #2 — idea_selection_node

script_node (enhanced)
  ↓ [MongoDB MCP: read successful_hooks]
  ↓ [Elastic MCP: audience_questions for this topic]
  ↓ LLM call with enriched context

critic_node (NEW)
  ↓ [Quality gate — score >= 7/10 to continue]
  ↓ (if score < 7: route back to script_node with critique)

thumbnail_node (enhanced)
  ↓ [MongoDB MCP: read viral_patterns — NOW POPULATED]
  ↓ LLM call with enriched context

save_generation_node (enhanced)
  ↓ [PostgreSQL: save generation record]
  ↓ [MongoDB MCP: update content_pieces]
  ↓ [MongoDB MCP: update topic_history in creator_memory]
  ↓ [Elastic MCP: index new content for future dedup]
```

## State additions

```python
class AgentState(TypedDict, total=False):
    # ... existing fields ...

    # Memory (NEW)
    creator_memory: dict          # full MongoDB creator_memory document
    successful_hooks: list[str]   # from creator_memory
    viral_patterns: list[str]     # from creator_memory (currently always [])
    topic_history: list[str]      # from creator_memory
    successful_title_patterns: list[str]

    # Intelligence (NEW)
    trending_topics: list[dict]   # from Elastic
    competitor_insights: list[dict] # from Elastic
    content_gaps: list[str]       # from ContentGapAgent
    similar_past_content: list[dict] # from Elastic dedup check

    # Evaluation (NEW)
    script_quality_score: float
    script_critique: str
    script_revision_count: int
```

---

# TASK 8 — File Structure

```
backend/app/

memory/
├── __init__.py
├── mongo_client.py              # MongoDB MCP connection + tool definitions
├── creator_memory_service.py    # CRUD for creator_memory collection
├── research_memory_service.py   # save/query research_sessions
├── content_memory_service.py    # save/query content_pieces
└── performance_memory_service.py # update performance signals post-upload

mcp/
├── __init__.py
├── mongodb/
│   ├── __init__.py
│   ├── client.py               # MongoDB MCP client wrapper
│   ├── tools.py                # MCP tool definitions (find, insert, update, aggregate)
│   └── schemas.py              # Collection schemas as Pydantic models
└── elastic/
    ├── __init__.py
    ├── client.py               # Elastic MCP client wrapper
    ├── tools.py                # MCP tool definitions (search, index, suggest)
    └── indexes.py              # Index mappings (trending_topics, competitor_content, etc.)

agents/
├── research_agent.py           # MODIFY: add trending + memory context
├── video_idea_agent.py         # MODIFY: add competitor + dedup context
├── script_agent.py             # MODIFY: add successful_hooks context
├── thumbnail_agent.py          # MODIFY: fix viral_patterns (currently always [])
├── seo_agent.py                # unchanged
├── upload_optimizer_agent.py   # unchanged
├── creator_profile_agent.py    # MODIFY: also write to MongoDB memory
├── youtube_research_agent.py   # MODIFY: also fetch comments for audience intel
├── critic_agent.py             # CREATE: quality gate
├── trend_agent.py              # CREATE: background trend intelligence
├── content_gap_agent.py        # CREATE: content opportunity finder
└── README.md

graph/
├── workflow.py                 # MODIFY: add memory/intelligence nodes
├── upload_workflow.py          # MODIFY: add keyword performance memory
├── creator_profile_workflow.py # MODIFY: also init MongoDB memory doc
├── state.py                    # MODIFY: add memory + intelligence fields
├── checkpointer.py             # unchanged

jobs/
├── __init__.py
├── trend_ingestion.py          # Scheduled: fetch trends → Elastic
├── competitor_ingestion.py     # Scheduled: scrape competitors → Elastic
└── performance_polling.py      # Scheduled: poll YouTube analytics → update records

services/
├── generation_service.py       # unchanged
├── upload_service.py           # MODIFY: trigger performance polling after upload
├── profile_service.py          # MODIFY: also init MongoDB memory on first profile
├── youtube_service.py          # unchanged
├── qwen_service.py             # unchanged
├── model_router.py             # unchanged
└── gemini_service.py           # unchanged (unused, cleanup optional)

models/
├── user.py                     # unchanged
├── creator_profile.py          # unchanged
├── youtube_account.py          # unchanged
├── youtube_video.py            # unchanged
├── generation.py               # unchanged
├── upload_record.py            # unchanged
├── plan.py                     # unchanged
├── thread.py                   # unchanged
└── project.py                  # unchanged
```

---

# TASK 9 — Implementation Plan

## Phase 1 — MongoDB MCP Integration (3-4 days)

**Goal:** Creator memory system live. `viral_patterns` and `successful_hooks` actually populated. `topic_history` preventing duplicate research.

**Files to create:**
- `app/mcp/mongodb/client.py`
- `app/mcp/mongodb/tools.py`
- `app/mcp/mongodb/schemas.py`
- `app/memory/mongo_client.py`
- `app/memory/creator_memory_service.py`
- `app/memory/research_memory_service.py`
- `app/memory/content_memory_service.py`

**Files to modify:**
- `app/graph/workflow.py` — replace `load_profile_node` with `load_memory_node`
- `app/graph/state.py` — add `creator_memory`, `viral_patterns`, `successful_hooks`, `topic_history`
- `app/agents/creator_profile_agent.py` — after saving to PostgreSQL, also write to MongoDB
- `app/graph/workflow.py` — update `save_generation_node` to write to MongoDB

**Estimated effort:** 3-4 days of focused work.

**Expected impact:** Immediately fixes the `viral_patterns: []` bug. Memory system visible in architecture. Judges can see MongoDB MCP being used for genuine persistence, not just a store.

---

## Phase 2 — Elastic MCP Integration (3-4 days)

**Goal:** Trend intelligence and content dedup live. Research Agent enriched with trending data.

**Files to create:**
- `app/mcp/elastic/client.py`
- `app/mcp/elastic/tools.py`
- `app/mcp/elastic/indexes.py`
- `app/jobs/trend_ingestion.py`

**Files to modify:**
- `app/agents/research_agent.py` — add trending topics context
- `app/agents/video_idea_agent.py` — add competitor context + dedup check
- `app/graph/workflow.py` — add Elastic calls to research and idea nodes

**Estimated effort:** 3-4 days.

**Expected impact:** Research is enriched with real trend data. IdeaAgent avoids duplicates. Judges see Elastic being used for actual search intelligence.

---

## Phase 3 — Memory-Aware Agents (2 days)

**Goal:** All agents read from creator memory. Prompts are dramatically enriched.

**Files to modify:**
- All agent files — add memory context to prompts
- `app/graph/state.py` — add all new memory fields

**Estimated effort:** 2 days.

**Expected impact:** Visible improvement in output quality. Each run builds on the last.

---

## Phase 4 — Intelligence Layer (2-3 days)

**Goal:** Critic Agent, Content Gap Agent, Trend Agent live.

**Files to create:**
- `app/agents/critic_agent.py`
- `app/agents/content_gap_agent.py`
- `app/agents/trend_agent.py`

**Files to modify:**
- `app/graph/workflow.py` — add critic node with conditional retry edge

**Estimated effort:** 2-3 days.

**Expected impact:** Demonstrably more sophisticated graph. Critic Agent creates a visible quality loop. Content Gap Agent is the most impressive demo feature.

---

## Phase 5 — Performance Intelligence (2 days, post-launch)

**Goal:** System learns from upload performance. Keywords that drove views are remembered.

**Files to create:**
- `app/jobs/performance_polling.py`
- `app/memory/performance_memory_service.py`

**Files to modify:**
- `app/services/upload_service.py` — trigger polling job after upload

**Estimated effort:** 2 days.

**Expected impact:** The system gets measurably smarter with each uploaded video. This is the long-term differentiator but requires real video data to demonstrate.

---

# TASK 10 — Hackathon Strategy

## Current project score: 7.5/10

**What judges will love about the current project:**
- Production-grade HITL with PostgreSQL checkpointing (non-trivial, impressive)
- Provider abstraction ready for MCP (shows foresight)
- Real YouTube OAuth with PKCE (not mock)
- 30-check automated health verification (professional)
- Clean agent separation, documented architecture

**What judges will penalize:**
- Zero MCP integration (the hackathon "strongly rewards" MCP)
- Memory system that doesn't actually remember (viral_patterns: [] is embarrassing if caught)
- No trend intelligence (static system)
- No competitor awareness

---

## After Phase 1 (MongoDB MCP): 8.5/10

The memory system alone moves the needle significantly. When a judge asks "does this system learn?" the answer changes from "it stores the profile" to "it maintains a growing knowledge base per creator across every session — research history, successful hooks, viral patterns, audience intelligence — all via MongoDB MCP." That's a fundamentally different demo.

---

## After Phase 2 (Elastic MCP): 9/10

Two MCPs in active use. Research Agent demonstrably enriched by trending data. IdeaAgent avoids generating content the creator already made. The architecture diagram shows data flowing through both MCP systems in every workflow run.

---

## After full implementation: 9.5/10

The Content Gap Agent is the demo centerpiece. You show a judge: "this system analyzed our creator's topic history, their audience's questions, and competitor content in the niche, and identified 5 specific topics the audience wants that no competitor has covered yet." That's a $1,000+/month SaaS feature, not a hackathon toy.

---

## What to prioritize for the demo

**Build these first:**
1. MongoDB MCP creator memory (Phase 1) — most visible MCP usage
2. Fix `viral_patterns: []` bug — always-empty fields are embarrassing if a judge reads the code
3. Content Gap Agent — single most impressive demo-able feature
4. Trend intelligence (even with seeded data) — Elastic MCP visibility

**Remove or hide these:**
- `gemini_service.py` — unused dead code, clean it up or it signals carelessness
- Empty `.txt` prompt files in `app/prompts/` — either use them or delete them
- `upload_optimizer_agent.py` — superseded by upload workflow SEO agents, confusing duplication

**What to emphasize in the pitch:**
- "This is not a content generator. It's a content operating system that gets smarter every time the creator uses it."
- Show the MongoDB memory growing across sessions in a live demo
- Show the Content Gap Agent identifying opportunities that competitors haven't covered
- Show the Elastic trend intelligence enriching research in real time

**The single most important demo moment:** Run the workflow twice on similar topics. Show that the second run knows about the first, avoids repetition, and builds on what was learned. No other hackathon submission will be able to show that.
