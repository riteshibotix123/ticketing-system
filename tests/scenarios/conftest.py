import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from tests.scenarios.helpers import Org, Portal, build_org


@pytest.fixture
def org(db: Session) -> Org:
    return build_org(db)


@pytest.fixture
def portal(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, org: Org
) -> Portal:
    return Portal(client=client, db=db, clock=clock, settings=settings, org=org)
