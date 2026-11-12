"""Map raw structural measurements to the existing frozen model input order."""

import numpy as np


STATS = ("mean", "variance", "min", "max", "entropy")


def vectorize(f):
    n, m = f["variables"], f["clauses"]
    if n <= 0 or m <= 0:
        raise ValueError("undefined trained statistics for empty input")
    counts = np.array([f[f"cls{i}"] for i in range(1, 10)] + [f["cls10p"]])
    widths = counts / m
    empty = max(0., 1 - widths.sum())
    basic = np.r_[np.log1p(n), np.log1p(m), empty, widths,
                  [f[p] / m for p in ("positive", "negative", "horn", "invhorn")],
                  [f[p + "_" + s] for p in ("balancecls", "balancevars") for s in STATS]]

    def stats(prefix):
        mean, variance, minimum, maximum, entropy = [f[prefix + "_" + s] for s in STATS]
        return np.array([np.log1p(mean), np.log1p(variance / max(mean ** 2, 1e-12)),
                         minimum / max(mean, 1e-12), np.log1p(maximum / max(mean, 1e-12)), entropy])

    linear42 = np.r_[basic, *[stats(p) for p in ("vcg_vdegree", "hornvars", "invhornvars")]]
    all57 = np.r_[linear42, *[stats(p) for p in ("vcg_cdegree", "vg_degree", "cg_degree")]]
    # The legacy view contains structural connected-component ratio. It is
    # preserved to reproduce the frozen model, rather than silently omitted.
    raw_empty = m - counts.sum()
    base28 = np.r_[
        np.log1p(n), np.log1p(m / n), np.sqrt(np.r_[empty, widths]),
        (f["positive"] - raw_empty) / m, (f["negative"] - raw_empty) / m,
        (f["invhorn"] - f["horn"]) / m,
        [f[p + "_" + s] for p in ("balancecls", "balancevars") for s in ("mean", "variance")],
        np.log1p(np.sqrt(f["vcg_vdegree_variance"]) / max(f["vcg_vdegree_mean"], 1e-12)),
        np.log1p(f["ccs"] / n), f["vcg_vdegree_entropy"], f["vcg_cdegree_entropy"],
        np.log1p(f["vg_degree_mean"]), np.log1p(f["cg_degree_mean"]),
        f["vg_degree_entropy"], f["cg_degree_entropy"]]
    tail = []
    for p in ("vcg_vdegree", "vcg_cdegree", "vg_degree", "cg_degree"):
        values = stats(p)
        tail.extend(values[[0, 1, 3, 2, 4]])
    for p in ("balancecls", "balancevars"):
        tail.extend((f[p + "_max"] - f[p + "_min"], f[p + "_entropy"]))
    legacy52 = np.r_[base28, tail]
    result = {"linear42": linear42, "all57": all57, "legacy52": legacy52}
    assert all(x.shape == (int(name.removeprefix("linear").removeprefix("all").removeprefix("legacy")),)
               and np.isfinite(x).all() for name, x in result.items())
    return result
