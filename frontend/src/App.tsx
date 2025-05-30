import { useState } from 'react'
import { GameThread } from './components/GameThread'
import { LiveGameThread } from './components/LiveGameThread'
import { RealTimeGameThread } from './components/RealTimeGameThread'
import { mockGameData, mockCompletedGame, mockFailedGame } from './mocks/gameData'

function App() {
  const [selectedDemo, setSelectedDemo] = useState<'in-progress' | 'completed' | 'failed'>('in-progress')
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [isRealTimeMode, setIsRealTimeMode] = useState(false)
  const [simulationSpeed, setSimulationSpeed] = useState(2)
  
  const getCurrentGameData = () => {
    switch (selectedDemo) {
      case 'completed':
        return mockCompletedGame
      case 'failed':
        return mockFailedGame
      default:
        return mockGameData
    }
  }

  const gameData = getCurrentGameData()

  const handleGameStart = (gameId: string) => {
    console.log('🚀 Real-time game started:', gameId)
  }

  const handleGameEnd = (finalState: any) => {
    console.log('🏁 Real-time game ended:', finalState.status)
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Demo controls */}
      <div className="fixed top-4 left-4 z-10 bg-white border border-gray-300 p-3 rounded shadow-lg">
        <div className="space-y-3">
          {/* Mode selector */}
          <div>
            <div className="text-xs text-gray-600 mb-1 font-medium">Mode:</div>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => {
                  setIsRealTimeMode(false);
                  setIsLiveMode(false);
                }}
                className={`px-3 py-1 text-xs rounded ${
                  !isRealTimeMode && !isLiveMode
                    ? 'bg-gray-200 border-gray-400 font-medium' 
                    : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                }`}
              >
                📊 Static Demo
              </button>
              <button
                onClick={() => {
                  setIsRealTimeMode(false);
                  setIsLiveMode(true);
                }}
                className={`px-3 py-1 text-xs rounded ${
                  !isRealTimeMode && isLiveMode
                    ? 'bg-purple-200 border-purple-400 font-medium' 
                    : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                }`}
              >
                ✨ Live Simulation
              </button>
              <button
                onClick={() => {
                  setIsRealTimeMode(true);
                  setIsLiveMode(false);
                }}
                className={`px-3 py-1 text-xs rounded ${
                  isRealTimeMode
                    ? 'bg-green-200 border-green-400 font-medium' 
                    : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                }`}
              >
                🚀 Real-Time API
              </button>
            </div>
          </div>
          
          {/* Demo selector - only for static/simulation modes */}
          {!isRealTimeMode && (
            <div>
              <div className="text-xs text-gray-600 mb-1 font-medium">Demo Data:</div>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedDemo('in-progress')}
                  className={`px-2 py-1 text-xs rounded ${
                    selectedDemo === 'in-progress' 
                      ? 'bg-blue-200 border-blue-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  In Progress
                </button>
                <button
                  onClick={() => setSelectedDemo('completed')}
                  className={`px-2 py-1 text-xs rounded ${
                    selectedDemo === 'completed' 
                      ? 'bg-green-200 border-green-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  Completed
                </button>
                <button
                  onClick={() => setSelectedDemo('failed')}
                  className={`px-2 py-1 text-xs rounded ${
                    selectedDemo === 'failed' 
                      ? 'bg-red-200 border-red-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  Failed
                </button>
              </div>
            </div>
          )}
          
          {/* Speed control for live simulation mode */}
          {isLiveMode && !isRealTimeMode && (
            <div>
              <div className="text-xs text-gray-600 mb-1 font-medium">Speed:</div>
              <div className="flex gap-1">
                <button
                  onClick={() => setSimulationSpeed(1)}
                  className={`px-2 py-1 text-xs rounded ${
                    simulationSpeed === 1 
                      ? 'bg-yellow-200 border-yellow-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  Fast
                </button>
                <button
                  onClick={() => setSimulationSpeed(2)}
                  className={`px-2 py-1 text-xs rounded ${
                    simulationSpeed === 2 
                      ? 'bg-yellow-200 border-yellow-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  Normal
                </button>
                <button
                  onClick={() => setSimulationSpeed(4)}
                  className={`px-2 py-1 text-xs rounded ${
                    simulationSpeed === 4 
                      ? 'bg-yellow-200 border-yellow-400 font-medium' 
                      : 'bg-gray-100 border-gray-300 hover:bg-gray-150'
                  }`}
                >
                  Slow
                </button>
              </div>
            </div>
          )}

          {/* Real-time mode info */}
          {isRealTimeMode && (
            <div className="text-xs text-gray-600 bg-green-50 p-2 rounded border border-green-200">
              <div className="font-medium text-green-800 mb-1">🌐 Connected to Live API</div>
              <div>Uses WebSocket for real-time updates from autonomous games</div>
            </div>
          )}
        </div>
      </div>

      {/* Game thread */}
      {isRealTimeMode ? (
        <RealTimeGameThread 
          onGameStart={handleGameStart}
          onGameEnd={handleGameEnd}
        />
      ) : isLiveMode ? (
        <LiveGameThread 
          gameState={gameData} 
          isLiveMode={true}
          simulationSpeed={simulationSpeed}
        />
      ) : (
        <GameThread gameState={gameData} />
      )}
    </div>
  )
}

export default App
