# Agents

Every agent in AI Content Studio is a **stateless Python function** that takes structured inputs, builds a personalized prompt, calls the LLM, and returns structured output. Agents have no database access and no side effects — those responsibilities belong to the workflow nodes that call them.

---

## Shared Personalization Layer

All content agents use `_profile_context()` from `research_agent.py` to inject the creator's profile into their prompt. This function converts the profile dict into a compact context block:

```
CREATOR PROFILE (use this to personalize your output):
- Niche: General Learning, Study Skills
- Topics: Python, Data Science, Machine Learning
- Audience: students and self-learners seeking foundational knowledge
- Audience Level: beginner
- Title Style: neutral and aspirational
- Description Style: empty or minimal
- Content Strengths: (none specified)
- Viral Patterns: (none specified)
```

This block is injected at the top of every agent's system prompt. Every agent sees the same creator context. The LLM uses it to calibrate vocabulary, complexity, examples, and tone.

---

## Model Routing

All agents call `get_model(plan, task)` from `services/model_router.py` to select the LLM before making the API call.

| Plan | Model Used |
|------|-----------|
| `normal` | `qwen-plus` for all tasks |
| `pro` | `qwen-plus` for all tasks |
| `plus` | `qwen-max` for research and script; `qwen-plus` for others |

The `plus` plan uses `qwen-max` for research and script generation because those tasks benefit most from deeper reasoning. SEO, ideas, and thumbnails don't require the same depth.

---

## Agent Reference

### `research_agent`

**File:** `research_agent.py`

**Purpose:** Research a video topic from the perspective of the creator's specific audience. Returns a structured research report that all downstream agents use as context.

**Function signature:**
```python
def research_agent(
    topic: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> str
```

**Inputs:**
- `topic` — the video topic (e.g. "How to learn Python fast")
- `plan` — model tier, controls which Qwen model is used
- `creator_profile` — full profile dict from `creator_profiles` table

**Output:** Markdown string containing:
1. Main ideas relevant to this creator's audience
2. Trending angles that match their content style
3. Audience pain points specific to their viewers
4. Viral opportunities that fit their channel

**Used by:** `research_node` in `graph/workflow.py`

**Example personalization:** A beginner Python channel gets research about motivation issues, time anxiety, and the overwhelm of conflicting advice. A finance channel targeting professionals gets research about specific investment strategies and regulatory context.

---

### `video_idea_agent`

**File:** `video_idea_agent.py`

**Purpose:** Generate exactly 5 video ideas that match the creator's title style, fit their audience level, and are informed by the research output.

**Function signature:**
```python
def video_idea_agent(
    topic: str,
    research: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> list[str]
```

**Inputs:**
- `topic` — the original video topic
- `research` — full output from `research_agent`
- `plan` — model tier
- `creator_profile` — includes `title_style` for pattern matching

**Output:** List of 5 strings. Each string is a video title + one sentence description.

**Output parsing:** Attempts JSON array parsing first. Falls back to line-by-line parsing (numbered/bulleted lists). Falls back to raw string as last resort. Never crashes.

**Used by:** `idea_node` in `graph/workflow.py`

**Example:** For a creator whose title style is "neutral and aspirational", ideas like *"Learn Python Like You're Learning Spanish — A language-learning approach that makes syntax stick"* rather than generic clickbait.

---

### `script_agent`

**File:** `script_agent.py`

**Purpose:** Write a complete, production-ready YouTube script for a selected video idea. Calibrates vocabulary complexity, tone, and examples to the creator's specific audience.

**Function signature:**
```python
def script_agent(
    topic: str,
    research: str,
    selected_idea: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> str
```

**Inputs:**
- `topic` — original topic
- `research` — research output (used for examples and pain points)
- `selected_idea` — the idea the user chose at HITL #2
- `plan` — model tier
- `creator_profile` — extracts `audience_level`, `audience_type`, and `description_style.tone`

**Output:** Markdown-formatted script with sections:
```
# Hook
# Introduction
# Main Content
# Conclusion
# Call To Action
```

**Used by:** `script_node` in `graph/workflow.py`

