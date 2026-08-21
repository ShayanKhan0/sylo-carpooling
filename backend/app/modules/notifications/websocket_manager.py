"""
WebSocket Manager for Real-Time Notifications

Manages WebSocket connections for real-time notification delivery.
Supports connection registry, heartbeat/ping, authentication, and message routing.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Set
from uuid import UUID
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages active WebSocket connections for real-time notifications.
    
    Features:
    - Connection registry (user_id → WebSocket)
    - Heartbeat/ping every 30 seconds
    - Graceful reconnection handling
    - Message queuing for offline users
    - Broadcast support
    """
    
    def __init__(self, heartbeat_interval: int = 30):
        """
        Initialize WebSocket Manager.
        
        Args:
            heartbeat_interval: Interval in seconds for heartbeat/ping messages
        """
        # Active connections: user_id → WebSocket
        self._connections: Dict[str, WebSocket] = {}
        
        # Connection metadata: user_id → {connected_at, last_ping, etc.}
        self._connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Message queue for offline users: user_id → list of messages
        self._offline_queue: Dict[str, list] = defaultdict(list)
        
        # Heartbeat configuration
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        
        # Statistics
        self._total_connections = 0
        self._total_messages_sent = 0
        self._total_messages_queued = 0
        
        logger.info(f"[WebSocketManager] Initialized with heartbeat_interval={heartbeat_interval}s")
    
    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        """
        Accept and register a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            user_id: User ID (UUID as string)
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            await websocket.accept()
            
            # If user already connected, close old connection
            if user_id in self._connections:
                logger.warning(f"[WebSocketManager] User {user_id} reconnecting, closing old connection")
                await self.disconnect(user_id)
            
            # Register connection
            self._connections[user_id] = websocket
            self._connection_metadata[user_id] = {
                "connected_at": datetime.utcnow().isoformat(),
                "last_ping": datetime.utcnow().isoformat(),
                "messages_sent": 0
            }
            
            self._total_connections += 1
            
            # Start heartbeat task
            self._heartbeat_tasks[user_id] = asyncio.create_task(
                self._heartbeat_loop(user_id)
            )
            
            logger.info(f"[WebSocketManager] User {user_id} connected (total: {len(self._connections)})")
            
            # Send queued messages
            await self._send_queued_messages(user_id)
            
            # Send connection confirmation
            await self.send_to_user(user_id, {
                "type": "connection",
                "status": "connected",
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return True
        
        except Exception as e:
            logger.error(f"[WebSocketManager] Error connecting user {user_id}: {e}")
            return False
    
    async def disconnect(self, user_id: str):
        """
        Disconnect and cleanup a WebSocket connection.
        
        Args:
            user_id: User ID to disconnect
        """
        if user_id in self._connections:
            # Cancel heartbeat task
            if user_id in self._heartbeat_tasks:
                self._heartbeat_tasks[user_id].cancel()
                del self._heartbeat_tasks[user_id]
            
            # Close WebSocket
            websocket = self._connections[user_id]
            try:
                await websocket.close()
            except Exception as e:
                logger.warning(f"[WebSocketManager] Error closing WebSocket for {user_id}: {e}")
            
            # Remove from registry
            del self._connections[user_id]
            del self._connection_metadata[user_id]
            
            logger.info(f"[WebSocketManager] User {user_id} disconnected (remaining: {len(self._connections)})")
    
    async def send_to_user(self, user_id: str, payload: Dict[str, Any]) -> bool:
        """
        Send message to a specific user.
        
        Args:
            user_id: User ID
            payload: Message payload (will be JSON serialized)
        
        Returns:
            True if sent successfully, False if queued (user offline)
        """
        # Ensure timestamp is present
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.utcnow().isoformat()
        
        # Check if user is connected
        if user_id in self._connections:
            try:
                websocket = self._connections[user_id]
                await websocket.send_json(payload)
                
                # Update metadata
                self._connection_metadata[user_id]["messages_sent"] += 1
                self._total_messages_sent += 1
                
                logger.debug(f"[WebSocketManager] Sent message to user {user_id}: {payload.get('type')}")
                return True
            
            except WebSocketDisconnect:
                logger.warning(f"[WebSocketManager] User {user_id} disconnected during send")
                await self.disconnect(user_id)
                # Queue message for next connection
                self._queue_message(user_id, payload)
                return False
            
            except Exception as e:
                logger.error(f"[WebSocketManager] Error sending to user {user_id}: {e}")
                return False
        else:
            # User offline, queue message
            self._queue_message(user_id, payload)
            return False
    
    async def broadcast(self, payload: Dict[str, Any], exclude_users: Optional[Set[str]] = None):
        """
        Broadcast message to all connected users.
        
        Args:
            payload: Message payload
            exclude_users: Set of user IDs to exclude from broadcast
        """
        exclude_users = exclude_users or set()
        
        # Add timestamp
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.utcnow().isoformat()
        
        connected_users = list(self._connections.keys())
        sent_count = 0
        failed_count = 0
        
        for user_id in connected_users:
            if user_id in exclude_users:
                continue
            
            success = await self.send_to_user(user_id, payload)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        logger.info(
            f"[WebSocketManager] Broadcast complete: sent={sent_count}, "
            f"failed={failed_count}, total_users={len(connected_users)}"
        )
    
    def is_connected(self, user_id: str) -> bool:
        """Check if user is currently connected."""
        return user_id in self._connections
    
    def get_connected_users(self) -> list[str]:
        """Get list of all connected user IDs."""
        return list(self._connections.keys())
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            "active_connections": len(self._connections),
            "total_connections_since_start": self._total_connections,
            "total_messages_sent": self._total_messages_sent,
            "total_messages_queued": self._total_messages_queued,
            "queued_users": len(self._offline_queue),
            "heartbeat_interval": self._heartbeat_interval
        }
    
    def _queue_message(self, user_id: str, payload: Dict[str, Any]):
        """
        Queue message for offline user.
        
        Args:
            user_id: User ID
            payload: Message payload
        """
        # Limit queue size per user to prevent memory bloat
        MAX_QUEUE_SIZE = 100
        
        if len(self._offline_queue[user_id]) >= MAX_QUEUE_SIZE:
            # Remove oldest message
            self._offline_queue[user_id].pop(0)
            logger.warning(f"[WebSocketManager] Queue full for user {user_id}, dropped oldest message")
        
        self._offline_queue[user_id].append(payload)
        self._total_messages_queued += 1
        
        logger.debug(f"[WebSocketManager] Queued message for offline user {user_id}")
    
    async def _send_queued_messages(self, user_id: str):
        """
        Send all queued messages to user upon connection.
        
        Args:
            user_id: User ID
        """
        if user_id in self._offline_queue and self._offline_queue[user_id]:
            queued_messages = self._offline_queue[user_id]
            logger.info(f"[WebSocketManager] Sending {len(queued_messages)} queued messages to {user_id}")
            
            for message in queued_messages:
                await self.send_to_user(user_id, message)
            
            # Clear queue
            del self._offline_queue[user_id]
    
    async def _heartbeat_loop(self, user_id: str):
        """
        Send periodic heartbeat/ping to keep connection alive.
        
        Args:
            user_id: User ID
        """
        try:
            while user_id in self._connections:
                await asyncio.sleep(self._heartbeat_interval)
                
                if user_id not in self._connections:
                    break
                
                # Send ping
                ping_payload = {
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                try:
                    websocket = self._connections[user_id]
                    await websocket.send_json(ping_payload)
                    
                    # Update last ping time
                    self._connection_metadata[user_id]["last_ping"] = datetime.utcnow().isoformat()
                    
                    logger.debug(f"[WebSocketManager] Sent ping to user {user_id}")
                
                except WebSocketDisconnect:
                    logger.warning(f"[WebSocketManager] User {user_id} disconnected during heartbeat")
                    await self.disconnect(user_id)
                    break
                
                except Exception as e:
                    logger.error(f"[WebSocketManager] Heartbeat error for user {user_id}: {e}")
                    await self.disconnect(user_id)
                    break
        
        except asyncio.CancelledError:
            logger.debug(f"[WebSocketManager] Heartbeat loop cancelled for user {user_id}")
    
    async def handle_client_message(self, user_id: str, message: Dict[str, Any]):
        """
        Handle incoming message from client (e.g., pong, ack).
        
        Args:
            user_id: User ID
            message: Message from client
        """
        message_type = message.get("type")
        
        if message_type == "pong":
            # Client responded to ping
            logger.debug(f"[WebSocketManager] Received pong from user {user_id}")
            self._connection_metadata[user_id]["last_ping"] = datetime.utcnow().isoformat()
        
        elif message_type == "ack":
            # Client acknowledged notification
            notification_id = message.get("notification_id")
            logger.debug(f"[WebSocketManager] User {user_id} acknowledged notification {notification_id}")
        
        else:
            logger.warning(f"[WebSocketManager] Unknown message type from user {user_id}: {message_type}")


# Global singleton instance
_websocket_manager: Optional[WebSocketManager] = None


def get_websocket_manager(heartbeat_interval: int = 30) -> WebSocketManager:
    """
    Get or create global WebSocket manager singleton.
    
    Args:
        heartbeat_interval: Heartbeat interval in seconds
    
    Returns:
        WebSocketManager instance
    """
    global _websocket_manager
    
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager(heartbeat_interval=heartbeat_interval)
    
    return _websocket_manager
