import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _safe_json_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _to_float(raw: Any) -> Optional[float]:
    try:
        if raw is None:
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_iso(raw: Any) -> Optional[str]:
    if isinstance(raw, datetime):
        # Treat DB naive timestamps as UTC to avoid timezone drift.
        dt = raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(raw, str):
        text_raw = raw.strip()
        if not text_raw:
            return None
        try:
            parsed = datetime.fromisoformat(text_raw.replace("Z", "+00:00"))
            parsed = (
                parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            )
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            return text_raw
    return str(raw) if raw is not None else None


def _format_incident_summary(row: Any) -> Dict[str, Any]:
    meta = _safe_json_dict(row.meta_data)
    role_raw = str(meta.get("triggered_by_role") or "").strip().lower()
    sender_role = (
        "Driver"
        if role_raw == "driver"
        else "Passenger"
        if role_raw == "passenger"
        else None
    )
    return {
        "incident_id": str(row.id),
        "ride_id": str(row.ride_id),
        "driver_id": str(row.driver_id) if row.driver_id else None,
        "incident_type": str(row.type),
        "severity": str(row.severity),
        "description": row.description,
        "detected_at": _to_iso(row.detected_at),
        "resolved_at": _to_iso(row.resolved_at),
        "reviewed": bool(row.reviewed),
        "assigned_to": meta.get("assigned_to"),
        "sender_role": sender_role,
        "notes_count": len(meta.get("admin_notes", []))
        if isinstance(meta.get("admin_notes"), list)
        else 0,
        "gps_lat": _to_float(row.location_lat),
        "gps_lng": _to_float(row.location_lng),
    }


