import numpy as np
import pytest

from corridor_watch.analysis import indices


def test_ndvi_known_values():
    red = np.array([[0.1, 0.3]])
    nir = np.array([[0.5, 0.3]])
    out = indices.ndvi(red, nir)
    assert out[0, 0] == pytest.approx((0.5 - 0.1) / (0.5 + 0.1))
    assert out[0, 1] == pytest.approx(0.0)


def test_ndvi_zero_denominator_is_nan_not_inf():
    out = indices.ndvi(np.array([[0.0]]), np.array([[0.0]]))
    assert np.isnan(out[0, 0])


def test_ndvi_respects_nodata_sentinel():
    out = indices.ndvi(np.array([[0.1, -9999.0]]), np.array([[0.5, 0.4]]), nodata=-9999.0)
    assert np.isfinite(out[0, 0])
    assert np.isnan(out[0, 1])


def test_ndvi_propagates_nan():
    out = indices.ndvi(np.array([[np.nan]]), np.array([[0.4]]))
    assert np.isnan(out[0, 0])


def test_delta_shape_mismatch_raises():
    with pytest.raises(ValueError, match="co-registered"):
        indices.delta(np.zeros((2, 2)), np.zeros((3, 3)))


def test_delta_values():
    out = indices.delta(np.array([[0.2]]), np.array([[0.5]]))
    assert out[0, 0] == pytest.approx(0.3)
