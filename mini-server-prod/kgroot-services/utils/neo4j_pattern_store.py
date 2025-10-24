"""
Neo4j Pattern Store
Stores and retrieves failure patterns from Neo4j
"""

from neo4j import GraphDatabase
from typing import List, Dict, Optional, Any
import json
import logging
from datetime import datetime

from models.graph import FaultEventKnowledgeGraph
from models.event import EventType, EventSeverity, AbstractEvent
from models.graph import RelationType

logger = logging.getLogger(__name__)


class Neo4jPatternStore:
    """
    Stores and manages failure patterns in Neo4j
    """

    def __init__(self, uri: str, username: str, password: str):
        """
        Initialize Neo4j connection

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
        """
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        logger.info(f"Connected to Neo4j at {uri}")

    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()

    def initialize_schema(self):
        """Create necessary indexes and constraints"""
        with self.driver.session() as session:
            # Constraint for FailurePattern
            session.run("""
                CREATE CONSTRAINT failure_pattern_id IF NOT EXISTS
                FOR (fp:FailurePattern) REQUIRE fp.pattern_id IS UNIQUE
            """)

            # Constraint for AbstractEvent
            session.run("""
                CREATE CONSTRAINT abstract_event_signature IF NOT EXISTS
                FOR (ae:AbstractEvent) REQUIRE ae.signature IS UNIQUE
            """)

            # Index for root cause type
            session.run("""
                CREATE INDEX failure_pattern_root_cause IF NOT EXISTS
                FOR (fp:FailurePattern) ON (fp.root_cause_type)
            """)

            # Index for frequency
            session.run("""
                CREATE INDEX failure_pattern_frequency IF NOT EXISTS
                FOR (fp:FailurePattern) ON (fp.frequency)
            """)

            logger.info("Neo4j schema initialized")

    def store_pattern(self, fekg: FaultEventKnowledgeGraph):
        """
        Store FEKG pattern in Neo4j

        Args:
            fekg: Fault Event Knowledge Graph to store
        """
        with self.driver.session() as session:
            session.execute_write(self._create_pattern_tx, fekg)
            logger.info(f"Stored pattern {fekg.pattern_id}")

    def _create_pattern_tx(self, tx, fekg: FaultEventKnowledgeGraph):
        """Transaction to create pattern"""
        # Create FailurePattern node
        tx.run("""
            MERGE (fp:FailurePattern {pattern_id: $pattern_id})
            SET fp.root_cause_type = $root_cause_type,
                fp.fault_type = $fault_type,
                fp.event_sequence = $event_sequence,
                fp.frequency = $frequency,
                fp.first_seen = datetime($first_seen),
                fp.last_seen = datetime($last_seen),
                fp.avg_resolution_time_seconds = $avg_resolution_time,
                fp.resolution_steps = $resolution_steps,
                fp.prevention_measures = $prevention_measures,
                fp.updated_at = datetime()
        """, {
            'pattern_id': fekg.pattern_id,
            'root_cause_type': fekg.root_cause_type,
            'fault_type': fekg.fault_type,
            'event_sequence': fekg.event_sequence,
            'frequency': fekg.frequency,
            'first_seen': fekg.first_seen.isoformat() if fekg.first_seen else None,
            'last_seen': fekg.last_seen.isoformat() if fekg.last_seen else None,
            'avg_resolution_time': fekg.avg_resolution_time_seconds,
            'resolution_steps': fekg.resolution_steps,
            'prevention_measures': fekg.prevention_measures
        })

        # Create AbstractEvent nodes
        for signature, abstract_event in fekg.abstract_events.items():
            tx.run("""
                MERGE (ae:AbstractEvent {signature: $signature})
                SET ae.event_type = $event_type,
                    ae.service_pattern = $service_pattern,
                    ae.severity = $severity,
                    ae.metric_threshold_pattern = $metric_threshold_pattern,
                    ae.occurrence_count = $occurrence_count
            """, {
                'signature': signature,
                'event_type': abstract_event.event_type.value,
                'service_pattern': abstract_event.service_pattern,
                'severity': abstract_event.severity.value,
                'metric_threshold_pattern': abstract_event.metric_threshold_pattern,
                'occurrence_count': abstract_event.occurrence_count
            })

            # Link pattern to events
            tx.run("""
                MATCH (fp:FailurePattern {pattern_id: $pattern_id})
                MATCH (ae:AbstractEvent {signature: $signature})
                MERGE (fp)-[:CONTAINS_EVENT]->(ae)
            """, {
                'pattern_id': fekg.pattern_id,
                'signature': signature
            })

        # Create relationships between events
        for source, target, data in fekg.graph.edges(data=True):
            tx.run("""
                MATCH (source:AbstractEvent {signature: $source})
                MATCH (target:AbstractEvent {signature: $target})
                MATCH (fp:FailurePattern {pattern_id: $pattern_id})
                MERGE (source)-[r:CAUSES {pattern_id: $pattern_id}]->(target)
                SET r.relation_type = $relation_type,
                    r.confidence = $confidence
            """, {
                'source': source,
                'target': target,
                'pattern_id': fekg.pattern_id,
                'relation_type': data.get('relation_type', 'unknown'),
                'confidence': data.get('confidence', 1.0)
            })

    def get_pattern(self, pattern_id: str) -> Optional[FaultEventKnowledgeGraph]:
        """
        Retrieve pattern by ID

        Args:
            pattern_id: Pattern identifier

        Returns:
            FaultEventKnowledgeGraph or None
        """
        with self.driver.session() as session:
            result = session.execute_read(self._get_pattern_tx, pattern_id)
            if result:
                return self._dict_to_fekg(result)
            return None

    def _get_pattern_tx(self, tx, pattern_id: str) -> Optional[Dict]:
        """Transaction to retrieve pattern"""
        result = tx.run("""
            MATCH (fp:FailurePattern {pattern_id: $pattern_id})
            OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
            OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES {pattern_id: $pattern_id}]->(ae2:AbstractEvent)
            RETURN fp, collect(DISTINCT ae) as abstract_events,
                   collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
        """, pattern_id=pattern_id)

        record = result.single()
        if not record:
            return None

        return {
            'pattern': dict(record['fp']),
            'abstract_events': [dict(ae) for ae in record['abstract_events'] if ae],
            'relations': record['relations']
        }

    def get_all_patterns(self) -> List[FaultEventKnowledgeGraph]:
        """
        Retrieve all patterns from database

        Returns:
            List of FaultEventKnowledgeGraph
        """
        with self.driver.session() as session:
            results = session.execute_read(self._get_all_patterns_tx)
            return [self._dict_to_fekg(r) for r in results]

    def _get_all_patterns_tx(self, tx) -> List[Dict]:
        """Transaction to retrieve all patterns"""
        result = tx.run("""
            MATCH (fp:FailurePattern)
            OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
            OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES]->(ae2:AbstractEvent)
            WHERE r.pattern_id = fp.pattern_id
            RETURN fp, collect(DISTINCT ae) as abstract_events,
                   collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
            ORDER BY fp.frequency DESC
        """)

        return [
            {
                'pattern': dict(record['fp']),
                'abstract_events': [dict(ae) for ae in record['abstract_events'] if ae],
                'relations': record['relations']
            }
            for record in result
        ]

    def search_patterns_by_root_cause(
        self,
        root_cause_type: str,
        limit: int = 10
    ) -> List[FaultEventKnowledgeGraph]:
        """
        Search patterns by root cause type

        Args:
            root_cause_type: Root cause type to search
            limit: Maximum number of results

        Returns:
            List of matching patterns
        """
        with self.driver.session() as session:
            results = session.execute_read(
                self._search_by_root_cause_tx,
                root_cause_type,
                limit
            )
            return [self._dict_to_fekg(r) for r in results]

    def _search_by_root_cause_tx(self, tx, root_cause_type: str, limit: int) -> List[Dict]:
        """Transaction to search by root cause"""
        result = tx.run("""
            MATCH (fp:FailurePattern {root_cause_type: $root_cause_type})
            OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
            OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES]->(ae2:AbstractEvent)
            WHERE r.pattern_id = fp.pattern_id
            RETURN fp, collect(DISTINCT ae) as abstract_events,
                   collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
            ORDER BY fp.frequency DESC
            LIMIT $limit
        """, root_cause_type=root_cause_type, limit=limit)

        return [
            {
                'pattern': dict(record['fp']),
                'abstract_events': [dict(ae) for ae in record['abstract_events'] if ae],
                'relations': record['relations']
            }
            for record in result
        ]

    def update_pattern_frequency(self, pattern_id: str):
        """Increment pattern frequency (matched again)"""
        with self.driver.session() as session:
            session.run("""
                MATCH (fp:FailurePattern {pattern_id: $pattern_id})
                SET fp.frequency = fp.frequency + 1,
                    fp.last_seen = datetime(),
                    fp.updated_at = datetime()
            """, pattern_id=pattern_id)
            logger.debug(f"Updated frequency for pattern {pattern_id}")

    def _dict_to_fekg(self, data: Dict) -> FaultEventKnowledgeGraph:
        """Convert Neo4j result to FEKG"""
        pattern_data = data['pattern']

        fekg = FaultEventKnowledgeGraph(
            pattern_id=pattern_data['pattern_id'],
            root_cause_type=pattern_data['root_cause_type'],
            fault_type=pattern_data.get('fault_type')
        )

        # Restore metadata
        fekg.event_sequence = pattern_data.get('event_sequence', [])
        fekg.frequency = pattern_data.get('frequency', 0)
        fekg.first_seen = (
            datetime.fromisoformat(pattern_data['first_seen'])
            if pattern_data.get('first_seen')
            else None
        )
        fekg.last_seen = (
            datetime.fromisoformat(pattern_data['last_seen'])
            if pattern_data.get('last_seen')
            else None
        )
        fekg.avg_resolution_time_seconds = pattern_data.get('avg_resolution_time_seconds')
        fekg.resolution_steps = pattern_data.get('resolution_steps', [])
        fekg.prevention_measures = pattern_data.get('prevention_measures', [])

        # Restore abstract events
        for ae_data in data.get('abstract_events', []):
            if not ae_data:
                continue

            abstract_event = AbstractEvent(
                event_type=EventType(ae_data['event_type']),
                service_pattern=ae_data['service_pattern'],
                severity=EventSeverity(ae_data['severity']),
                metric_threshold_pattern=ae_data.get('metric_threshold_pattern'),
                occurrence_count=ae_data.get('occurrence_count', 0)
            )
            fekg.add_abstract_event(abstract_event)

        # Restore relations
        for relation in data.get('relations', []):
            if not relation or len(relation) < 3:
                continue

            source_sig, rel_data, target_sig = relation
            if not source_sig or not target_sig:
                continue

            try:
                fekg.add_abstract_relation(
                    source_sig,
                    target_sig,
                    RelationType(rel_data.get('relation_type', 'correlates_with')),
                    rel_data.get('confidence', 1.0)
                )
            except ValueError:
                # Event not in graph, skip
                continue

        return fekg

    def get_statistics(self) -> Dict[str, Any]:
        """Get pattern library statistics"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (fp:FailurePattern)
                OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
                RETURN count(DISTINCT fp) as pattern_count,
                       count(DISTINCT ae) as event_type_count,
                       sum(fp.frequency) as total_matches,
                       collect(DISTINCT fp.root_cause_type) as root_cause_types
            """)

            record = result.single()
            return {
                'pattern_count': record['pattern_count'],
                'event_type_count': record['event_type_count'],
                'total_matches': record['total_matches'],
                'root_cause_types': record['root_cause_types']
            }
