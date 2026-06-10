"""
app/routes/upload.py

File upload endpoints — let users upload video and thumbnail files
to the server before triggering the YouTube publish workflow.

Endpoints:
  POST /upload/video      — upload a .mp4/.mov file, returns server path
  POST /upload/thumbnail  — upload a .jpg/.png file, returns server path
  GET  /upload/files      — list user's uploaded files
  DELETE /upload/files/{filename} — delete an uploaded file
"""
import os
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["file-upload"])

# ── Upload directory ──────────────────────────────────────────────
UPLOAD_BASE = Path("uploads")

# Expanded MIME types — browsers/OS report these inconsistently
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",          # .mov
    "video/x-msvideo",          # .avi
    "video/x-matroska",         # .mkv
    "video/matroska",           # .mkv (alternate)
    "video/webm",
    "video/mpeg",
    "video/ogg",
    "video/3gpp",
    "application/octet-stream", # Windows fallback for unknown binary files
    "application/x-matroska",   # .mkv on some systems
}

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".3gp"}

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/octet-stream", # Windows fallback
}

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MAX_VIDEO_SIZE_MB     = 2048   # 2 GB
MAX_THUMBNAIL_SIZE_MB = 5      # 5 MB


def _user_dir(user_id: int) -> Path:
    """Return (and create) the upload directory for a user."""
    path = UPLOAD_BASE / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(original: str, prefix: str = "") -> str:
    """Generate a unique filename keeping the original extension."""
    ext  = Path(original).suffix.lower()
    name = f"{prefix}{uuid.uuid4().hex}{ext}"
    return name


def _is_valid_video(file: UploadFile) -> bool:
    """
    Validate by content_type OR file extension.
    Windows often sends application/octet-stream for video files,
    so we accept the file if either check passes.
    """
    content_type_ok = file.content_type in ALLOWED_VIDEO_TYPES
    ext = Path(file.filename or "").suffix.lower()
    extension_ok = ext in ALLOWED_VIDEO_EXTENSIONS
    return content_type_ok or extension_ok


def _is_valid_image(file: UploadFile) -> bool:
    """Validate by content_type OR file extension."""
    content_type_ok = file.content_type in ALLOWED_IMAGE_TYPES
    ext = Path(file.filename or "").suffix.lower()
    extension_ok = ext in ALLOWED_IMAGE_EXTENSIONS
    return content_type_ok or extension_ok


# ── Video upload ──────────────────────────────────────────────────

@router.post("/video")
async def upload_video_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a video file to the server.

    Returns the server-side file path to use in
    POST /workflow/upload/start as video_file_path.

    Supported formats: .mp4, .mov, .avi, .mkv, .webm
    Max size: 2 GB
    """
    if not _is_valid_video(file):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type} ({Path(file.filename or '').suffix}). "
                   f"Allowed: mp4, mov, avi, mkv, webm"
        )

    user_dir = _user_dir(current_user.id)
    filename = _safe_filename(file.filename or "video.mp4", prefix="video_")
    file_path = user_dir / filename

    # Stream to disk in chunks to handle large files
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                buffer.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    # Check final size
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {size_mb:.0f}MB. Max: {MAX_VIDEO_SIZE_MB}MB"
        )

    abs_path = str(file_path.resolve())
    print(f"[upload] video saved: {abs_path} ({size_mb:.1f}MB)")

    return {
        "filename":         filename,
        "original_name":    file.filename,
        "size_mb":          round(size_mb, 2),
        "content_type":     file.content_type,
        "video_file_path":  abs_path,
        "message":          "Video uploaded. Use video_file_path in POST /workflow/upload/start"
    }


# ── Thumbnail upload ──────────────────────────────────────────────

@router.post("/thumbnail")
async def upload_thumbnail_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a thumbnail image to the server.

    Returns the server-side file path to use in
    POST /workflow/upload/start as thumbnail_file_path.

    Supported formats: .jpg, .png, .webp
    Max size: 5 MB (YouTube limit)
    """
    if not _is_valid_image(file):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type} ({Path(file.filename or '').suffix}). "
                   f"Allowed: jpg, png, webp"
        )

    user_dir  = _user_dir(current_user.id)
    filename  = _safe_filename(file.filename or "thumbnail.jpg", prefix="thumb_")
    file_path = user_dir / filename

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_THUMBNAIL_SIZE_MB:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Thumbnail too large: {size_mb:.1f}MB. YouTube max is {MAX_THUMBNAIL_SIZE_MB}MB"
        )

    abs_path = str(file_path.resolve())
    print(f"[upload] thumbnail saved: {abs_path} ({size_mb:.2f}MB)")

    return {
        "filename":              filename,
        "original_name":         file.filename,
        "size_mb":               round(size_mb, 3),
        "content_type":          file.content_type,
        "thumbnail_file_path":   abs_path,
        "message":               "Thumbnail uploaded. Use thumbnail_file_path in POST /workflow/upload/start"
    }


# ── List user files ───────────────────────────────────────────────

@router.get("/files")
def list_uploaded_files(
    current_user: User = Depends(get_current_user),
):
    """List all files uploaded by the current user."""
    user_dir = _user_dir(current_user.id)
    files = []
    for f in sorted(user_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            stat = f.stat()
            files.append({
                "filename":   f.name,
                "size_mb":    round(stat.st_size / (1024 * 1024), 2),
                "full_path":  str(f.resolve()),
                "type":       "video" if f.suffix in (".mp4", ".mov", ".avi", ".mkv") else "image",
                "created_at": stat.st_mtime,
            })
    return {"user_id": current_user.id, "files": files, "count": len(files)}


# ── Delete file ───────────────────────────────────────────────────

@router.delete("/files/{filename}")
def delete_uploaded_file(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """Delete an uploaded file. Only the file owner can delete their files."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = _user_dir(current_user.id) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    file_path.unlink()
    return {"deleted": True, "filename": filename}
