"""Autonomous task endpoints.

POST /autonomous/start        — start a plan-and-execute task
POST /autonomous/{id}/cancel  — cancel a running task
GET  /autonomous/{id}/status  — get current plan state
GET  /autonomous/{id}/stream  — SSE stream of real-time plan events
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import StreamingResponse

from helpers.agents.autonomous_loop import create_loop, get_loop, remove_loop
from helpers.routes.dependencies import get_current_user
from helpers.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/autonomous", tags=["autonomous"])

# In-memory SSE queues: task_id → asyncio.Queue of event dicts
_sse_queues: dict[str, asyncio.Queue] = {}


def _make_event_callback(task_id: str):
    """Return a callback that puts events into the SSE queue."""
    def on_event(data: dict) -> None:
        q = _sse_queues.get(task_id)
        if q:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for task %s", task_id)
    return on_event


@router.post("/start")
async def start_autonomous(
    task: str = Form(...),
    _user: dict = Depends(get_current_user),
):
    """Start an autonomous plan-and-execute task. Returns the task_id."""
    if not task.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task cannot be empty")

    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    callback = _make_event_callback("")  # placeholder — rebound below

    task_id, loop = create_loop(task, lambda d: None)  # create to get id first
    _sse_queues[task_id] = q

    # Now bind the real callback
    loop.on_event = _make_event_callback(task_id)

    async def _run_and_cleanup():
        try:
            await loop.run()
        except Exception as exc:
            logger.exception("Autonomous loop error for task %s", task_id)
            q.put_nowait({"type": "error", "task_id": task_id, "error": str(exc)})
        finally:
            # Signal SSE stream to close
            q.put_nowait({"type": "__done__", "task_id": task_id})

    asyncio.create_task(_run_and_cleanup())
    return {"task_id": task_id}


@router.post("/{task_id}/cancel")
async def cancel_autonomous(
    task_id: str,
    _user: dict = Depends(get_current_user),
):
    """Cancel a running autonomous task."""
    loop = get_loop(task_id)
    if not loop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    loop.cancel()
    return {"cancelled": True}


@router.get("/{task_id}/status")
async def get_autonomous_status(
    task_id: str,
    _user: dict = Depends(get_current_user),
):
    """Return the current plan state."""
    loop = get_loop(task_id)
    if not loop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return loop.plan.model_dump()


@router.get("/{task_id}/stream")
async def stream_autonomous(
    task_id: str,
    _user: dict = Depends(get_current_user),
):
    """SSE stream of real-time autonomous task events."""
    q = _sse_queues.get(task_id)
    if not q:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or not started")

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                if event.get("type") == "__done__":
                    yield f"event: done\ndata: {json.dumps(event)}\n\n"
                    break

                yield f"event: update\ndata: {json.dumps(event)}\n\n"
        finally:
            remove_loop(task_id)
            _sse_queues.pop(task_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
