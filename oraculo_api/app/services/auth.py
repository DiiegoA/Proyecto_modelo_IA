from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, ResourceNotFoundError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.repositories import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


class AuthService:
    def __init__(self, user_repository: UserRepository, settings: Settings):
        self.user_repository = user_repository
        self.settings = settings

    def register(self, payload: RegisterRequest) -> UserResponse:
        if self.user_repository.get_by_email(payload.email):
            raise ConflictError("A user with that email already exists.", {"email": payload.email})

        user = self.user_repository.create(
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        return UserResponse.model_validate(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.user_repository.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError("Inactive user.")

        access_token = create_access_token(
            subject=user.id,
            role=user.role,
            settings=self.settings,
        )
        return TokenResponse(
            access_token=access_token,
            expires_in_seconds=self.settings.access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )

    def get_user(self, user_id: str) -> User:
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User", user_id)
        return user
