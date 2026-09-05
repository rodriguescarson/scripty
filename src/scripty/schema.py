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
  SELECT project, scene, take, shot, t_s, frame_id, entity, entity_kind, attribute,
         trimBoth(lowerUTF8(value)) AS value, confidence
  FROM scripty.inventory FINAL
  WHERE project = {project:String} AND scene = {scene:String} AND confidence >= {min_conf:Float32}
),
-- presence per (take, frame, entity): explicit 'present = absent' wins; any other row means present
presence AS (
  SELECT take, shot, t_s, frame_id, entity, any(entity_kind) AS entity_kind,
         if(countIf(attribute = 'present' AND value IN ('absent','no','removed')) > 0, 'absent', 'present') AS value,
         max(confidence) AS confidence, count() AS n_rows
  FROM inv GROUP BY take, shot, t_s, frame_id, entity
),
attr_pairs AS (
  SELECT a.entity AS entity, a.entity_kind AS entity_kind, a.attribute AS attribute,
         a.take AS take_a, a.frame_id AS frame_a, a.value AS value_a, a.confidence AS conf_a,
         b.take AS take_b, b.frame_id AS frame_b, b.value AS value_b, b.confidence AS conf_b,
         least(a.confidence, b.confidence) AS sql_score,
         if(a.take != b.take, 'cross_take', 'cross_shot') AS pair_kind
  FROM inv a INNER JOIN inv b ON a.entity = b.entity AND a.attribute = b.attribute
  WHERE a.frame_id < b.frame_id AND a.value != b.value AND a.attribute != 'present'
    AND position(a.value, b.value) = 0 AND position(b.value, a.value) = 0
    AND ((a.take != b.take AND a.shot = b.shot AND abs(a.t_s - b.t_s) <= {t_tol:Float32}) OR (a.take = b.take AND a.shot != b.shot))
    AND (a.take = b.take OR a.take = {reference:String} OR b.take = {reference:String})
),
-- presence pairs: same shot and moment across takes; an entity the reference take saw (>= 2 rows) and the other
-- take reports absent, or does not report at all (LEFT JOIN, inferred absence — the verifier decides)
presence_pairs AS (
  SELECT a.entity AS entity, a.entity_kind AS entity_kind, 'present' AS attribute,
         a.take AS take_a, a.frame_id AS frame_a, a.value AS value_a, a.confidence AS conf_a,
         b.take AS take_b, b.frame_id AS frame_b, if(b.frame_id = '', 'absent (not reported)', b.value) AS value_b, if(b.frame_id = '', 0.6, b.confidence) AS conf_b,
         least(a.confidence, if(b.frame_id = '', 0.6, b.confidence)) AS sql_score, 'cross_take' AS pair_kind
  FROM presence a
  INNER JOIN (SELECT DISTINCT take, shot, t_s, frame_id FROM inv) fr ON fr.shot = a.shot AND fr.t_s = a.t_s
  LEFT JOIN presence b ON b.frame_id = fr.frame_id AND b.entity = a.entity
  WHERE fr.take != a.take AND a.take = {reference:String} AND a.n_rows >= 2 AND a.entity_kind IN ('prop','set_dressing','wardrobe')
    AND (b.frame_id = '' OR b.value != a.value)
)
SELECT * FROM (SELECT * FROM attr_pairs UNION ALL SELECT * FROM presence_pairs)
ORDER BY (pair_kind = 'cross_shot'),
         multiIf(attribute IN ('present','state','count','level','side','orientation','held_by','position'), 0, attribute = 'color', 1, 2),
         sql_score DESC
LIMIT {limit:UInt32}
"""
