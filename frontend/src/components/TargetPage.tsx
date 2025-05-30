interface TargetPageProps {
  targetPage: string;
  isReached: boolean;
}

export function TargetPage({ targetPage, isReached }: TargetPageProps) {
  const getWikipediaUrl = (pageTitle: string) => {
    return `https://en.wikipedia.org/wiki/${encodeURIComponent(pageTitle.replace(/ /g, '_'))}`;
  };

  return (
    <div className="target-fixed">
      <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Target</div>
      <div className="flex items-center justify-between">
        <a 
          href={getWikipediaUrl(targetPage)}
          target="_blank"
          rel="noopener noreferrer"
          className={`page-title ${isReached ? 'text-green-600' : ''}`}
        >
          {targetPage}
        </a>
        {isReached && (
          <span className="text-green-600 text-sm font-medium">
            Reached!
          </span>
        )}
      </div>
    </div>
  );
} 