from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from playgram.db.library import (
    add_tag,
    get_history,
    get_track_by_id,
    list_tags,
    list_tracks,
    remove_tag,
    record_play_event,
    set_rating,
)

router = APIRouter(tags=["library"])


@router.get("/tracks")
def api_list_tracks(tag: str | None = None, rating: int | None = None):
    return {"tracks": list_tracks(tag=tag, rating=rating)}


@router.get("/tags")
def api_list_tags():
    return {"tags": list_tags()}


@router.get("/history")
def api_history(limit: int = 50):
    return {"history": get_history(limit=limit)}


@router.post("/tracks/{track_id}/events")
def api_track_event(track_id: int, event: str):
    if event not in {"play", "ended"}:
        raise HTTPException(status_code=400, detail="event must be 'play' or 'ended'")
    track = get_track_by_id(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    record_play_event(track_id=track_id, event=event)
    return {"ok": True}


@router.post("/tracks/{track_id}/tags")
def api_add_tag(track_id: int, tag: str):
    track = get_track_by_id(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    add_tag(track_id=track_id, tag=tag)
    return {"ok": True}


@router.put("/tracks/{track_id}/rating")
def api_set_rating(track_id: int, rating: int | None = None):
    track = get_track_by_id(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    if rating is not None and not (1 <= rating <= 3):
        raise HTTPException(status_code=400, detail="rating must be 1, 2, or 3")
    set_rating(track_id=track_id, rating=rating)
    return {"ok": True}


@router.delete("/tracks/{track_id}/tags")
def api_remove_tag(track_id: int, tag: str):
    track = get_track_by_id(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    remove_tag(track_id=track_id, tag=tag)
    return {"ok": True}


@router.get("/tracks/{track_id}/stream")
def api_stream(track_id: int):
    track = get_track_by_id(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    path = track["local_path"]
    if not path:
        raise HTTPException(status_code=409, detail="track not downloaded yet")
    return FileResponse(path)
