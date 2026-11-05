"""Reuse the H02 formal worker contract in a separate H03 namespace."""
from pathlib import Path
import run_signed_features as execution

execution.CAMPAIGN=execution.ROOT/'autoresearch/H03_root_propagation_residual'

if __name__=='__main__':
    execution.main()
