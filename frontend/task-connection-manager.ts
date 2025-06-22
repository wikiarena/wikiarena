import { WebSocketClient } from './websocket.js';
import { GameEvent, ConnectionStatus, WebSocketConfig } from './types.js';

// =============================================================================
// Task Connection Manager - WebSocket Communication Abstraction
// =============================================================================

export interface TaskConnectionStatus {
  overallStatus: 'disconnected' | 'connecting' | 'connected' | 'partial' | 'error';
  gameConnections: Map<string, ConnectionStatus>;
  connectedGames: number;
  totalGames: number;
  errors: string[];
}

export class TaskConnectionManager {
  private connections: Map<string, WebSocketClient> = new Map();
  private eventHandler: (gameId: string, event: GameEvent) => void;
  private statusListeners: Set<(status: TaskConnectionStatus) => void> = new Set();
  private baseConfig: Omit<WebSocketConfig, 'url'>;

  constructor(
    eventHandler: (gameId: string, event: GameEvent) => void,
    baseConfig: Omit<WebSocketConfig, 'url'> = {}
  ) {
    this.eventHandler = eventHandler;
    this.baseConfig = {
      reconnectInterval: 3000,
      maxReconnectAttempts: 5,
      ...baseConfig
    };
    
    console.log('🔌 TaskConnectionManager initialized');
  }

  // =============================================================================
  // Connection Lifecycle Management
  // =============================================================================

  async connectToTask(gameIds: string[]): Promise<void> {
    console.log(`🔌 Connecting to task with ${gameIds.length} games:`, gameIds);
    
    this.notifyStatusListeners(); // Initial status update
    
    // Create connection promises for all games
    const connectionPromises = gameIds.map(gameId => this.connectToGame(gameId));
    
    try {
      // Attempt to connect to all games simultaneously
      await Promise.allSettled(connectionPromises);
      
      const status = this.getTaskConnectionStatus();
      console.log(`🔌 Task connection completed: ${status.connectedGames}/${status.totalGames} games connected`);
      
      if (status.connectedGames === 0) {
        throw new Error('Failed to connect to any games in the task');
      }
      
      if (status.connectedGames < status.totalGames) {
        console.warn(`⚠️ Partial connection: ${status.connectedGames}/${status.totalGames} games connected`);
      }
      
    } catch (error) {
      console.error('❌ Task connection failed:', error);
      throw error;
    }
  }

  private async connectToGame(gameId: string): Promise<void> {
    const gameWebSocketUrl = `ws://localhost:8000/api/games/${gameId}/ws`;
    
    console.log(`🔌 Connecting to game ${gameId}: ${gameWebSocketUrl}`);
    
    // Create WebSocket client for this game
    const client = new WebSocketClient({
      url: gameWebSocketUrl,
      ...this.baseConfig
    });
    
    // Set up event routing with game context
    client.onMessage(event => {
      console.log(`📨 Received event for game ${gameId}:`, event.type);
      this.eventHandler(gameId, event);
    });
    
    // Set up status monitoring
    client.onStatusChange(status => {
      console.log(`📊 Game ${gameId} status:`, status.connected ? 'connected' : 'disconnected');
      this.notifyStatusListeners();
    });
    
    // Store connection
    this.connections.set(gameId, client);
    
    try {
      // Connect to this game
      client.connect();
      
      // Wait for connection to be established or fail
      await this.waitForConnection(client, gameId);
      
      console.log(`✅ Successfully connected to game ${gameId}`);
      
    } catch (error) {
      console.error(`❌ Failed to connect to game ${gameId}:`, error);
      // Don't remove the connection - keep it for retry attempts
      throw error;
    }
  }

