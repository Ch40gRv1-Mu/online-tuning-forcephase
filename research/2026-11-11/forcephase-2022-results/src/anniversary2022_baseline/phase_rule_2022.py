"""Frozen two-threshold selector for the 2022 Anniversary replay."""

import argparse
import math


SCC_CUT = 0.10
WIDTH_CUT = 5.73


def choose_action(scc_demand_share=None, mean_clause_width=None):
    """Use verified eligible features only, represented by None when unavailable."""
    if scc_demand_share is not None and math.isfinite(scc_demand_share) and scc_demand_share > SCC_CUT:
        return "Fminus"
    if mean_clause_width is not None and math.isfinite(mean_clause_width) and mean_clause_width > WIDTH_CUT:
        return "Fplus"
    return "D"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scc-demand-share", type=float)
    parser.add_argument("--mean-clause-width", type=float)
    args = parser.parse_args()
    print(choose_action(args.scc_demand_share, args.mean_clause_width))


if __name__ == "__main__":
    main()
