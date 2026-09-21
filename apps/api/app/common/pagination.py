from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class PageParams:
    page: int
    size: int
    # Defaulted: three routers construct this directly and omitted it, which made every one of those
    # list endpoints raise a TypeError instead of returning a page.
    sort: str | None = None


def page_params(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    sort: str | None = Query(None, pattern=r"^-?[a-z_]+$", description="Field name, prefix '-' for descending"),
) -> PageParams:
    return PageParams(page, size, sort)
