import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rateshock.cpi import cpi_releases            # noqa: E402
from rateshock.dataset import build               # noqa: E402


@pytest.fixture(scope="session")
def data():
    events, prices, panel, df = build(save=False)
    return {"events": events, "prices": prices, "panel": panel, "df": df}


@pytest.fixture(scope="session")
def releases():
    return cpi_releases()
