from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def is_none(value: object) -> bool:
    return value is None


class Page[T](ApiModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class UserRef(ApiModel):
    id: str
    name: str
    email: str
    title: str | None = Field(default=None, exclude_if=is_none)


class SystemActor(ApiModel):
    id: Literal["system"] = "system"
    name: Literal["System"] = "System"


type Actor = UserRef | SystemActor

SYSTEM_ACTOR: Final = SystemActor()
