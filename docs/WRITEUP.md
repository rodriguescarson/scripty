# Scripty — the continuity agent that publishes its own false-positive rate

_Devpost story draft. Numbers in «» are filled from `docs/eval/*.json` after the pre-registered run._

## Inspiration

On every film set there is one person whose job is to notice that the wine glass was half full in take 2 and empty in take 4, that the tie was knotted in the wide and loose in the close-up, that the actor's cigarette is in the wrong hand. The script supervisor — "scripty" — does it with continuity photos, a lined script and an eye trained over years, at the pace of a shooting day. It is the last part of filmmaking that has never been touched by tooling: one academic paper in 2009 with a handful of citations, three shelved patents from companies that hit the same wall, and nothing open source.

The wall is not detection. Any vision model can see that a glass changed. The wall is *intentional versus error*: the glass emptied because the actor drank. Every previous attempt claimed to handle that and could not show how well. Scripty is built the other way round: it detects, it lets a second model rule intentional-or-error, and then it **measures how often that ruling is wrong** on an evaluation whose pass/fail conditions were written before the run.

## What it does

1. **Ingest takes.** Shot boundaries by histogram distance (OpenCV, deterministic), frames sampled at the start/middle/end of every shot plus every three seconds.
2. **Inventory every frame with Gemini 2.5 Flash** (Vertex AI): 8–25 rows of (entity, attribute, value) per frame — props and their position/state/count, wardrobe, hair and makeup, set dressing, liquid levels, which hand holds what, which side of frame each character is on. Entity names are anchored to the character or the set so the same object gets the same name across frames.
3. **ClickHouse finds the candidates.** One SQL query over `scripty.inventory`: same scene, same entity and attribute, different value across takes or shots. Per-frame inventories are columnar, high-volume data — a shooting day is tens of thousands of rows — and the join is the mechanism, not a cache.
4. **Gemini 2.5 Pro looks at each candidate pair** and rules *continuity_error / intentional_change / same / uncertain* with a confidence and a two-sentence explanation citing what is visible in each frame.
5. **The supervisor reads a ranked shortlist** with both frames side by side, and asks the **Scripty agent** (Google ADK) questions in plain English — "what changed on the desk between take A and take C?" — which it answers through the official **`mcp-clickhouse` MCP server** (read-only SQL, the only data access it has), plus one tool that lets it look at a frame pair.
6. **The evaluation page** shows recall, precision and the control false-positive rate from the pre-registered run, per planted kind, with every frame pair behind every number.

## How I built it

| Layer | What | Runtime / partner use |
|---|---|---|
| Vision | `google-genai` on Vertex AI: `gemini-2.5-flash` inventory (JSON schema, temperature 0.1), `gemini-2.5-pro` pairwise verification | Google Cloud AI, called on every frame and every candidate |
| Data | ClickHouse 24.8, self-hosted on Cloud Run (2 GiB, single node); tables `frames`, `inventory`, `findings`, `eval_labels` (ReplacingMergeTree) | partner service at runtime |
| Agent | `google-adk` `LlmAgent` with `McpToolset` → `mcp-clickhouse` (`run_query`, `list_tables`) + a `look_at_pair` function tool | partner MCP server at runtime |
| App | FastAPI + one static page on Cloud Run; evidence frames on a public GCS bucket | Google Cloud |
| Eval | `plant.py`: Gemini bounding boxes → OpenCV inpaint/move/recolour/mirror with a planting log as ground truth; `eval_run.py` computes the pre-registered metrics | — |
| Footage | *Charade* (1963) and *Night of the Living Dead* (1968), public domain, archive.org | — |

The continuity query, verbatim:

```sql
SELECT a.entity, a.attribute, a.take AS take_a, a.value AS value_a, b.take AS take_b, b.value AS value_b,
       least(a.confidence, b.confidence) AS sql_score
FROM inv a INNER JOIN inv b ON a.entity = b.entity AND a.attribute = b.attribute AND a.frame_id < b.frame_id
WHERE lowerUTF8(a.value) != lowerUTF8(b.value) AND (a.take != b.take OR a.shot != b.shot)
ORDER BY sql_score DESC
```

## The hard problem, named: intentional versus error

«Filled from the run: the within-take error rate on real shot pairs, the per-kind recall, and what the verifier got wrong most often.»

## The evaluation (pre-registered)

Population: «N» scenes selected deterministically from the full film (30–150 s, 3–12 shots), not a hand-picked sample. Three takes per scene: **A** (original frames), **CONTROL** (reframed and re-exposed, nothing changed), **PLANTED** (one planted error per shot: prop removed, moved, recoloured, or the frame mirrored). Operating point fixed before the run: `verdict = continuity_error AND confidence ≥ 0.6`. Pass conditions written first: recall ≥ 60 %, precision ≥ 50 %, control ≤ 1 positive per scene.

Result: «recall / precision / control FPR / PASS-FAIL, per-kind table».

## Challenges I ran into

«Filled after the run.»

## Accomplishments that I'm proud of

- The first continuity checker with a published false-positive rate and a control condition.
- A partner integration that is the mechanism: the continuity check *is* a ClickHouse join, and the agent's only route to data is `mcp-clickhouse`.
- Built solo, from an empty repository, inside the contest window, on public-domain footage anyone can re-run.

## What I learned

«Filled after the run.»

## What's next

Live ingest from on-set camera cards; the lined script as a first-class object (which line was spoken during which frame, so the agent can answer "what was she holding on that line"); a supervisor-in-the-loop feedback table so verified verdicts recalibrate the confidence; more kinds of planted error (liquid levels, cigarette burn-down) and human-labelled real errors from open-licence student films.

## Built with

google-adk · google-genai (Vertex AI Gemini 2.5 Flash / Pro) · ClickHouse + mcp-clickhouse · Cloud Run · Cloud Storage · FastAPI · OpenCV · Python 3.12
