"""Mark existing zero-product extraction results as failed and not reviewable."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_21"
down_revision = "20260907_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    empty_document_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT q.document_id
                FROM quotations q
                JOIN documents d ON d.id = q.document_id
                LEFT JOIN quotation_line_items li ON li.quotation_id = q.id
                WHERE d.status NOT IN ('approved', 'rejected')
                  AND q.review_status NOT IN ('approved', 'rejected')
                GROUP BY q.id, q.document_id
                HAVING COUNT(li.id) = 0
                """
            )
        )
    ]
    if not empty_document_ids:
        return
    placeholders = ", ".join(f":document_{index}" for index in range(len(empty_document_ids)))
    params = {f"document_{index}": document_id for index, document_id in enumerate(empty_document_ids)}
    bind.execute(
        sa.text(
            "UPDATE documents SET status = 'failed', "
            "failure_reason = 'No products could be extracted from this source.' "
            f"WHERE id IN ({placeholders})"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "UPDATE quotations SET system_decision = 'extraction_failed', review_status = 'not_reviewable' "
            f"WHERE document_id IN ({placeholders})"
        ),
        params,
    )


def downgrade() -> None:
    bind = op.get_bind()
    empty_document_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT id FROM documents "
                "WHERE status = 'failed' "
                "AND failure_reason = 'No products could be extracted from this source.'"
            )
        )
    ]
    if not empty_document_ids:
        return
    placeholders = ", ".join(f":document_{index}" for index in range(len(empty_document_ids)))
    params = {f"document_{index}": document_id for index, document_id in enumerate(empty_document_ids)}
    bind.execute(
        sa.text(
            "UPDATE documents SET status = 'pending_review', failure_reason = NULL "
            f"WHERE id IN ({placeholders})"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "UPDATE quotations SET system_decision = 'pending_review', review_status = 'pending_review' "
            f"WHERE document_id IN ({placeholders})"
        ),
        params,
    )
