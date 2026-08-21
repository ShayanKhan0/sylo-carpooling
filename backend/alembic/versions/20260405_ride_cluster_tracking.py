"""Add cluster_run_id and cluster_label to ride_requests for AI tracking

Revision ID: 20260405_ride_cluster
Revises: 20260313_1917_cea48e476f21
Create Date: 2026-04-05

Adds two columns to ride_requests to track which clustering run
matched a request and which cluster label it received.
This allows post-run analytics and UI status display.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260405_ride_cluster"
down_revision = "cea48e476f21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add cluster tracking columns to ride_requests
    op.add_column(
        "ride_requests",
        sa.Column(
            "cluster_run_id",
            sa.String(36),
            nullable=True,
            comment="ID of the clustering run that matched this request",
        ),
    )
    op.add_column(
        "ride_requests",
        sa.Column(
            "cluster_label",
            sa.Integer,
            nullable=True,
            comment="DBSCAN cluster label assigned (-1 = solo/noise)",
        ),
    )

    # Index for efficient cluster-run queries
    op.create_index(
        "idx_rr_cluster_run",
        "ride_requests",
        ["cluster_run_id"],
    )

    # Table to store clustering run summaries for audit/analytics
    op.create_table(
        "ai_cluster_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("algorithm_used", sa.String(64), nullable=False),
        sa.Column("total_requests", sa.Integer, nullable=False, default=0),
        sa.Column("total_clusters", sa.Integer, nullable=False, default=0),
        sa.Column("grouped_passengers", sa.Integer, nullable=False, default=0),
        sa.Column("solo_passengers", sa.Integer, nullable=False, default=0),
        sa.Column("match_rate_pct", sa.Float, nullable=False, default=0.0),
        sa.Column("elapsed_ms", sa.Float, nullable=False, default=0.0),
        sa.Column("dry_run", sa.Boolean, nullable=False, default=False),
        sa.Column("status", sa.String(32), nullable=False, default="completed"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("config_json", sa.JSON, nullable=True, comment="Hyper-parameters used"),
    )


def downgrade() -> None:
    op.drop_table("ai_cluster_runs")
    op.drop_index("idx_rr_cluster_run", table_name="ride_requests")
    op.drop_column("ride_requests", "cluster_label")
    op.drop_column("ride_requests", "cluster_run_id")
