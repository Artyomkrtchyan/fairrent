"""Read A07's stable view directly; the pipeline owns publication and thresholds."""
import psycopg
from psycopg.rows import dict_row

try:
    from .market_models import MarketAggregate, MarketQuery
except ImportError:
    from market_models import MarketAggregate, MarketQuery


SOURCE = "list.am"


def market_where(query: MarketQuery, *, dates: bool = True):
    clauses, params = ["source = %s"], [SOURCE]
    if query.district_id is not None:
        clauses.append("district_id = %s")
        params.append(query.district_id)
    if dates:
        for value, operator in ((query.period_start, ">="), (query.period_end, "<=")):
            if value is not None:
                clauses.append(f"period_start {operator} %s")
                params.append(value)
    return " AND ".join(clauses), params


class MarketRepository:
    def search(self, query: MarketQuery):
        where, params = market_where(query)
        coverage_where, coverage_params = market_where(query, dates=False)
        # Coverage, filtered count and page must describe one database snapshot.
        with psycopg.connect(connect_timeout=3, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            coverage = connection.execute(
                "SELECT min(period_start) AS available_from, max(period_start) AS available_to "
                f"FROM weekly_neighborhood_asking_price_index WHERE {coverage_where}",
                coverage_params,
            ).fetchone()
            total = connection.execute(
                f"SELECT count(*) AS total FROM weekly_neighborhood_asking_price_index WHERE {where}",
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                "SELECT district_id, period_start, period_end, sample_count, "
                "per_sqm_sample_count AS area_sample_count, "
                "median_asking_price_usd_month AS median_usd_month, "
                "median_asking_price_usd_per_sqm_month AS median_usd_m2, "
                "price_status AS status, data_as_of "
                f"FROM weekly_neighborhood_asking_price_index WHERE {where} "
                "ORDER BY period_start ASC, district_id ASC LIMIT %s OFFSET %s",
                [*params, query.page_size, (query.page - 1) * query.page_size],
            ).fetchall()
        return ([MarketAggregate.model_validate(row) for row in rows], total,
                coverage["available_from"], coverage["available_to"])
