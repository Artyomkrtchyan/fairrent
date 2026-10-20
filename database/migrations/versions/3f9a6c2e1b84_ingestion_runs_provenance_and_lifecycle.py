"""ingestion runs, source identity, provenance and listing lifecycle [A02][A04]

Revision ID: 3f9a6c2e1b84
Revises: 89c3800d8fdf
Create Date: 2026-10-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3f9a6c2e1b84'
down_revision: Union[str, Sequence[str], None] = '89c3800d8fdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ingestion_runs -----------------------------------------------------
    op.create_table(
        'ingestion_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='running', nullable=False),
        sa.Column('is_complete', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pages_requested', sa.Integer(), nullable=True),
        sa.Column('pages_fetched', sa.Integer(), nullable=True),
        sa.Column('listings_seen', sa.Integer(), server_default='0', nullable=False),
        sa.Column('listings_saved', sa.Integer(), server_default='0', nullable=False),
        sa.Column('listings_quarantined', sa.Integer(), server_default='0', nullable=False),
        sa.Column('listings_deactivated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'success', 'partial', 'failed')",
                           name='ck_ingestion_runs_status'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ingestion_runs_source_started', 'ingestion_runs', ['source', 'started_at'])

    # --- timestamps become timezone-aware (existing values were UTC) ---------
    op.alter_column('properties', 'created_at', existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True,
                    server_default=sa.func.now(),
                    postgresql_using="created_at AT TIME ZONE 'UTC'")
    op.alter_column('listings', 'created_at', existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True,
                    server_default=sa.func.now(),
                    postgresql_using="created_at AT TIME ZONE 'UTC'")
    op.execute("UPDATE price_observations SET recorded_at = now() WHERE recorded_at IS NULL")
    op.alter_column('price_observations', 'recorded_at', existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True, nullable=False,
                    server_default=sa.func.now(),
                    postgresql_using="recorded_at AT TIME ZONE 'UTC'")

    # --- listings: provenance + lifecycle -----------------------------------
    op.add_column('listings', sa.Column('url', sa.Text(), nullable=True))
    op.add_column('listings', sa.Column('original_price', sa.Float(), nullable=True))
    op.add_column('listings', sa.Column('original_currency', sa.String(length=3), nullable=True))
    op.add_column('listings', sa.Column('original_period', sa.String(), nullable=True))
    op.add_column('listings', sa.Column('exchange_rate', sa.Float(), nullable=True))
    op.add_column('listings', sa.Column('exchange_rate_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('listings', sa.Column('utilities_included', sa.Boolean(), nullable=True))
    op.add_column('listings', sa.Column('first_seen_at', sa.DateTime(timezone=True),
                                        server_default=sa.func.now(), nullable=False))
    op.add_column('listings', sa.Column('last_seen_at', sa.DateTime(timezone=True),
                                        server_default=sa.func.now(), nullable=False))
    op.add_column('listings', sa.Column('last_seen_run_id', sa.Integer(), nullable=True))
    op.add_column('listings', sa.Column('consecutive_misses', sa.Integer(),
                                        server_default='0', nullable=False))
    op.add_column('listings', sa.Column('is_active', sa.Boolean(),
                                        server_default=sa.true(), nullable=False))
    op.add_column('listings', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))

    # Backfill existing rows (unknown stays NULL; nothing is invented).
    op.execute("UPDATE listings SET source = 'list.am' WHERE source IS NULL")
    op.execute("UPDATE listings SET url = raw_data ->> 'url' WHERE url IS NULL AND raw_data IS NOT NULL")
    op.execute("UPDATE listings SET first_seen_at = COALESCE(created_at, now()), "
               "last_seen_at = COALESCE(created_at, now())")
    op.alter_column('listings', 'source', existing_type=sa.String(), nullable=False,
                    server_default='list.am')

    op.create_foreign_key('fk_listings_last_seen_run_id', 'listings', 'ingestion_runs',
                          ['last_seen_run_id'], ['id'], ondelete='SET NULL')

    # --- source identity: unique per (source, external_id) -------------------
    op.drop_index('ix_listings_external_id', table_name='listings')
    op.create_index('ix_listings_external_id', 'listings', ['external_id'], unique=False)
    op.create_unique_constraint('uq_listings_source_external_id', 'listings', ['source', 'external_id'])
    op.create_index('ix_listings_property_id', 'listings', ['property_id'], unique=False)
    op.create_index('ix_listings_source_active', 'listings', ['source', 'is_active'], unique=False)

    op.create_check_constraint('ck_listings_consecutive_misses_nonneg', 'listings', 'consecutive_misses >= 0')
    op.create_check_constraint('ck_listings_original_price_positive', 'listings',
                               'original_price IS NULL OR original_price > 0')
    op.create_check_constraint('ck_listings_exchange_rate_positive', 'listings',
                               'exchange_rate IS NULL OR exchange_rate > 0')

    # --- price_observations: provenance --------------------------------------
    op.add_column('price_observations', sa.Column('run_id', sa.Integer(), nullable=True))
    op.add_column('price_observations', sa.Column('original_price', sa.Float(), nullable=True))
    op.add_column('price_observations', sa.Column('original_currency', sa.String(length=3), nullable=True))
    op.add_column('price_observations', sa.Column('original_period', sa.String(), nullable=True))
    op.add_column('price_observations', sa.Column('exchange_rate', sa.Float(), nullable=True))
    op.add_column('price_observations', sa.Column('exchange_rate_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('price_observations', sa.Column('utilities_included', sa.Boolean(), nullable=True))
    op.create_foreign_key('fk_price_observations_run_id', 'price_observations', 'ingestion_runs',
                          ['run_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_price_observations_listing_recorded', 'price_observations',
                    ['listing_id', 'recorded_at'], unique=False)
    op.create_check_constraint('ck_price_observations_original_price_positive', 'price_observations',
                               'original_price IS NULL OR original_price > 0')


def downgrade() -> None:
    op.drop_constraint('ck_price_observations_original_price_positive', 'price_observations', type_='check')
    op.drop_index('ix_price_observations_listing_recorded', table_name='price_observations')
    op.drop_constraint('fk_price_observations_run_id', 'price_observations', type_='foreignkey')
    for col in ('utilities_included', 'exchange_rate_at', 'exchange_rate', 'original_period',
                'original_currency', 'original_price', 'run_id'):
        op.drop_column('price_observations', col)

    op.drop_constraint('ck_listings_exchange_rate_positive', 'listings', type_='check')
    op.drop_constraint('ck_listings_original_price_positive', 'listings', type_='check')
    op.drop_constraint('ck_listings_consecutive_misses_nonneg', 'listings', type_='check')
    op.drop_index('ix_listings_source_active', table_name='listings')
    op.drop_index('ix_listings_property_id', table_name='listings')
    op.drop_constraint('uq_listings_source_external_id', 'listings', type_='unique')
    op.drop_index('ix_listings_external_id', table_name='listings')
    op.create_index('ix_listings_external_id', 'listings', ['external_id'], unique=True)
    op.drop_constraint('fk_listings_last_seen_run_id', 'listings', type_='foreignkey')
    op.alter_column('listings', 'source', existing_type=sa.String(), nullable=True, server_default=None)
    for col in ('deactivated_at', 'is_active', 'consecutive_misses', 'last_seen_run_id', 'last_seen_at',
                'first_seen_at', 'utilities_included', 'exchange_rate_at', 'exchange_rate',
                'original_period', 'original_currency', 'original_price', 'url'):
        op.drop_column('listings', col)

    op.alter_column('price_observations', 'recorded_at', existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=False, nullable=True, server_default=None,
                    postgresql_using="recorded_at AT TIME ZONE 'UTC'")
    op.alter_column('listings', 'created_at', existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=True, server_default=None,
                    postgresql_using="created_at AT TIME ZONE 'UTC'")
    op.alter_column('properties', 'created_at', existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=True, server_default=None,
                    postgresql_using="created_at AT TIME ZONE 'UTC'")

    op.drop_index('ix_ingestion_runs_source_started', table_name='ingestion_runs')
    op.drop_table('ingestion_runs')
