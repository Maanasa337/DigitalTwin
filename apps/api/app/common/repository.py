import builtins
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core.db import Base
from app.core.errors import UnprocessableError


class CrudRepository[M: Base]:
    model: type[M]
    sortable: frozenset[str] = frozenset({"created_at"})
    default_sort: str = "-created_at"

    def __init__(self, session: Session) -> None:
        self.session = session

    def _select(self) -> Select[tuple[M]]:
        stmt = select(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return stmt

    def get(self, id_: uuid.UUID) -> M | None:
        return self.session.scalars(self._select().where(self.model.id == id_)).first()  # type: ignore[attr-defined]

    def list(self, params: PageParams, filters: Sequence[ColumnElement[bool]] = ()) -> tuple[builtins.list[M], int]:
        stmt = self._select().where(*filters)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.session.scalars(
            stmt.order_by(self._order_by(params.sort or self.default_sort))
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        ).all()
        return list(items), total

    def all(self, filters: Sequence[ColumnElement[bool]] = ()) -> builtins.list[M]:
        return list(self.session.scalars(self._select().where(*filters).order_by(self._order_by(self.default_sort))))

    def create(self, obj: M) -> M:
        self.session.add(obj)
        self.session.flush()
        return obj

    def update(self, obj: M, values: dict[str, Any]) -> M:
        for key, value in values.items():
            setattr(obj, key, value)
        self.session.flush()
        return obj

    def soft_delete(self, obj: M) -> None:
        obj.deleted_at = func.now()  # type: ignore[attr-defined]
        self.session.flush()

    def _order_by(self, sort: str) -> ColumnElement[Any]:
        field = sort.removeprefix("-")
        if field not in self.sortable:
            raise UnprocessableError(f"Cannot sort by '{field}'. Allowed: {', '.join(sorted(self.sortable))}")
        column = getattr(self.model, field)
        return column.desc() if sort.startswith("-") else column.asc()
