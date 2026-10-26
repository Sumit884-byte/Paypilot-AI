"""Loan cash-flow math shared by offer guard and affordability.

Effective annualised cost is the internal rate of return of the borrower's
cash flows, not a relabelled nominal interest rate.

Cash flows (borrower's point of view), one period per instalment:

    t = 0:      + net proceeds (principal minus non-contingent upfront fees)
    t = 1..n:   - level instalment

Contingent charges (penalties, cheque-bounce fees) are excluded because they
are not certain. Let r be the per-period IRR. The effective annualised cost is

    (1 + r) ** periods_per_year - 1

When a contractual instalment is not supplied, a level payment is built with
the standard reducing-balance formula. A nominal annual rate is divided by the
number of periods per year. A figure that is already an effective annual rate
is converted with (1 + effective) ** (1 / periods_per_year) - 1 before that
formula is applied. Which convention was used is always reported by the caller.
"""

from __future__ import annotations

import math

import numpy as np

MAX_NOMINAL_ANNUAL_RATE = 5.0  # 500 percent; above this the inputs are rejected


class CalculationError(ValueError):
    """The cash flows do not support the requested calculation."""


def level_payment(
    principal: float,
    annual_nominal_rate: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    """Reducing-balance level instalment. annual_nominal_rate is a decimal (0.18 = 18%)."""
    if principal <= 0:
        raise CalculationError("principal must be positive")
    if n_periods < 1:
        raise CalculationError("number of periods must be at least 1")
    if periods_per_year < 1:
        raise CalculationError("periods per year must be at least 1")
    if not math.isfinite(annual_nominal_rate) or annual_nominal_rate < 0:
        raise CalculationError("nominal annual rate must be zero or positive")
    if annual_nominal_rate > MAX_NOMINAL_ANNUAL_RATE:
        raise CalculationError("nominal annual rate is above the supported maximum of 500%")
    periodic = annual_nominal_rate / periods_per_year
    if periodic == 0:
        return float(principal) / n_periods
    growth = (1.0 + periodic) ** n_periods
    return float(principal * periodic * growth / (growth - 1.0))


def periodic_rate_from_effective_annual(effective_annual: float, periods_per_year: int) -> float:
    """Convert an effective annual rate (decimal) into an equivalent per-period rate."""
    if periods_per_year < 1:
        raise CalculationError("periods per year must be at least 1")
    if not math.isfinite(effective_annual) or effective_annual < 0:
        raise CalculationError("effective annual rate must be zero or positive")
    if effective_annual > MAX_NOMINAL_ANNUAL_RATE:
        raise CalculationError("effective annual rate is above the supported maximum of 500%")
    return (1.0 + effective_annual) ** (1.0 / periods_per_year) - 1.0


def level_payment_from_effective_annual(
    principal: float,
    effective_annual: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    """Level instalment whose zero-fee IRR matches an effective annual rate."""
    periodic = periodic_rate_from_effective_annual(effective_annual, periods_per_year)
    # level_payment expects a nominal annual rate, i.e. periodic * periods_per_year.
    return level_payment(principal, periodic * periods_per_year, n_periods, periods_per_year)


def solve_periodic_irr(net_proceeds: float, instalment: float, n_periods: int) -> float:
    """Per-period IRR for +net_proceeds at t=0 and n equal instalments afterwards.

    The NPV is strictly increasing in the discount rate when proceeds are positive
    and every instalment is positive, so bisection has a single root.
    """
    if n_periods < 1:
        raise CalculationError("number of periods must be at least 1")
    if not math.isfinite(net_proceeds) or net_proceeds <= 0:
        raise CalculationError("net proceeds must be positive")
    if not math.isfinite(instalment) or instalment <= 0:
        raise CalculationError("instalment must be positive")

    inflows = float(net_proceeds)
    payment = float(instalment)
    periods = np.arange(n_periods + 1, dtype=float)
    amounts = np.empty(n_periods + 1, dtype=float)
    amounts[0] = inflows
    amounts[1:] = -payment

    def npv(rate: float) -> float:
        return float(np.sum(amounts / np.power(1.0 + rate, periods)))

    if abs(npv(0.0)) <= 1e-6:
        return 0.0

    low = -0.9
    high = 0.0
    npv_low = npv(low)
    npv_high = npv(high)
    expands = 0
    while npv_high <= 0.0 and high < 10.0 and expands < 40:
        high = 0.05 if high <= 0.0 else high * 2.0
        npv_high = npv(high)
        expands += 1
    if npv_low > 0.0:
        low = -0.999
        npv_low = npv(low)
    if npv_low == 0.0:
        return low
    if npv_high == 0.0:
        return high
    if npv_low * npv_high > 0.0:
        raise CalculationError("could not bracket a per-period IRR for these cash flows")

    for _ in range(80):
        mid = (low + high) / 2.0
        value = npv(mid)
        if abs(value) <= 1e-8:
            return mid
        # NPV rises with the rate, so a positive NPV means the root is lower.
        if value > 0.0:
            high = mid
        else:
            low = mid
    return (low + high) / 2.0


def effective_annual_rate(net_proceeds: float, instalment: float, n_periods: int, periods_per_year: int) -> float:
    """Effective annualised borrowing cost as a decimal."""
    if periods_per_year < 1:
        raise CalculationError("periods per year must be at least 1")
    periodic = solve_periodic_irr(net_proceeds, instalment, n_periods)
    if periodic <= -1.0:
        raise CalculationError("per-period IRR is below -100%")
    return (1.0 + periodic) ** periods_per_year - 1.0


def npv_at_periodic_rate(net_proceeds: float, instalment: float, n_periods: int, periodic_rate: float) -> float:
    """NPV used by tests to confirm a solved IRR, independent of the solver loop."""
    total = float(net_proceeds)
    for t in range(1, n_periods + 1):
        total -= float(instalment) / (1.0 + periodic_rate) ** t
    return total
