import type { Move } from '../types/game';

interface PageTweetProps {
  move: Move;
  gameStartTime: string;
}

export function PageTweet({ move, gameStartTime }: PageTweetProps) {
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
    <div className="page-card">
      {/* Header: Page title and time delta (like Twitter) */}
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

      {/* Model reasoning (like tweet body) */}
      {move.model_response && (
        <div className="model-reasoning">
          {move.model_response}
        </div>
      )}
    </div>
  );
} 