"""
Router-wide organisation check.

``enforce_org_scope`` runs before any handler of the router it is attached to. It looks at every
id in the path (and the ``case_id`` filter in the query string) and refuses, with the same 404 an
unknown id gets, any id that belongs to another organisation. Handlers therefore never need to
remember to check, and a new route that takes an id is covered the day it is added.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request

from ipo_engine.screening.api.dependencies import Container, get_container
from ipo_engine.screening.core.security import get_principal, request_settings
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.tenancy import SCOPED_PARAMS, UNSCOPED_PARAMS, owner_org

_ENTITY = {
    "case_id": "case",
    "document_id": "document",
    "report_id": "report",
    "item_id": "review item",
    "comment_id": "comment",
}


def enforce_org_scope(request: Request, c: Container = Depends(get_container)) -> None:
    ids: dict[str, str] = {k: str(v) for k, v in request.path_params.items()}
    query_case = request.query_params.get("case_id")
    if query_case:
        ids["case_id"] = query_case
    checked = {k: v for k, v in ids.items() if k not in UNSCOPED_PARAMS}
    if not checked:
        return  # nothing to scope (health, lists, public rules): the route's own auth applies
    # Resolve the caller here only when there is an id to check, so public routes stay public.
    p = get_principal(request, request_settings(request), request.headers.get("authorization"))
    for name, value in checked.items():
        if name not in SCOPED_PARAMS:
            # An id this module cannot place must fail loudly, not be served unchecked.
            raise RuntimeError(f"route parameter {name!r} has no organisation scope rule")
        try:
            UUID(value)
        except ValueError:
            continue  # not an id at all: the route's own validation answers 422
        if owner_org(c.db, name, value) != p.org_id:
            raise NotFoundError(_ENTITY[name], value)
