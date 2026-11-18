"""The engine adapter on the engine's own demo store (slow: builds a snapshot), then the full build from it."""
import json
from datetime import date

import pytest

from dsereport import build, schema, source

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def demo_inputs(tmp_path_factory):
    demo = pytest.importorskip("pnf_app.demo")
    path = str(tmp_path_factory.mktemp("demo") / "demo.sqlite3")
    demo.build(path, sessions=320, end=date(2026, 9, 24))
    return source.collect(path)


def test_collect_returns_plain_json(demo_inputs):
    text = json.dumps(demo_inputs, default=str)
    assert json.loads(text)["asof"] == demo_inputs["asof"]


def test_collect_has_every_section(demo_inputs):
    for key in ("sessions", "dsex", "market_bp", "bp_series", "sector_bp", "sector_rows", "sector_series",
                "stocks", "daily", "events"):
        assert key in demo_inputs
    assert demo_inputs["stocks"] and demo_inputs["daily"]
    assert len(demo_inputs["dsex"]["close"]) == len(demo_inputs["dsex"]["dates"])


def test_stock_fields_are_trimmed(demo_inputs):
    st = next(iter(demo_inputs["stocks"].values()))
    assert len(st["close"]) <= source.STOCK_BARS and "buy_at" in st and "pf" in st


def test_a_report_builds_and_validates_from_the_demo_store(demo_inputs):
    report = build.build_report(demo_inputs, None, built_at="2026-09-24T11:00:00Z")
    assert schema.validate(report) == []
