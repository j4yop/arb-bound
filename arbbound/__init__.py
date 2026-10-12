"""arb-bound: is an MCX cross-contract gold spread ever actually tradeable?

The package answers one question with evidence:

    MCX lists the same metal in four physical delivery sizes. When two of those
    contracts trade at a visible price gap, does that gap represent an
    opportunity, or is it the cost of physically closing the trade?

Because delivery is compulsory and fabrication cost is dominated by a fixed
per-bar charge, the gap has a structural floor. This package derives that floor
from contract specifications, tests it walk-forward without look-ahead, and
reports where the observed basis broke in ways structure alone cannot explain.
"""

from .bound import PairBound, compute_pair_bound
from .contracts import CONTRACTS, ContractSpec, spec_for
from .ingest import daily_basis, load_csv_bhavcopy, load_json_bhavcopy

__version__ = "0.1.0"

__all__ = [
    "PairBound",
    "compute_pair_bound",
    "CONTRACTS",
    "ContractSpec",
    "spec_for",
    "daily_basis",
    "load_csv_bhavcopy",
    "load_json_bhavcopy",
]