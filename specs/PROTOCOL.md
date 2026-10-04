# Q-DETECT internal specification

Protocol locked to Weng et al., Opt. Express 29, 27661 (2021), arXiv:2104.12059v2.
Detector statistics from Abruzzo et al., arXiv:1111.2798.
Finite-size Chernoff / sampling from Yin et al., Sci. Rep. 10, 14312 (2020), as used by Weng.
Forgery reduction for three-party six-state SARG04 from Yin, Fu, Chen, Phys. Rev. A 93, 032316 (2016), arXiv:1507.03333 — the paper Weng cites for \(e_p(e_b)\) and \(I_B\).

Notation is Weng’s, not reconstructed.

## 0. Declared assumptions (state first)

1. Weng analyses prepare-and-measure over insecure quantum channels. We distribute the same six-state qubits by teleportation. We assume ideal Bell measurement + the publicly specified Pauli correction is operationally equivalent, from the security layer’s point of view, to delivery of the intended eigenstate. Teleportation-channel imperfections are an effective error process subject to the protocol’s own parameter estimation and abort conditions.
2. Do **not** cite Shor–Preskill as that bridge. Shor–Preskill equates entanglement-based and prepare-and-measure QKD; it says nothing about a signature scheme’s finite-size \(T_a/T_v\) bounds surviving a teleportation layer.
3. Pauli eigenstates are invariant as a set under Pauli corrections (Wallden et al., PRA 91, 042304 (2015)). That is supporting structure for the assumption, not a reduction.
4. The Q-DETECT monitor is **decoupled** from accept/reject. Acceptance is solely Weng’s \(T_a, T_v\). Detection decides certifiability of the **next** signature. This avoids an unproven composite proof.
5. Detector domain: Pauli-twirled effective channels. Pauli twirling is an actual randomization, not a free consequence of teleporting.
6. Bell-resource fidelity is assumed; entanglement verification is out of prototype scope.
7. Q-DETECT does not provide information-theoretic security. Weng’s protocol does, under its model. Q-DETECT certifies operation within that model.

## 1. Parties, channels, encoding

- Signer Alice, authenticator Bob, verifier Charlie (three-party, \(M=3\)).
- Insecure quantum channels Alice→Bob and Alice→Charlie (here: Bell-pair distribution).
- Authenticated classical channels between every pair.
- Six Pauli eigenstates \(|\pm x\rangle, |\pm y\rangle, |\pm z\rangle\).
- Twelve SARG04 sets, axis-ordered:

  - XY: \(\{|\omega_1 x\rangle, |\omega_2 y\rangle\}\), first = logic 0, second = logic 1
  - YZ: \(\{|\omega_3 y\rangle, |\omega_4 z\rangle\}\)
  - ZX: \(\{|\omega_5 z\rangle, |\omega_6 x\rangle\}\)

  \(\omega_i \in \{+,-\}\). A given state belongs to exactly four sets (Weng’s example for \(|+x\rangle\)).

- Recipients measure randomly in \(X, Y\) or \(Z\).
- Conclusive iff the outcome is orthogonal to exactly one state of the announced set. Ideal conclusive fraction \(P^c = 1/6\) (Weng). Abort if \(P^c\) “deviates greatly” from \(1/6\).
- They do **not** announce which results are conclusive.

## 2. Pipeline

### Key generation

For each future message bit \(m \in \{0,1\}\):

1. Alice prepares two independent sequences \(A_{B,m}\) and \(A_{C,m}\) of six-state qubits.
2. Each qubit is teleported: Bell pair, Alice Bell measurement, two authenticated correction bits, recipient Pauli correction.
3. Recipients announce clicks. No-click data discarded.
4. Post-matching (Weng, after Lu et al. 2021): Alice takes the order of states in \(S_{AB,m}\) as reference and reorders \(S_{AC,m}\) (and tells Charlie to reorder his outcomes the same way) so the prepared-state sequences match by type. Leftover unmatched shots are dropped. This is classical; it is the repudiation countermeasure that older QS-L protocols got from symmetrization.
5. Alice assigns each remaining position a set containing the state she sent. All three parties encode logic bits. Inconclusive = \(\bot\).

Weng also uses decoy intensities \(\lambda \in \{\mu,\nu,0\}\). This prototype distributes **true single qubits** by teleportation, so every click is a single-photon event. Decoy estimation of \(s_{Ck}^{c\mu}\) collapses to the observed conclusive count. That is a model restriction, stated in the dashboard.

### Estimation

Charlie randomly selects fraction \(t\) of the string as test bits. Alice announces those bits. Parties compute conclusive mismatch rates \(E_B^{ct}, E_C^{ct}\) and conclusive fractions \(P_B^c, P_C^c\). Test bits discarded. Remaining untested length \(n^u = (1-t)n\).

