"""Initial database schema with all models

Revision ID: 202512260810
Revises:
Create Date: 2025-12-26 08:10:39.744776

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202512260810"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables for BSAI agent system."""

    # user_settings table
    op.create_table(
        "user_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(length=255), nullable=True),
        sa.Column("qa_max_retries", sa.INTEGER(), nullable=False, server_default="3"),
        sa.Column("preferred_llm", sa.VARCHAR(length=100), nullable=True),
        sa.Column("cost_limit_daily", sa.DECIMAL(precision=10, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=False)

    # sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(length=255), nullable=True),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default="active"),
        sa.Column("total_input_tokens", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column(
            "total_cost_usd", sa.DECIMAL(precision=10, scale=6), nullable=False, server_default="0"
        ),
        sa.Column("context_usage_ratio", sa.FLOAT(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_status"), "sessions", ["status"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    # system_prompts table
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("agent_type", sa.VARCHAR(length=20), nullable=False),
        sa.Column("version", sa.INTEGER(), nullable=False),
        sa.Column("template", sa.TEXT(), nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_name_version"),
    )
    op.create_index(
        op.f("ix_system_prompts_agent_type"), "system_prompts", ["agent_type"], unique=False
    )
    op.create_index(
        op.f("ix_system_prompts_is_active"), "system_prompts", ["is_active"], unique=False
    )
    op.create_index(op.f("ix_system_prompts_name"), "system_prompts", ["name"], unique=False)

    # tasks table
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("original_request", sa.TEXT(), nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default="pending"),
        sa.Column("final_result", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_session_id"), "tasks", ["session_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)

    # memory_snapshots table
    op.create_table(
        "memory_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_type", sa.VARCHAR(length=30), nullable=False, server_default="auto"),
        sa.Column("compressed_context", sa.TEXT(), nullable=False),
        sa.Column("key_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_count", sa.INTEGER(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_snapshots_session_id"), "memory_snapshots", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_snapshots_snapshot_type"),
        "memory_snapshots",
        ["snapshot_type"],
        unique=False,
    )

    # milestones table
    op.create_table(
        "milestones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("sequence_number", sa.INTEGER(), nullable=False),
        sa.Column("title", sa.VARCHAR(length=255), nullable=False),
        sa.Column("complexity", sa.VARCHAR(length=20), nullable=False),
        sa.Column("selected_llm", sa.VARCHAR(length=100), nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default="pending"),
        sa.Column("worker_output", sa.TEXT(), nullable=True),
        sa.Column("qa_result", sa.TEXT(), nullable=True),
        sa.Column("retry_count", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column(
            "cost_usd", sa.DECIMAL(precision=10, scale=6), nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_milestones_complexity"), "milestones", ["complexity"], unique=False)
    op.create_index(op.f("ix_milestones_status"), "milestones", ["status"], unique=False)
    op.create_index(op.f("ix_milestones_task_id"), "milestones", ["task_id"], unique=False)

    # llm_usage_logs table
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("milestone_id", sa.UUID(), nullable=True),
        sa.Column("agent_type", sa.VARCHAR(length=20), nullable=False),
        sa.Column("llm_provider", sa.VARCHAR(length=50), nullable=False),
        sa.Column("llm_model", sa.VARCHAR(length=100), nullable=False),
        sa.Column("input_tokens", sa.INTEGER(), nullable=False),
        sa.Column("output_tokens", sa.INTEGER(), nullable=False),
        sa.Column("cost", sa.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("latency_ms", sa.INTEGER(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_usage_logs_agent_type"), "llm_usage_logs", ["agent_type"], unique=False
    )
    op.create_index(
        op.f("ix_llm_usage_logs_llm_model"), "llm_usage_logs", ["llm_model"], unique=False
    )
    op.create_index(
        op.f("ix_llm_usage_logs_llm_provider"), "llm_usage_logs", ["llm_provider"], unique=False
    )
    op.create_index(
        op.f("ix_llm_usage_logs_milestone_id"), "llm_usage_logs", ["milestone_id"], unique=False
    )
    op.create_index(
        op.f("ix_llm_usage_logs_session_id"), "llm_usage_logs", ["session_id"], unique=False
    )

    # generated_prompts table
    op.create_table(
        "generated_prompts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("milestone_id", sa.UUID(), nullable=False),
        sa.Column("system_prompt_id", sa.UUID(), nullable=False),
        sa.Column("generated_content", sa.TEXT(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
        ),
        sa.ForeignKeyConstraint(
            ["system_prompt_id"],
            ["system_prompts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_generated_prompts_milestone_id"),
        "generated_prompts",
        ["milestone_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_prompts_system_prompt_id"),
        "generated_prompts",
        ["system_prompt_id"],
        unique=False,
    )

    # prompt_usage_history table
    op.create_table(
        "prompt_usage_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("generated_prompt_id", sa.UUID(), nullable=False),
        sa.Column("success", sa.BOOLEAN(), nullable=False),
        sa.Column("qa_passed", sa.BOOLEAN(), nullable=False),
        sa.Column("retry_count", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("feedback", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generated_prompt_id"],
            ["generated_prompts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prompt_usage_history_generated_prompt_id"),
        "prompt_usage_history",
        ["generated_prompt_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index(
        op.f("ix_prompt_usage_history_generated_prompt_id"), table_name="prompt_usage_history"
    )
    op.drop_table("prompt_usage_history")

    op.drop_index(op.f("ix_generated_prompts_system_prompt_id"), table_name="generated_prompts")
    op.drop_index(op.f("ix_generated_prompts_milestone_id"), table_name="generated_prompts")
    op.drop_table("generated_prompts")

    op.drop_index(op.f("ix_llm_usage_logs_session_id"), table_name="llm_usage_logs")
    op.drop_index(op.f("ix_llm_usage_logs_milestone_id"), table_name="llm_usage_logs")
    op.drop_index(op.f("ix_llm_usage_logs_llm_provider"), table_name="llm_usage_logs")
    op.drop_index(op.f("ix_llm_usage_logs_llm_model"), table_name="llm_usage_logs")
    op.drop_index(op.f("ix_llm_usage_logs_agent_type"), table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")

    op.drop_index(op.f("ix_milestones_task_id"), table_name="milestones")
    op.drop_index(op.f("ix_milestones_status"), table_name="milestones")
    op.drop_index(op.f("ix_milestones_complexity"), table_name="milestones")
    op.drop_table("milestones")

    op.drop_index(op.f("ix_memory_snapshots_snapshot_type"), table_name="memory_snapshots")
    op.drop_index(op.f("ix_memory_snapshots_session_id"), table_name="memory_snapshots")
    op.drop_table("memory_snapshots")

    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_session_id"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_system_prompts_name"), table_name="system_prompts")
    op.drop_index(op.f("ix_system_prompts_is_active"), table_name="system_prompts")
    op.drop_index(op.f("ix_system_prompts_agent_type"), table_name="system_prompts")
    op.drop_table("system_prompts")

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_status"), table_name="sessions")
    op.drop_table("sessions")

    op.drop_index(op.f("ix_user_settings_user_id"), table_name="user_settings")
    op.drop_table("user_settings")
