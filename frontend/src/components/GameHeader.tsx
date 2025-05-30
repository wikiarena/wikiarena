import type { GameState } from '../types/game';

interface GameHeaderProps {
  gameState: GameState;
}

export function GameHeader({ gameState }: GameHeaderProps) {
  const getStatusDisplay = () => {
    switch (gameState.status) {
      case 'not_started':
        return { text: 'Not Started', color: 'text-gray-600', bg: 'bg-gray-100' };
      case 'in_progress':
        return { text: 'In Progress', color: 'text-blue-600', bg: 'bg-blue-100' };
      case 'won':
        return { text: 'Won!', color: 'text-green-600', bg: 'bg-green-100' };
      case 'lost_max_steps':
        return { text: 'Lost - Max Steps', color: 'text-orange-600', bg: 'bg-orange-100' };
      case 'lost_invalid_move':
        return { text: 'Lost - Invalid Move', color: 'text-red-600', bg: 'bg-red-100' };
      case 'error':
        return { text: 'Error', color: 'text-red-600', bg: 'bg-red-100' };
      default:
        return { text: 'Unknown', color: 'text-gray-600', bg: 'bg-gray-100' };
    }
  };

  const status = getStatusDisplay();
  const duration = gameState.end_timestamp 
    ? Math.round((new Date(gameState.end_timestamp).getTime() - new Date(gameState.start_timestamp).getTime()) / 1000)
    : Math.round((Date.now() - new Date(gameState.start_timestamp).getTime()) / 1000);

  return (
    <div className="bg-white border-2 border-retro-border shadow-retro p-6 mb-6">
      {/* Title */}
      <h1 className="text-3xl font-bold text-center mb-4 font-wiki">
        🏛️ Wikipedia Arena
      </h1>
      
      {/* Game info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-sm text-gray-600">Journey</div>
          <div className="font-mono text-lg">
            <span className="text-green-600 font-bold">{gameState.start_page}</span>
            <span className="mx-2 text-gray-400">→</span>
            <span className="text-red-600 font-bold">{gameState.target_page}</span>
          </div>
        </div>
        
        <div>
          <div className="text-sm text-gray-600">Status</div>
          <div className={`inline-block px-3 py-1 rounded font-medium ${status.color} ${status.bg}`}>
            {status.text}
          </div>
        </div>
        
        <div>
          <div className="text-sm text-gray-600">Progress</div>
          <div className="font-mono">
            <span className="text-lg font-bold">{gameState.steps}</span>
            <span className="text-gray-500"> steps</span>
            <span className="mx-2">•</span>
            <span className="text-gray-500">{duration}s</span>
          </div>
        </div>
      </div>
      
      {/* Game ID */}
      <div className="text-center mt-4 text-xs text-gray-500 font-mono">
        Game ID: {gameState.game_id}
      </div>
    </div>
  );
} 