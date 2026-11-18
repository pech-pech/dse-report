"""The pending objective uses the engine's chart and scale (FixedScale box 1, reversal 3); no price store needed."""
from pnf.chart import build_chart
from pnf.scale import FixedScale

from dsereport.source import _pending


def _chart(closes):
    return build_chart(closes, closes, closes, scale=FixedScale(1.0), reversal=3)


# X 10->20, O 20->15, X 15->18 : one box under the 19 trigger above the old top 20? trigger = 21 (top 20 + 1)
UP_DOWN_UP = [10, 12, 14, 16, 18, 20, 18, 16, 15, 17, 18]


def test_objective_uses_engine_formula_and_first_resistance():
    ch = _chart(UP_DOWN_UP)
    cur = ch.columns[-1]
    assert cur.direction == "X"
    got = _pending(ch, 21.0)
    lo = ch.scale.level(cur.lo)
    top = ch.scale.floor_box(21.0)
    assert got["objective"] == round(lo + 3 * (top - cur.lo + 1) * 1.0, 2)
    assert got["resistance"] is None          # nothing above the trigger


def test_resistance_is_nearest_column_top_above_trigger():
    ch = _chart([30, 10, 25, 15, 18])          # O 30->10, X ->25, O ->15, X ->18
    got = _pending(ch, 19.0)
    x_top = ch.columns[-3]
    assert x_top.direction == "X" and got["resistance"] == ch.scale.level(x_top.hi) > 19.0


def test_no_pending_without_trigger_or_on_an_o_column():
    assert _pending(_chart(UP_DOWN_UP), None) is None
    assert _pending(_chart([10, 15, 20, 16]), 21.0) is None   # current column is O
    assert _pending(None, 21.0) is None
    assert _pending(_chart(UP_DOWN_UP), 17.0) is None         # trigger inside the current column
