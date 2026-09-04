"""
Announcement endpoints for the High School Management System API
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from ..database import (
    announcements_collection,
    sessions_collection,
    teachers_collection,
)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    message: str
    expiration_date: str
    start_date: Optional[str] = None


class AnnouncementUpdate(BaseModel):
    message: Optional[str] = None
    expiration_date: Optional[str] = None
    start_date: Optional[str] = None


def _require_teacher(session_token: Optional[str]) -> Dict[str, Any]:
    """Validate that the session belongs to a teacher/admin"""
    if not session_token:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    session = sessions_collection.find_one({
        "_id": session_token,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    teacher = teachers_collection.find_one(
        {"_id": session["username"]}) if session else None
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid or expired session")

    return teacher


def _validate_dates(start_date: Optional[str], expiration_date: str):
    """Ensure the expiration date is present and, when a start date exists, that it precedes it"""
    if not expiration_date:
        raise HTTPException(
            status_code=400, detail="Expiration date is required")

    try:
        expiration = date.fromisoformat(expiration_date)
        start = date.fromisoformat(start_date) if start_date else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be valid ISO dates")

    if start and start > expiration:
        raise HTTPException(
            status_code=400,
            detail="Start date must be on or before the expiration date")


def _serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    serialized = dict(announcement)
    serialized["id"] = serialized.pop("_id")
    return serialized


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get all announcements that are currently active (public endpoint used for the banner)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today}}
        ]
    }

    return [
        _serialize(announcement)
        for announcement in announcements_collection.find(query).sort("expiration_date", 1)
    ]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(
    session_token: Optional[str] = Cookie(None)
) -> List[Dict[str, Any]]:
    """Get all announcements, including expired/future ones - requires teacher authentication"""
    _require_teacher(session_token)

    return [
        _serialize(announcement)
        for announcement in announcements_collection.find().sort("expiration_date", -1)
    ]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    announcement: AnnouncementCreate,
    session_token: Optional[str] = Cookie(None)
) -> Dict[str, Any]:
    """Create a new announcement - requires teacher authentication"""
    teacher = _require_teacher(session_token)
    _validate_dates(announcement.start_date, announcement.expiration_date)

    new_announcement = {
        "_id": str(uuid.uuid4()),
        "message": announcement.message,
        "start_date": announcement.start_date,
        "expiration_date": announcement.expiration_date,
        "created_by": teacher["username"],
        "created_at": date.today().isoformat()
    }
    announcements_collection.insert_one(new_announcement)

    return _serialize(new_announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    session_token: Optional[str] = Cookie(None)
) -> Dict[str, Any]:
    """Update an existing announcement - requires teacher authentication"""
    _require_teacher(session_token)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates = {
        key: value
        for key, value in announcement.dict(exclude_unset=True).items()
    }

    merged_start_date = updates.get("start_date", existing.get("start_date"))
    merged_expiration_date = updates.get(
        "expiration_date", existing.get("expiration_date"))
    _validate_dates(merged_start_date, merged_expiration_date)

    if updates:
        announcements_collection.update_one(
            {"_id": announcement_id}, {"$set": updates})

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    session_token: Optional[str] = Cookie(None)
) -> Dict[str, str]:
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(session_token)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
