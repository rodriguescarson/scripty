# Scripty — evaluation plan (pre-registered, written before any run)

_Frozen 2026-09-05 03:55 IST. Numbers below are the pass/fail conditions; whatever the run produces is published as-is, including a fail._

## Question

Does Scripty's continuity detector separate real continuity errors from the ordinary differences between takes, and how badly does it fail on the intentional-vs-error problem that stalled every prior attempt (Adobe/Sony patents, one 2009 paper)?

## Population

- Source footage: public-domain features *Charade* (1963, colour) and *Night of the Living Dead* (1968, b/w), from archive.org.
- Scenes: every scene the deterministic clusterer selects (30–150 s, 3–12 shots, interior or static-camera dialogue) — the **full selected population**, not a convenient sample. Target ≥ 24 scenes; the actual N is reported.
- Takes per scene: **A** (original sampled frames), **CONTROL** (A with reframing/exposure jitter, no semantic change), **PLANTED** (A with jitter plus one planted error per shot: prop removed / prop moved / prop recoloured / frame mirrored). Ground truth = the planting log.

## Detector under test

Inventory (Gemini 2.5 Flash, one call per frame) → ClickHouse candidates (same scene, same entity+attribute, different value across takes) → pairwise verification (Gemini 2.5 Pro) → findings with verdict ∈ {continuity_error, intentional_change, same, uncertain} and confidence.

**Operating point (fixed now):** a finding counts as a positive when `verdict = continuity_error AND confidence ≥ 0.6`.

## Metrics

- **Recall (planted):** fraction of planted shot-level errors (A vs PLANTED) with at least one positive finding on the same shot whose entity or category matches the planted object/kind (`flipped` matches any `screen_direction`/`side`/`position` finding).
- **Precision (planted scenes):** positives on A-vs-PLANTED pairs that match a planted label ÷ all positives on those pairs.
- **Control false-positive rate:** positives on A-vs-CONTROL pairs, per scene (mean) — the detector's noise floor with zero semantic change.
- **Intentional-vs-error confusion:** across real *within-take* shot pairs of A (legit changes between shots of a scene), the fraction labelled `continuity_error` — reported, not thresholded, because there is no ground truth for it.

## Pass / fail (decided before the run)

- PASS if recall ≥ 0.60 **and** precision ≥ 0.50 on planted scenes **and** control FPR ≤ 1.0 positive finding per scene.
- Otherwise FAIL, published with the numbers and the confusion breakdown by planted kind.

## What gets published either way

Per-scene table (recall, positives, control positives), per-kind recall (removed / moved / recoloured / flipped), the calibration of `confidence` against correctness (reliability bins), the exact SQL, and the frame pairs behind every number.
