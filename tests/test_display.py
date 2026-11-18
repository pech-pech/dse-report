from dsereport import display


def test_sector_name_maps_known_and_keeps_others():
    assert display.sector_name("FuelPower") == "Fuel & Power"
    assert display.sector_name("Bank") == "Bank"


def test_relabel_replaces_in_values_keys_and_sentences():
    report = {"rows": [{"sector": "TravelLeisur", "chg": 2.9}],
              "by_sector": {"ServRealEst": 21.1, "Bank": 5},
              "lede": "ServRealEst led (+3.7%) and Financial In lagged; Misc flat.", "n": 3, "x": None}
    out = display.relabel(report)
    assert out["rows"][0]["sector"] == "Travel & Leisure"
    assert set(out["by_sector"]) == {"Services & Real Estate", "Bank"}
    assert out["lede"] == "Services & Real Estate led (+3.7%) and Financial Institutions lagged; Miscellaneous flat."
    assert out["n"] == 3 and out["x"] is None
    assert report["rows"][0]["sector"] == "TravelLeisur"      # the input is not changed


def test_relabel_does_not_touch_parts_of_other_words():
    assert display.relabel("Miscellaneous FuelPowers MiscX") == "Miscellaneous FuelPowers MiscX"
    assert display.relabel("Fuel & Power") == "Fuel & Power"   # already a display name: unchanged
