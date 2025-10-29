"""
Neo4j service for RCA queries
"""
from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class Neo4jService:
    """Service for Neo4j graph database operations"""

    def __init__(self):
        self.driver: Optional[Driver] = None

    def connect(self):
        """Initialize Neo4j connection"""
        try:
            self.driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
            logger.info("Closed Neo4j connection")

    def find_root_causes(
        self,
        client_id: str,
        time_range_hours: int = 24,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find likely root causes (events with no upstream causes but cause downstream events)
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
        ORDER BY effects_caused DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                hours=time_range_hours,
                limit=limit
            )
            return [dict(record) for record in result]

    def find_causal_chain(
        self,
        event_id: str,
        client_id: str,
        max_hops: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find causal chain leading to a specific event
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

        WITH nodes(path) as events, relationships(path) as rels, path_confidence

        UNWIND range(0, size(events)-1) as idx

        WITH
          idx,
          events[idx] as event,
          CASE WHEN idx < size(rels) THEN rels[idx] ELSE null END as next_rel,
          path_confidence

        OPTIONAL MATCH (event)-[:ABOUT]->(r:Resource {client_id: $client_id})

        RETURN
          idx + 1 as step,
          event.eid as event_id,
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
            return [dict(record) for record in result]

    def get_blast_radius(
        self,
        root_event_id: str,
        client_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find all events affected by a root cause
        """
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
            return [dict(record) for record in result]

    def find_events_by_criteria(
        self,
        client_id: str,
        reasons: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        resource_kinds: Optional[List[str]] = None,
        time_range_hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search events by various criteria
        """
        query_parts = [
            "MATCH (e:Episodic {client_id: $client_id})",
            "WHERE e.event_time > datetime() - duration({hours: $hours})"
        ]

        params = {
            "client_id": client_id,
            "hours": time_range_hours,
            "limit": limit
        }

        if reasons:
            query_parts.append("AND e.reason IN $reasons")
            params["reasons"] = reasons

        query_parts.append("OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource {client_id: $client_id})")

        if namespaces:
            query_parts.append("WHERE r.ns IN $namespaces")
            params["namespaces"] = namespaces

        if resource_kinds:
            if namespaces:
                query_parts.append("AND r.kind IN $kinds")
            else:
                query_parts.append("WHERE r.kind IN $kinds")
            params["kinds"] = resource_kinds

        query_parts.append("""
        RETURN
          e.eid as event_id,
          e.reason as reason,
          e.event_time as timestamp,
          e.message as message,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as namespace
        ORDER BY e.event_time DESC
        LIMIT $limit
        """)

        query = "\n".join(query_parts)

        with self.driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def get_topology_for_resource(
        self,
        resource_name: str,
        namespace: str,
        client_id: str
    ) -> Dict[str, Any]:
        """
        Get topology view for a specific resource
        """
        query = """
        MATCH (r:Resource {name: $name, ns: $namespace, client_id: $client_id})

        // Find pods selected by this service
        OPTIONAL MATCH (r)-[sel:SELECTS {client_id: $client_id}]->(pod:Resource {client_id: $client_id})

        // Find nodes pods run on
        OPTIONAL MATCH (pod)-[runs:RUNS_ON {client_id: $client_id}]->(node:Resource {client_id: $client_id})

        // Find upstream services (services that select this resource)
        OPTIONAL MATCH (upstream:Resource {kind: 'Service', client_id: $client_id})-[:SELECTS {client_id: $client_id}]->(r)

        // Find downstream (resources this controls)
        OPTIONAL MATCH (r)-[:CONTROLS {client_id: $client_id}]->(downstream:Resource {client_id: $client_id})

        RETURN
          r.name as service_name,
          r.kind as kind,
          r.ns as namespace,
          collect(DISTINCT {name: pod.name, status: pod.status}) as pods,
          collect(DISTINCT node.name) as nodes,
          collect(DISTINCT upstream.name) as upstream_services,
          collect(DISTINCT downstream.name) as downstream_resources
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                name=resource_name,
                namespace=namespace,
                client_id=client_id
            )
            record = result.single()
            return dict(record) if record else {}

    def get_resources_catalog(
        self,
        client_id: str,
        kinds: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get catalog of resources with metadata
        """
        query_parts = [
            "MATCH (r:Resource {client_id: $client_id})"
        ]

        params = {
            "client_id": client_id,
            "limit": limit,
            "offset": offset
        }

        where_clauses = []
        if kinds:
            where_clauses.append("r.kind IN $kinds")
            params["kinds"] = kinds

        if namespaces:
            where_clauses.append("r.ns IN $namespaces")
            params["namespaces"] = namespaces

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))

        query_parts.append("""
        // Count recent events for this resource
        OPTIONAL MATCH (e:Episodic {client_id: $client_id})-[:ABOUT]->(r)
        WHERE e.event_time > datetime() - duration({hours: 24})

        // Count dependencies
        OPTIONAL MATCH (r)-[:SELECTS|RUNS_ON|CONTROLS {client_id: $client_id}]->(dep:Resource {client_id: $client_id})

        WITH r, count(DISTINCT e) as recent_events, collect(DISTINCT dep.name) as dependencies

        RETURN
          r.name as name,
          r.kind as kind,
          r.ns as namespace,
          r.created_at as created_at,
          r.labels as labels,
          r.owner as owner,
          r.size as size,
          recent_events,
          dependencies
        ORDER BY r.created_at DESC
        SKIP $offset
        LIMIT $limit
        """)

        query = "\n".join(query_parts)

        with self.driver.session() as session:
            result = session.run(query, **params)
            resources = [dict(record) for record in result]

            # Get total count
            count_query = "MATCH (r:Resource {client_id: $client_id})"
            if where_clauses:
                count_query += " WHERE " + " AND ".join(where_clauses)
            count_query += " RETURN count(r) as total"

            count_result = session.run(count_query, **params)
            total_count = count_result.single()["total"]

            return {
                "resources": resources,
                "total_count": total_count,
                "page_size": limit,
                "offset": offset
            }

    def get_health_summary(self, client_id: str) -> Dict[str, Any]:
        """
        Get real-time health summary
        """
        query = """
        // Count resources by health status
        MATCH (r:Resource {client_id: $client_id})
        WITH
          count(DISTINCT CASE
            WHEN r.status IN ['Running', 'Active', 'Healthy', 'Succeeded'] OR r.status IS NULL
            THEN r
          END) as healthy_count,
          count(DISTINCT CASE
            WHEN r.status IN ['Failed', 'Error', 'CrashLoopBackOff', 'OOMKilled', 'Pending', 'Unknown']
            THEN r
          END) as unhealthy_count,
          count(r) as total

        // Count active incidents (root causes in last hour)
        CALL {
          MATCH (e:Episodic {client_id: $client_id})
          WHERE e.event_time > datetime() - duration({hours: 1})
            AND NOT EXISTS {
              MATCH (:Episodic {client_id: $client_id})-[:POTENTIAL_CAUSE {client_id: $client_id}]->(e)
            }
          OPTIONAL MATCH (e)-[pc:POTENTIAL_CAUSE {client_id: $client_id}]->(downstream:Episodic {client_id: $client_id})
          WITH e, count(downstream) as effects
          WHERE effects > 0
          RETURN count(e) as active_incidents
        }

        // Top issues
        CALL {
          MATCH (e:Episodic {client_id: $client_id})
          WHERE e.event_time > datetime() - duration({hours: 24})
          RETURN e.reason as reason, count(*) as count
          ORDER BY count DESC
          LIMIT 5
        }

        RETURN
          healthy_count as healthy,
          unhealthy_count as unhealthy,
          total,
          active_incidents,
          collect({reason: reason, count: count}) as top_issues,
          datetime() as timestamp
        """

        with self.driver.session() as session:
            result = session.run(query, client_id=client_id)
            record = result.single()
            if record:
                data = dict(record)
                # Convert Neo4j DateTime to Python datetime
                if 'timestamp' in data and data['timestamp']:
                    data['timestamp'] = data['timestamp'].to_native()
                return data
            return {}

    def get_cross_service_failures(
        self,
        client_id: str,
        time_range_hours: int = 24,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Find failures that propagated across services (topology-enhanced)
        """
        query = """
        MATCH (e1:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE {client_id: $client_id}]->(e2:Episodic {client_id: $client_id})
        WHERE pc.distance_score IN [0.85, 0.70, 0.55]
          AND e1.event_time > datetime() - duration({hours: $hours})

        OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource {client_id: $client_id})
        OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource {client_id: $client_id})
        OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS* {client_id: $client_id}]-(r2)

        RETURN
          e1.eid as cause_event_id,
          e1.reason as cause_reason,
          r1.kind + '/' + r1.name as cause_resource,
          r1.ns as cause_namespace,
          e1.event_time as cause_timestamp,
          e2.eid as effect_event_id,
          e2.reason as effect_reason,
          r2.kind + '/' + r2.name as effect_resource,
          r2.ns as effect_namespace,
          e2.event_time as effect_timestamp,
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
            return [dict(record) for record in result]


# Global Neo4j service instance
neo4j_service = Neo4jService()
