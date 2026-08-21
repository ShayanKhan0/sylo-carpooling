"""
WebSocket Handler for Real-Time Telemetry Streaming

Manages WebSocket connections, authentication, and message processing.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.telemetry.schemas import TelemetryPoint
from app.modules.telemetry.service import TelemetryService, get_service

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages active WebSocket connections.
    """
    
    def __init__(self):
        self.active_connections: dict[UUID, list[WebSocket]] = {}
    
    async def connect(self, ride_id: UUID, websocket: WebSocket):
        """Accept WebSocket connection"""
        await websocket.accept()
        
        if ride_id not in self.active_connections:
            self.active_connections[ride_id] = []
        
        self.active_connections[ride_id].append(websocket)
        logger.info(f"✅ WebSocket connected for ride {ride_id}")
    
    def disconnect(self, ride_id: UUID, websocket: WebSocket):
        """Remove WebSocket connection"""
        if ride_id in self.active_connections:
            self.active_connections[ride_id].remove(websocket)
            
            if not self.active_connections[ride_id]:
                del self.active_connections[ride_id]
        
        logger.info(f"❌ WebSocket disconnected for ride {ride_id}")
    
    async def broadcast(self, ride_id: UUID, message: dict):
        """Broadcast message to all connections for a ride"""
        if ride_id not in self.active_connections:
            return
        
        disconnected = []
        
        for connection in self.active_connections[ride_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to connection: {e}")
                disconnected.append(connection)
        
        # Remove dead connections
        for conn in disconnected:
            self.disconnect(ride_id, conn)


# Global manager instance
ws_manager = WebSocketManager()


async def _is_location_sharing_enabled(db: AsyncSession, user_id: UUID) -> bool:
    """Return True when telemetry sharing is enabled for the user."""
    try:
        result = await db.execute(
            text(
                """
                SELECT COALESCE(share_location_enabled, TRUE) AS share_location_enabled
                FROM user_profiles
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.first()
        return bool(row[0]) if row else True
    except Exception:
        return True


async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str],
    secret_key: str,
    algorithm: str = "HS256"
) -> Optional[dict]:
    """
    Authenticate WebSocket connection via JWT token.
    
    Args:
        websocket: WebSocket instance
        token: JWT token from query params or headers
        secret_key: JWT secret key
        algorithm: JWT algorithm
        
    Returns:
        Decoded token payload or None if invalid
    """
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return None
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        await websocket.close(code=4002, reason="Invalid authentication token")
        return None


async def handle_telemetry_stream(
    websocket: WebSocket,
    ride_id: UUID,
    db: AsyncSession,
    token: Optional[str] = None,
    secret_key: str = "your-secret-key",
    service: Optional[TelemetryService] = None,
    ping_interval: int = 30
):
    """
    Handle WebSocket telemetry streaming for a ride.
    
    Args:
        websocket: WebSocket connection
        ride_id: Ride UUID
        db: Database session
        token: JWT authentication token
        secret_key: JWT secret key
        service: Telemetry service instance
        ping_interval: Seconds between ping messages
    """
    # Authenticate
    user_payload = await authenticate_websocket(websocket, token, secret_key)
    if not user_payload:
        return  # Connection closed by authenticate_websocket
    
    user_id = user_payload.get("sub")
    logger.info(f"🔐 WebSocket authenticated for user {user_id}, ride {ride_id}")

    try:
        user_uuid = UUID(str(user_id))
    except Exception:
        user_uuid = None

    if user_uuid is not None:
        sharing_enabled = await _is_location_sharing_enabled(db, user_uuid)
        if not sharing_enabled:
            await websocket.accept()
            await websocket.send_json({
                "type": "location_sharing_disabled",
                "ride_id": str(ride_id),
                "message": "Location sharing is disabled for this account."
            })
            await websocket.close(code=1008, reason="Location sharing disabled")
            logger.info(
                "Telemetry websocket blocked due to disabled location sharing for user %s ride %s",
                user_uuid,
                ride_id,
            )
            return
    
    # Connect
    await ws_manager.connect(ride_id, websocket)
    
    # Get service
    if service is None:
        service = get_service()
    
    # Track last ping time
    last_ping = datetime.utcnow()
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "welcome",
            "ride_id": str(ride_id),
            "message": "Connected to telemetry stream"
        })
        
        while True:
            # Check if ping needed
            now = datetime.utcnow()
            if (now - last_ping).total_seconds() >= ping_interval:
                await websocket.send_json({"type": "ping", "timestamp": now.isoformat()})
                last_ping = now
            
            # Wait for message with timeout
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=1.0  # 1 second timeout for checking pings
                )
            except asyncio.TimeoutError:
                continue  # No message received, loop back to check ping
            
            # Parse message
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON format"
                })
                continue
            
            # Handle pong response
            if data.get("type") == "pong":
                logger.debug(f"Received pong from ride {ride_id}")
                continue
            
            # Validate telemetry point
            try:
                point = TelemetryPoint(**data)
            except ValidationError as e:
                await websocket.send_json({
                    "type": "error",
                    "error": "Validation failed",
                    "details": e.errors()
                })
                continue
            
            # Process telemetry point
            result = await service.process_telemetry_point(
                db=db,
                ride_id=ride_id,
                point=point
            )
            
            # Send acknowledgment
            if result["success"]:
                location_message = {
                    "type": "location",
                    "ride_id": str(ride_id),
                    "timestamp": point.timestamp.isoformat(),
                    "lat": point.lat,
                    "lng": point.lng,
                    "speed": point.speed,
                    "bearing": point.bearing,
                    "accuracy": point.accuracy,
                }
                await ws_manager.broadcast(ride_id, location_message)

                response = {
                    "type": "ack",
                    "point_id": result["point_id"],
                    "timestamp": point.timestamp.isoformat()
                }
                
                # Include anomaly warnings
                if result.get("anomalies"):
                    response["anomalies"] = result["anomalies"]
                    response["type"] = "warning"
                
                await websocket.send_json(response)
                
                logger.debug(f"Processed telemetry point for ride {ride_id}")
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": result.get("error", "Processing failed")
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for ride {ride_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error for ride {ride_id}: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    
    finally:
        # Cleanup
        ws_manager.disconnect(ride_id, websocket)
        logger.info(f"WebSocket handler finished for ride {ride_id}")
