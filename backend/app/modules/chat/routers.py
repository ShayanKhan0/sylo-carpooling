"""
Chat Module - API Router (thread-based private ride chat).
"""

from __future__ import annotations

import logging
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.notifications.models import NotificationPriorityEnum, NotificationTypeEnum
from app.modules.notifications.schemas import NotificationCreate
from app.modules.notifications.service import send_push_notification
from app.modules.users.models import UserProfile
from . import crud
from .models import ChatThread
from .schema_compat import ensure_chat_schema_compat
from .schemas import (
    ChatConversation,
    ChatMessageCreate,
    ChatMessageOut,
    ChatThreadEnsureRequest,
    ChatThreadListResponse,
    ChatThreadOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _ride_origin(ride: object) -> str:
    return str(
        getattr(ride, "start_point_address", None)
        or getattr(ride, "origin", None)
        or "Origin"
    )


def _ride_destination(ride: object) -> str:
    return str(
        getattr(ride, "end_point_address", None)
        or getattr(ride, "destination", None)
        or "Destination"
    )


def _lock_reason_human(reason: Optional[str]) -> str:
    mapping = {
        "ride_completed": "Ride completed",
        "ride_cancelled": "Ride cancelled",
        "booking_cancelled": "Booking cancelled",
        "booking_missing": "Booking unavailable",
    }
    return mapping.get((reason or "").strip().lower(), "Chat locked")


async def _resolve_thread_for_context(
    db: AsyncSession,
    *,
    ride_id: UUID,
    current_user: User,
    booking_id: Optional[UUID] = None,
    passenger_id: Optional[UUID] = None,
) -> tuple[ChatThread, dict[str, object]]:
    await ensure_chat_schema_compat(db)

    ride = await crud.get_ride(db, ride_id)
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    booking_ctx = None
    if booking_id is not None:
        booking_ctx = await crud.get_booking_context_by_id(db, booking_id)
        if not booking_ctx or booking_ctx.ride_id != ride.id:
            raise HTTPException(status_code=404, detail="Booking not found for this ride")
    else:
        target_passenger_id = passenger_id or current_user.id
        booking_ctx = await crud.find_latest_booking_context(
            db,
            ride_id=ride.id,
            passenger_id=target_passenger_id,
        )
        if booking_ctx is None:
            raise HTTPException(
                status_code=404,
                detail="Booking context not found for this ride/passenger",
            )

    is_driver = ride.driver_id == current_user.id
    is_passenger = booking_ctx.passenger_id == current_user.id
    if not (is_driver or is_passenger):
        raise HTTPException(
            status_code=403,
            detail="You are not authorized for this ride chat thread",
        )

    thread = await crud.get_or_create_thread_for_booking(
        db,
        ride=ride,
        booking_ctx=booking_ctx,
    )
    lock_state = await crud.sync_thread_lock_state(db, thread)
    await db.commit()
    await db.refresh(thread)
    return thread, lock_state


async def _thread_or_404(
    db: AsyncSession,
    *,
    thread_id: UUID,
    current_user: User,
) -> ChatThread:
    await ensure_chat_schema_compat(db)
    thread = await crud.get_thread_by_id(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Chat thread not found")

    if current_user.id not in {thread.driver_id, thread.passenger_id}:
        raise HTTPException(status_code=403, detail="Not authorized for this chat thread")
    return thread


async def _build_thread_out(
    db: AsyncSession,
    *,
    thread: ChatThread,
    current_user_id: UUID,
    lock_state: Optional[dict[str, object]] = None,
    unread_count: Optional[int] = None,
    user_cache: Optional[Dict[str, Optional[User]]] = None,
    profile_cache: Optional[Dict[str, Optional[str]]] = None,
    ride_cache: Optional[Dict[str, object]] = None,
) -> ChatThreadOut:
    if user_cache is None:
        user_cache = {}
    if profile_cache is None:
        profile_cache = {}
    if ride_cache is None:
        ride_cache = {}

    if lock_state is None:
        lock_state = await crud.sync_thread_lock_state(db, thread)

    counterpart_user_id = (
        thread.passenger_id if current_user_id == thread.driver_id else thread.driver_id
    )
    counterpart_key = str(counterpart_user_id)
    if counterpart_key not in user_cache:
        user_cache[counterpart_key] = await db.get(User, counterpart_user_id)
    counterpart = user_cache[counterpart_key]

    if counterpart_key not in profile_cache:
        photo_result = await db.execute(
            select(UserProfile.profile_photo).where(UserProfile.user_id == counterpart_user_id)
        )
        photo = photo_result.scalar_one_or_none()
        profile_cache[counterpart_key] = str(photo) if photo else None
    counterpart_photo = profile_cache[counterpart_key]

    ride_key = str(thread.ride_id)
    if ride_key not in ride_cache:
        ride_cache[ride_key] = await crud.get_ride(db, thread.ride_id)
    ride = ride_cache[ride_key]

    if unread_count is None:
        unread_count = await crud.get_thread_unread_count(
            db,
            thread_id=thread.id,
            user_id=current_user_id,
        )

    return ChatThreadOut(
        id=thread.id,
        ride_id=thread.ride_id,
        booking_id=thread.booking_id,
        booking_source=thread.booking_source,
        driver_id=thread.driver_id,
        passenger_id=thread.passenger_id,
        status=thread.status,
        lock_reason=thread.lock_reason,
        locked_at=thread.locked_at,
        can_send=bool(lock_state.get("can_send", False)),
        message_count=int(thread.message_count or 0),
        unread_count=int(unread_count or 0),
        last_message_at=thread.last_message_at,
        last_message_preview=thread.last_message_preview,
        counterpart_user_id=counterpart_user_id,
        counterpart_name=counterpart.full_name if counterpart else "User",
        counterpart_profile_photo=counterpart_photo,
        ride_origin=_ride_origin(ride) if ride else None,
        ride_destination=_ride_destination(ride) if ride else None,
        ride_departure_time=getattr(ride, "departure_time", None) if ride else None,
    )


async def _build_conversation(
    db: AsyncSession,
    *,
    thread: ChatThread,
    current_user: User,
    limit: int,
    before: Optional[UUID],
) -> ChatConversation:
    lock_state = await crud.sync_thread_lock_state(db, thread)
    messages = await crud.get_thread_messages(
        db,
        thread.id,
        limit=limit,
        before_id=before,
    )
    total = await crud.count_thread_messages(db, thread.id)

    marked = await crud.mark_thread_messages_read(
        db,
        thread_id=thread.id,
        reader_id=current_user.id,
    )

    if lock_state.get("changed") or marked > 0:
        await db.commit()
        await db.refresh(thread)

    sender_cache: dict[str, str] = {}
    out_messages: list[ChatMessageOut] = []
    for msg in reversed(messages):
        sender_key = str(msg.sender_id)
        if sender_key not in sender_cache:
            sender = await db.get(User, msg.sender_id)
            sender_cache[sender_key] = sender.full_name if sender else "User"
        out_messages.append(
            ChatMessageOut(
                id=msg.id,
                thread_id=msg.thread_id,
                ride_id=msg.ride_id,
                sender_id=msg.sender_id,
                sender_name=sender_cache[sender_key],
                receiver_id=msg.receiver_id,
                content=msg.content,
                is_read=msg.is_read,
                created_at=msg.created_at,
            )
        )

    thread_out = await _build_thread_out(
        db,
        thread=thread,
        current_user_id=current_user.id,
        lock_state=lock_state,
        unread_count=0,
    )
    return ChatConversation(thread=thread_out, messages=out_messages, total=total)


async def _safe_send_chat_push(
    db: AsyncSession,
    *,
    thread: ChatThread,
    sender: User,
    receiver_id: UUID,
    content: str,
) -> None:
    sender_name = (sender.full_name or "").strip() or "User"
    metadata = {
        "event": "chat_message",
        "thread_id": str(thread.id),
        "ride_id": str(thread.ride_id),
        "booking_id": str(thread.booking_id),
        "booking_source": thread.booking_source,
        "sender_id": str(sender.id),
        "sender_name": sender_name,
        "receiver_id": str(receiver_id),
        "thread_status": thread.status,
        "lock_reason": thread.lock_reason or "",
    }

    try:
        await send_push_notification(
            db=db,
            background_tasks=None,
            notification_data=NotificationCreate(
                user_id=receiver_id,
                title=f"New message from {sender_name}",
                message=content,
                type=NotificationTypeEnum.RIDE,
                priority=NotificationPriorityEnum.NORMAL,
                metadata=metadata,
            ),
        )
    except Exception as exc:  # pragma: no cover - notification best effort
        logger.warning("Chat push send failed (thread=%s): %s", thread.id, exc)


@router.post(
    "/thread",
    response_model=ChatThreadOut,
    summary="Create/get ride booking chat thread",
)
async def ensure_thread(
    body: ChatThreadEnsureRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread, lock_state = await _resolve_thread_for_context(
        db,
        ride_id=body.ride_id,
        current_user=current_user,
        booking_id=body.booking_id,
        passenger_id=body.passenger_id,
    )
    return await _build_thread_out(
        db,
        thread=thread,
        current_user_id=current_user.id,
        lock_state=lock_state,
    )


@router.get(
    "/threads",
    response_model=ChatThreadListResponse,
    summary="List my chat threads",
)
async def list_threads(
    state: str = Query("all", pattern="^(all|active|history)$"),
    limit: int = Query(100, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_chat_schema_compat(db)
    threads = await crud.get_user_threads(db, user_id=current_user.id, limit=500)

    user_cache: dict[str, Optional[User]] = {}
    profile_cache: dict[str, Optional[str]] = {}
    ride_cache: dict[str, object] = {}
    unread_cache: dict[str, int] = {}

    changed = False
    out: list[ChatThreadOut] = []
    for thread in threads:
        lock_state = await crud.sync_thread_lock_state(db, thread)
        if bool(lock_state.get("changed")):
            changed = True

        thread_key = str(thread.id)
        if thread_key not in unread_cache:
            unread_cache[thread_key] = await crud.get_thread_unread_count(
                db,
                thread_id=thread.id,
                user_id=current_user.id,
            )

        item = await _build_thread_out(
            db,
            thread=thread,
            current_user_id=current_user.id,
            lock_state=lock_state,
            unread_count=unread_cache[thread_key],
            user_cache=user_cache,
            profile_cache=profile_cache,
            ride_cache=ride_cache,
        )

        is_locked = not item.can_send
        if state == "active" and is_locked:
            continue
        if state == "history" and (not is_locked or item.message_count <= 0):
            continue
        out.append(item)

    if changed:
        await db.commit()

    total = len(out)
    paged = out[skip : skip + limit]
    unread_total = await crud.get_user_unread_count(db, user_id=current_user.id)
    return ChatThreadListResponse(threads=paged, total=total, unread_total=unread_total)


@router.get(
    "/threads/{thread_id}/messages",
    response_model=ChatConversation,
    summary="Get thread messages",
)
async def get_thread_messages(
    thread_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[UUID] = Query(None, description="Cursor: load messages before this ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = await _thread_or_404(db, thread_id=thread_id, current_user=current_user)
    return await _build_conversation(
        db,
        thread=thread,
        current_user=current_user,
        limit=limit,
        before=before,
    )


@router.post(
    "/threads/{thread_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a chat message to thread",
)
async def send_thread_message(
    thread_id: UUID,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = await _thread_or_404(db, thread_id=thread_id, current_user=current_user)
    lock_state = await crud.sync_thread_lock_state(db, thread)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    if not bool(lock_state.get("can_send", False)):
        reason = _lock_reason_human(thread.lock_reason)
        raise HTTPException(
            status_code=400,
            detail=f"Chat is locked ({reason}).",
        )

    receiver_id = (
        thread.passenger_id if current_user.id == thread.driver_id else thread.driver_id
    )

    msg = await crud.create_thread_message(
        db,
        thread=thread,
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
    )
    await db.commit()
    await db.refresh(thread)

    await _safe_send_chat_push(
        db,
        thread=thread,
        sender=current_user,
        receiver_id=receiver_id,
        content=content,
    )

    return ChatMessageOut(
        id=msg.id,
        thread_id=msg.thread_id,
        ride_id=msg.ride_id,
        sender_id=msg.sender_id,
        sender_name=current_user.full_name,
        receiver_id=msg.receiver_id,
        content=msg.content,
        is_read=msg.is_read,
        created_at=msg.created_at,
    )


@router.get(
    "/threads/{thread_id}/unread",
    summary="Get unread count for one thread",
)
async def get_thread_unread_count(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _thread_or_404(db, thread_id=thread_id, current_user=current_user)
    count = await crud.get_thread_unread_count(
        db,
        thread_id=thread_id,
        user_id=current_user.id,
    )
    return {"status": "ok", "data": {"unread_count": count}}


@router.post(
    "/threads/{thread_id}/read",
    summary="Mark thread messages as read",
)
async def mark_thread_as_read(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _thread_or_404(db, thread_id=thread_id, current_user=current_user)
    count = await crud.mark_thread_messages_read(
        db,
        thread_id=thread_id,
        reader_id=current_user.id,
    )
    await db.commit()
    return {"status": "ok", "data": {"marked_read": count}}


@router.get(
    "/unread-count",
    summary="Get total unread chat count",
)
async def get_chat_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_chat_schema_compat(db)
    count = await crud.get_user_unread_count(db, user_id=current_user.id)
    return {"status": "ok", "data": {"unread_count": count}}


# ---------------------------------------------------------------------------
# Legacy compatibility endpoints (ride_id based)
# ---------------------------------------------------------------------------


@router.get(
    "/{ride_id}",
    response_model=ChatConversation,
    summary="Legacy: Get ride chat messages",
)
async def get_chat_messages_legacy(
    ride_id: UUID,
    booking_id: Optional[UUID] = Query(None),
    passenger_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    before: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread, _ = await _resolve_thread_for_context(
        db,
        ride_id=ride_id,
        current_user=current_user,
        booking_id=booking_id,
        passenger_id=passenger_id,
    )
    return await _build_conversation(
        db,
        thread=thread,
        current_user=current_user,
        limit=limit,
        before=before,
    )


@router.post(
    "/{ride_id}",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Legacy: Send ride chat message",
)
async def send_message_legacy(
    ride_id: UUID,
    body: ChatMessageCreate,
    booking_id: Optional[UUID] = Query(None),
    passenger_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread, _ = await _resolve_thread_for_context(
        db,
        ride_id=ride_id,
        current_user=current_user,
        booking_id=booking_id,
        passenger_id=passenger_id,
    )
    return await send_thread_message(
        thread_id=thread.id,
        body=body,
        db=db,
        current_user=current_user,
    )


@router.get(
    "/{ride_id}/unread",
    summary="Legacy: get ride unread chat count",
)
async def get_unread_count_legacy(
    ride_id: UUID,
    booking_id: Optional[UUID] = Query(None),
    passenger_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread, _ = await _resolve_thread_for_context(
        db,
        ride_id=ride_id,
        current_user=current_user,
        booking_id=booking_id,
        passenger_id=passenger_id,
    )
    count = await crud.get_thread_unread_count(
        db,
        thread_id=thread.id,
        user_id=current_user.id,
    )
    return {"status": "ok", "data": {"unread_count": count}}


@router.post(
    "/{ride_id}/read",
    summary="Legacy: mark ride chat as read",
)
async def mark_as_read_legacy(
    ride_id: UUID,
    booking_id: Optional[UUID] = Query(None),
    passenger_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread, _ = await _resolve_thread_for_context(
        db,
        ride_id=ride_id,
        current_user=current_user,
        booking_id=booking_id,
        passenger_id=passenger_id,
    )
    marked = await crud.mark_thread_messages_read(
        db,
        thread_id=thread.id,
        reader_id=current_user.id,
    )
    await db.commit()
    return {"status": "ok", "data": {"marked_read": marked}}
