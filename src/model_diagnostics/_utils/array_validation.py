import numpy as np
import numpy.typing as npt


def validate_2_arrays(
    a: npt.ArrayLike, b: npt.ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """Validate 2 arrays."""
    # Note: If the input is an pyarrow array, np.asarray produces a read-only ndarray.
    a = np.asarray(a)
    b = np.asarray(b)
    if a.ndim != b.ndim:
        raise ValueError(
            f"Arrays must have the same dimension, got {a.ndim=} and {b.ndim=}."
        )
    for i in range(a.ndim):
        if a.shape[i] != b.shape[i]:
            raise ValueError(
                f"Arrays must have the same shape, got {a.shape=} and {b.shape=}."
            )
    return a, b
