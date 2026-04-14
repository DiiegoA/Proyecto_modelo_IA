from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseSchema):
    total: int
    skip: int
    limit: int


class TimestampedSchema(BaseSchema):
    created_at: datetime
    updated_at: datetime
