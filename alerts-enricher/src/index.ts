import { Kafka, Consumer, Producer, EachMessagePayload, CompressionTypes, CompressionCodecs } from 'kafkajs';
import { AlertGrouper, Alert } from './alert-grouper';
import { compress, decompress } from '@mongodb-js/zstd';

// Register ZSTD codec for KafkaJS
CompressionCodecs[CompressionTypes.ZSTD] = () => ({
  async compress(buffer: Buffer) {
    return await compress(buffer);
  },
  async decompress(buffer: Buffer) {
    return await decompress(buffer);
  }
});

console.log('[enricher] ZSTD codec registered');

// Environment configuration
const KAFKA_BROKERS = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
const KAFKA_GROUP = process.env.KAFKA_GROUP || 'alerts-enricher-alerts';
const INPUT_TOPIC = process.env.INPUT_TOPIC || 'events.normalized';
const OUTPUT_TOPIC = process.env.OUTPUT_TOPIC || 'alerts.enriched';
const STATE_RESOURCE_TOPIC = process.env.STATE_RESOURCE_TOPIC || 'state.k8s.resource';
const STATE_TOPOLOGY_TOPIC = process.env.STATE_TOPOLOGY_TOPIC || 'state.k8s.topology';
const GROUPING_WINDOW_MIN = parseInt(process.env.GROUPING_WINDOW_MIN || '5', 10);
const ENABLE_GROUPING = process.env.ENABLE_GROUPING !== 'false'; // default: enabled

// In-memory state caches (compacted topic data)
const resourceState = new Map<string, any>();
const topologyState = new Map<string, any>();

// Initialize alert grouper
const alertGrouper = new AlertGrouper(GROUPING_WINDOW_MIN);

// Stats tracking
let processedCount = 0;
let groupedCount = 0;
let deduplicatedCount = 0;

interface NormalizedEvent {
  etype: string;
  event_id: string;
  event_time: string;
  reason: string;
  severity: string;
  message: string;
  subject?: {
    kind: string;
    ns: string;
    name: string;
    uid?: string;
  };
  [key: string]: any;
}

interface EnrichedAlert extends NormalizedEvent {
  enrichment: {
    resource?: any;
    related_resources?: any[];
    topology?: any[];
    enriched_at: string;
    // Grouping information
    group_id?: string;
    group_count?: number;
    is_grouped?: boolean;
    similar_alerts?: number;
  };
}

// Kafka setup - will be initialized in main() after ZSTD codec is registered
let kafka: Kafka;
let consumer: Consumer;
let producer: Producer;

// Build resource key from subject
function buildResourceKey(subject: any): string {
  if (!subject) return '';
  return `${subject.kind}:${subject.ns}:${subject.name}`;
}

// Enrich alert with context
async function enrichAlert(event: NormalizedEvent): Promise<EnrichedAlert | null> {
  // Only enrich Prometheus alerts
  if (event.etype !== 'prom.alert') {
    return null;
  }

  const enriched: EnrichedAlert = {
    ...event,
    enrichment: {
      enriched_at: new Date().toISOString(),
    },
  };

  // Get resource state
  if (event.subject) {
    const resourceKey = buildResourceKey(event.subject);
    const resource = resourceState.get(resourceKey);
    if (resource) {
      enriched.enrichment.resource = resource;
    }

    // Get related topology
    const related: any[] = [];
    for (const [key, edge] of topologyState.entries()) {
      const fromKey = buildResourceKey({
        kind: edge.from?.split(':')[0],
        ns: edge.from?.split(':')[1],
        name: edge.from?.split(':')[2],
      });
      const toKey = buildResourceKey({
        kind: edge.to?.split(':')[0],
        ns: edge.to?.split(':')[1],
        name: edge.to?.split(':')[2],
      });

      if (fromKey === resourceKey || toKey === resourceKey) {
        related.push(edge);
      }
    }

    if (related.length > 0) {
      enriched.enrichment.topology = related;
    }

    // Get related resources from topology
    const relatedResourceKeys = new Set<string>();
    for (const edge of related) {
      const fromKey = buildResourceKey({
        kind: edge.from?.split(':')[0],
        ns: edge.from?.split(':')[1],
        name: edge.from?.split(':')[2],
      });
      const toKey = buildResourceKey({
        kind: edge.to?.split(':')[0],
        ns: edge.to?.split(':')[1],
        name: edge.to?.split(':')[2],
      });
      if (fromKey !== resourceKey) relatedResourceKeys.add(fromKey);
      if (toKey !== resourceKey) relatedResourceKeys.add(toKey);
    }

    const relatedResources: any[] = [];
    for (const key of relatedResourceKeys) {
      const res = resourceState.get(key);
      if (res) {
        relatedResources.push(res);
      }
    }

    if (relatedResources.length > 0) {
      enriched.enrichment.related_resources = relatedResources;
    }
  }

  return enriched;
}

