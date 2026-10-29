import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PageParams,
    fetch_page,
    parse_sort,
)
from app.models import Department
from tests.factories import make_department


def test_defaults() -> None:
    params = PageParams()
    assert (params.page, params.page_size, params.offset) == (1, DEFAULT_PAGE_SIZE, 0)


def test_offset() -> None:
    assert PageParams(page=3, page_size=10).offset == 20


@pytest.mark.parametrize(("page", "page_size", "field"), [(0, 25, "page"), (1, 0, "page_size")])
def test_bounds_rejected(page: int, page_size: int, field: str) -> None:
    with pytest.raises(ApiError) as caught:
        PageParams(page=page, page_size=page_size)
    assert caught.value.code is ErrorCode.VALIDATION_ERROR
    assert caught.value.fields is not None
    assert field in caught.value.fields


def test_page_size_above_max_rejected() -> None:
    with pytest.raises(ApiError):
        PageParams(page_size=MAX_PAGE_SIZE + 1)
    assert PageParams(page_size=MAX_PAGE_SIZE).page_size == MAX_PAGE_SIZE


def test_parse_sort_whitelist() -> None:
    allowed = {"created_at": "asc", "-created_at": "desc"}
    assert parse_sort(None, allowed, "created_at") == "asc"
    assert parse_sort("-created_at", allowed, "created_at") == "desc"
    with pytest.raises(ApiError) as caught:
        parse_sort("password_hash", allowed, "created_at")
    assert caught.value.code is ErrorCode.VALIDATION_ERROR
    assert caught.value.fields is not None
    assert "sort" in caught.value.fields


def test_fetch_page_counts_and_slices(db: Session) -> None:
    codes = ["PGAA", "PGAB", "PGAC", "PGAD", "PGAE"]
    for code in codes:
        make_department(db, code)
    statement = select(Department).where(Department.id.like("PGA%")).order_by(Department.id.desc())
    result = fetch_page(db, statement, PageParams(page=2, page_size=2))
    assert result.total == 5
    assert (result.page, result.page_size) == (2, 2)
    assert [department.id for department in result.items] == ["PGAC", "PGAB"]
    empty = fetch_page(db, statement, PageParams(page=4, page_size=2))
    assert empty.total == 5
    assert empty.items == []
