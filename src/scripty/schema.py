"""ClickHouse schema. Every frame's inventory is a row per (entity, attribute); continuity checks are SQL."""
DDL = [
    """CREATE DATABASE IF NOT EXISTS scripty""",
    """CREATE TABLE IF NOT EXISTS scripty.frames (
        project String, scene String, take String, shot UInt16, t_s Float32, frame_id String,
        image_path String, width UInt16, height UInt16, ingested_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree ORDER BY (project, scene, take, shot, t_s)""",
    """CREATE TABLE IF NOT EXISTS scripty.inventory (
        project String, scene String, take String, shot UInt16, t_s Float32, frame_id String,
        entity String, entity_kind LowCardinality(String), attribute LowCardinality(String), value String,
        confidence Float32, region String, model LowCardinality(String), extracted_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree ORDER BY (project, scene, entity, attribute, take, shot, t_s)""",
    """CREATE TABLE IF NOT EXISTS scripty.findings (
        project String, scene String, finding_id String, category LowCardinality(String), entity String, attribute LowCardinality(String),
        take_a String, frame_a String, value_a String, take_b String, frame_b String, value_b String,
        sql_score Float32, verified UInt8, verdict LowCardinality(String), confidence Float32, explanation String,
        created_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree ORDER BY (project, scene, finding_id)""",
    """CREATE TABLE IF NOT EXISTS scripty.eval_labels (
        project String, scene String, take String, entity String, attribute LowCardinality(String), planted_kind LowCardinality(String), description String,
        created_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree ORDER BY (project, scene, take, entity, attribute)""",
]

# The continuity query is the product. Same scene, same entity+attribute, different value across takes
# (or across shots within the same take). Each row is a candidate the agent can verify visually.
CANDIDATES_SQL = """
WITH inv AS (
  SELECT project, scene, take, shot, t_s, frame_id, entity, entity_kind, attribute, value, confidence
  FROM scripty.inventory FINAL
  WHERE project = {project:String} AND scene = {scene:String} AND confidence >= {min_conf:Float32}
)
SELECT a.entity AS entity, a.entity_kind AS entity_kind, a.attribute AS attribute,
       a.take AS take_a, a.frame_id AS frame_a, a.value AS value_a, a.confidence AS conf_a,
       b.take AS take_b, b.frame_id AS frame_b, b.value AS value_b, b.confidence AS conf_b,
       least(a.confidence, b.confidence) AS sql_score
FROM inv a
INNER JOIN inv b ON a.entity = b.entity AND a.attribute = b.attribute AND a.frame_id < b.frame_id
WHERE lowerUTF8(a.value) != lowerUTF8(b.value) AND (a.take != b.take OR a.shot != b.shot)
ORDER BY sql_score DESC
LIMIT {limit:UInt32}
"""
