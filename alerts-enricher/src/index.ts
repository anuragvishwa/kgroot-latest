import { Kafka, Consumer, Producer, EachMessagePayload, CompressionTypes, CompressionCodecs } from 'kafkajs';
const ZstdCodec = require('zstd-codec').ZstdCodec;

// Register ZSTD codec
ZstdCodec.run((zstd: any) => {
  CompressionCodecs[CompressionTypes.ZSTD] = () => ({
    compress: () => (value: Buffer) => Buffer.from(zstd.compress(value)),
    decompress: () => (value: Buffer) => Buffer.from(zstd.decompress(value))
  });
  console.log('[enricher] ZSTD codec registered');
});

// Environment configuration
const KAFKA_BROKERS = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
const KAFKA_GROUP = process.env.KAFKA_GROUP || 'alerts-enricher-alerts';
const INPUT_TOPIC = process.env.INPUT_TOPIC || 'events.normalized';
const OUTPUT_TOPIC = process.env.OUTPUT_TOPIC || 'alerts.enriched';
const STATE_RESOURCE_TOPIC = process.env.STATE_RESOURCE_TOPIC || 'state.k8s.resource';
const STATE_TOPOLOGY_TOPIC = process.env.STATE_TOPOLOGY_TOPIC || 'state.k8s.topology';

// In-memory state caches (compacted topic data)
const resourceState = new Map<string, any>();
const topologyState = new Map<string, any>();

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
  };
}

// Kafka setup
const kafka = new Kafka({
  clientId: 'alerts-enricher',
  brokers: KAFKA_BROKERS,
});

const consumer: Consumer = kafka.consumer({ groupId: KAFKA_GROUP });
const producer: Producer = kafka.producer();

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
    const enriched = await enrichAlert(data);
    if (enriched) {
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
        `[enricher] Enriched alert: ${enriched.reason} for ${buildResourceKey(enriched.subject!)}`
      );
    }
  }
}

// Main function
async function main() {
  console.log('[enricher] Starting alerts-enricher...');
  console.log(`[enricher] Kafka brokers: ${KAFKA_BROKERS.join(', ')}`);
  console.log(`[enricher] Consumer group: ${KAFKA_GROUP}`);
  console.log(`[enricher] Input topic: ${INPUT_TOPIC}`);
  console.log(`[enricher] Output topic: ${OUTPUT_TOPIC}`);

  await consumer.connect();
  await producer.connect();

  console.log('[enricher] Connected to Kafka');

  // Subscribe to all needed topics
  await consumer.subscribe({ topics: [INPUT_TOPIC, STATE_RESOURCE_TOPIC, STATE_TOPOLOGY_TOPIC] });

  console.log('[enricher] Subscribed to topics, consuming messages...');

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
