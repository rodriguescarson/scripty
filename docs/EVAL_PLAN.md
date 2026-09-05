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

## Run 2 — post-hoc fixes (added 2026-09-05, after run 1 had scored 4 of 31 scenes)

Run 1 is scored exactly as pre-registered and its numbers are published unchanged. Inspecting one scene of run 1
(scene030, 12 labels, 1 strict hit, 10 control false positives) showed four pipeline defects, all upstream of the
verifier. They are fixed in a second code path and re-scored against the **same labels, same frames, same reference
inventories**; only the CONTROL and PLANTED inventories are recomputed and the candidate stage is changed.

| # | Defect found in run 1 | Evidence | Fix (run 2) |
|---|---|---|---|
| 1 | A presence pair required two reference rows **on the same frame**; the removed basket had one row per frame (colour on one sample, position on the next) although PLANTED explicitly reported `present = absent`. | `wicker basket`: A rows on frames feb8ab/935557, PLANTED `absent` on 6f6ae4 — no candidate. | Explicit `absent` pairs no longer need the two-row guard; only inferred absence (entity unreported) keeps it. |
| 2 | Anchoring the other takes to the reference **entity list** made the model answer with presence rows only (position rows: A 73, PLANTED 29, CONTROL 9), so a recolour never met a colour row to pair with. | `womans scarf/hood`: A `color = brown`, PLANTED only `present`, `state`. | Anchor to the full attribute sheet (`entity: color=…, position=…`) and require every attribute re-reported. |
| 3 | Flopped shots surfaced only as one entity's coarse position change, which the verifier called `same` (confidence 1.0). | 8 flipped shots, 3 position candidates, 0 confirmed. | Lateral-order detector: when ≥ 2 shared entities and ≥ 80 % of them swap left/right between takes, the frame pair itself becomes a candidate (`whole frame / orientation`) for the verifier. |
| 4 | Free-text `state` values (`partially zipped`, `mostly up`, `styled`, `combed`) paired with each other on identical frames and were confirmed as errors with confidence 1.0 — the entire control false-positive population. | 10 of 10 control positives in scene030 were zipper/hair states. | Controlled vocabulary enforced at query time for `state`, `color`, `position`; state pairs 63 → 13 on the same inventory. |

Pass/fail thresholds are unchanged (recall ≥ 0.6, precision ≥ 0.5, control false positives ≤ 1 per scene) and both
matchers (plan, strict) are reported for both runs. Run 2 is a post-hoc iteration and is labelled as such wherever its
numbers appear.
