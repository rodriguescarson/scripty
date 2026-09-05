# Devpost paste pack — Scripty (Agentic Cinema · ClickHouse track)

Form: https://agentic-cinema.devpost.com/ → Enter a submission. Deadline Sep 9, 2:00 PM PDT (Sep 10, 02:30 IST). Submit by Sep 8.

**Project name:** Scripty

**Tagline (≤ 200 chars):** The continuity agent for script supervisors — and the first one that publishes its own false-positive rate.

**Track:** ClickHouse (runtime: `mcp-clickhouse` MCP server against a self-hosted ClickHouse cluster on Cloud Run)

**Google Cloud at runtime:** Vertex AI Gemini 2.5 Flash + Pro via `google-genai`; Google ADK (`google-adk`) agent; Cloud Run; Cloud Storage.

**Hosted URL:** https://scripty-q62ufgdryq-uc.a.run.app

**Repo (public before submitting):** https://github.com/rodriguescarson/scripty — Apache-2.0, detected in About.

**Video:** «YouTube link, ≤ 3 min, public»

**Story:** paste `docs/WRITEUP.md` (numbers filled from `docs/eval/charade.json`).

**Built with:** google-adk, google-genai, vertex-ai, gemini, clickhouse, mcp, cloud-run, cloud-storage, fastapi, opencv, python

**Thumbnail:** `docs/img/finding-tie.jpg` (16:9 crop) — a finding with both frames.

**Data sources (rules ask):** *Charade* (1963) and *Night of the Living Dead* (1968), public domain, archive.org; all inventories/findings are generated at runtime; the evaluation set is planted on public-domain frames with a published planting log.

**Findings & learnings (rules ask):** «from the eval: recall / precision / control FPR / per-kind; the verifier's confidence is uninformative (always 1.0) — reported, not hidden; intentional-vs-error confusion examples».

Also make the repo public: `gh repo edit rodriguescarson/scripty --visibility public --accept-visibility-change-consequences` (Carson runs this; the classifier blocks Claude).
