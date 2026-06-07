# MCP Integration

AI Content Studio is designed from the ground up to support Model Context Protocol (MCP) servers as a first-class integration layer. The provider abstraction in `app/youtube_provider/` is the foundation of this design.

---

## What MCP Means for This Project

MCP (Model Context Protocol) is an open standard that allows AI agents to connect to external tools and data sources through a standardized interface. For a content creation platform, MCP servers can replace direct API integrations with tool-calling interfaces that agents can use naturally.

Instead of:
```python
youtube = build("youtube", "v3", credentials=credentials)
response = youtube.videos().insert(...)
```

An MCP-enabled agent calls:
```
tool: upload_video
input: {title, description, tags, video_path}
```

The MCP server handles authentication, rate limiting, and error handling. The agent doesn't know or care how the upload works — it just calls a tool.

---

## Current Provider Architecture

The upload workflow uses a provider abstraction that makes MCP activation a configuration change, not a code change.

```
app/youtube_provider/
├── __init__.py                  ← Factory function: picks MCP or API
├── base.py                      ← Abstract interface
├── youtube_api_provider.py      ← YouTube Data API v3 implementation
└── youtube_mcp_provider.py      ← MCP implementation (stub)
```

### Abstract Interface (`base.py`)

```python
class YouTubeProviderBase(ABC):
    @abstractmethod
    def upload_video(self, video_file_path, title, description,
                     tags, category_id, privacy_status) -> dict: ...

    @abstractmethod
    def upload_thumbnail(self, video_id, thumbnail_path) -> dict: ...

    @abstractmethod
    def refresh_credentials(self) -> bool: ...
```

The upload workflow nodes call only methods on this interface. They never import `YouTubeAPIProvider` or `YouTubeMCPProvider` directly.

### Factory (`__init__.py`)

```python
def get_youtube_provider(user_id: int, db) -> YouTubeProviderBase:
    mcp_url = os.getenv("YOUTUBE_MCP_URL", "")
    if mcp_url:
        return YouTubeMCPProvider(mcp_url=mcp_url, user_id=user_id)
    return YouTubeAPIProvider(user_id=user_id, db=db)
```

**To activate MCP:** Set `YOUTUBE_MCP_URL=https://your-mcp-server/sse` in `.env`. No code changes required.

---

## YouTube Data API Provider

The current production implementation. Handles the full upload lifecycle.

**Features:**
- OAuth token management with automatic refresh
- Resumable video upload (`MediaFileUpload` with 5MB chunks)
- Retry logic (up to 3 attempts, exponential backoff)
- Differentiated retry behavior (no retry on 4xx, retry on 5xx)
- Thumbnail upload with mime-type detection
- Category name → YouTube category ID mapping

**Location:** `app/youtube_provider/youtube_api_provider.py`

---

## YouTube MCP Provider (Stub)

The MCP provider stub is in `app/youtube_provider/youtube_mcp_provider.py`. It implements the same interface but raises `NotImplementedError` for all methods.

**To implement when a YouTube MCP server is available:**

```python
class YouTubeMCPProvider(YouTubeProviderBase):
    def upload_video(self, video_file_path, title, description,
                     tags, category_id, privacy_status) -> dict:
        response = requests.post(
            f"{self.mcp_url}/tools/upload_video",
            json={
                "video_path": video_file_path,
                "title": title,
                "description": description,
                "tags": tags,
                "category_id": category_id,
                "privacy_status": privacy_status,
            }
        )
        return response.json()
```

The MCP server manages its own OAuth credentials — the provider doesn't need access to the `YouTubeAccount` DB row, which is why `YouTubeMCPProvider.__init__` doesn't take a `db` parameter.

---

## Future MCP Integrations

The provider pattern will be extended to other services as MCP servers become available.

### Google Drive MCP

**Purpose:** Store generated video files, thumbnails, and scripts in Google Drive rather than the local filesystem.

**Current:** Video file paths are local absolute paths passed to `/workflow/upload/start`.

**With Drive MCP:**
```python
class GoogleDriveProvider:
    def get_file(self, drive_file_id: str) -> bytes: ...
    def save_file(self, name: str, content: bytes) -> str: ...
```

The upload workflow would accept a `drive_file_id` instead of a local path.

### Google Calendar MCP

**Purpose:** Schedule video uploads at optimal posting times.

**Current:** `scheduled_at` field exists in `UploadState` but is not implemented.

**With Calendar MCP:**
```python
class CalendarProvider:
    def get_optimal_time(self, channel_id: str, day_of_week: str) -> str: ...
    def schedule_upload(self, video_id: str, publish_at: str) -> bool: ...
```

### MongoDB MCP (Analytics)

**Purpose:** Store and query video performance data from YouTube Analytics API.

**Why MongoDB for this use case:** Video analytics are time-series data with variable fields (different metrics available for different video ages). Document storage handles this better than relational tables.

**Planned agent:** `AnalyticsAgent` — reads historical performance from MongoDB, identifies what content performs best, feeds insights back into the creator profile.

---

## Why MCP Matters for Agentic Systems

In a traditional API integration, the developer writes code that calls specific endpoints. The agent doesn't understand what it's doing — it just executes the code.

In an MCP-enabled system, the agent has access to a **tool registry**. It can:
1. Discover what tools are available
2. Decide which tool to call based on the task
3. Interpret the result and decide next steps

This is the difference between a scripted automation and a genuinely autonomous agent. The LangGraph nodes in this project are currently scripted — they always call the same tools in the same order. With MCP tool discovery, a future version of the workflow could be more dynamic:

```
Research Agent: "I need to find trending topics. Let me check what tools are available."
→ discovers: youtube_analytics_tool, google_trends_tool, reddit_search_tool
→ calls all three, synthesizes results
→ returns personalized research that no scripted agent could produce
```

The provider abstraction in this codebase is the first step toward that future.

---

## Activation Checklist

| Integration | Status | Activation |
|---|---|---|
| YouTube Data API | ✅ Active | Default |
| YouTube MCP | 🔧 Stub ready | Set `YOUTUBE_MCP_URL` in `.env` |
| Google Drive MCP | 📋 Planned | Implement `DriveProvider` |
| Google Calendar MCP | 📋 Planned | Implement `CalendarProvider` |
| MongoDB MCP | 📋 Planned | Implement `AnalyticsProvider` |
