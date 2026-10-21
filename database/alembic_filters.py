def make_include_hooks(target_metadata):
    project_tables = set(target_metadata.tables)

    def include_name(name, type_, parent_names):
        if type_ == "schema":
            return name is None                 # default schema only: no tiger/topology/...
        if type_ == "table":
            return name in project_tables
        return True

    def include_object(obj, name, type_, reflected, compare_to):
        if type_ == "table":
            return name in project_tables
        table = getattr(obj, "table", None)     # columns, indexes, constraints of other tables
        if table is not None and table.name not in project_tables:
            return False
        return True

    return include_name, include_object