**Personalization details:**
- Extracts `audience_level` (beginner/intermediate/advanced) and adjusts vocabulary
- Extracts `audience_type` for example selection
- Extracts `description_style.tone` for overall writing style
- Uses research pain points to create a resonant hook

---

### `thumbnail_agent`

**File:** `thumbnail_agent.py`

**Purpose:** Generate a complete thumbnail brief and AI image generation prompt tailored to the creator's brand and viral patterns.

**Function signature:**
```python
def thumbnail_agent(
    topic: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> str
```

**Inputs:**
- `topic` — original topic
- `script` — full script (used to extract the hook and key visual moments)
- `plan` — model tier
- `creator_profile` — extracts `viral_patterns` and `audience.audience_type`

**Output:** Markdown string with five sections:
1. **Thumbnail Text** — short overlay text (3-5 words)
2. **Thumbnail Concept** — visual scene description
3. **Emotion** — psychological trigger (curiosity, urgency, fear of missing out)
4. **Color Suggestions** — brand-appropriate palette
5. **Thumbnail Prompt** — ready-to-paste prompt for Imagen, DALL-E, or Midjourney

**Used by:** `thumbnail_node` in `graph/workflow.py`

**Note:** This agent generates a *concept and prompt*, not an actual image. Image generation (Imagen/DALL-E integration) is on the roadmap.

---

### `seo_agent`

**File:** `seo_agent.py`

**Purpose:** Generate SEO-optimized metadata for a completed video. Used standalone (not in the main content workflow).

**Function signature:**
```python
def seo_agent(
    topic: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> str
```

**Inputs:**
- `topic` — video topic
- `script` — full script
- `plan` — model tier
- `creator_profile` — extracts `main_topics` for tag suggestions and `audience_type` for targeting

**Output:** Markdown string with:
1. SEO Title — matches creator's title style, optimized for search
2. Description — 150-200 words matching their description style
3. 15 Tags — mix of broad and niche tags including their main channel topics
4. 10 Hashtags — relevant to their niche

**Note:** This agent is defined but not called by the main content workflow. SEO generation in the upload workflow is handled directly in the upload workflow nodes (`seo_title_node`, `seo_description_node`, `tags_node`) for finer control over each component. This agent is available for standalone use cases.

---

### `creator_profile_agent`

**File:** `creator_profile_agent.py`

**Purpose:** Analyze a YouTube channel and return a structured creator profile used for personalization.

**Two components in one file:**

**`creator_profile_agent()` function** — the LLM-based analysis:
```python
def creator_profile_agent(
    channel_info: dict,
    videos: list[dict],
    plan: str = "normal",
) -> CreatorProfileOutput
```

**`CreatorProfileAgent` class** — the DB-integrated orchestrator:
```python
class CreatorProfileAgent:
    def fetch_videos(self, user_id, db) -> list
    def save_profile(self, user_id, channel_id, ..., db) -> CreatorProfile
    def run(self, user_id, channel_info, db) -> dict
```

**Output schema (Pydantic validated):**
```python
class CreatorProfileOutput(BaseModel):
    creator_niche: str
    main_topics: list[str]
    audience_type: str
    audience_level: str        # "beginner" | "intermediate" | "advanced" | "mixed"
    title_style: str
    description_style: str
    content_strengths: list[str]
    recommended_video_types: list[str]
    viral_patterns: list[str]
```

**Used by:** `creator_profile_node` in `graph/creator_profile_workflow.py`

**Why Pydantic validation:** The LLM occasionally returns malformed JSON or missing fields. Pydantic catches these before they reach the database, preventing silent data corruption.

---

### `upload_optimizer_agent`

**File:** `upload_optimizer_agent.py`

**Purpose:** Standalone SEO metadata generation for video uploads. Used by the upload optimizer workflow.

**Function signature:**
```python
def upload_optimizer_agent(
    topic: str,
    script: str,
    plan: str = "normal",
) -> str
```

**Note:** This agent does not use creator profile personalization. It is a simpler, profile-agnostic alternative to the `seo_agent` for cases where personalization is not needed.

**Output:** Markdown string with title, description (100 words max), 10 tags, 5 hashtags.
