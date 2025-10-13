/**
 * Database Configuration and Connection Management
 */

import neo4j, { Driver, Session } from 'neo4j-driver';
import { logger } from '../utils/logger';

export class Neo4jConnection {
  private static instance: Neo4jConnection;
  private driver: Driver | null = null;

  private constructor() {}

  public static getInstance(): Neo4jConnection {
    if (!Neo4jConnection.instance) {
      Neo4jConnection.instance = new Neo4jConnection();
    }
    return Neo4jConnection.instance;
  }

  public async connect(): Promise<void> {
    const uri = process.env.NEO4J_URI || 'neo4j://localhost:7687';
    const user = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD || 'password';

    try {
      this.driver = neo4j.driver(
        uri,
        neo4j.auth.basic(user, password),
        {
          maxConnectionPoolSize: 50,
          connectionAcquisitionTimeout: 30000,
          maxTransactionRetryTime: 30000,
        }
      );

      // Verify connectivity
      await this.driver.verifyConnectivity();
      logger.info('✅ Connected to Neo4j database');
    } catch (error) {
      logger.error('❌ Failed to connect to Neo4j:', error);
      throw error;
    }
  }

  public getDriver(): Driver {
    if (!this.driver) {
      throw new Error('Database not connected. Call connect() first.');
    }
    return this.driver;
  }

  public getSession(): Session {
    return this.getDriver().session();
  }

  public async close(): Promise<void> {
    if (this.driver) {
      await this.driver.close();
      logger.info('🔌 Neo4j connection closed');
    }
  }

  public async healthCheck(): Promise<boolean> {
    try {
      const session = this.getSession();
      try {
        await session.run('RETURN 1');
        return true;
      } finally {
        await session.close();
      }
    } catch (error) {
      logger.error('Neo4j health check failed:', error);
      return false;
    }
  }
}

export const db = Neo4jConnection.getInstance();
