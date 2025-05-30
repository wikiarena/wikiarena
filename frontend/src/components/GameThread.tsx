import type { GameState } from '../types/game';
import { PageTweet } from './PageTweet';
import { ErrorCard } from './ErrorCard';

interface GameThreadProps {
  gameState: GameState;
}

export function GameThread({ gameState }: GameThreadProps) {
  const isGameWon = gameState.status === 'won';

  return (
    <div className="max-w-2xl mx-auto py-4">
      {/* Starting page as first card - only if no moves yet */}
      {gameState.moves.length === 0 && (
        <div className="page-card">
          <div className="flex items-center justify-between">
            <a 
              href={`https://en.wikipedia.org/wiki/${encodeURIComponent(gameState.start_page.replace(/ /g, '_'))}`}
              target="_blank"
              rel="noopener noreferrer"
              className="page-title"
            >
              {gameState.start_page}
            </a>
            <span className="time-delta">0s</span>
          </div>
        </div>
      )}

      {/* Move thread */}
      {gameState.moves.map((move, index) => (
        <div key={`${move.step}-${move.from_page_title}`}>
          {/* Connection line from previous (except for first move) */}
          {index > 0 && (
            <div className="flex flex-col items-center">
              <div className="thread-connector h-4"></div>
            </div>
          )}

          {move.error ? (
            <ErrorCard move={move} gameStartTime={gameState.start_timestamp} />
          ) : (
            <PageTweet move={move} gameStartTime={gameState.start_timestamp} />
          )}
        </div>
      ))}

      {/* Connection line to target if game is won */}
      {isGameWon && gameState.moves.length > 0 && (
        <div className="flex flex-col items-center">
          <div className="thread-connector h-4"></div>
        </div>
      )}

      {/* Target page in the thread */}
      <div className={`page-card ${isGameWon ? 'border-green-300 bg-green-50' : 'border-gray-400 bg-gray-50'}`}>
        <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Target</div>
        <div className="flex items-center justify-between">
          <a 
            href={`https://en.wikipedia.org/wiki/${encodeURIComponent(gameState.target_page.replace(/ /g, '_'))}`}
            target="_blank"
            rel="noopener noreferrer"
            className={`page-title ${isGameWon ? 'text-green-600' : ''}`}
          >
            {gameState.target_page}
          </a>
          {isGameWon && (
            <span className="text-green-600 text-sm font-medium">
              Reached!
            </span>
          )}
        </div>
      </div>
    </div>
  );
} 