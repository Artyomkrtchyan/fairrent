"""exchange-rate provenance: rate_source and rate_date [C01/C03]

Revision ID: 5b7d2e91c4a6
Revises: 3f9a6c2e1b84
Create Date: 2026-10-21 12:00:00.000000

`exchange_rate_at` keeps meaning "when the conversion was performed"; the rate's own origin and
effective date are stored separately in `rate_source` and `rate_date`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5b7d2e91c4a6'
down_revision: Union[str, Sequence[str], None] = '3f9a6c2e1b84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('listings', 'price_observations'):
        op.add_column(table, sa.Column('rate_source', sa.String(), nullable=True))
        op.add_column(table, sa.Column('rate_date', sa.Date(), nullable=True))
        # Every rate stored so far came from the static constants; their effective date was never
        # recorded, so rate_date stays NULL (unknown) rather than being guessed.
        op.execute(f"UPDATE {table} SET rate_source = 'static-config' WHERE exchange_rate IS NOT NULL")


def downgrade() -> None:
    for table in ('price_observations', 'listings'):
        op.drop_column(table, 'rate_date')
        op.drop_column(table, 'rate_source')
