import os
import re

import pytest
from sqlalchemy import inspect

from src.db import get_engine
from src.etl.schema import TABLES_DROP_ORDER, apply_schema, ddl_files, split_statements

requires_db = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="defina RUN_DB_TESTS=1 para testar contra o MySQL",
)


def test_split_statements_ignores_comments_and_blank_parts():
    script = "-- comentário\nCREATE TABLE a (id INT);\n\n-- outro\nCREATE TABLE b (id INT);\n"
    assert split_statements(script) == ["CREATE TABLE a (id INT)", "CREATE TABLE b (id INT)"]


def test_ddl_files_are_ordered_and_skip_database_creation():
    names = [path.name for path in ddl_files()]
    assert names
    assert names == sorted(names)
    assert not any(name.startswith("00_") for name in names)


def test_every_statement_creates_a_table_if_not_exists():
    for path in ddl_files():
        statements = split_statements(path.read_text(encoding="utf-8"))
        assert statements, path.name
        assert all(s.startswith("CREATE TABLE IF NOT EXISTS") for s in statements), path.name


def test_drop_order_covers_every_table_and_drops_children_first():
    created = []
    for path in ddl_files():
        for statement in split_statements(path.read_text(encoding="utf-8")):
            name = re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", statement).group(1)
            created.append(name)
            for referenced in re.findall(r"REFERENCES\s+(\w+)", statement):
                assert TABLES_DROP_ORDER.index(name) < TABLES_DROP_ORDER.index(referenced)
    assert sorted(created) == sorted(TABLES_DROP_ORDER)


@requires_db
def test_schema_can_be_applied_twice_and_creates_every_table():
    engine = get_engine()
    apply_schema(engine)
    apply_schema(engine)
    assert set(inspect(engine).get_table_names()) >= set(TABLES_DROP_ORDER)