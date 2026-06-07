# Prompts

All prompts in AI Content Studio are **embedded directly in agent functions** rather than stored in external files. This is an intentional design decision: prompts reference dynamic variables (creator profile, topic, research output) that make static template files impractical.

The `.txt` files in this directory (`research.txt`, `script.txt`, etc.) are empty placeholders left from an earlier version of the architecture. They are not used.

---

## Why Prompts Are Embedded in Agents

In a simple LLM app, static prompt files work well. In a multi-agent pipeline with personalization, prompts need to:

1. Inject dynamic creator profile context (audience level, title style, viral patterns)
2. Include previous agent outputs (research → ideas → script chain)
3. Specify exact JSON schemas for structured outputs
4. Adapt based on plan tier (which model is being called)

This makes f-string prompts in Python functions the most maintainable approach. The prompt and its variables are co-located, making it easy to understand what the LLM receives.

---

## Prompt Inventory

### Research Prompt

**Location:** `agents/research_agent.py` → `research_agent()`

**Used by:** `research_node` in content generation workflow

**When called:** First LLM call after creator profile is loaded. Runs before any HITL checkpoint.

**Model:** `qwen-plus` (normal/pro), `qwen-max` (plus)

**Structure:**
```
You are a YouTube research expert helping a specific creator.

{creator_profile_context}

Research this topic for the creator above. Tailor insights to their audience level and niche.

Topic: {topic}

Return:
1. Main ideas relevant to this creator's audience
2. Trending angles that match their content style
3. Audience pain points specific to their viewers
4. Viral opportunities that fit their channel
```

**Personalization variables:** Full creator profile context block (niche, topics, audience type, audience level, title style, description style, content strengths, viral patterns).

**Expected output:** Free-form markdown. No structured format required — this is context for the next agents, not a structured data output.

**Design note:** The prompt explicitly asks for audience-specific pain points and channel-specific viral opportunities. A generic research prompt returns generic results. The creator profile context forces the LLM to think about the specific audience.

---

### Video Idea Prompt

**Location:** `agents/video_idea_agent.py` → `video_idea_agent()`

**Used by:** `idea_node` in content generation workflow

**When called:** After user approves research at HITL #1.

**Model:** `qwen-plus` for all tiers

**Structure:**
```
You are a YouTube strategist working for a specific creator.

{creator_profile_context}

Topic: {topic}

Research:
{research_output}

Generate exactly 5 viral video ideas personalized for this creator.
Match their title style: "{title_style}"
Make ideas fit their audience level and niche — not generic YouTube advice.

Return ONLY a JSON array of exactly 5 strings. No markdown, no explanation, no preamble.
Each string is one complete video idea title + one sentence description.

Example format:
["Idea one title — one sentence why it works", ...]
```

**Personalization variables:** Creator profile context, plus `title_style` extracted separately and included explicitly in the instruction.

**Expected output:** JSON array of exactly 5 strings. The parser handles malformed output with two fallbacks (line-by-line parsing, then raw string).

**Design note:** The JSON output format is specified with an example. LLMs follow examples more reliably than abstract descriptions. The `title_style` is included twice — once in the profile context and once explicitly in the instruction — because it's the most important personalization signal for this agent.

---

### Script Prompt

**Location:** `agents/script_agent.py` → `script_agent()`

**Used by:** `script_node` in content generation workflow

**When called:** After user selects an idea at HITL #2. Most expensive LLM call in the pipeline.

**Model:** `qwen-plus` (normal/pro), `qwen-max` (plus)

**Structure:**
```
You are an expert YouTube script writer working for a specific creator.

{creator_profile_context}

Original Topic: {topic}
Selected Video Idea: {selected_idea}

Research:
{research_output}

Write a complete YouTube script tailored to:
- Audience: {audience_type}
- Level: {audience_level} — adjust complexity and vocabulary accordingly
- Tone: {tone}

Requirements:
- Strong hook in first 15 seconds that grabs THIS creator's specific audience
- Clear introduction that matches their channel style
- Main content with multiple sections at the right complexity level
- Real examples that resonate with this audience
- Conversational tone matching the creator's style
- Strong CTA at the end

Format:
# Hook
# Introduction
# Main Content
# Conclusion
# Call To Action
```

**Personalization variables:** Full profile context + `audience_type`, `audience_level`, and `tone` extracted individually and included as explicit constraints. The phrase *"THIS creator's specific audience"* in the hook requirement forces the LLM to stay in the context of the personalization.

**Expected output:** Markdown-formatted script with five required sections. No JSON parsing — the output is stored as-is.

---

### Thumbnail Prompt

**Location:** `agents/thumbnail_agent.py` → `thumbnail_agent()`

**Used by:** `thumbnail_node` in content generation workflow

