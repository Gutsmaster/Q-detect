"""Physical and protocol constants. Weng et al. 2021 unless noted."""

from __future__ import annotations

import math

# Pauli axes
X, Y, Z = 0, 1, 2
AXIS_NAME = ("X", "Y", "Z")
I_PAULI, X_PAULI, Y_PAULI, Z_PAULI = 0, 1, 2, 3
PAULI_NAME = ("I", "X", "Y", "Z")

# Weng simulation parameters (Opt. Express 29, 27661)
FIBER_LOSS_DB_PER_KM = 0.16
DARK_COUNT_PROB = 1e-7
DETECTION_EFFICIENCY = 0.93
MISALIGNMENT_ED = 0.001  # 0.1% in the 150 km / 265 km headline figures
IDEAL_CONCLUSIVE_PROB = 1.0 / 6.0  # Weng, six-state SARG04

# Security targets, Weng §III last paragraph
EPS_TOT_TARGET = 1e-9
EPS_FOR_TARGET = 1e-10
EPS_ROB_TARGET = 1e-10
EPS_REP_TARGET = 1e-10

# Honest anisotropic fibre used in the centrepiece experiment (team brief §3.6)
HONEST_P = (0.027, 0.033, 0.045)  # (p_X, p_Y, p_Z)
HONEST_E = (0.078, 0.072, 0.060)  # (e_X, e_Y, e_Z) = cyclic sums
HONEST_AGGREGATE = 0.070
CALIBRATION_WOBBLE = 0.08  # relative per-axis shape wobble (brief §3.8 caveat)

# Abruzzo et al. 2011 detector PE
EPS_PE_DEFAULT = 1e-10

# Contract / meter
WC_TAG_BITS = 64  # Wegman–Carter tag; ε ≈ 2^{-64} per authenticated message

# Two operating points, kept distinct on purpose.
# detector_demo: the 7% anisotropic fibre of the centrepiece experiment.
#   SARG04 conclusive mismatch is ≈12.3% here (measured in this codebase).
#   T_a sits above that so honest signatures accept; T_v sits below 50% so a
#   random forgery fails. Weng's ε_for is NOT the reason — E_BF at this noise
#   does not sit above T_v. Display that honestly.
# weng: misalignment e_d = 0.1% as in Weng's 150 km / 265 km figures.
TA_DEMO, TV_DEMO = 0.22, 0.32
TA_WENG, TV_WENG = 0.015, 0.045
PC_ABORT_DEV = 0.10  # abort if |P^c − 1/6| exceeds this

# Yin 2016a two-photon six-state intercept (the source Weng cites)
SQRT2 = math.sqrt(2)
EP_INTERCEPT_YIN2016 = (2.0 - SQRT2) / 4.0  # ≈ 0.1464
EP_SLOPE_SIX_STATE = 3.0 / (2.0 * SQRT2)  # ≈ 1.0607
EP_INTERCEPT_WENG_PRINTED = (4.0 - SQRT2) / 4.0  # ≈ 0.6464; see PROTOCOL.md
