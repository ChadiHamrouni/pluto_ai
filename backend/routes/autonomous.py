"""Autonomous task endpoints.

POST /autonomous/start        — start a plan-and-execute task
POST /autonomous/{id}/cancel  — cancel a running task
GET  /autonomous/{id}/status  — get current plan state
GET  /autonomous/{id}/stream  — SSE stream of real-time plan events
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Form, HTTPException, status
from fastapi.responses import StreamingResponse

from helpers.agents.autonomous.loop import create_loop, get_loop, remove_loop
from helpers.agents.session.session_store import append_turn, session_exists, update_session_title
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
    session_id: str = Form(default=""),
):
    """Start an autonomous plan-and-execute task. Returns the task_id."""
    if not task.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task cannot be empty")

    q: asyncio.Queue = asyncio.Queue(maxsize=200)

    created = create_loop(task, lambda d: None)  # create to get id first
    task_id = created.task_id
    loop = created.loop
    _sse_queues[task_id] = q

    # Now bind the real callback
    loop.on_event = _make_event_callback(task_id)

    _session_id = session_id.strip() if session_id else ""

    # Check if history is empty before the task starts (for title logic)
    _session_valid = False
    _history_empty = True
    if _session_id and await session_exists(_session_id):
        _session_valid = True
        from helpers.agents.session.session_store import get_history as _get_history
        _history_empty = not bool(await _get_history(_session_id, max_turns=1))

    async def _run_and_cleanup():
        try:
            await loop.run()
        except Exception as exc:
            logger.exception("Autonomous loop error for task %s", task_id)
            q.put_nowait({"type": "error", "task_id": task_id, "error": str(exc)})
        finally:
            plan = loop.plan

            # Persist to session history
            if _session_valid:
                user_msg = f"[AUTO] {task}"
                assistant_msg = plan.final_response or (
                    "Autonomous task completed."
                    if plan.status == "completed"
                    else "Autonomous task stopped."
                )
                await append_turn(_session_id, user_msg, assistant_msg)
                if _history_empty:
                    title = task[:50] + ("…" if len(task) > 50 else "")
                    await update_session_title(_session_id, title)

            # Signal SSE stream to close — include full plan so frontend has final_response
            q.put_nowait({
                "type": "__done__",
                "task_id": task_id,
                "plan": plan.model_dump(),
            })

    asyncio.create_task(_run_and_cleanup())
    return {"task_id": task_id}


@router.post("/{task_id}/cancel")
async def cancel_autonomous(
    task_id: str,
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
):
    """Return the current plan state."""
    loop = get_loop(task_id)
    if not loop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return loop.plan.model_dump()


@router.get("/{task_id}/stream")
async def stream_autonomous(
    task_id: str,
):
    """SSE stream of real-time autonomous task events."""
    q = _sse_queues.get(task_id)
    if not q:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or not started"
        )

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
