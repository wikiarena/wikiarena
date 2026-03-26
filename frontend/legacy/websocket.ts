import { GameEvent, WebSocketConfig, ConnectionStatus } from './types.js';

// =============================================================================
// WebSocket Client - Handles all WebSocket communication
// =============================================================================

export class WebSocketClient {
  private socket: WebSocket | null = null;
  private config: WebSocketConfig;
  private status: ConnectionStatus;
  private reconnectTimeout: number | null = null;
  private messageHandlers: Set<(event: GameEvent) => void> = new Set();
  private statusHandlers: Set<(status: ConnectionStatus) => void> = new Set();

  constructor(config: WebSocketConfig) {
    this.config = {
      reconnectInterval: 3000, // 3 seconds
      maxReconnectAttempts: 5,
      ...config
    };

    this.status = {
      connected: false,
      connecting: false,
      error: null,
      reconnectAttempts: 0
    };
  }

  // =============================================================================
  // Connection Management
  // =============================================================================

  updateUrl(newUrl: string): void {
    console.log(`🔄 Updating WebSocket URL from ${this.config.url} to ${newUrl}`);
    this.config.url = newUrl;
    
    // If currently connected, disconnect first
    if (this.isConnected()) {
      this.disconnect();
    }
  }

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      console.log('🔌 Already connected to WebSocket');
      return;
    }

    if (this.status.connecting) {
      console.log('🔌 Connection already in progress');
      return;
    }

    this.updateStatus({ 
      connecting: true, 
      error: null 
    });

    console.log(`🔌 Connecting to WebSocket: ${this.config.url}`);

    try {
      this.socket = new WebSocket(this.config.url);
      this.setupSocketEventHandlers();
    } catch (error) {
      console.error('❌ Failed to create WebSocket:', error);
      this.handleConnectionError('Failed to create WebSocket connection');
    }
  }

  disconnect(): void {
    console.log('🔌 Disconnecting WebSocket...');
    
    // Clear any pending reconnection
    this.clearReconnectTimeout();
    
    // Reset reconnect attempts
    this.status.reconnectAttempts = 0;
    
    if (this.socket) {
      // Remove event listeners to prevent unwanted reconnection
      this.socket.onopen = null;
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onmessage = null;
      
      if (this.socket.readyState === WebSocket.OPEN) {
        this.socket.close();
      }
      
      this.socket = null;
    }

    this.updateStatus({
      connected: false,
      connecting: false,
      error: null
    });
  }

  // =============================================================================
  // Event Handlers Setup
  // =============================================================================

  private setupSocketEventHandlers(): void {
    if (!this.socket) return;

    this.socket.onopen = () => {
      console.log('✅ WebSocket connected successfully');
      this.status.reconnectAttempts = 0;
      this.clearReconnectTimeout();
      
      this.updateStatus({
        connected: true,
        connecting: false,
        error: null
      });
    };

    this.socket.onclose = (event) => {
      console.log('❌ WebSocket disconnected:', event.code, event.reason);
      
      this.updateStatus({
        connected: false,
        connecting: false,
        error: event.reason || 'Connection closed'
      });

      // Attempt reconnection if it wasn't a manual disconnect
      if (event.code !== 1000 && this.shouldReconnect()) {
        this.scheduleReconnect();
      }
    };

    this.socket.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
      this.handleConnectionError('WebSocket connection error');
    };

    this.socket.onmessage = (event) => {
      this.handleMessage(event);
    };
  }

  // =============================================================================
  // Message Handling
  // =============================================================================

  private handleMessage(event: MessageEvent): void {
    try {
      const gameEvent = JSON.parse(event.data) as GameEvent;
      
      // Validate basic event structure
      if (!this.isValidGameEvent(gameEvent)) {
        console.warn('⚠️ Received invalid event structure:', gameEvent);
        return;
      }

      console.log('📨 Received WebSocket event:', gameEvent.type, gameEvent);
      
      // Notify all message handlers
      this.messageHandlers.forEach(handler => {
        try {
          handler(gameEvent);
        } catch (error) {
          console.error('❌ Error in message handler:', error);
        }
      });

    } catch (error) {
      console.error('❌ Failed to parse WebSocket message:', error);
      console.error('Raw message:', event.data);
    }
  }

  private isValidGameEvent(event: any): event is GameEvent {
    return (
      event &&
      typeof event === 'object' &&
      typeof event.type === 'string'
      // No data field required - backend sends flat structure
    );
  }

  // =============================================================================
  // Reconnection Logic
  // =============================================================================

  private shouldReconnect(): boolean {
    return this.status.reconnectAttempts < (this.config.maxReconnectAttempts || 5);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) {
      return; // Already scheduled
    }

    const delay = this.config.reconnectInterval || 3000;
    console.log(`🔄 Scheduling reconnection in ${delay}ms (attempt ${this.status.reconnectAttempts + 1})`);

    this.reconnectTimeout = window.setTimeout(() => {
      this.status.reconnectAttempts++;
      this.clearReconnectTimeout();
      
      if (this.shouldReconnect()) {
        console.log(`🔄 Attempting reconnection (${this.status.reconnectAttempts}/${this.config.maxReconnectAttempts})`);
        this.connect();
      } else {
        console.error('❌ Max reconnection attempts reached');
        this.updateStatus({
          error: 'Max reconnection attempts reached'
        });
      }
    }, delay);
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  private handleConnectionError(message: string): void {
    console.error('❌ Connection error:', message);
    
    this.updateStatus({
      connected: false,
      connecting: false,
      error: message
    });
  }

  // =============================================================================
  // Status Management
  // =============================================================================

  private updateStatus(updates: Partial<ConnectionStatus>): void {
    this.status = { ...this.status, ...updates };
    
    // Notify status handlers
    this.statusHandlers.forEach(handler => {
      try {
        handler(this.status);
      } catch (error) {
        console.error('❌ Error in status handler:', error);
      }
    });
  }

  // =============================================================================
  // Public API
  // =============================================================================

  onMessage(handler: (event: GameEvent) => void): () => void {
    this.messageHandlers.add(handler);
    
    // Return unsubscribe function
    return () => {
      this.messageHandlers.delete(handler);
    };
  }

  onStatusChange(handler: (status: ConnectionStatus) => void): () => void {
    this.statusHandlers.add(handler);
    
    // Immediately call with current status
    handler(this.status);
    
    // Return unsubscribe function
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  getStatus(): ConnectionStatus {
    return { ...this.status };
  }

  isConnected(): boolean {
    return this.status.connected;
  }

  getUrl(): string {
    return this.config.url;
  }

  // Send message (for future use if needed)
  send(message: any): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.warn('⚠️ Cannot send message: WebSocket not connected');
      return false;
    }

    try {
      this.socket.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error('❌ Failed to send message:', error);
      return false;
    }
  }
} 
