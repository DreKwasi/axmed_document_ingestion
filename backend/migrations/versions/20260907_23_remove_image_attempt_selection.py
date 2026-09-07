"""Keep image extraction attempts as peers, without a selected-result flag."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_23"
down_revision = "20260907_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("image_extraction_attempts") as batch:
        batch.drop_column("selected")


def downgrade() -> None:
    with op.batch_alter_table("image_extraction_attempts") as batch:
        batch.add_column(sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()))