  private async waitForConnection(client: WebSocketClient, gameId: string, timeoutMs: number = 10000): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Connection timeout for game ${gameId} after ${timeoutMs}ms`));
      }, timeoutMs);
      
      const checkConnection = () => {
        const status = client.getStatus();
        
        if (status.connected) {
          clearTimeout(timeout);
          resolve();
        } else if (status.error && !status.connecting) {
          clearTimeout(timeout);
          reject(new Error(`Connection failed for game ${gameId}: ${status.error}`));
        } else if (status.connecting) {
          // Still connecting, check again
          setTimeout(checkConnection, 100);
        } else {
          // Not connecting and not connected - something went wrong
          clearTimeout(timeout);
          reject(new Error(`Unexpected connection state for game ${gameId}`));
        }
      };
      
      // Start checking immediately
      checkConnection();
    });
  }

  // =============================================================================
  // Connection Management
  // =============================================================================

  disconnectFromTask(): void {
    console.log(`🔌 Disconnecting from task with ${this.connections.size} games`);
    
    this.connections.forEach((client, gameId) => {
      console.log(`🔌 Disconnecting from game ${gameId}`);
      client.disconnect();
    });
    
    this.connections.clear();
    this.notifyStatusListeners();
    
    console.log('🔌 Task disconnection complete');
  }

  disconnectFromGame(gameId: string): void {
    const client = this.connections.get(gameId);
    if (client) {
      console.log(`🔌 Disconnecting from game ${gameId}`);
      client.disconnect();
      this.connections.delete(gameId);
      this.notifyStatusListeners();
    } else {
      console.warn(`⚠️ No connection found for game ${gameId}`);
    }
  }

  retryConnection(gameId: string): Promise<void> {
    console.log(`🔄 Retrying connection for game ${gameId}`);
    
    // Disconnect existing connection if any
    this.disconnectFromGame(gameId);
    
    // Reconnect
    return this.connectToGame(gameId);
  }

  // =============================================================================
  // Status Monitoring
  // =============================================================================

  getTaskConnectionStatus(): TaskConnectionStatus {
    const gameConnections = new Map<string, ConnectionStatus>();
    const errors: string[] = [];
    let connectedGames = 0;
    
    this.connections.forEach((client, gameId) => {
      const status = client.getStatus();
      gameConnections.set(gameId, status);
      
      if (status.connected) {
        connectedGames++;
      }
      
      if (status.error) {
        errors.push(`Game ${gameId}: ${status.error}`);
      }
    });
    
    const totalGames = this.connections.size;
    let overallStatus: TaskConnectionStatus['overallStatus'];
    
    if (totalGames === 0) {
      overallStatus = 'disconnected';
    } else if (connectedGames === totalGames) {
      overallStatus = 'connected';
    } else if (connectedGames === 0) {
      overallStatus = errors.length > 0 ? 'error' : 'disconnected';
    } else {
      // Some connected, some not
      overallStatus = 'partial';
    }
    
    // Check if any are still connecting
    const hasConnecting = Array.from(gameConnections.values()).some(status => status.connecting);
    if (hasConnecting && overallStatus !== 'connected') {
      overallStatus = 'connecting';
    }
    
    return {
      overallStatus,
      gameConnections,
      connectedGames,
      totalGames,
      errors
    };
  }

  getGameConnectionStatus(gameId: string): ConnectionStatus | null {
    const client = this.connections.get(gameId);
    return client ? client.getStatus() : null;
  }

  isTaskConnected(): boolean {
    const status = this.getTaskConnectionStatus();
    return status.overallStatus === 'connected';
  }

  isGameConnected(gameId: string): boolean {
    const client = this.connections.get(gameId);
    return client ? client.isConnected() : false;
  }

  // =============================================================================
  // Status Subscription
  // =============================================================================

  onStatusChange(listener: (status: TaskConnectionStatus) => void): () => void {
    this.statusListeners.add(listener);
    
    // Immediately notify with current status
    listener(this.getTaskConnectionStatus());
    
    // Return unsubscribe function
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  private notifyStatusListeners(): void {
    const status = this.getTaskConnectionStatus();
    
    this.statusListeners.forEach(listener => {
      try {
        listener(status);
      } catch (error) {
        console.error('❌ Error in task connection status listener:', error);
      }
    });
  }

  // =============================================================================
  // Connection Information
  // =============================================================================

  getConnectedGameIds(): string[] {
    const connectedGames: string[] = [];
    
    this.connections.forEach((client, gameId) => {
      if (client.isConnected()) {
        connectedGames.push(gameId);
      }
    });
    
    return connectedGames;
  }

  getGameUrls(): Map<string, string> {
    const urls = new Map<string, string>();
    
    this.connections.forEach((client, gameId) => {
      urls.set(gameId, client.getUrl());
    });
    
    return urls;
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  getConnectionCount(): number {
    return this.connections.size;
  }

  hasAnyConnections(): boolean {
    return this.connections.size > 0;
  }

  // For debugging
  debugConnections(): void {
    console.log('🔍 Task Connection Debug:', {
      totalConnections: this.connections.size,
      gameIds: Array.from(this.connections.keys()),
      status: this.getTaskConnectionStatus(),
      gameUrls: Object.fromEntries(this.getGameUrls())
    });
  }

  // =============================================================================
  // Cleanup
  // =============================================================================

  destroy(): void {
    console.log('🧹 Destroying TaskConnectionManager');
    
    // Disconnect all games
    this.disconnectFromTask();
    
    // Clear listeners
    this.statusListeners.clear();
    
    console.log('✅ TaskConnectionManager destroyed');
  }
} 