async def list_active_sos_incidents(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> Dict[str, Any]:
    q = text(
        """
        SELECT id, ride_id, driver_id, type, severity, description, detected_at, resolved_at,
               reviewed, reviewed_by, admin_remarks, meta_data, location_lat, location_lng
        FROM incident_reports
        WHERE LOWER(CAST(type AS TEXT)) = 'sos'
          AND resolved_at IS NULL
        ORDER BY detected_at DESC
        LIMIT :limit
        """
    )
    rows = (await db.execute(q, {"limit": max(1, min(limit, 500))})).mappings().all()
    items = [_format_incident_summary(row) for row in rows]
    return {"status": "ok", "data": {"items": items, "total": len(items)}, "error": None}


async def list_historical_sos_incidents(
    db: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    q = text(
        """
        SELECT id, ride_id, driver_id, type, severity, description, detected_at, resolved_at,
               reviewed, reviewed_by, admin_remarks, meta_data, location_lat, location_lng
        FROM incident_reports
        WHERE LOWER(CAST(type AS TEXT)) = 'sos'
          AND resolved_at IS NOT NULL
        ORDER BY COALESCE(resolved_at, detected_at) DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (
        await db.execute(
            q,
            {
                "limit": max(1, min(limit, 500)),
                "offset": max(0, offset),
            },
        )
    ).mappings().all()
    items = [_format_incident_summary(row) for row in rows]
    return {"status": "ok", "data": {"items": items, "total": len(items)}, "error": None}


async def list_unlinked_sos_incidents(
    db: AsyncSession,
    *,
    active_only: bool,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    # Keep this table available even if migrations were skipped.
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS unlinked_sos_incidents (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(30),
                role VARCHAR(40) NOT NULL,
                gps_lat NUMERIC(10,7),
                gps_lng NUMERIC(10,7),
                message TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMP WITH TIME ZONE NULL,
                reviewed BOOLEAN NOT NULL DEFAULT FALSE,
                meta_data TEXT NULL
            )
            """
        )
    )
    where = "resolved_at IS NULL" if active_only else "resolved_at IS NOT NULL"
    q = text(
        f"""
        SELECT id, user_id, full_name, email, phone, role, gps_lat, gps_lng, message,
               created_at, resolved_at, reviewed, meta_data
        FROM unlinked_sos_incidents
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (
        await db.execute(
            q,
            {"limit": max(1, min(limit, 500)), "offset": max(0, offset)},
        )
    ).mappings().all()
    items = []
    for row in rows:
        items.append(
            {
                "incident_id": str(row["id"]),
                "user_id": str(row["user_id"]),
                "name": row["full_name"],
                "email": row["email"],
                "phone": row["phone"],
                "role": row["role"],
                "message": row["message"],
                "gps_lat": _to_float(row["gps_lat"]),
                "gps_lng": _to_float(row["gps_lng"]),
                "detected_at": _to_iso(row["created_at"]),
                "resolved_at": _to_iso(row["resolved_at"]),
                "reviewed": bool(row["reviewed"]),
            }
        )
    return {"status": "ok", "data": {"items": items, "total": len(items)}, "error": None}


async def resolve_unlinked_incident(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
) -> Dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT id, meta_data
                FROM unlinked_sos_incidents
                WHERE id = :incident_id
                LIMIT 1
                """
            ),
            {"incident_id": incident_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No-ride SOS incident not found",
        )

    meta = _safe_json_dict(row["meta_data"])
    meta["resolved_by"] = str(admin_user_id)
    meta["resolved_at"] = datetime.now(timezone.utc).isoformat()

    await db.execute(
        text(
            """
            UPDATE unlinked_sos_incidents
            SET reviewed = TRUE,
                resolved_at = :resolved_at,
                meta_data = :meta_data
            WHERE id = :incident_id
            """
        ),
        {
            "incident_id": incident_id,
            "resolved_at": datetime.now(timezone.utc),
            "meta_data": json.dumps(meta),
        },
    )
    await db.commit()
    return {"status": "ok", "data": {"incident_id": str(incident_id)}, "error": None}


async def get_sos_incident_detail(
    db: AsyncSession,
    *,
    incident_id: UUID,
) -> Dict[str, Any]:
    incident_q = text(
        """
        SELECT id, ride_id, driver_id, type, severity, description, ai_score,
               detected_at, resolved_at, reviewed, reviewed_by, admin_remarks,
               meta_data, location_lat, location_lng
        FROM incident_reports
        WHERE id = :incident_id
          AND LOWER(CAST(type AS TEXT)) = 'sos'
        LIMIT 1
        """
    )
    incident = (
        await db.execute(incident_q, {"incident_id": incident_id})
    ).mappings().first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SOS incident not found",
        )

    ride_q = text(
        """
        SELECT
            r.id,
            r.driver_id,
            r.vehicle_id,
            r.start_point_lat,
            r.start_point_lng,
            r.start_point_address,
            r.end_point_lat,
            r.end_point_lng,
            r.end_point_address,
            r.departure_time,
            r.status,
            r.route_distance_km,
            r.estimated_duration_minutes,
            r.polyline,
            r.route_selected_key,
            r.route_alternatives,
            u.full_name AS driver_name,
            u.email AS driver_email,
            u.phone AS driver_phone,
            v.make,
            v.model,
            v.year,
            v.plate_number,
            v.color,
            v.seats_total
        FROM rides r
        LEFT JOIN users u ON u.id = r.driver_id
        LEFT JOIN vehicles v ON v.id = r.vehicle_id
        WHERE r.id = :ride_id
        LIMIT 1
        """
    )
    ride = (await db.execute(ride_q, {"ride_id": incident["ride_id"]})).mappings().first()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ride linked to SOS incident was not found",
        )

    passengers_q = text(
        """
        SELECT
            rb.id AS booking_id,
            rb.passenger_id,
            rb.status AS booking_status,
            rb.booked_seats,
            rb.pickup_lat,
            rb.pickup_lng,
            rb.pickup_address,
            rb.dropoff_lat,
            rb.dropoff_lng,
            rb.dropoff_address,
            rb.planned_pickup_eta,
            rb.planned_dropoff_eta,
            u.full_name,
            u.email,
            u.phone
        FROM ride_bookings rb
        JOIN users u ON u.id = rb.passenger_id
        WHERE rb.ride_id = :ride_id
        ORDER BY rb.booking_time ASC
        """
    )
    passengers_rows = (
        await db.execute(passengers_q, {"ride_id": incident["ride_id"]})
    ).mappings().all()
    passengers: List[Dict[str, Any]] = []
    stop_markers: List[Dict[str, Any]] = []
    for row in passengers_rows:
        passengers.append(
            {
                "booking_id": str(row.booking_id),
                "passenger_id": str(row.passenger_id),
                "name": row.full_name,
                "email": row.email,
                "phone": row.phone,
                "booking_status": str(row.booking_status),
                "booked_seats": int(row.booked_seats or 0),
                "pickup_address": row.pickup_address,
                "dropoff_address": row.dropoff_address,
                "planned_pickup_eta": _to_iso(row.planned_pickup_eta),
                "planned_dropoff_eta": _to_iso(row.planned_dropoff_eta),
                "pickup_lat": _to_float(row.pickup_lat),
                "pickup_lng": _to_float(row.pickup_lng),
                "dropoff_lat": _to_float(row.dropoff_lat),
                "dropoff_lng": _to_float(row.dropoff_lng),
            }
        )
        if row.pickup_lat is not None and row.pickup_lng is not None:
            stop_markers.append(
                {
                    "type": "pickup",
                    "booking_id": str(row.booking_id),
                    "lat": _to_float(row.pickup_lat),
                    "lng": _to_float(row.pickup_lng),
                    "address": row.pickup_address,
                }
            )
        if row.dropoff_lat is not None and row.dropoff_lng is not None:
            stop_markers.append(
                {
                    "type": "dropoff",
                    "booking_id": str(row.booking_id),
                    "lat": _to_float(row.dropoff_lat),
                    "lng": _to_float(row.dropoff_lng),
                    "address": row.dropoff_address,
                }
            )

    telemetry_q = text(
        """
        SELECT gps_lat, gps_lng, timestamp
        FROM telemetry_data
        WHERE ride_id = :ride_id
        ORDER BY timestamp ASC
        LIMIT 1200
        """
    )
    telemetry_rows = (
        await db.execute(telemetry_q, {"ride_id": incident["ride_id"]})
    ).mappings().all()
    live_path = [
        {
            "lat": _to_float(row.gps_lat),
            "lng": _to_float(row.gps_lng),
            "timestamp": _to_iso(row.timestamp),
        }
        for row in telemetry_rows
        if _to_float(row.gps_lat) is not None and _to_float(row.gps_lng) is not None
    ]

    meta = _safe_json_dict(incident["meta_data"])
    incident_detail = {
        "incident_id": str(incident["id"]),
        "ride_id": str(incident["ride_id"]),
        "incident_type": str(incident["type"]),
        "severity": str(incident["severity"]),
        "description": incident["description"],
        "ai_score": _to_float(incident["ai_score"]),
        "detected_at": _to_iso(incident["detected_at"]),
        "resolved_at": _to_iso(incident["resolved_at"]),
        "reviewed": bool(incident["reviewed"]),
        "reviewed_by": str(incident["reviewed_by"]) if incident["reviewed_by"] else None,
        "admin_remarks": incident["admin_remarks"],
        "gps_lat": _to_float(incident["location_lat"]),
        "gps_lng": _to_float(incident["location_lng"]),
        "assigned_to": meta.get("assigned_to"),
        "admin_notes": meta.get("admin_notes", []),
    }

    data = {
        "incident": incident_detail,
        "ride": {
            "id": str(ride["id"]),
            "status": str(ride["status"]),
            "departure_time": _to_iso(ride["departure_time"]),
            "origin": {
                "lat": _to_float(ride["start_point_lat"]),
                "lng": _to_float(ride["start_point_lng"]),
                "address": ride["start_point_address"],
            },
            "destination": {
                "lat": _to_float(ride["end_point_lat"]),
                "lng": _to_float(ride["end_point_lng"]),
                "address": ride["end_point_address"],
            },
            "route_distance_km": _to_float(ride["route_distance_km"]),
            "estimated_duration_minutes": (
                int(ride["estimated_duration_minutes"])
                if ride["estimated_duration_minutes"] is not None
                else None
            ),
            "polyline": ride["polyline"],
            "route_selected_key": ride["route_selected_key"],
            "route_alternatives": _safe_json_dict(ride["route_alternatives"]),
        },
        "driver": {
            "id": str(ride["driver_id"]),
            "name": ride["driver_name"],
            "email": ride["driver_email"],
            "phone": ride["driver_phone"],
        },
        "vehicle": {
            "vehicle_id": str(ride["vehicle_id"]) if ride["vehicle_id"] else None,
            "make": ride["make"],
            "model": ride["model"],
            "year": ride["year"],
            "plate_number": ride["plate_number"],
            "color": ride["color"],
            "seats_total": ride["seats_total"],
        },
        "passengers": passengers,
        "route": {
            "live_path": live_path,
            "stops": stop_markers,
        },
    }
    return {"status": "ok", "data": data, "error": None}


