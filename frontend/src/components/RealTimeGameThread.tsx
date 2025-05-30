import { useState, useEffect, useRef } from 'react';
import type { GameState, Move } from '../types/game';
import { PageTweet } from './PageTweet';
import { ErrorCard } from './ErrorCard';

interface RealTimeGameThreadProps {
  onGameStart?: (gameId: string) => void;
  onGameEnd?: (finalState: GameState) => void;
}

interface WebSocketMessage {
  type: 'connection_established' | 'game_started' | 'turn_played' | 'game_finished' | 'error';
  game_id: string;
  timestamp: string;
  game_state?: GameState;
  move?: Move;
  game_over?: boolean;
  background?: boolean;
  error?: string;
  error_type?: string;
  final_status?: string;
  total_steps?: number;
  message?: string;
}

interface ConnectionState {
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  error?: string;
}

export function RealTimeGameThread({ onGameStart, onGameEnd }: RealTimeGameThreadProps) {
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [connection, setConnection] = useState<ConnectionState>({ status: 'disconnected' });
  const [isStarting, setIsStarting] = useState(false);
  const [updateCount, setUpdateCount] = useState(0);
  const [latestMove, setLatestMove] = useState<Move | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // Game configuration
  const [gameConfig, setGameConfig] = useState({
    start_page: 'Computer Science',
    target_page: 'Philosophy',
    max_steps: 20,
    model_provider: 'random',
    model_name: 'random'
  });

  const startNewGame = async () => {
    if (isStarting) return;
    
    setIsStarting(true);
    setGameState(null);
    setLatestMove(null);
    setUpdateCount(0);
    setIsThinking(false);
    
    try {
      setConnection({ status: 'connecting' });
      
      const response = await fetch('http://localhost:8000/api/games?background=true', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(gameConfig)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      const gameId = data.game_id;
      
      setGameState(data.game_state);
      onGameStart?.(gameId);
      
      // Connect to WebSocket for real-time updates
      connectWebSocket(gameId);
      
    } catch (error) {
      console.error('Failed to start game:', error);
      setConnection({ 
        status: 'error', 
        error: error instanceof Error ? error.message : 'Unknown error' 
      });
    } finally {
      setIsStarting(false);
    }
  };

  const connectWebSocket = (gameId: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const wsUrl = `ws://localhost:8000/api/games/${gameId}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnection({ status: 'connected' });
      console.log('WebSocket connected for game:', gameId);
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      setConnection({ status: 'disconnected' });
      
      // Auto-reconnect if the connection was unexpected closed and game is still active
      if (gameState?.status === 'in_progress' && event.code !== 1000) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log('Attempting to reconnect...');
          connectWebSocket(gameId);
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnection({ status: 'error', error: 'WebSocket connection failed' });
    };
  };

  const handleWebSocketMessage = (data: WebSocketMessage) => {
    setUpdateCount(prev => prev + 1);
    
    console.log('WebSocket message:', data.type, data);

    switch (data.type) {
      case 'connection_established':
        console.log('✅ WebSocket connection established');
        break;

      case 'game_started':
        if (data.game_state) {
          setGameState(data.game_state);
          setIsThinking(true);
        }
        break;

      case 'turn_played':
        if (data.game_state) {
          setGameState(data.game_state);
          setLatestMove(data.move || null);
          setIsThinking(!data.game_over);
          
          if (data.game_over) {
            setIsThinking(false);
          }
        }
        break;

      case 'game_finished':
        if (data.game_state) {
          setGameState(data.game_state);
          setIsThinking(false);
          onGameEnd?.(data.game_state);
        }
        break;

      case 'error':
        console.error('Game error:', data.error);
        setConnection({ status: 'error', error: data.error });
        setIsThinking(false);
        break;
    }
  };

  const disconnect = () => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnect');
      wsRef.current = null;
    }
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    setConnection({ status: 'disconnected' });
    setGameState(null);
    setIsThinking(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, []);

  const getStatusColor = () => {
    switch (connection.status) {
      case 'connected': return 'text-green-600 bg-green-50';
      case 'connecting': return 'text-yellow-600 bg-yellow-50';
      case 'error': return 'text-red-600 bg-red-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getStatusText = () => {
    switch (connection.status) {
      case 'connected': return '🟢 Connected - Live Updates';
      case 'connecting': return '🟡 Connecting...';
      case 'error': return `🔴 Error: ${connection.error}`;
      default: return '⚪ Disconnected';
    }
  };

  const renderCurrentThinking = () => {
    if (!isThinking || !gameState) return null;

    return (
      <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <div className="flex items-center space-x-3">
          <div className="thinking-animation">
            <span className="thinking-dot animate-pulse">●</span>
            <span className="thinking-dot animate-pulse" style={{animationDelay: '0.2s'}}>●</span>
            <span className="thinking-dot animate-pulse" style={{animationDelay: '0.4s'}}>●</span>
          </div>
          <span className="text-blue-700 font-medium">Model is thinking about next move...</span>
        </div>
        <div className="mt-2 text-sm text-blue-600">
          Currently on: <strong>{gameState.current_page}</strong>
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      {/* Control Panel */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">🤖 Autonomous Wikipedia Racing</h2>
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor()}`}>
            {getStatusText()}
          </div>
        </div>

        {/* Game Configuration */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <input
            type="text"
            value={gameConfig.start_page}
            onChange={(e) => setGameConfig(prev => ({ ...prev, start_page: e.target.value }))}
            placeholder="Start page"
            className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={connection.status === 'connected'}
          />
          <input
            type="text"
            value={gameConfig.target_page}
            onChange={(e) => setGameConfig(prev => ({ ...prev, target_page: e.target.value }))}
            placeholder="Target page"
            className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={connection.status === 'connected'}
          />
          <input
            type="number"
            value={gameConfig.max_steps}
            onChange={(e) => setGameConfig(prev => ({ ...prev, max_steps: parseInt(e.target.value) || 20 }))}
            placeholder="Max steps"
            min="5"
            max="50"
            className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={connection.status === 'connected'}
          />
          <select
            value={gameConfig.model_provider}
            onChange={(e) => setGameConfig(prev => ({ ...prev, model_provider: e.target.value }))}
            className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={connection.status === 'connected'}
          >
            <option value="random">Random Model</option>
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI</option>
          </select>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={startNewGame}
            disabled={isStarting || connection.status === 'connected'}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isStarting ? 'Starting...' : '🚀 Start New Race'}
          </button>
          
          {connection.status === 'connected' && (
            <button
              onClick={disconnect}
              className="px-6 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 font-medium"
            >
              🛑 Stop Race
            </button>
          )}
        </div>

        {/* Stats */}
        {gameState && (
          <div className="mt-4 flex gap-6 text-sm">
            <span className="text-gray-600">
              <strong>Game ID:</strong> {gameState.game_id}
            </span>
            <span className="text-gray-600">
              <strong>Steps:</strong> {gameState.steps}
            </span>
            <span className="text-gray-600">
              <strong>Status:</strong> {gameState.status}
            </span>
            <span className="text-gray-600">
              <strong>Updates:</strong> {updateCount}
            </span>
          </div>
        )}
      </div>

      {/* Game Thread */}
      {gameState && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
          <div className="max-w-2xl mx-auto">
            
            {/* Starting page */}
            <div className="page-card mb-4">
              <div className="flex items-center justify-between">
                <a 
                  href={`https://en.wikipedia.org/wiki/${encodeURIComponent(gameState.start_page.replace(/ /g, '_'))}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="page-title text-lg font-semibold text-blue-600 hover:text-blue-800"
                >
                  📍 {gameState.start_page}
                </a>
                <span className="text-sm text-gray-500">Starting Point</span>
              </div>
              <div className="text-sm text-gray-600 mt-1">
                🎯 Target: <strong>{gameState.target_page}</strong>
              </div>
            </div>

            {/* Thread connector */}
            {gameState.moves.length > 0 && (
              <div className="flex flex-col items-center mb-4">
                <div className="w-0.5 h-8 bg-gray-300"></div>
              </div>
            )}

            {/* Moves */}
            {gameState.moves.map((move, index) => (
              <div key={index}>
                <PageTweet 
                  move={move} 
                  gameStartTime={gameState.start_timestamp}
                />
                
                {/* Connector to next move or thinking */}
                {(index < gameState.moves.length - 1 || isThinking) && (
                  <div className="flex flex-col items-center my-4">
                    <div className="w-0.5 h-8 bg-gray-300"></div>
                  </div>
                )}
              </div>
            ))}

            {/* Current thinking indicator */}
            {renderCurrentThinking()}

            {/* Game completion status */}
            {gameState.status !== 'in_progress' && (
              <div className="mt-6 p-4 rounded-lg text-center">
                {gameState.status === 'won' && (
                  <div className="bg-green-50 border border-green-200 text-green-800">
                    <div className="text-2xl mb-2">🎉</div>
                    <div className="font-bold">Success!</div>
                    <div className="text-sm">Reached {gameState.target_page} in {gameState.steps} steps</div>
                  </div>
                )}
                
                {gameState.status === 'lost_max_steps' && (
                  <div className="bg-yellow-50 border border-yellow-200 text-yellow-800">
                    <div className="text-2xl mb-2">⏰</div>
                    <div className="font-bold">Max Steps Reached</div>
                    <div className="text-sm">Game ended after {gameState.steps} steps</div>
                  </div>
                )}
                
                {gameState.status === 'error' && (
                  <div className="bg-red-50 border border-red-200 text-red-800">
                    <div className="text-2xl mb-2">❌</div>
                    <div className="font-bold">Game Error</div>
                    <div className="text-sm">An error occurred during gameplay</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* No game state */}
      {!gameState && connection.status === 'disconnected' && (
        <div className="text-center py-12 text-gray-500">
          <div className="text-4xl mb-4">🎮</div>
          <div className="text-lg mb-2">Ready to start an autonomous Wikipedia race!</div>
          <div className="text-sm">Configure your game above and click "Start New Race"</div>
        </div>
      )}
    </div>
  );
} 