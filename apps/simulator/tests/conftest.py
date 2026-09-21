from pathlib import Path

import pytest

from sim.catalog import Catalog
from sim.engine import Engine

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture
def engine(catalog: Catalog) -> Engine:
    """Fleet starting Monday 06:00 plant time (shift A), one tick per sim minute."""
    return Engine(catalog, seed=5, tick_s=60.0)
