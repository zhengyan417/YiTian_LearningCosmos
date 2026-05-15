"""Validation helpers for the data_query skill.

Two distinct surfaces, two checks:

- ``check_sql_readonly`` — SECONDARY defence for ``run_sql``. The PRIMARY one is
  the read-only PostgreSQL account behind ``DATA_QUERY_READONLY_DSN``; the regex
  here just stops obvious mistakes before they hit the wire and provides a
  clearer error message to the LLM than a database permission denial.
- ``check_url_host`` — PRIMARY defence for ``http_api_call``. There is no
  network-level enforcement (no egress proxy in the template), so the host
  whitelist must be tight and absolute.
"""

import re
from typing import Tuple
from urllib.parse import urlparse

from app.core.config import settings

# Forbidden write / DDL / admin keywords, matched as whole words so column names
# like ``update_time`` or ``drop_count`` don't trigger false positives.
_FORBIDDEN_SQL_KEYWORDS = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|"
    r"call|do|copy|vacuum|cluster|reindex|listen|notify|lock|"
    r"set|reset|prepare|execute|deallocate|begin|commit|rollback|savepoint"
    r")\b",
    re.IGNORECASE,
)

# ``run_sql`` accepts only queries starting with these keywords.
_ALLOWED_SQL_PREFIXES = frozenset({"select", "with", "explain", "show"})


def check_sql_readonly(sql: str) -> Tuple[bool, str]:
    """Return ``(ok, reason)`` for an LLM-supplied SQL string.

    Rejects: empty input, multi-statement input, anything that doesn't start with
    SELECT/WITH/EXPLAIN/SHOW, or anything containing a forbidden write keyword.
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False, "SQL is empty."

    # Multi-statement guard: a remaining ``;`` after rstrip means a second statement.
    if ";" in stripped:
        return False, "Multiple statements are not allowed in a single call."

    first_word = stripped.split(None, 1)[0].lower()
    if first_word not in _ALLOWED_SQL_PREFIXES:
        return False, (
            f"Only SELECT / WITH / EXPLAIN / SHOW queries are allowed (got '{first_word}'). Rewrite as a SELECT."
        )

    if _FORBIDDEN_SQL_KEYWORDS.search(stripped):
        return False, (
            "Query contains a forbidden write / DDL / transaction keyword. "
            "Even string literals containing these keywords are rejected — rewrite "
            "the query without the offending word, or escape the literal differently."
        )

    return True, ""


def check_url_host(url: str) -> Tuple[bool, str]:
    """Return ``(ok, reason)`` for an LLM-supplied URL.

    Rejects: invalid URLs, non-http(s) schemes, and any host outside
    ``settings.DATA_QUERY_ALLOWED_HOSTS``.
    """
    try:
        parsed = urlparse(url)
    except ValueError as e:
        return False, f"Could not parse URL: {e}"

    if parsed.scheme not in {"http", "https"}:
        return False, f"Only http(s) is allowed (got scheme '{parsed.scheme}')."

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "URL has no host component."

    allowed = {h.strip().lower() for h in settings.DATA_QUERY_ALLOWED_HOSTS if h.strip()}
    if host not in allowed:
        return False, (
            f"Host '{host}' is not in DATA_QUERY_ALLOWED_HOSTS. Ask the user / operator to add it before retrying."
        )

    return True, ""
