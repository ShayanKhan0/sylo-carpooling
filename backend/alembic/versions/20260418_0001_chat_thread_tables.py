"""Add chat thread tables

Revision ID: 20260418_chat_threads
Revises: 20260414_ride_overlap_excl
Create Date: 2026-04-18
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260418_chat_threads"
down_revision = "20260414_ride_overlap_excl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_threads (
            id UUID PRIMARY KEY,
            ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
            booking_id UUID NOT NULL,
            booking_source VARCHAR(20) NOT NULL DEFAULT 'ride_bookings',
            driver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            lock_reason VARCHAR(50),
            locked_at TIMESTAMPTZ,
            last_message_at TIMESTAMPTZ,
            last_message_preview VARCHAR(280),
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_threads_ride_booking_source
        ON chat_threads (ride_id, booking_id, booking_source)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_threads_driver_status
        ON chat_threads (driver_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_threads_passenger_status
        ON chat_threads (passenger_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_threads_status_last_message
        ON chat_threads (status, last_message_at)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_thread_messages (
            id UUID PRIMARY KEY,
            thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
            ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
            sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_thread_messages_thread_created
        ON chat_thread_messages (thread_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_thread_messages_receiver_unread
        ON chat_thread_messages (receiver_id, is_read)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_thread_messages_ride_created
        ON chat_thread_messages (ride_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_thread_messages_ride_created")
    op.execute("DROP INDEX IF EXISTS ix_chat_thread_messages_receiver_unread")
    op.execute("DROP INDEX IF EXISTS ix_chat_thread_messages_thread_created")
    op.execute("DROP TABLE IF EXISTS chat_thread_messages")

    op.execute("DROP INDEX IF EXISTS ix_chat_threads_status_last_message")
    op.execute("DROP INDEX IF EXISTS ix_chat_threads_passenger_status")
    op.execute("DROP INDEX IF EXISTS ix_chat_threads_driver_status")
    op.execute("DROP INDEX IF EXISTS ux_chat_threads_ride_booking_source")
    op.execute("DROP TABLE IF EXISTS chat_threads")
