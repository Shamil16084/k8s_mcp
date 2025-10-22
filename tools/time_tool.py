from fastapi import APIRouter
from datetime import datetime

# Metadata
name = "get_current_time"
description = "Returns the current hour, minute, and second."
endpoint = f"/tools/{name}"

# Create a router for this tool
router = APIRouter()

@router.post(endpoint)
def get_current_time():
    now = datetime.now()
    return {
        "hour": now.hour,
        "minute": now.minute,
        "second": now.second
    }

# This function will be called by the main server to register this tool
def register(app):
    app.include_router(router)
