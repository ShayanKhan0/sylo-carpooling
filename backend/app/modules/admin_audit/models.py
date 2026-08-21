"""
Database models for Admin Audit Logs (Prompt 12D).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class AdminAuditLog(Base):
    """
    Append-only admin audit log.
    """
    __tablename__ = "admin_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    action_type = Column(String(100), nullable=False, index=True)
    target_entity = Column(String(100), nullable=False, index=True)
    target_id = Column(String(100), nullable=True, index=True)
    meta_data = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True, index=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    admin = relationship("User", foreign_keys=[admin_id])

    __table_args__ = (
        Index("idx_admin_audit_action_type", "action_type"),
        Index("idx_admin_audit_target_entity", "target_entity"),
        Index("idx_admin_audit_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<AdminAuditLog(id={self.id}, action_type={self.action_type}, target_entity={self.target_entity})>"
