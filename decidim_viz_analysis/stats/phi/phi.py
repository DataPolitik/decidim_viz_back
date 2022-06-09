import pandas as pd
import numpy as np
import sys
from math import sqrt
from sklearn.metrics import matthews_corrcoef


def __compute_phi(author_source: pd.Series, author_target: pd.Series):
    source_np: np.ndarray = author_source.values
    target_np: np.ndarray = author_target.values

    phi: float = matthews_corrcoef(source_np, target_np)
    den: float = sqrt(1 - phi * phi)

    t: float = sys.maxsize
    if den > 0:
        try:
            t = (phi * sqrt(len(source_np) - 2)) / sqrt(1 - phi * phi)
        except:
            print("N {}\n".format(len(source_np)))
            t = 0

    return phi, t
