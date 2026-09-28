# Q-METER

A **simulator** of a teleportation-based quantum digital signature, plus a web dashboard that runs the pipeline and shows what the detectors decided.

It is software on a laptop, not lab hardware. No machine-learning libraries.

Run every command from **this folder** (the one that contains `qmeter/` and `dashboard/`). It does not depend on a particular home directory or Anaconda path.

---

## What the code does

Alice wants to **sign a message** so Bob and Charlie can be sure it came from her, even after a quantum computer exists.

1. Alice prepares random six-state quantum keys and **teleports** them to Bob and Charlie (the secret particles never travel down the fibre).
2. Recipients measure in a random basis X, Y, or Z.
3. **Post-matching** lines Charlie’s sequence up with Bob’s so Alice cannot give Bob good keys and Charlie bad keys, then deny the signature.
4. Alice publishes the classical key for message bit `m`.
5. **Bob** checks his mismatch rate against a strict threshold \(T_a\). If it passes, he forwards only classical data.
6. **Charlie** checks against his own keys at a looser threshold \(T_v\).

Two extra layers sit **beside** that verdict, and never override it:

- **Q-METER** looks at the *shape* of errors on the three axes, not just the total error rate. An honest warm fibre and an attacker biasing one axis can produce the same 7% total error. The scalar protocol cannot tell them apart; the shape test can.
- **Contract engine** decides whether there is enough unused key, and whether the link is still trustworthy enough, to sign the **next** message. If not, it defers (fail closed) instead of issuing a weaker signature.

---

## Install

Python 3.10 or newer. A virtual environment is the reliable way (avoids a broken system NumPy, which some Macs have):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows:  .venv\Scripts\activate
python -m pip install -r requirements.txt
```

If `python3` is not found, use `python`.

Optional check that the physics engine is intact:

```bash
python -m pytest tests/ -q
```

---

## Run the dashboard

With the venv activated (or after `./run_dashboard.sh`, which uses `.venv` automatically if it exists):

```bash
python dashboard/app.py
```

or

```bash
./run_dashboard.sh
```

Then open **http://127.0.0.1:5055** in a browser on the same computer.

That address is local to the machine that started the server. Sending someone the URL does not share the app; send them this folder instead.

To use another port:

```bash
QMETER_PORT=8080 python dashboard/app.py
```

---

## Stop the dashboard

Closing the browser tab is **not** enough. The Python server keeps running.

- In the terminal that started it, press **Ctrl+C**.
- Or, from this folder: `./stop_dashboard.sh`

---

## How to use the dashboard

1. Leave **Attack** on Honest for a first run, or pick an attack (Z-bias, forgery, replay, …).
2. Optionally set pulse count `N`, fibre length in km, seed, and intensity.
3. Click the teal **Run live pipeline** button (not the pipeline chips in the middle — those are labels).
4. Wait for **Finished** under the button. The three tiles at the top update.

Pre-computed evidence (seed 141) is in the right-hand **Seeded experiments** list. Click a name to load it. To regenerate:

```bash
python experiments/generate_experiment.py --seed 141 --condition all
```

Command-line run without the browser:

```bash
python -m qmeter --attack z_bias --n 12000 --km 0
```

---

## What you are looking at

Three questions, three answers. Do not mix them.

| Tile / column | Question | Words |
|---|---|---|
| **Protocol** (QDS verifier) | Is *this* signature valid? | **ACCEPT** — Bob passed \(T_a\) and Charlie passed \(T_v\). **REJECT** — Charlie did not accept. **ABORT (Bob)** — Bob never forwarded. |
| **Q-METER** | Does the error *shape* still match this fibre’s calibrated honest pattern? | **CONSISTENT** — yes. **VIOLATION** — no. That is “security model mismatch,” not automatically “an eavesdropper.” |
| **Contract** | May we sign the *next* message? | **ADMIT** — link looks honest enough and key material remains. **DEFER** — stop. Typical reasons: Q-METER violation, fibre too noisy for the security margin, or not enough unused pairs. |

Q-METER never changes ACCEPT/REJECT. A row can be **ACCEPT + VIOLATION + DEFER**: *this signature was valid; do not use the link for the next one.*

---

## How to interpret typical results

The centrepiece table is the result that matters.

| Situation | Total error | Axis breakdown \(e_X / e_Y / e_Z\) | Protocol | Q-METER | Contract |
|---|---|---|---|---|---|
| Honest fibre | ~7% | ~7.8 / 7.2 / 6.0 (naturally a bit lopsided) | ACCEPT | CONSISTENT | ADMIT |
| Honest drift | ~7% | still the honest family | ACCEPT | CONSISTENT | ADMIT |
| Attacker biasing one axis | ~7% (same total) | e.g. 10.5 / 10.5 / **0** | ACCEPT | VIOLATION | DEFER |
| Fibre much noisier, still honest-shaped | ~12% | compatible shape | ACCEPT | CONSISTENT | DEFER |
| Forgery (fake key string) | honest-looking channel | — | REJECT | often CONSISTENT | ADMIT (the *link* is fine) |

The protocol column can stay ACCEPT on the biased-axis attack because it only sees one number — the total error — which is still under the line. That is the point of Q-METER.

Other useful numbers on the page:

- **\(E^{cu}\) vs \(T\)** — conclusive mismatch versus the authentication (\(T_a\), Bob) or verification (\(T_v\), Charlie) threshold.
- **\(P^c\)** — fraction of conclusive SARG04 results. Ideal is \(1/6 \approx 16.7\%\).
- **Pair click** — at 0 km this is 100% (lab mode). At 10 km both photons of each Bell pair survive about 60% of the time, so you get fewer samples.
- **Mahalanobis \(D^2\)** — distance of the recovered error shape from the calibrated honest family. Above the 99% threshold → VIOLATION.

Two operating points (dropdown):

- **Detector demo** — 7% anisotropic fibre, the table above. This is the demo.
- **Weng** — much quieter channel (\(e_d = 0.1\%\)), where Weng’s published forgery bound \(\varepsilon_{\mathrm{for}}\) is the relevant budget. At 7% noise that bound is not advertised on purpose; the meter must not invent a number.

---

## Folder layout

```
qmeter/        physics engine (states, teleportation, SARG04, detector, attacks)
dashboard/     web UI
experiments/   seeded runs (generate_experiment.py, results/)
tests/         physics identities
papers/        source PDFs
specs/         internal protocol spec
```

---

## Papers

| Used for | Citation |
|---|---|
| Protocol, thresholds, finite-size security | Weng et al., Opt. Express 29, 27661 (2021) |
| Per-axis finite-key margins | Abruzzo et al., arXiv:1111.2798 (2011) |
| Phase-error formula Weng cites | Yin, Fu, Chen, Phys. Rev. A 93, 032316 (2016) |
| Post-matching | Lu et al., Opt. Express 29, 10162 (2021) |

Declared assumption, stated up front: replacing Weng’s direct transmission with teleportation plus the public Pauli correction is **assumed** equivalent for the security layer. That is not a published theorem. Do not cite Shor–Preskill as the bridge.
