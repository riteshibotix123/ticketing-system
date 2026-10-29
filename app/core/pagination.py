from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import validation_error

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class PageParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> None:
        if page < 1:
            raise validation_error({"page": "Must be at least 1"})
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise validation_error({"page_size": f"Must be between 1 and {MAX_PAGE_SIZE}"})
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    total: int
    page: int
    page_size: int


def count_rows[T](session: Session, statement: Select[tuple[T]]) -> int:
    counted = select(func.count()).select_from(statement.order_by(None).subquery())
    return session.scalar(counted) or 0


def fetch_page[T](
    session: Session, statement: Select[tuple[T]], params: PageParams
) -> PageResult[T]:
    total = count_rows(session, statement)
    items = list(session.scalars(statement.limit(params.page_size).offset(params.offset)))
    return PageResult(items=items, total=total, page=params.page, page_size=params.page_size)


def parse_sort[T](sort: str | None, allowed: Mapping[str, T], default: str) -> T:
    key = sort.strip() if sort else default
    if key not in allowed:
        raise validation_error({"sort": f"Must be one of: {', '.join(sorted(allowed))}"})
    return allowed[key]
