# Scripty — demo video plan (≤ 3:00; only the first three minutes may be judged)

Screencast of the live Cloud Run app, narrated. No marketing film. Front-load the pitch.

| t | On screen | Say |
|---|---|---|
| 0:00–0:15 | Scene board, a scene selected, findings visible | "Scripty is a continuity assistant for the script supervisor: the wine glass that was half full in take 2 and empty in take 4. It finds those across takes — and it is the first one that publishes how often it is wrong." |
| 0:15–0:50 | One finding: two frames side by side, verdict, explanation | "Every frame is inventoried by Gemini into rows: entity, attribute, value. ClickHouse finds every entity whose attribute changed between takes of the same scene — that join *is* the check. Gemini Pro then looks at both frames and rules continuity error, intentional change, or same. Here is the explanation, citing what it saw." |
| 0:50–1:20 | Ask Scripty: "what changed on the table between take A and PLANTED in scene 021?" → answer with tool calls | "The agent is Google ADK. Its only route to data is the official mcp-clickhouse server — read-only SQL — plus one tool that lets it look at a frame pair. Ask it what a supervisor would ask at call time." |
| 1:20–2:10 | Evaluation panel: recall, precision, control FP/scene, per-kind table, PASS/FAIL | "Nobody has shipped this because intentional-versus-error stalls it. So we measured it instead of claiming it: real scenes from a public-domain film, a control take with nothing changed, a planted take with known errors, pass/fail written before the run. These are the numbers, published as they came out." |
| 2:10–2:40 | A planted pair (removed prop) caught; a control false positive shown honestly | "This is a planted removal it caught. This is a control frame it flagged wrongly — the noise floor a supervisor needs to know before trusting the shortlist." |
| 2:40–2:55 | README architecture table | "Vertex AI Gemini, ADK, ClickHouse on Cloud Run through mcp-clickhouse, Cloud Run, Cloud Storage. Built solo, from an empty repo, inside the window. Every number has a frame pair behind it." |

Production: record with the Chrome extension GIF recorder → ffmpeg to MP4 at 1280×720, then narration via the fallback TTS pipeline (`scripts/make_video.py` pattern from Underwrite) unless Carson records. Upload public on YouTube; paste the link on Devpost.