### Messaging

To sign \(m\), Alice sends \(\{m, K_{A,m}^u\}\) to Bob.

- Bob accepts iff \(E_B^{cu} \le T_a\), else abort (does not forward).
- If Bob accepts he forwards **only classical data** \(\{m, K_{A,m}^u\}\) to Charlie. No quantum states are forwarded. Independent distribution + classical forward is the no-cloning rebuttal.
- Charlie accepts iff \(E_C^{cu} \le T_v\).

Dual thresholds with \(T_a < T_v\) are what make this a signature rather than authentication.

Certified early rejection (ours, arithmetic, not a sequential bound): if remaining positions cannot bring the mismatch rate under the threshold, reject now. Statistical early **acceptance** is explicitly cut.

## 3. Finite-size formulae (Weng §III)

Chernoff variant, \(\beta = \ln(1/\varepsilon_1)\):

\[
\overline{a}^* = a + \beta + \sqrt{2\beta a + \beta^2}, \qquad
\underline{a}^* = a - \tfrac{\beta}{2} - \sqrt{2\beta a + \beta^2/4}.
\]

### Phase error, three-party (\(k = M-1 = 2\) in Weng’s WCS analysis)

Weng Eq. (8) as printed:

\[
e_p = \frac{4-\sqrt{2}}{4} + \frac{3}{2\sqrt{2}} e_b \quad (M=3).
\]

The intercept \((4-\sqrt{2})/4 \approx 0.646\) is inconsistent with (i) the source Weng cites, Yin et al. 2016a Eq. (1), which is

\[
e_p = \frac{2-\sqrt{2}}{4} + \frac{3}{2\sqrt{2}} e_b,
\]

and (ii) Weng’s own \(M=4\) intercept \(1/4\). Using the printed intercept makes \(e_p > 1/2\) for all \(e_b \ge 0\) and collapses the forgery bound. **Default in code: Yin 2016a**, with Weng’s printed formula available as a flagged alternative. See `qdetect/finite_size.py`.

Mutual information: \(I_B = H(e_p \mid e_b)\). Conservative implementation uses \(I_B = h_2(e_p)\) (binary entropy), which upper-bounds the conditional entropy. Then

\[
h_2(E_{BF,k}^*) = 1 - I_B.
\]

Invert \(h_2\) on \([0,1/2]\) to get \(E_{BF,k}^*\).

### Forgery (Weng Eq. 9)

\[
\varepsilon_{\mathrm{for}} = \exp\left[-\frac{(E_{BF,k}^*-T_{v,k})^2}{2 E_{BF,k}^*} n_k^{cu}\right],
\quad T_{v,k} = T_v \, n^{cu}/n_k^{cu}.
\]

For single-qubit teleportation \(n_k^{cu} = n^{cu}\) so \(T_{v,k}=T_v\).

### Repudiation (Weng Eqs. 11–13)

\[
\varepsilon_{\mathrm{rep}} = \exp\left[-\frac{(A - P_B^c T_a)^2}{2A} n^u\right],
\]

where \(A\) solves

\[
\frac{\bigl[P_C^c T_v - P_C^c(\overline{\Delta}^{cu}/n^{cu} + A/P_B^c)\bigr]^2}{3 P_C^c(\overline{\Delta}^{cu}/n^{cu} + A/P_B^c)}
= \frac{(A - P_B^c T_a)^2}{2A}
\]

subject to \(P_B^c T_a < A < P_B^c(T_v - \overline{\Delta}^{cu}/n^{cu})\).

\(\overline{\Delta}^{cu}\) is the relative Hamming-distance bound between Bob’s and Charlie’s conclusive untested strings, from random sampling without replacement (Yin 2020 / Yin 2016 appendix).

### Robustness

Probability Bob rejects an honest signature: random sampling without replacement, Yin 2016 Eq. (6) / Lu 2021.

### Assembly (Weng Eq. 14)

\[
\varepsilon_{\mathrm{tot}} = 11\varepsilon_1 + \varepsilon_2 + \varepsilon_{\mathrm{rob}} + \varepsilon_{\mathrm{for}} + \varepsilon_{\mathrm{rep}} \quad (M=3).
\]

Targets: \(\varepsilon_{\mathrm{tot}} \le 10^{-9}\), \(\varepsilon_{\mathrm{for}},\varepsilon_{\mathrm{rob}},\varepsilon_{\mathrm{rep}} \le 10^{-10}\), \(\varepsilon_1=\varepsilon_2\).

