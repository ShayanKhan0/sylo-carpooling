"""
Publisher for Telemetry Streaming

Publishes telemetry data via in-memory queue for real-time processing.
"""

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """
    In-memory publisher for telemetry streaming.
    """
    
    def __init__(self, **kwargs):
        """Initialize publisher with in-memory queue."""
        self.using_redis = False
        self.in_memory_queue = []
        logger.info("TelemetryPublisher initialized (in-memory)")
    
    async def publish_telemetry_point(
        self,
        ride_id: UUID,
        point_data: Dict[str, Any]
    ) -> bool:
        """
        Publish telemetry point.
        
        Channel format: telemetry:ride:{ride_id}
        
        Args:
            ride_id: Ride UUID
            point_data: Telemetry point dictionary
            
        Returns:
            True if published successfully
        """
        channel = f"telemetry:ride:{ride_id}"
        
        try:
            message = {
                "ride_id": str(ride_id),
                "timestamp": point_data.get('timestamp', ''),
                "lat": point_data.get('lat'),
                "lng": point_data.get('lng'),
                "speed": point_data.get('speed'),
                "bearing": point_data.get('bearing'),
                "accuracy": point_data.get('accuracy'),
                "event_type": "telemetry_point"
            }
            
            self.in_memory_queue.append({
                "channel": channel,
                "message": message
            })
            
            # Limit queue size
            if len(self.in_memory_queue) > 1000:
                self.in_memory_queue.pop(0)
            
            logger.debug(f"Published telemetry: {channel}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to publish telemetry: {e}", exc_info=True)
            return False
    
    async def publish_anomaly_alert(
        self,
        ride_id: UUID,
        anomaly_data: Dict[str, Any]
    ) -> bool:
        """
        Publish anomaly alert.
        
        Channel format: telemetry:anomaly:{ride_id}
        
        Args:
            ride_id: Ride UUID
            anomaly_data: Anomaly alert dictionary
            
        Returns:
            True if published successfully
        """
        channel = f"telemetry:anomaly:{ride_id}"
        
        try:
            message = {
                "ride_id": str(ride_id),
                "event_type": "anomaly_alert",
                **anomaly_data
            }
            
            self.in_memory_queue.append({
                "channel": channel,
                "message": message
            })
            logger.info(f"Published anomaly alert: {channel}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to publish anomaly alert: {e}", exc_info=True)
            return False
    
    def get_in_memory_messages(self) -> list:
        """Get all in-memory queued messages (for testing)"""
        return self.in_memory_queue.copy()
    
    def clear_in_memory_queue(self):
        """Clear in-memory queue"""
        self.in_memory_queue.clear()


# Global publisher instance (initialized in service layer)
_publisher_instance: Optional[TelemetryPublisher] = None


def get_publisher() -> TelemetryPublisher:
    """Get global publisher instance"""
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = TelemetryPublisher()
    return _publisher_instance


def set_publisher(publisher: TelemetryPublisher):
    """Set global publisher instance"""
    global _publisher_instance
    _publisher_instance = publisher
