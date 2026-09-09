# Devpost paste pack — Scripty (Agentic Cinema · ClickHouse track)

Form: https://agentic-cinema.devpost.com/ → Enter a submission. Deadline Sep 9, 2:00 PM PDT (Sep 10, 02:30 IST).

**Project name:** Scripty

**Tagline (≤ 200 chars):** The continuity agent for script supervisors — and the first one that publishes its own false-positive rate.

**Track:** ClickHouse (runtime: `mcp-clickhouse` MCP server against a self-hosted ClickHouse cluster on Cloud Run)

**Google Cloud at runtime:** Vertex AI Gemini 2.5 Flash + Pro via `google-genai`; Google ADK (`google-adk`) agent; Cloud Run; Cloud Storage.

**Hosted URL:** https://scripty-q62ufgdryq-uc.a.run.app

**Repo:** https://github.com/rodriguescarson/scripty — public, Apache-2.0, detected in About.

**Video:** `docs/scripty-demo.mp4` (108 s, 1280x720, 3.1 MB) → upload to YouTube as **public**, paste the link.

**Story:** paste `docs/WRITEUP.md` (numbers from `docs/eval/charade-r2.json`, the run-2 six-scene result).

**Built with:** google-adk, google-genai, vertex-ai, gemini, clickhouse, mcp, cloud-run, cloud-storage, fastapi, opencv, python

**Thumbnail:** `docs/img/finding-tie.jpg` (16:9 crop) — a finding with both frames.

**Data sources (rules ask):** *Charade* (1963) and *Night of the Living Dead* (1968), public domain, archive.org; all inventories/findings are generated at runtime; the evaluation set is planted on public-domain frames with a published planting log.

**Findings & learnings (rules ask):** Pre-registered on 6 scenes / 45 planted labels, published as it came out:
recall **0.267** (bar was 0.60 — **FAIL**), precision **1.00** (bar 0.50), control false positives **0.33/scene** (bar 1.0).
Per kind: flipped 8/22, moved 2/5, removed 1/4, recoloured 1/14. Anchoring the pass on a reference-take inventory cut
control false positives from 2.75 to 0.33 per scene — the single biggest effect measured. An earlier single-scene rerun
scored 1.00 recall and is reported rather than quoted: one scene was not evidence. The verifier's own confidence is
uninformative (always 1.0), so it is reported, not used as a gate.
