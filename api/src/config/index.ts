/**
 * Application Configuration
 */

import dotenv from 'dotenv';

dotenv.config();

export const config = {
  // Server
  port: parseInt(process.env.PORT || '3000', 10),
  host: process.env.HOST || '0.0.0.0',
  env: process.env.NODE_ENV || 'development',

  // Neo4j
  neo4j: {
    uri: process.env.NEO4J_URI || 'neo4j://localhost:7687',
    user: process.env.NEO4J_USER || 'neo4j',
    password: process.env.NEO4J_PASSWORD || 'password',
  },

  // Kafka (optional)
  kafka: {
    enabled: process.env.KAFKA_ENABLED === 'true',
    brokers: process.env.KAFKA_BROKERS?.split(',') || ['localhost:9092'],
    clientId: process.env.KAFKA_CLIENT_ID || 'kg-api',
  },

  // RCA Settings
  rca: {
    defaultTimeWindow: 15, // minutes
    defaultMaxHops: 3,
    defaultMinConfidence: 0.4,
  },

  // Search Settings
  search: {
    defaultTopK: 10,
    defaultMinSimilarity: 0.6,
    defaultTimeWindowDays: 7,
  },

  // Rate Limiting
  rateLimit: {
    windowMs: 60 * 1000, // 1 minute
    max: 1000, // requests per window
  },

  // Authentication
  auth: {
    enabled: process.env.AUTH_ENABLED === 'true',
    apiKeyHeader: 'X-API-Key',
    apiKeys: process.env.API_KEYS?.split(',') || [],
  },

  // CORS
  cors: {
    origin: process.env.CORS_ORIGIN?.split(',') || '*',
    credentials: true,
  },

  // Logging
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    pretty: process.env.NODE_ENV === 'development',
  },

  // Pagination
  pagination: {
    defaultPageSize: 20,
    maxPageSize: 100,
  },
} as const;
