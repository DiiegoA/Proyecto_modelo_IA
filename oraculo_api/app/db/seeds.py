from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models import UserRole
from app.db.repositories import UserRepository

logger = logging.getLogger("oraculo_api.seeds")


def seed_admin_user(session: Session, settings: Settings) -> None:
    if not settings.auto_seed_admin:
        return
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return

    repository = UserRepository(session)
    existing_user = repository.get_by_email(settings.seed_admin_email)
    if existing_user:
        return

    repository.create(
        email=settings.seed_admin_email,
        full_name=settings.seed_admin_name,
        password_hash=hash_password(settings.seed_admin_password),
        role=UserRole.ADMIN.value,
    )
    logger.info("Default admin user created for bootstrap.")
