"""
A standard free-cash-flow DCF assumes a company with a normal operating
model. It breaks down for banks, loss-making companies, and companies
with too little history to establish a trend. This module flags those
cases instead of silently producing a confident-looking wrong number.
"""

from dataclasses import dataclass

from app.pipeline.yahoo import FinancialSnapshot

UNSUITABLE_SECTORS = {"Financial Services", "Financials", "Banks", "Insurance"}


@dataclass
class SuitabilityResult:
    suitable: bool
    reasons: list


def check_suitability(snap: FinancialSnapshot) -> SuitabilityResult:
    reasons = []

    if snap.currency_mismatch_unresolved:
        reasons.append(
            f"This ticker's financial statements are reported in {snap.financial_currency} but it "
            f"trades in {snap.currency}, and no live FX rate was available to reconcile the two. "
            "Any fair value shown would mix two currencies and cannot be trusted."
        )

    if snap.sector in UNSUITABLE_SECTORS:
        reasons.append(
            f"{snap.company_name} is classified under {snap.sector}. Banks and financial "
            "institutions use debt as a raw material rather than a financing choice, so a "
            "standard free cash flow DCF does not apply here. Results shown are not meaningful."
        )

    if snap.ebit_history and snap.ebit_history[-1] < 0:
        reasons.append(
            "Operating income (EBIT) was negative in the most recent reported year. "
            "Projecting negative cash flow forward with a fixed growth rate produces "
            "unreliable results for loss-making companies."
        )

    if len(snap.revenue_history) < 3:
        reasons.append(
            "Fewer than 3 years of financial history are available, which is not enough "
            "to estimate a reliable growth trend."
        )

    return SuitabilityResult(suitable=len(reasons) == 0, reasons=reasons)
