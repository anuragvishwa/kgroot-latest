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
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find likely root causes (events with no upstream causes)

        Returns events that:
        - Have no POTENTIAL_CAUSE relationships pointing TO them
        - Have POTENTIAL_CAUSE relationships pointing FROM them (caused other events)
        """
        query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > datetime() - duration({hours: $hours})
          AND NOT EXISTS {
            MATCH (:Episodic {client_id: $client_id})-[:POTENTIAL_CAUSE {client_id: $client_id}]->(e)
          }

        OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource {client_id: $client_id})
        OPTIONAL MATCH (e)-[pc:POTENTIAL_CAUSE {client_id: $client_id}]->(downstream:Episodic {client_id: $client_id})

        WITH e, r, count(downstream) as effects_caused
        WHERE effects_caused > 0

        RETURN
          e.eid as event_id,
          e.reason as reason,
          e.event_time as timestamp,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as namespace,
          effects_caused as blast_radius
        ORDER BY effects_caused DESC, e.event_time DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                hours=time_range_hours,
                limit=limit
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
        MATCH path = (root:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE*1..$max_hops {client_id: $client_id}]->(target:Episodic {eid: $event_id, client_id: $client_id})

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

        OPTIONAL MATCH (event)-[:ABOUT]->(r:Resource {client_id: $client_id})

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
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all events affected by a root cause (blast radius)"""
        query = """
        MATCH path = (root:Episodic {eid: $root_event_id, client_id: $client_id})-[:POTENTIAL_CAUSE* {client_id: $client_id}]->(affected:Episodic {client_id: $client_id})

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

        OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource {client_id: $client_id})
        OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource {client_id: $client_id})
        OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS* {client_id: $client_id}]-(r2)

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