async def _update_incident_admin_state(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
    remarks: Optional[str] = None,
    assigned_to: Optional[str] = None,
    resolve: bool = False,
    add_note: Optional[str] = None,
) -> Dict[str, Any]:
    fetch_q = text(
        """
        SELECT id, meta_data, admin_remarks, reviewed, resolved_at
        FROM incident_reports
        WHERE id = :incident_id
        LIMIT 1
        """
    )
    row = (await db.execute(fetch_q, {"incident_id": incident_id})).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SOS incident not found",
        )

    meta = _safe_json_dict(row["meta_data"])
    if assigned_to is not None:
        meta["assigned_to"] = assigned_to
        meta["assigned_at"] = datetime.now(timezone.utc).isoformat()
        meta["assigned_by"] = str(admin_user_id)

    if add_note:
        notes = meta.get("admin_notes")
        if not isinstance(notes, list):
            notes = []
        notes.append(
            {
                "note": add_note,
                "at": datetime.now(timezone.utc).isoformat(),
                "by": str(admin_user_id),
            }
        )
        meta["admin_notes"] = notes

    merged_remarks = (row["admin_remarks"] or "").strip()
    if remarks:
        merged_remarks = remarks.strip() if not merged_remarks else f"{merged_remarks}\n{remarks.strip()}"

    update_q = text(
        """
        UPDATE incident_reports
        SET
            reviewed = TRUE,
            admin_remarks = :admin_remarks,
            meta_data = :meta_data,
            resolved_at = CASE WHEN :resolve_flag = TRUE THEN NOW() ELSE resolved_at END
        WHERE id = :incident_id
        """
    )
    await db.execute(
        update_q,
        {
            "incident_id": incident_id,
            "admin_remarks": merged_remarks if merged_remarks else None,
            "meta_data": json.dumps(meta) if meta else None,
            "resolve_flag": resolve,
        },
    )
    await db.commit()
    return {"status": "ok", "data": {"incident_id": str(incident_id)}, "error": None}


