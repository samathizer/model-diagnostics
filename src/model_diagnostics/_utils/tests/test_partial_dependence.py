import sys
import warnings

import numpy as np
import polars as pl
import pytest
from numpy.testing import assert_allclose, assert_equal
from polars.testing import assert_frame_equal
from sklearn.base import RegressorMixin
from sklearn.inspection import partial_dependence

from model_diagnostics._utils.array import get_second_dimension, safe_index_rows
from model_diagnostics._utils.partial_dependence import compute_partial_dependence


@pytest.mark.parametrize("n_max", [None, 50])
@pytest.mark.parametrize("weights", [None, True])
@pytest.mark.parametrize("feature_type", ["numeric", "cat", "enum", "string"])
@pytest.mark.parametrize("data_container", ["list", "pandas", "polars", "pyarrow"])
def test_compute_partial_dependence(n_max, weights, feature_type, data_container):
    """Test compute_partial_dependence vs scikit-learn version."""
    try:
        pandas = sys.modules["pandas"]
    except KeyError:
        pandas = None
    try:
        pyarrow = sys.modules["pyarrow"]
    except KeyError:
        pyarrow = None
    if data_container == "pandas" and pandas is None:
        pytest.skip()
    if data_container == "pyarrow" and pyarrow is None:
        pytest.skip()

    n_obs = 100
    n_bins = 10
    X = pl.DataFrame(
        {
            "a": np.arange(n_obs) % n_bins,
            "b": np.sin(np.arange(n_obs)),
        }
    )
    if feature_type == "cat":
        dtype = pl.Categorical
        X = X.with_columns(pl.col("a").cast(pl.Utf8).cast(dtype))
        cat_index = [0]
    elif feature_type == "enum":
        dtype = pl.Enum(categories=X.get_column("a").unique().cast(pl.Utf8))
        X = X.with_columns(pl.col("a").cast(dtype))
        cat_index = [0]
    elif feature_type == "string":
        dtype = pl.Utf8
        X = X.with_columns(pl.col("a").cast(dtype))
        cat_index = [0]
    else:
        cat_index = None

    X_orig = X.clone()
    # Convert X to something scikit-learn can work with.
    if pandas is None:
        if feature_type in ["cat", "enum"]:
            pytest.skip()
        else:
            X_skl = X.to_numpy()
    elif pyarrow is None:
        X_skl = pandas.api.interchange.from_dataframe(X)
    else:
        X_skl = X.to_pandas()
    grid = X.get_column("a").unique().sort()

    if data_container == "list":
        X = [list(row.values()) for row in X.to_dicts()]
    elif data_container == "pandas":
        X = X.to_pandas()
    elif data_container == "pyarrow":
        X = X.to_arrow()

    if weights is not None:
        weights = np.ones(n_obs)

    def predict(X):
        a = get_second_dimension(X, 0)
        b = get_second_dimension(X, 1)
        if hasattr(a, "to_numpy"):
            a = a.to_numpy()
            b = b.to_numpy()
        a = a.astype(float)
        return a + 2 * b + 3 * a * b

    rng = np.random.default_rng(123) if n_max is not None else None

    pd_values = compute_partial_dependence(
        pred_fun=predict,
        X=X,
        feature_index=0,
        grid=grid,
        weights=weights,
        n_max=n_max,
        rng=rng,
    )

    class ModelWrapPredict(RegressorMixin):
        def fit(self, X):
            self.is_fitted_ = True
            return self

        def predict(self, X):
            return predict(X)

    model = ModelWrapPredict().fit(X)
    if n_max is not None and n_max < n_obs:
        # This mimicks the subsampling in compute_partial_dependence.
        rng = np.random.default_rng(123)  # exact same as above
        row_indices = rng.choice(n_obs, size=n_max, replace=False)
        X_skl = safe_index_rows(X_skl, row_indices)

    with warnings.catch_warnings():
        warnings.simplefilter(action="ignore", category=DeprecationWarning)
        pd_sklearn = partial_dependence(
            estimator=model, X=X_skl, features=0, categorical_features=cat_index
        )

    if feature_type == "numeric":
        assert_allclose(grid, pd_sklearn["grid_values"][0])
    else:
        assert_equal(grid, pd_sklearn["grid_values"][0])
    assert_allclose(pd_values, pd_sklearn["average"][0])

    # Check that X was not modified on the way.
    assert_frame_equal(
        X_orig, pl.DataFrame(X, schema=["a", "b"], orient="row"), check_dtypes=False
    )
