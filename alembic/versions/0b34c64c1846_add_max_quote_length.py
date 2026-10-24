"""add max quote length

Revision ID: 0b34c64c1846
Revises: 8f4344cf4855
Create Date: 2026-10-24 14:06:48.269264

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b34c64c1846"
down_revision: str | Sequence[str] | None = "8f4344cf4855"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "guildsettings",
        sa.Column(
            "max_quote_length",
            sa.Integer(),
            nullable=False,
            server_default="500",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("guildsettings", "max_quote_length")