async def acknowledge_incident(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
    remarks: Optional[str],
) -> Dict[str, Any]:
    return await _update_incident_admin_state(
        db,
        incident_id=incident_id,
        admin_user_id=admin_user_id,
        remarks=remarks or "Acknowledged by admin.",
    )


async def assign_incident(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
    assigned_to: str,
    remarks: Optional[str],
) -> Dict[str, Any]:
    return await _update_incident_admin_state(
        db,
        incident_id=incident_id,
        admin_user_id=admin_user_id,
        assigned_to=assigned_to.strip(),
        remarks=remarks or f"Assigned to {assigned_to.strip()}",
    )


async def resolve_incident(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
    remarks: Optional[str],
) -> Dict[str, Any]:
    return await _update_incident_admin_state(
        db,
        incident_id=incident_id,
        admin_user_id=admin_user_id,
        remarks=remarks or "Resolved by admin.",
        resolve=True,
    )


async def add_incident_note(
    db: AsyncSession,
    *,
    incident_id: UUID,
    admin_user_id: UUID,
    note: str,
) -> Dict[str, Any]:
    note_text = note.strip()
    if not note_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="note is required",
        )
    return await _update_incident_admin_state(
        db,
        incident_id=incident_id,
        admin_user_id=admin_user_id,
        add_note=note_text,
    )