### \(L_{\min}\) (contract engine)

Forgery budget, closed form (derived):

\[
n^{cu} \ge \frac{2 E_{BF}^* \ln(1/\varepsilon_{\mathrm{for}})}{(E_{BF}^*-T_v)^2}.
\]

Repudiation and robustness budgets are solved numerically from Eqs. 11 and the sampling formula. The meter displays only derived values. \(L_{\min}\) is the maximum of the derived budgets. If the \(A\)-interval is empty, repudiation is **not** claimed and the meter says so.

## 4. Teleportation layer

Standard qubit teleportation of \(|\psi\rangle\) through \(|\Phi^+\rangle\):

| Bell outcome | Correction |
|---|---|
| \(\Phi^+\) | \(I\) |
| \(\Psi^+\) | \(X\) |
| \(\Phi^-\) | \(Z\) |
| \(\Psi^-\) | \(XZ\) |

A Pauli error on Bob’s half of the pair, or a flip of the correction bits, is an extra Pauli on the teleported qubit. Under Pauli twirling this is a Pauli channel \((p_I, p_X, p_Y, p_Z)\).

Loss: both photons of the pair must be detected. Fibre \(\eta = 10^{-\alpha L/10}\), \(\alpha = 0.16\,\mathrm{dB/km}\) (Weng). Dark counts produce a random click.

Misalignment \(e_d\) is folded into the Pauli channel.

Correction bits are authenticated (Wegman–Carter with pre-shared key for an ITS claim; HMAC otherwise with the ITS claim withdrawn at that plane).

## 5. Q-DETECT detector (Tier 3; not on the acceptance path)

Matching-basis events (recipient measured in the preparation axis, labels public after signing) give \((e_X, e_Y, e_Z)\). Abruzzo finite-size:

\[
e_i \le e_{i,m_i} + 2\zeta(\varepsilon_{\mathrm{PE}}, m_i), \quad
\zeta(\varepsilon_{\mathrm{PE}}, m) = \sqrt{\frac{\ln(1/\varepsilon_{\mathrm{PE}}) + 2\ln(m+1)}{8m}}.
\]

Inversion (do **not** clip negatives):

\[
e_X = p_Y + p_Z, \quad p_X = (e_Y + e_Z - e_X)/2
\]

and cyclic. Domain: Pauli-twirled channels. Non-unital channels break this; demonstrated as a negative result.

Commutation blind spot: a Pauli error \(E\) on a \(+1\) eigenstate of \(P\) is invisible iff \([E,P]=0\), i.e. \(E=P\). Pure single-axis attack of magnitude \(p\) yields aggregate observed error \(2p/3\). Against threshold \(T\), the attacker stays under the line while \(p < 1.5 T\).

Honest reference (anisotropic fibre, not “anisotropy = attack”):

\[
(p_X, p_Y, p_Z) = (0.027, 0.033, 0.045)
\Rightarrow (e_X, e_Y, e_Z) = (7.8\%, 7.2\%, 6.0\%), \text{ aggregate } 7.0\%.
\]

Statistic: Mahalanobis distance of \((\hat p_X, \hat p_Y, \hat p_Z)\) from the calibrated honest family, thresholded at the 99th percentile of the calibration ensemble. Output: CONSISTENT / VIOLATION. \(H_1 \ne\) Eve; wording is “security model violation”.

Scope: channel manipulation with a fixed rotation axis. An adaptive eavesdropper who randomizes her basis erases the axis signature. Not a general eavesdropper detector.

## 6. Three decision layers (kept separate)

| Layer | Owner | States |
|---|---|---|
| QDS verifier | Weng \(T_a / T_v\) | ACCEPT / REJECT |
| Q-DETECT monitor | model consistency | CONSISTENT / VIOLATION |
| Contract engine | resource certification | ADMIT / DEFER |

## 7. Attacks (distinct mechanisms, not labels)

- Forgery: Bob replaces \(K_A^u\) with a guessed string.
- Impersonation: unsigned party claims to be Alice.
- Replay: reuse a consumed one-time key.
- Channel manipulation: axis-biased Pauli.
- Correction-bit tampering: flip authenticated-classical BM bits (wrong Pauli correction, no quantum-layer signal if MAC is absent).
- Unauthorized verification: party never issued key material.
- Repudiation demonstration: skip post-matching / give Charlie a worse channel.

Known gap: invited-but-compromised credential used by someone else.

## 8. What this codebase is not

- Not a decoy-state WCS optical simulation. Single-qubit teleportation + effective channel.
- Not a proof that teleportation preserves Weng’s bounds.
- Not tomography, not “channel fingerprinting”.
- No ML libraries.