**When called:** After script is generated. Last agent in the content generation pipeline.

**Model:** `qwen-plus` for all tiers

**Structure:**
```
You are a YouTube thumbnail expert working for a specific creator.

{creator_profile_context}

Topic: {topic}
Script: {script}

This creator's viral patterns: {viral_patterns}
Target audience: {audience_type}

Design a thumbnail that fits this creator's channel style and will appeal to their specific audience.

Generate:
1. Thumbnail Text — short, punchy, matches creator's title style
2. Thumbnail Concept — visual description tailored to their audience
3. Emotion — the emotion this thumbnail should trigger in their viewers
4. Color Suggestions — colors that match their channel brand/niche
5. Thumbnail Prompt — detailed AI image generation prompt for this specific creator
```

**Personalization variables:** Full profile context, plus `viral_patterns` and `audience_type` extracted separately. The `viral_patterns` field is the key signal — it tells the LLM what visual patterns have worked on this channel historically.

**Expected output:** Markdown with five numbered sections. Output is stored as-is in the `thumbnail` field of the generation record.

---

### Creator Profile Prompt

**Location:** `agents/creator_profile_agent.py` → `creator_profile_agent()`

**Used by:** `creator_profile_node` in creator profile workflow

**When called:** When user hits `POST /creator-profile/generate`.

**Model:** `qwen-plus` for all tiers

**Structure:**
```
You are an expert YouTube channel analyst.

Analyze the following YouTube creator and return a JSON profile.

=== CHANNEL INFO ===
Name: {channel_name}
Subscribers: {subscribers}
Total Views: {total_views}
Video Count: {video_count}
Description: {description}

=== RECENT VIDEOS ({n} sampled) ===
- "{title}" | views: {views} | likes: {likes} | comments: {comments}
...

=== INSTRUCTIONS ===
Return ONLY a valid JSON object. No markdown. No explanation. No preamble.
Use exactly these field names and types:

{
  "creator_niche": "string",
  "main_topics": ["string", ...],
  "audience_type": "string",
  "audience_level": "string — one of: beginner, intermediate, advanced, mixed",
  "title_style": "string",
  "description_style": "string",
  "content_strengths": ["string", ...],
  "recommended_video_types": ["string", ...],
  "viral_patterns": ["string", ...]
}
```

**Key design decisions:**
- The exact JSON schema is specified in the prompt (field names, types, valid enum values for `audience_level`). This dramatically reduces malformed output compared to asking for "a JSON profile" without a schema.
- `audience_level` is constrained to four values to prevent creative variations like "complete beginners" or "somewhat advanced" that would break downstream logic.
- Videos are sampled to the 30 most recent before being sent. The prompt receives only title, views, likes, and comments — not full descriptions — to stay within context limits.

**Expected output:** Valid JSON matching the `CreatorProfileOutput` Pydantic schema. Pydantic validation runs after JSON parsing — if any required field is missing or the wrong type, a `ValueError` is raised with a clear error message before touching the database.

---

### SEO Prompts (Upload Workflow)

The upload workflow uses three separate prompts instead of one combined SEO prompt. Each is in `graph/upload_workflow.py`.

#### SEO Title Prompt

**Used by:** `seo_title_node`

**Instruction:** Generate ONE title under 70 characters with the main keyword near the beginning. Return only the title text — no quotes, no explanation.

**Why separate from description:** Gives the LLM full attention for a single critical output. A combined prompt often produces a weaker title when the description is generated at the same time.

#### SEO Description Prompt

**Used by:** `seo_description_node`

**Instruction:** 150-200 words, opens with the most important information, includes CTA, has `[TIMESTAMPS]` and `[LINKS]` placeholders.

**Context passed:** Topic + generated title + first 1,500 characters of script.

#### Tags Prompt

**Used by:** `tags_node`

**Instruction:** Return structured JSON with exactly 15 tags (no # symbol), exactly 5 hashtags (with # prefix), and a YouTube category name.

**Structured output format:**
```json
{
  "tags": [...],
  "hashtags": [...],
  "category": "Education"
}
```

**Fallback:** If JSON parsing fails, returns `[topic]` for tags, empty list for hashtags, and `"Education"` for category. The workflow continues — a tag failure doesn't abort the upload.

---

## Prompt Version Tracking

The creator profile prompt version is tracked in the `creator_profiles.prompt_version` column (currently `"v1"`). When the profile prompt is improved:

1. Bump `PROMPT_VERSION = "v2"` in `creator_profile_agent.py`
2. New profiles are saved with `prompt_version = "v2"`
3. Query `WHERE prompt_version != 'v2'` to find profiles that need regeneration
4. Old profiles remain valid until explicitly regenerated

Content agent prompts (research, ideas, script, thumbnail) are not versioned yet. This is a future improvement — tracked in the roadmap.
