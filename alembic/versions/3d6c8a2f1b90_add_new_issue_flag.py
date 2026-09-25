"""add persisted new-issue flag to risk assessments

Revision ID: 3d6c8a2f1b90
Revises: 8a04017a1a4d
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3d6c8a2f1b90"
down_revision: Union[str, None] = "8a04017a1a4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "risk_assessments",
        sa.Column("is_new_issue", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("risk_assessments", "is_new_issue")
