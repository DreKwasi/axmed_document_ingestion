"""Remove persisted source-content fingerprints from document records."""

import sqlalchemy as sa
from alembic import op

revision = "20260909_25"
down_revision = "20260908_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_content_sha256")
        batch.drop_column("content_sha256")


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))
        batch.create_index("ix_documents_content_sha256", ["content_sha256"])