// Process each message
async function processMessage(payload: EachMessagePayload): Promise<void> {
  const { topic, partition, message } = payload;

  if (!message.value) return;

  const data = JSON.parse(message.value.toString());

  // Update state caches from compacted topics
  if (topic === STATE_RESOURCE_TOPIC) {
    const key = buildResourceKey(data);
    if (data.op === 'DELETE') {
      resourceState.delete(key);
    } else {
      resourceState.set(key, data);
    }
    return;
  }

  if (topic === STATE_TOPOLOGY_TOPIC) {
    if (data.op === 'DELETE') {
      topologyState.delete(data.id);
    } else {
      topologyState.set(data.id, data);
    }
    return;
  }

  // Process events from INPUT_TOPIC
  if (topic === INPUT_TOPIC) {
    processedCount++;

    const enriched = await enrichAlert(data);
    if (enriched) {
      // Apply alert grouping if enabled
      if (ENABLE_GROUPING) {
        const groupResult = alertGrouper.processAlert(enriched as Alert);

        if (groupResult) {
          if (groupResult.action === 'duplicate') {
            deduplicatedCount++;
            console.log(
              `[enricher] Deduplicated alert: ${enriched.reason} (group: ${groupResult.group.group_id})`
            );
            // Don't send duplicate alerts
            return;
          }

          if (groupResult.action === 'grouped') {
            groupedCount++;
          }

          // Add grouping metadata
          enriched.enrichment.group_id = groupResult.group.group_id;
          enriched.enrichment.group_count = groupResult.group.count;
          enriched.enrichment.is_grouped = groupResult.action === 'grouped';
          enriched.enrichment.similar_alerts = groupResult.group.count - 1;
        }
      }

      await producer.send({
        topic: OUTPUT_TOPIC,
        messages: [
          {
            key: enriched.event_id,
            value: JSON.stringify(enriched),
          },
        ],
      });

      console.log(
        `[enricher] Enriched alert: ${enriched.reason} for ${buildResourceKey(enriched.subject!)} ` +
        `(grouped: ${enriched.enrichment.is_grouped}, count: ${enriched.enrichment.group_count})`
      );
    }
  }
}

// Print stats periodically
function printStats() {
  const grouperStats = alertGrouper.getStats();
  console.log('\n=== Alert Enricher Stats ===');
  console.log(`Processed: ${processedCount} alerts`);
  console.log(`Grouped: ${groupedCount} alerts`);
  console.log(`Deduplicated: ${deduplicatedCount} alerts`);
  console.log(`Active Groups: ${grouperStats.active_groups}`);
  console.log(`Total Groups: ${grouperStats.total_groups}`);
  console.log(`Deduplication Rate: ${grouperStats.deduplication_rate}`);
  console.log(`Resource State Cache: ${resourceState.size} entries`);
  console.log(`Topology State Cache: ${topologyState.size} entries`);
  console.log('===========================\n');
}

// Main function
async function main() {
  console.log('[enricher] Starting alerts-enricher...');
  console.log(`[enricher] Kafka brokers: ${KAFKA_BROKERS.join(', ')}`);
  console.log(`[enricher] Consumer group: ${KAFKA_GROUP}`);
  console.log(`[enricher] Input topic: ${INPUT_TOPIC}`);
  console.log(`[enricher] Output topic: ${OUTPUT_TOPIC}`);
  console.log(`[enricher] Alert grouping: ${ENABLE_GROUPING ? 'ENABLED' : 'DISABLED'}`);
  console.log(`[enricher] Grouping window: ${GROUPING_WINDOW_MIN} minutes`);

  // Initialize Kafka (supports gzip, snappy, and uncompressed)
  kafka = new Kafka({
    clientId: 'alerts-enricher',
    brokers: KAFKA_BROKERS,
  });

  consumer = kafka.consumer({ groupId: KAFKA_GROUP });
  producer = kafka.producer();

  await consumer.connect();
  await producer.connect();

  console.log('[enricher] Connected to Kafka');

  // Subscribe to all needed topics
  await consumer.subscribe({ topics: [INPUT_TOPIC, STATE_RESOURCE_TOPIC, STATE_TOPOLOGY_TOPIC] });

  console.log('[enricher] Subscribed to topics, consuming messages...');

  // Print stats every 5 minutes
  setInterval(printStats, 5 * 60 * 1000);

  await consumer.run({
    eachMessage: processMessage,
  });
}



// Graceful shutdown
async function shutdown() {
  console.log('[enricher] Shutting down...');
  await consumer.disconnect();
  await producer.disconnect();
  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

// Start
main().catch((err) => {
  console.error('[enricher] Fatal error:', err);
  process.exit(1);
});
