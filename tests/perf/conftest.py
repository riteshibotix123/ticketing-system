from pathlib import Path

import pytest

PERF_DIR = Path(__file__).resolve().parent
SKIP_UNDER_COVERAGE = pytest.mark.skip(
    reason="timing budgets are not meaningful under coverage; run tests/perf without --cov"
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("cov_source", default=None):
        return
    for item in items:
        if PERF_DIR in Path(str(item.path)).resolve().parents:
            item.add_marker(SKIP_UNDER_COVERAGE)
