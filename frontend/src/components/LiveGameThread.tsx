import { useState, useEffect } from 'react';
import type { GameState, Move } from '../types/game';
import { PageTweet } from './PageTweet';
import { ErrorCard } from './ErrorCard';

interface LiveGameThreadProps {
  gameState: GameState;
  isLiveMode?: boolean;
  simulationSpeed?: number; // seconds between steps
}

interface SimulationState {
  currentMoveIndex: number;
  showingReasoning: boolean;
  typingText: string;
  isThinking: boolean;
}

export function LiveGameThread({ 
  gameState, 
  isLiveMode = false, 
  simulationSpeed = 3 
}: LiveGameThreadProps) {
  const [simulation, setSimulation] = useState<SimulationState>({
    currentMoveIndex: -1,
    showingReasoning: false,
    typingText: '',
    isThinking: false
  });

  const isGameWon = gameState.status === 'won';
  const visibleMoves = isLiveMode 
    ? gameState.moves.slice(0, simulation.currentMoveIndex + 1)
    : gameState.moves;

  // Reset simulation when gameState changes
  useEffect(() => {
    if (isLiveMode) {
      setSimulation({
        currentMoveIndex: -1,
        showingReasoning: false,
        typingText: '',
        isThinking: false
      });
    }
  }, [gameState, isLiveMode]);

  // Live simulation logic
  useEffect(() => {
    if (!isLiveMode || gameState.moves.length === 0) return;

    const timer = setTimeout(() => {
      setSimulation(prev => {
        const nextMoveIndex = prev.currentMoveIndex + 1;
        
        if (nextMoveIndex >= gameState.moves.length) {
          return prev; // Simulation complete
        }

        return {
          ...prev,
          currentMoveIndex: nextMoveIndex,
          isThinking: true,
          showingReasoning: false,
          typingText: ''
        };
      });
    }, simulationSpeed * 1000);

    return () => clearTimeout(timer);
  }, [simulation.currentMoveIndex, isLiveMode, simulationSpeed, gameState.moves.length]);

  // Typing animation for current move reasoning
  useEffect(() => {
    if (!isLiveMode || !simulation.isThinking) return;
    
    const currentMove = gameState.moves[simulation.currentMoveIndex];
    if (!currentMove?.model_response) {
      setSimulation(prev => ({ ...prev, isThinking: false, showingReasoning: true }));
      return;
    }

    const fullText = currentMove.model_response;
    let currentIndex = 0;

    const typeText = () => {
      if (currentIndex <= fullText.length) {
        setSimulation(prev => ({
          ...prev,
          typingText: fullText.slice(0, currentIndex),
          showingReasoning: currentIndex === fullText.length
        }));
        currentIndex++;
        setTimeout(typeText, 30); // Typing speed
      } else {
        setSimulation(prev => ({ 
          ...prev, 
          isThinking: false, 
          showingReasoning: true 
        }));
      }
    };

    // Start typing after a brief pause
    const startTyping = setTimeout(typeText, 800);
    return () => clearTimeout(startTyping);
  }, [simulation.currentMoveIndex, simulation.isThinking, isLiveMode, gameState.moves]);

  const getCurrentPageCard = () => {
    if (!isLiveMode) return null;
    
    const currentMove = gameState.moves[simulation.currentMoveIndex];
    if (!currentMove) return null;

    const timeDelta = currentMove.timestamp 
      ? Math.floor((new Date(currentMove.timestamp).getTime() - new Date(gameState.start_timestamp).getTime()) / 1000)
      : 0;

    return (
      <div className="page-card">
        <div className="flex items-center justify-between">
          <a 
            href={`https://en.wikipedia.org/wiki/${encodeURIComponent(currentMove.to_page_title?.replace(/ /g, '_') || '')}`}
            target="_blank"
            rel="noopener noreferrer"
            className="page-title"
          >
            {currentMove.to_page_title || currentMove.from_page_title}
          </a>
          <span className="time-delta">{timeDelta}s</span>
        </div>
        
        {simulation.isThinking && (
          <div className="mt-2 flex items-center space-x-2 text-gray-500">
            <div className="thinking-animation">
              <span className="thinking-dot">●</span>
              <span className="thinking-dot">●</span>
              <span className="thinking-dot">●</span>
            </div>
            <span className="text-sm">thinking...</span>
          </div>
        )}
        
        {simulation.typingText && (
          <div className="model-reasoning">
            {simulation.typingText}
            {simulation.isThinking && <span className="typing-cursor">|</span>}
          </div>
        )}
      </div>
    );
  };

  const getNextPagePreview = () => {
    if (!isLiveMode || !simulation.showingReasoning) return null;
    
    const nextMoveIndex = simulation.currentMoveIndex + 1;
    const nextMove = gameState.moves[nextMoveIndex];
    
    if (!nextMove) {
      // Show target if game is won
      if (isGameWon) return null;
      return null;
    }

    const timeDelta = nextMove.timestamp 
      ? Math.floor((new Date(nextMove.timestamp).getTime() - new Date(gameState.start_timestamp).getTime()) / 1000)
      : 0;

    return (
      <>
        <div className="flex flex-col items-center">
          <div className="thread-connector h-4"></div>
        </div>
        <div className="page-card border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between">
            <a 
              href={`https://en.wikipedia.org/wiki/${encodeURIComponent(nextMove.to_page_title?.replace(/ /g, '_') || '')}`}
              target="_blank"
              rel="noopener noreferrer"
              className="page-title text-gray-600"
            >
              {nextMove.to_page_title || nextMove.from_page_title}
            </a>
            <span className="time-delta text-gray-400">{timeDelta}s</span>
          </div>
        </div>
      </>
    );
  };

  return (
    <div className="max-w-2xl mx-auto py-4">
      {/* Starting page - always show */}
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

      {/* Completed moves */}
      {visibleMoves.map((move, index) => (
        <div key={`${move.step}-${move.from_page_title}`}>
          <div className="flex flex-col items-center">
            <div className="thread-connector h-4"></div>
          </div>

          {move.error ? (
            <ErrorCard move={move} gameStartTime={gameState.start_timestamp} />
          ) : (
            <PageTweet move={move} gameStartTime={gameState.start_timestamp} />
          )}
        </div>
      ))}

      {/* Current move being processed (live mode only) */}
      {isLiveMode && simulation.currentMoveIndex >= 0 && (
        <>
          {visibleMoves.length > 0 && (
            <div className="flex flex-col items-center">
              <div className="thread-connector h-4"></div>
            </div>
          )}
          {getCurrentPageCard()}
          {getNextPagePreview()}
        </>
      )}

      {/* Connection line to target if game is won */}
      {((isLiveMode && simulation.showingReasoning && isGameWon) || (!isLiveMode && isGameWon)) && visibleMoves.length > 0 && (
        <div className="flex flex-col items-center">
          <div className="thread-connector h-4"></div>
        </div>
      )}

      {/* Target page */}
      {((!isLiveMode) || (isLiveMode && (simulation.showingReasoning || isGameWon))) && (
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
      )}
    </div>
  );
} 