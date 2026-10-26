"""Persist weekly neighborhood asking-price index aggregates for A07.

Revision ID: a07_neighborhood_price_index
Revises: a05_geo_20261022
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a07_neighborhood_price_index"
down_revision: Union[str, Sequence[str], None] = "a05_geo_20261022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekly_neighborhood_price_indexes",
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("district_id", sa.String(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("median_price_usd_month", sa.Numeric(12, 2), nullable=True),
        sa.Column("median_price_usd_per_sqm", sa.Numeric(12, 2), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("per_sqm_sample_count", sa.Integer(), nullable=False),
        sa.Column("minimum_sample_count", sa.Integer(), server_default="5", nullable=False),
        sa.Column("price_status", sa.String(), nullable=False),
        sa.Column("per_sqm_status", sa.String(), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("price_basis", sa.String(), server_default="asking", nullable=False),
        sa.PrimaryKeyConstraint("source", "district_id", "period_start"),
        sa.CheckConstraint("length(source) > 0", name="ck_weekly_neighborhood_source_nonempty"),
        sa.CheckConstraint("EXTRACT(ISODOW FROM period_start) = 1",
                           name="ck_weekly_neighborhood_monday_start"),
        sa.CheckConstraint("period_end = period_start + 6", name="ck_weekly_neighborhood_period"),
        sa.CheckConstraint(
            "sample_count >= 0 AND per_sqm_sample_count >= 0 AND "
            "per_sqm_sample_count <= sample_count AND minimum_sample_count > 0",
            name="ck_weekly_neighborhood_sample_counts"),
        sa.CheckConstraint("median_price_usd_month IS NULL OR median_price_usd_month > 0",
                           name="ck_weekly_neighborhood_median_price_positive"),
        sa.CheckConstraint(
            "median_price_usd_per_sqm IS NULL OR median_price_usd_per_sqm > 0",
            name="ck_weekly_neighborhood_median_unit_price_positive"),
        sa.CheckConstraint("price_status IN ('available', 'insufficient_data')",
                           name="ck_weekly_neighborhood_price_status"),
        sa.CheckConstraint("per_sqm_status IN ('available', 'insufficient_data')",
                           name="ck_weekly_neighborhood_per_sqm_status"),
        sa.CheckConstraint(
            "(price_status = 'available' AND sample_count >= minimum_sample_count "
            "AND median_price_usd_month IS NOT NULL) OR "
            "(price_status = 'insufficient_data' AND sample_count < minimum_sample_count "
            "AND median_price_usd_month IS NULL)",
            name="ck_weekly_neighborhood_price_sparse_policy"),
        sa.CheckConstraint(
            "(per_sqm_status = 'available' AND per_sqm_sample_count >= minimum_sample_count "
            "AND median_price_usd_per_sqm IS NOT NULL) OR "
            "(per_sqm_status = 'insufficient_data' AND per_sqm_sample_count < minimum_sample_count "
            "AND median_price_usd_per_sqm IS NULL)",
            name="ck_weekly_neighborhood_per_sqm_sparse_policy"),
        sa.CheckConstraint("price_basis = 'asking'", name="ck_weekly_neighborhood_price_basis"),
    )
    op.create_index("ix_weekly_neighborhood_period", "weekly_neighborhood_price_indexes",
                    ["source", "district_id", "period_start"])
    op.execute("""
        CREATE VIEW weekly_neighborhood_asking_price_index AS
        SELECT source, district_id, period_start, period_end,
               median_price_usd_month AS median_asking_price_usd_month,
               median_price_usd_per_sqm AS median_asking_price_usd_per_sqm_month,
               sample_count, per_sqm_sample_count, minimum_sample_count,
               price_status, per_sqm_status, data_as_of, generated_at,
               price_basis,
               'Advertised rental asking prices; not signed-contract or transaction prices.'::text
                   AS interpretation
        FROM weekly_neighborhood_price_indexes
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS weekly_neighborhood_asking_price_index")
    op.drop_index("ix_weekly_neighborhood_period", table_name="weekly_neighborhood_price_indexes")
    op.drop_table("weekly_neighborhood_price_indexes")
