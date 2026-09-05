# Narration (fallback video). One paragraph per segment, matched to docs/VIDEO.md.

1. Scripty is a continuity assistant for the script supervisor: the wine glass that was half full in take two and empty in take four, the tie that changed between the wide and the close-up. It finds those across takes, and it is the first one that publishes how often it is wrong.

2. Every sampled frame is inventoried by Gemini into rows: entity, attribute, value. ClickHouse finds every entity whose attribute changed between takes or shots of the same scene. That join is the check. Gemini Pro then looks at both frames and rules continuity error, intentional change, or same, with an explanation citing what it saw.

3. The agent is built with Google ADK. Its only route to the data is the official mcp-clickhouse server, read-only SQL, plus one tool that lets it look at a frame pair. A supervisor asks what changed on the table between two takes and gets rows back, not opinions.

4. Nobody has shipped this because the intentional-versus-error problem stalls it. Instead of claiming to have solved it, we measured it: real scenes from a public-domain film, a control take with nothing changed, a planted take with known errors, and pass or fail written before the run. These are the numbers, published as they came out.

5. This is a planted recolour it caught. This is a control frame it flagged wrongly, with full confidence. The verifier's confidence turned out to carry no information, so the report says so instead of hiding it. That is the noise floor a supervisor needs to know before trusting the shortlist.

6. Vertex AI Gemini, Google ADK, ClickHouse on Cloud Run through mcp-clickhouse, Cloud Run and Cloud Storage. Built solo from an empty repository inside the contest window, on footage anyone can re-run. Every number has a frame pair behind it.
