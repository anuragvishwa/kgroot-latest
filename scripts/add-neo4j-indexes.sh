#!/bin/bash
# Add Neo4j indexes for production performance

echo "🔧 Adding Neo4j indexes and constraints..."

docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa <<'EOF'
-- Resource indexes
CREATE INDEX resource_uid IF NOT EXISTS FOR (r:Resource) ON (r.uid);
CREATE INDEX resource_name IF NOT EXISTS FOR (r:Resource) ON (r.name, r.namespace);
CREATE INDEX resource_kind IF NOT EXISTS FOR (r:Resource) ON (r.kind);

-- Episodic indexes
CREATE INDEX episodic_time IF NOT EXISTS FOR (e:Episodic) ON (e.eventTime);
CREATE INDEX episodic_severity IF NOT EXISTS FOR (e:Episodic) ON (e.severity);
CREATE INDEX episodic_subject IF NOT EXISTS FOR (e:Episodic) ON (e.subjectName);
CREATE INDEX episodic_etype IF NOT EXISTS FOR (e:Episodic) ON (e.etype);

-- PromTarget indexes
CREATE INDEX promtarget_url IF NOT EXISTS FOR (pt:PromTarget) ON (pt.scrapeUrl);
CREATE INDEX promtarget_health IF NOT EXISTS FOR (pt:PromTarget) ON (pt.health);

-- Unique constraints
CREATE CONSTRAINT resource_uid_unique IF NOT EXISTS FOR (r:Resource) REQUIRE r.uid IS UNIQUE;
CREATE CONSTRAINT episodic_id_unique IF NOT EXISTS FOR (e:Episodic) REQUIRE e.eventId IS UNIQUE;

EOF

echo ""
echo "✅ Indexes and constraints created!"
echo ""
echo "Verifying indexes:"
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "SHOW INDEXES"
