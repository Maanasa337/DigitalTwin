import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.common.repository import CrudRepository
from app.core.audit import snapshot, write_audit
from app.core.db import Base
from app.core.errors import NotFoundError
from app.core.security import CurrentUser


class CrudService[M: Base]:
    """Create/update/retire with the audit row written in the same transaction as the change."""

    entity: str
    label: str

    def __init__(self, session: Session, repo: CrudRepository[M]) -> None:
        self.session = session
        self.repo = repo

    def get_or_404(self, id_: uuid.UUID) -> M:
        obj = self.repo.get(id_)
        if obj is None:
            raise NotFoundError(f"{self.label} {id_} not found")
        return obj

    def create(self, actor: CurrentUser | None, obj: M) -> M:
        self.repo.create(obj)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=obj.id,  # type: ignore[attr-defined]
            action="create",
            after=snapshot(obj),
        )
        self.session.commit()
        return obj

    def update(self, actor: CurrentUser | None, obj: M, values: dict[str, Any]) -> M:
        before = snapshot(obj)
        self.repo.update(obj, values)
        write_audit(
            self.session,
            actor=actor,
            entity=self.entity,
            entity_id=obj.id,  # type: ignore[attr-defined]
            action="update",
            before=before,
            after=snapshot(obj),
        )
        self.session.commit()
        return obj

    def retire(self, actor: CurrentUser | None, obj: M) -> None:
        before = snapshot(obj)
        self.repo.soft_delete(obj)
        write_audit(self.session, actor=actor, entity=self.entity, entity_id=obj.id, action="delete", before=before)  # type: ignore[attr-defined]
        self.session.commit()
