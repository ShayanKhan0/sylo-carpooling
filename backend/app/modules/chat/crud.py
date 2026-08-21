"""
Chat Module - CRUD Operations (thread-based).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking as LegacyBooking
from app.models.ride import Ride
from app.modules.rides.models import RideBooking
from .models import ChatThread, ChatThreadMessage

ACTIVE_RIDE_STATUSES = {"open", "scheduled", "in_progress", "ongoing"}
LOCKED_RIDE_STATUSES = {"completed", "cancelled"}
SENDABLE_BOOKING_STATUSES = {"booked", "reserved", "confirmed", "completed"}
LOCKED_BOOKING_STATUSES = {"cancelled"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _norm_status(value: object) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw).strip().lower()


def _preview(content: str, max_len: int = 280) -> str:
    clean = " ".join((content or "").split())
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 3]}..."


@dataclass
class BookingContext:
    booking_id: UUID
    ride_id: UUID
    passenger_id: UUID
    status: str
    source: str
    created_at: Optional[datetime]


def _booking_context_from_ride_booking(booking: RideBooking) -> BookingContext:
    return BookingContext(
        booking_id=booking.id,
        ride_id=booking.ride_id,
        passenger_id=booking.passenger_id,
        status=_norm_status(getattr(booking, "status", "")),
        source="ride_bookings",
        created_at=getattr(booking, "booking_time", None)
        or getattr(booking, "created_at", None),
    )


def _booking_context_from_legacy_booking(booking: LegacyBooking) -> BookingContext:
    return BookingContext(
        booking_id=booking.id,
        ride_id=booking.ride_id,
        passenger_id=booking.passenger_id,
        status=_norm_status(getattr(booking, "status", "")),
        source="bookings",
        created_at=getattr(booking, "created_at", None),
    )


async def get_ride(db: AsyncSession, ride_id: UUID) -> Optional[Ride]:
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    return result.scalar_one_or_none()


async def get_booking_context_by_id(
    db: AsyncSession,
    booking_id: UUID,
) -> Optional[BookingContext]:
    canonical = await db.execute(
        select(RideBooking).where(RideBooking.id == booking_id)
    )
    booking = canonical.scalar_one_or_none()
    if booking:
        return _booking_context_from_ride_booking(booking)

    legacy = await db.execute(
        select(LegacyBooking).where(LegacyBooking.id == booking_id)
    )
    legacy_booking = legacy.scalar_one_or_none()
    if legacy_booking:
        return _booking_context_from_legacy_booking(legacy_booking)

    return None


async def find_latest_booking_context(
    db: AsyncSession,
    ride_id: UUID,
    passenger_id: UUID,
) -> Optional[BookingContext]:
    candidates: list[BookingContext] = []

    canonical = await db.execute(
        select(RideBooking)
        .where(
            RideBooking.ride_id == ride_id,
            RideBooking.passenger_id == passenger_id,
        )
        .order_by(RideBooking.booking_time.desc())
        .limit(10)
    )
    candidates.extend(
        _booking_context_from_ride_booking(row) for row in canonical.scalars().all()
    )

    legacy = await db.execute(
        select(LegacyBooking)
        .where(
            LegacyBooking.ride_id == ride_id,
            LegacyBooking.passenger_id == passenger_id,
        )
        .order_by(LegacyBooking.created_at.desc())
        .limit(10)
    )
    candidates.extend(
        _booking_context_from_legacy_booking(row) for row in legacy.scalars().all()
    )

    if not candidates:
        return None

    def _sort_key(item: BookingContext) -> datetime:
        dt = item.created_at
        if isinstance(dt, datetime):
            return dt
        return datetime.fromtimestamp(0, tz=timezone.utc)

    candidates.sort(key=_sort_key, reverse=True)
    return candidates[0]


async def get_thread_by_id(db: AsyncSession, thread_id: UUID) -> Optional[ChatThread]:
    result = await db.execute(select(ChatThread).where(ChatThread.id == thread_id))
    return result.scalar_one_or_none()


async def get_or_create_thread_for_booking(
    db: AsyncSession,
    *,
    ride: Ride,
    booking_ctx: BookingContext,
) -> ChatThread:
    existing = await db.execute(
        select(ChatThread).where(
            ChatThread.ride_id == ride.id,
            ChatThread.booking_id == booking_ctx.booking_id,
            ChatThread.booking_source == booking_ctx.source,
        )
    )
    thread = existing.scalar_one_or_none()
    if thread:
        return thread

    thread = ChatThread(
        ride_id=ride.id,
        booking_id=booking_ctx.booking_id,
        booking_source=booking_ctx.source,
        driver_id=ride.driver_id,
        passenger_id=booking_ctx.passenger_id,
        status="active",
        message_count=0,
    )
    db.add(thread)
    await db.flush()
    return thread


def compute_lock_state(ride_status: str, booking_status: str) -> tuple[bool, Optional[str], bool]:
    status = ride_status.strip().lower()
    booking = booking_status.strip().lower()

    locked = False
    lock_reason: Optional[str] = None

    if status == "completed":
        locked = True
        lock_reason = "ride_completed"
    elif status == "cancelled":
        locked = True
        lock_reason = "ride_cancelled"
    elif booking in LOCKED_BOOKING_STATUSES:
        locked = True
        lock_reason = "booking_cancelled"
    elif booking == "":
        locked = True
        lock_reason = "booking_missing"

    can_send = (
        (not locked)
        and status in ACTIVE_RIDE_STATUSES
        and booking in SENDABLE_BOOKING_STATUSES
    )
    return locked, lock_reason, can_send


async def _load_booking_status_for_thread(db: AsyncSession, thread: ChatThread) -> str:
    if thread.booking_source == "ride_bookings":
        canonical = await db.execute(
            select(RideBooking.status).where(RideBooking.id == thread.booking_id)
        )
        canonical_status = canonical.scalar_one_or_none()
        if canonical_status is not None:
            return _norm_status(canonical_status)

        # Fallback if historical thread points to legacy booking id.
        legacy = await db.execute(
            select(LegacyBooking.status).where(LegacyBooking.id == thread.booking_id)
        )
        return _norm_status(legacy.scalar_one_or_none())

    legacy = await db.execute(
        select(LegacyBooking.status).where(LegacyBooking.id == thread.booking_id)
    )
    legacy_status = legacy.scalar_one_or_none()
    if legacy_status is not None:
        return _norm_status(legacy_status)

    canonical = await db.execute(
        select(RideBooking.status).where(RideBooking.id == thread.booking_id)
    )
    return _norm_status(canonical.scalar_one_or_none())


async def sync_thread_lock_state(
    db: AsyncSession,
    thread: ChatThread,
) -> dict[str, object]:
    ride = await get_ride(db, thread.ride_id)
    ride_status = _norm_status(getattr(ride, "status", "")) if ride else ""
    booking_status = await _load_booking_status_for_thread(db, thread)

    locked, lock_reason, can_send = compute_lock_state(ride_status, booking_status)
    next_status = "locked" if locked else "active"

    changed = (
        _norm_status(thread.status) != next_status
        or (thread.lock_reason or "") != (lock_reason or "")
    )

    if changed:
        thread.status = next_status
        thread.lock_reason = lock_reason
        thread.updated_at = _now_utc()
        if locked and thread.locked_at is None:
            thread.locked_at = _now_utc()
        if not locked:
            thread.locked_at = None

    return {
        "locked": locked,
        "lock_reason": lock_reason,
        "can_send": can_send,
        "ride_status": ride_status,
        "booking_status": booking_status,
        "changed": changed,
    }


async def get_thread_messages(
    db: AsyncSession,
    thread_id: UUID,
    *,
    limit: int = 100,
    before_id: Optional[UUID] = None,
) -> list[ChatThreadMessage]:
    query = select(ChatThreadMessage).where(ChatThreadMessage.thread_id == thread_id)

    if before_id:
        cursor = await db.execute(
            select(ChatThreadMessage).where(
                ChatThreadMessage.id == before_id,
                ChatThreadMessage.thread_id == thread_id,
            )
        )
        cursor_msg = cursor.scalar_one_or_none()
        if cursor_msg:
            query = query.where(ChatThreadMessage.created_at < cursor_msg.created_at)

    query = query.order_by(ChatThreadMessage.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_thread_messages(db: AsyncSession, thread_id: UUID) -> int:
    result = await db.execute(
        select(func.count(ChatThreadMessage.id)).where(
            ChatThreadMessage.thread_id == thread_id
        )
    )
    return int(result.scalar() or 0)


async def create_thread_message(
    db: AsyncSession,
    *,
    thread: ChatThread,
    sender_id: UUID,
    receiver_id: UUID,
    content: str,
) -> ChatThreadMessage:
    msg = ChatThreadMessage(
        thread_id=thread.id,
        ride_id=thread.ride_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        content=content,
        is_read=False,
    )
    db.add(msg)

    thread.message_count = int(thread.message_count or 0) + 1
    thread.last_message_at = _now_utc()
    thread.last_message_preview = _preview(content)
    thread.updated_at = _now_utc()

    await db.flush()
    return msg


async def mark_thread_messages_read(
    db: AsyncSession,
    *,
    thread_id: UUID,
    reader_id: UUID,
) -> int:
    result = await db.execute(
        update(ChatThreadMessage)
        .where(
            ChatThreadMessage.thread_id == thread_id,
            ChatThreadMessage.receiver_id == reader_id,
            ChatThreadMessage.is_read.is_(False),
        )
        .values(is_read=True)
    )
    return int(result.rowcount or 0)


async def get_thread_unread_count(
    db: AsyncSession,
    *,
    thread_id: UUID,
    user_id: UUID,
) -> int:
    result = await db.execute(
        select(func.count(ChatThreadMessage.id)).where(
            ChatThreadMessage.thread_id == thread_id,
            ChatThreadMessage.receiver_id == user_id,
            ChatThreadMessage.is_read.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def get_user_unread_count(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> int:
    result = await db.execute(
        select(func.count(ChatThreadMessage.id)).where(
            ChatThreadMessage.receiver_id == user_id,
            ChatThreadMessage.is_read.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def get_user_threads(
    db: AsyncSession,
    *,
    user_id: UUID,
    limit: int = 500,
) -> list[ChatThread]:
    result = await db.execute(
        select(ChatThread)
        .where(
            or_(
                ChatThread.driver_id == user_id,
                ChatThread.passenger_id == user_id,
            )
        )
        .order_by(func.coalesce(ChatThread.last_message_at, ChatThread.created_at).desc())
        .limit(limit)
    )
    return list(result.scalars().all())
