import numpy as np
import pytest

from core.plan_calibration import fit_affine, apply_affine


def test_affine_round_trip():
    px=[[0,0],[100,0],[0,100],[100,100]]
    xy=[[10,20],[110,20],[10,120],[110,120]]
    coef,rms=fit_affine(px,xy)
    assert rms < 1e-10
    assert np.allclose(apply_affine(35,60,coef),[45,80])


def test_affine_rejects_collinear_points():
    with pytest.raises(ValueError):
        fit_affine([[0,0],[1,1],[2,2]],[[0,0],[1,1],[2,2]])
