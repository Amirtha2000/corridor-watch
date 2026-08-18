import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from corridor_watch.analysis import risk

UTM = "EPSG:32633"
WEIGHTS = {"veg_fraction": 0.4, "ndvi_p90": 0.25, "growth_fraction": 0.35}
THRESHOLDS = {"high": 0.6, "medium": 0.35}


def scored_input(veg, p90, growth, n_pixels=100, valid=1.0):
    return gpd.GeoDataFrame(
        {
            "segment_id": ["s1"],
            "n_pixels": [n_pixels],
            "valid_fraction": [valid],
            "ndvi_mean": [0.5],
            "ndvi_p90": [p90],
            "veg_fraction": [veg],
            "growth_fraction": [growth],
        },
        geometry=[box(0, 0, 10, 10)],
        crs=UTM,
    )


def test_score_bounds():
    hi = risk.score(scored_input(1.0, 0.9, 1.0), WEIGHTS, THRESHOLDS)
    lo = risk.score(scored_input(0.0, 0.0, 0.0), WEIGHTS, THRESHOLDS)
    assert hi["risk_score"].iloc[0] == pytest.approx(1.0)
    assert lo["risk_score"].iloc[0] == pytest.approx(0.0)
    assert hi["risk_class"].iloc[0] == "high"
    assert lo["risk_class"].iloc[0] == "low"


def test_no_data_segment_is_flagged_not_scored_low():
    out = risk.score(
        scored_input(np.nan, np.nan, np.nan, n_pixels=0, valid=0.0), WEIGHTS, THRESHOLDS
    )
    assert out["risk_class"].iloc[0] == "no-data"


def test_missing_driver_column_raises():
    bad = scored_input(0.5, 0.5, 0.5).drop(columns=["veg_fraction"])
    with pytest.raises(ValueError, match="missing driver"):
        risk.score(bad, WEIGHTS, THRESHOLDS)


def test_wrong_weight_keys_raise():
    with pytest.raises(ValueError, match="weights"):
        risk.score(scored_input(0.5, 0.5, 0.5), {"veg_fraction": 1.0}, THRESHOLDS)


def test_ranking_orders_by_score():
    a = scored_input(0.9, 0.8, 0.9)
    b = scored_input(0.1, 0.3, 0.0)
    b["segment_id"] = ["s2"]
    both = risk.score(
        gpd.GeoDataFrame(pd.concat([a, b], ignore_index=True), crs=UTM), WEIGHTS, THRESHOLDS
    )
    assert both.iloc[0]["segment_id"] == "s1"
    assert both.iloc[0]["rank"] == 1
