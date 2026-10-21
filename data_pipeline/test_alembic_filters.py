from sqlalchemy import Column, Index, Integer, MetaData, Table
from database.alembic_filters import make_include_hooks
from database.models import Base


def hooks():
    return make_include_hooks(Base.metadata)

def foreign_table(name="spatial_ref_sys"):
    return Table(name, MetaData(), Column("id", Integer))


def test_project_tables_are_included_extension_tables_are_not():
    include_name, include_object = hooks()
    for name in Base.metadata.tables:
        assert include_name(name, "table", {}) and include_object(Base.metadata.tables[name], name, "table", True, None)
    for ext in ("spatial_ref_sys", "geocode_settings", "topology", "layer", "pagc_gaz", "loader_lookuptables"):
        assert not include_name(ext, "table", {})
        assert not include_object(foreign_table(ext), ext, "table", True, None)


def test_only_the_default_schema_is_reflected():
    include_name, _ = hooks()
    assert include_name(None, "schema", {})
    for schema in ("tiger", "tiger_data", "topology"):
        assert not include_name(schema, "schema", {})


def test_indexes_and_columns_of_foreign_tables_are_ignored():
    _, include_object = hooks()
    ext = foreign_table("some_extension_table")
    idx = Index("ix_ext", ext.c.id)
    assert not include_object(idx, "ix_ext", "index", True, None)
    assert not include_object(ext.c.id, "id", "column", True, None)


def test_indexes_of_project_tables_are_kept():
    _, include_object = hooks()
    listings = Base.metadata.tables["listings"]
    idx = next(iter(listings.indexes))
    assert include_object(idx, idx.name, "index", True, None)
