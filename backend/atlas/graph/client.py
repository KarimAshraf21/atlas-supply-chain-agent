from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from neo4j import Driver, GraphDatabase

from ..config import get_settings


@lru_cache
def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password.get_secret_value()))


@contextmanager
def session() -> Iterator[Any]:
    with get_driver().session(database=get_settings().neo4j_database) as sess:
        yield sess


def run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Run a read or write query and return records as plain dicts."""
    records, _, _ = get_driver().execute_query(query, params, database_=get_settings().neo4j_database)
    return [r.data() for r in records]
