import type { Move } from '../types/game';

interface ErrorCardProps {
  move: Move;
  gameStartTime: string;
}

export function ErrorCard({ move, gameStartTime }: ErrorCardProps) {
  const getTimeDelta = () => {
    if (!move.timestamp) return '0s';
    const startTime = new Date(gameStartTime).getTime();
    const moveTime = new Date(move.timestamp).getTime();
    const deltaSeconds = Math.round((moveTime - startTime) / 1000);
    return `${deltaSeconds}s`;
  };

  const getWikipediaUrl = (pageTitle: string) => {
    return `https://en.wikipedia.org/wiki/${encodeURIComponent(pageTitle.replace(/ /g, '_'))}`;
  };

  return (
    <div className="page-card border-red-300 bg-red-50">
      {/* Header: Current page and time delta */}
      <div className="flex items-center justify-between">
        <a 
          href={getWikipediaUrl(move.from_page_title)}
          target="_blank"
          rel="noopener noreferrer"
          className="page-title"
        >
          {move.from_page_title}
        </a>
        <span className="time-delta">
          {getTimeDelta()}
        </span>
      </div>

      {/* Model reasoning if provided */}
      {move.model_response && (
        <div className="model-reasoning">
          {move.model_response}
        </div>
      )}

      {/* Error message in Wikipedia style */}
      {move.error && (
        <div className="mt-3 p-3 border border-red-400 bg-red-100">
          <div className="text-red-800 text-sm">
            <strong>Navigation failed:</strong> {move.error.message}
          </div>
          {move.tool_call_attempt?.arguments?.page && (
            <div className="text-red-600 text-sm mt-1">
              Attempted to navigate to: "{move.tool_call_attempt.arguments.page}"
            </div>
          )}
        </div>
      )}
    </div>
  );
} 