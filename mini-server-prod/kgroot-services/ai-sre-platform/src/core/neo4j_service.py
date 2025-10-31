"""Neo4j service for causality graph queries"""

from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Neo4jService:
    """Service for interacting with Neo4j causality graph"""

    def __init__(self, uri: str, user: str, password: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Connected to Neo4j at {uri}")

    def close(self):
        """Close Neo4j driver"""
        self.driver.close()

    def verify_connectivity(self) -> bool:
        """Verify Neo4j connection"""
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity failed: {e}")
            return False

    def find_root_causes(
        self,
        client_id: str,
        time_range_hours: int = 24,
        limit: int = 10,
        max_upstream_causes: int = 10,
        namespace: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Dynamically find root causes WITHOUT requiring specific event_id.

        Works for ANY:
        - Time range (configurable hours, or explicit from_time/to_time)
        - Namespace (optional filter)
        - Tenant (client_id)

        Strategy:
        1. Find events with ≤10 upstream causes (early in causal chain)
        2. Sort by: fewest upstream first, then highest blast radius
        3. Filter out normal operations (Pulled, Created, Started, etc.)
        4. Include actual failures (BackOff, Failed, Unhealthy, OOMKilled, etc.)
        """
        query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > $from_time
          AND e.event_time <= $to_time
          AND e.etype IN ['k8s.event', 'k8s.log']
          AND NOT e.reason IN ['Pulled', 'Created', 'Started', 'Scheduled', 'Completed',
                               'SuccessfulCreate', 'SuccessfulDelete', 'Killing', 'SawCompletedJob']

        // Flexible Resource matching: works with or without client_id
        OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
        WHERE (r.client_id = $client_id OR (r.client_id IS NULL AND r.ns IS NOT NULL))
          AND ($namespace IS NULL OR r.ns = $namespace)

        OPTIONAL MATCH (upstream:Episodic {client_id: $client_id})-[:POTENTIAL_CAUSE {client_id: $client_id}]->(e)
        OPTIONAL MATCH (e)-[:POTENTIAL_CAUSE {client_id: $client_id}]->(downstream:Episodic {client_id: $client_id})

        WITH e, r,
             count(DISTINCT upstream) as upstream_count,
             count(DISTINCT downstream) as effects_caused
        WHERE effects_caused > 0
          AND upstream_count <= $max_upstream

        RETURN
          e.eid as event_id,
          e.reason as reason,
          e.event_time as timestamp,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as namespace,
          upstream_count as upstream_causes,
          effects_caused as blast_radius
        ORDER BY upstream_count ASC, effects_caused DESC, e.event_time DESC
        LIMIT $limit
        """

        # Calculate time range
        if not to_time:
            to_time = datetime.utcnow()
        if not from_time:
            from_time = to_time - timedelta(hours=time_range_hours)

        with self.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                from_time=from_time,
                to_time=to_time,
                namespace=namespace,
                limit=limit,
                max_upstream=max_upstream_causes
            )

            root_causes = []
            for record in result:
                root_causes.append({
                    "event_id": record["event_id"],
                    "reason": record["reason"],
                    "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                    "resource_kind": record["resource_kind"],
                    "resource_name": record["resource_name"],
                    "namespace": record["namespace"],
                    "upstream_causes": record["upstream_causes"],
                    "blast_radius": record["blast_radius"]
                })

            return root_causes

    def find_causal_chain(
        self,
        event_id: str,
        client_id: str,
        max_hops: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get causal chain leading to a specific event

        Returns the path from root cause to target event
        """
        query = """
        MATCH path = (root:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE*1..3]->(target:Episodic {eid: $event_id, client_id: $client_id})
        WHERE ALL(rel IN relationships(path) WHERE rel.client_id = $client_id)

        WITH
          root,
          target,
          path,
          reduce(conf = 1.0, rel IN relationships(path) | conf * rel.confidence) as path_confidence,
          length(path) as hops

        ORDER BY path_confidence DESC, hops ASC
        LIMIT 1

        UNWIND range(0, size(nodes(path))-1) as idx

        WITH
          idx,
          nodes(path)[idx] as event,
          CASE WHEN idx < size(relationships(path)) THEN relationships(path)[idx] ELSE null END as next_rel,
          path_confidence

        // Flexible Resource matching
        OPTIONAL MATCH (event)-[:ABOUT]->(r:Resource)
        WHERE r.client_id = $client_id OR (r.client_id IS NULL AND r.ns IS NOT NULL)

        RETURN
          idx + 1 as step,
          event.reason as reason,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as namespace,
          event.event_time as timestamp,
          CASE WHEN next_rel IS NOT NULL THEN next_rel.confidence ELSE null END as confidence_to_next,
          path_confidence as overall_confidence
        ORDER BY idx
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                event_id=event_id,
                client_id=client_id,
                max_hops=max_hops
            )

            chain = []
            for record in result:
                chain.append({
                    "step": record["step"],
                    "reason": record["reason"],
                    "resource_kind": record["resource_kind"],
                    "resource_name": record["resource_name"],
                    "namespace": record["namespace"],
                    "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                    "confidence_to_next": record["confidence_to_next"],
                    "overall_confidence": record["overall_confidence"]
                })

            return chain

    def get_blast_radius(
        self,
        root_event_id: str,
        client_id: str,
        limit: int = 50,
        max_hops: int = 5
    ) -> List[Dict[str, Any]]:
        """Get all events affected by a root cause (blast radius)"""
        query = """
        MATCH path = (root:Episodic {eid: $root_event_id, client_id: $client_id})-[:POTENTIAL_CAUSE*1..5]->(affected:Episodic {client_id: $client_id})
        WHERE ALL(rel IN relationships(path) WHERE rel.client_id = $client_id)

        WITH
          affected,
          min(length(path)) as min_hops,
          max([rel IN relationships(path) | rel.confidence]) as max_confidence

        OPTIONAL MATCH (affected)-[:ABOUT]->(r:Resource {client_id: $client_id})

        RETURN
          affected.eid as event_id,
          affected.reason as reason,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as namespace,
          affected.event_time as timestamp,
          min_hops as distance_from_root,
          max_confidence as confidence
        ORDER BY min_hops ASC, max_confidence DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                root_event_id=root_event_id,
                client_id=client_id,
                limit=limit
            )

            blast_radius = []
            for record in result:
                blast_radius.append({
                    "event_id": record["event_id"],
                    "reason": record["reason"],
                    "resource_kind": record["resource_kind"],
                    "resource_name": record["resource_name"],
                    "namespace": record["namespace"],
                    "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                    "distance_from_root": record["distance_from_root"],
                    "confidence": record["confidence"]
                })

            return blast_radius

    def get_cross_service_failures(
        self,
        client_id: str,
        time_range_hours: int = 24,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get failures that propagated across services (topology-enhanced)"""
        query = """
        MATCH (e1:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE {client_id: $client_id}]->(e2:Episodic {client_id: $client_id})
        WHERE pc.distance_score IN [0.85, 0.70, 0.55]
          AND e1.event_time > datetime() - duration({hours: $hours})

        // Flexible Resource matching: works with or without client_id
        OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource)
        WHERE r1.client_id = $client_id OR (r1.client_id IS NULL AND r1.ns IS NOT NULL)

        OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource)
        WHERE r2.client_id = $client_id OR (r2.client_id IS NULL AND r2.ns IS NOT NULL)

        // Flexible topology matching: works with or without client_id on relationships
        OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)
        WHERE ALL(rel IN relationships(topology_path)
          WHERE rel.client_id = $client_id OR rel.client_id IS NULL)

        RETURN
          e1.reason as cause_reason,
          r1.kind + '/' + r1.name as cause_resource,
          e2.reason as effect_reason,
          r2.kind + '/' + r2.name as effect_resource,
          pc.confidence as confidence,
          length(topology_path) as topology_hops,
          [rel IN relationships(topology_path) | type(rel)] as topology_path_types
        ORDER BY pc.confidence DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                hours=time_range_hours,
                limit=limit
            )

            failures = []
            for record in result:
                failures.append({
                    "cause_reason": record["cause_reason"],
                    "cause_resource": record["cause_resource"],
                    "effect_reason": record["effect_reason"],
                    "effect_resource": record["effect_resource"],
                    "confidence": record["confidence"],
                    "topology_hops": record["topology_hops"],
                    "topology_path_types": record["topology_path_types"]
                })

            return failures

    def get_event_count(
        self,
        client_id: str,
        time_range_hours: int = 24
    ) -> int:
        """Get count of events in time range"""
        query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > datetime() - duration({hours: $hours})
        RETURN count(e) as event_count
        """

        with self.driver.session() as session:
            result = session.run(query, client_id=client_id, hours=time_range_hours)
            record = result.single()
            return record["event_count"] if record else 0

    def semantic_search_events(
        self,
        query_embedding: List[float],
        client_id: str,
        time_range_hours: Optional[int] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for events using embedding vector (GraphRAG)

        Note: This is a simplified implementation. For production GraphRAG:
        1. Add vector index to Neo4j: CREATE VECTOR INDEX event_embeddings IF NOT EXISTS FOR (e:Episodic) ON (e.embedding)
        2. Store embeddings during event ingestion
        3. Use Neo4j's native vector search: db.index.vector.queryNodes()

        For now, we return text-based search as fallback.
        """
        # For now, use text-based search as fallback
        # TODO: Implement true vector search once Neo4j has event embeddings

        query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE ($time_range_hours IS NULL OR e.event_time > datetime() - duration({hours: $time_range_hours}))

        // Optional: Filter to events with resource context only
        // Uncomment the next line to exclude log entries without resources
        // AND EXISTS((e)-[:ABOUT]->(:Resource))

        OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource {client_id: $client_id})

        RETURN
            e.eid as event_id,
            e.reason as reason,
            e.message as message,
            e.etype as event_type,
            e.severity as severity,
            r.kind as resource_kind,
            r.name as resource_name,
            r.ns as namespace,
            e.event_time as timestamp,
            e.client_id as client_id
        ORDER BY e.event_time DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                time_range_hours=time_range_hours,
                limit=limit
            )

            events = []
            for record in result:
                events.append({
                    "event_id": record["event_id"],
                    "reason": record["reason"],
                    "message": record["message"],
                    "event_type": record["event_type"],
                    "severity": record["severity"],
                    "resource_kind": record["resource_kind"],
                    "resource_name": record["resource_name"],
                    "namespace": record["namespace"],
                    "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                    "client_id": record["client_id"],
                    "similarity_score": 0.8  # Placeholder - would be computed from embedding
                })

            logger.info(f"Semantic search returned {len(events)} events (text-based fallback)")
            return events