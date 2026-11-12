"""Frozen linear42 input mapping without requiring the unused other15 fields."""

import numpy as np


def linear42_vector(f):
    n,m=f["variables"],f["clauses"]
    if n<=0 or m<=0: raise ValueError("undefined trained statistics for empty input")
    names=("mean","variance","min","max","entropy")
    counts=np.array([f[f"cls{k}"] for k in range(1,10)]+[f["cls10p"]])
    widths=counts/m
    basic=np.r_[np.log1p(n),np.log1p(m),max(0.,1-widths.sum()),widths,
        [f[k]/m for k in ("positive","negative","horn","invhorn")],
        [f[p+"_"+s] for p in ("balancecls","balancevars") for s in names]]
    def stats(p):
        mean,variance,minimum,maximum,entropy=[f[p+"_"+s] for s in names]
        return np.array([np.log1p(mean),np.log1p(variance/max(mean**2,1e-12)),
            minimum/max(mean,1e-12),np.log1p(maximum/max(mean,1e-12)),entropy])
    vector=np.r_[basic,*[stats(p) for p in ("vcg_vdegree","hornvars","invhornvars")]]
    assert vector.shape==(42,) and np.isfinite(vector).all()
    return vector
