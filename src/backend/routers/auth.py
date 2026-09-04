"""
Authentication endpoints for the High School Management System API
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Response
from typing import Any, Dict, Optional

from ..database import sessions_collection, teachers_collection, verify_password

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@router.post("/login")
def login(username: str, password: str, response: Response) -> Dict[str, Any]:
    """Login a teacher account"""
    # Find the teacher in the database
    teacher = teachers_collection.find_one({"_id": username})

    # Verify password using Argon2 verifier from database.py
    if not teacher or not verify_password(teacher.get("password", ""), password):
        raise HTTPException(
            status_code=401, detail="Invalid username or password")

    session_token = secrets.token_urlsafe(32)
    sessions_collection.insert_one({
        "_id": session_token,
        "username": teacher["username"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=8),
    })
    response.set_cookie(
        "session_token", session_token, httponly=True, samesite="lax",
        max_age=8 * 60 * 60
    )

    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }


@router.get("/check-session")
def check_session(session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """Check if a session is valid"""
    session = sessions_collection.find_one({
        "_id": session_token,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    }) if session_token else None
    teacher = teachers_collection.find_one(
        {"_id": session["username"]}) if session else None

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }
