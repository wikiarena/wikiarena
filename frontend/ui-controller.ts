import { GameState, ConnectionStatus, RenderingMode } from './types.js';

// =============================================================================
// UI Controller - Handles all DOM updates and user interactions
// =============================================================================

export class UIController {
  private elements: Map<string, HTMLElement> = new Map();
  private onStepToMove?: (moveIndex: number) => void;

  constructor() {
    this.initializeElements();
    this.setupInitialState();
  }

  // =============================================================================
  // Element Management
  // =============================================================================

  private initializeElements(): void {
    const elementIds = [
      'connection-indicator',
      'connection-text',
      'start-game-btn',
      'game-id',
      'game-status',
      'start-page',
      'target-page',
      'current-page',
      'move-count',
      'optimal-distance',
      'optimal-paths-count',
      'moves-container',
      'loading-state',
      'graph-canvas',
      'error-display',
      'error-message',
      // Stepping controls
      'step-backward-btn',
      'step-forward-btn',
      'live-mode-btn',
      'step-info',
      'stepping-controls',
      // Progress bar
      'progress-bar-container',
      'progress-bar-fill'
    ];

    elementIds.forEach(id => {
      const element = document.getElementById(id);
      if (element) {
        this.elements.set(id, element);
      } else {
        console.warn(`⚠️ Element not found: ${id}`);
      }
    });

    console.log(`✅ UI Controller initialized with ${this.elements.size} elements`);
  }

  private setupInitialState(): void {
    this.updateConnectionStatus({
      connected: false,
      connecting: false,
      error: null,
      reconnectAttempts: 0
    });

    this.updateLoadingState('Click "Start New Game" to begin');
  }

  // =============================================================================
  // Connection Status Updates
  // =============================================================================

  updateConnectionStatus(status: ConnectionStatus): void {
    // Update connection indicator
    const indicator = this.elements.get('connection-indicator');
    if (indicator) {
      indicator.className = `status-indicator ${status.connected ? 'connected' : ''}`;
    }

    // Update connection text
    const text = this.elements.get('connection-text');
    if (text) {
      if (status.connecting) {
        text.textContent = 'Starting game...';
      } else if (status.connected) {
        text.textContent = 'Game connected';
      } else if (status.error) {
        text.textContent = 'Connection error';
      } else {
        text.textContent = 'Ready to start';
      }
    }

    // Start Game button is always enabled (no need for separate connect step)
    const startGameBtn = this.elements.get('start-game-btn') as HTMLButtonElement;
    if (startGameBtn) {
      // Only disable during connection attempts
      startGameBtn.disabled = status.connecting;
    }
  }

  // =============================================================================
  // Game State Updates
  // =============================================================================

  updateGameState(state: GameState, steppingInfo?: {
    currentMoveIndex: number;
    viewingMoveIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    console.log('🖥️ UI: Updating with new game state');

    // Update game info panel
    this.updateGameInfo(state);

    // Update page history with stepping info for proper visual indicators
    this.updatePageHistory(state, steppingInfo);

    // Update progress bar
    this.updateProgressBar(state);

    // Update graph visibility
    this.updateGraphVisibility(state);

    // Update stepping controls if stepping info provided
    if (steppingInfo) {
      this.updateSteppingControls(
        steppingInfo.currentMoveIndex,
        steppingInfo.viewingMoveIndex,
        steppingInfo.renderingMode,
        steppingInfo.canStepForward,
        steppingInfo.canStepBackward
      );
    }
  }

  private updateGameInfo(state: GameState): void {
    const updates = [
      ['game-id', state.gameId || '-'],
      ['game-status', this.formatGameStatus(state)],
      ['start-page', state.startPage || '-'],
      ['target-page', state.targetPage || '-'],
      ['current-page', state.currentPage || '-'],
      ['move-count', state.totalMoves.toString()],
      ['optimal-distance', state.currentDistance?.toString() || '-'],
      ['optimal-paths-count', state.optimalPaths.length > 0 ? state.optimalPaths.length.toString() : '-']
    ];

    updates.forEach(([elementId, value]) => {
      const element = this.elements.get(elementId);
      if (element) {
        element.textContent = value;
      }
    });
  }

  private formatGameStatus(state: GameState): string {
    switch (state.status) {
      case 'not_started':
        return 'Not Started';
      case 'in_progress':
        return 'In Progress';
      case 'finished':
        return state.success ? 'Completed!' : 'Failed';
      default:
        return 'Unknown';
    }
  }

  private updatePageHistory(state: GameState, steppingInfo?: {
    currentMoveIndex: number;
    viewingMoveIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    const container = this.elements.get('moves-container');
    if (!container) return;

    // Clear existing content
    container.innerHTML = '';

    // Get viewing info for proper visual indicators
    const viewingMoveIndex = steppingInfo?.viewingMoveIndex ?? -1;
    const currentMoveIndex = steppingInfo?.currentMoveIndex ?? -1;

    // Build page history - ALL pages in the game
    const pageHistory: Array<{
      title: string, 
      type: 'start' | 'target' | 'visited' | 'current' | 'future', 
      step?: number,
      moveIndex: number,
      isViewing: boolean
    }> = [];
    
    // Add start page (move 0 in our new indexing)
    if (state.startPage) {
      const isCurrentPage = state.currentPage === state.startPage;
      const isTargetPage = state.startPage === state.targetPage;
      const isViewing = viewingMoveIndex === 0;
      
      let pageType: 'start' | 'target' | 'visited' | 'current' | 'future';
      if (isTargetPage) {
        pageType = 'target';
      } else if (isCurrentPage && isViewing) {
        pageType = 'current';
      } else {
        pageType = 'start';
      }

      pageHistory.push({
        title: state.startPage,
        type: pageType,
        step: 0,
        moveIndex: 0,
        isViewing
      });
    }

    // Add ALL pages from moves (not just up to viewing index)
    state.moves.forEach((move, index) => {
      const moveIndex = index + 1; // moves[0] = moveIndex 1, moves[1] = moveIndex 2, etc.
      const isCurrentPage = move.to_page_title === state.currentPage;
      const isTargetPage = move.to_page_title === state.targetPage;
      const isViewing = viewingMoveIndex === moveIndex;
      const isFuture = moveIndex > currentMoveIndex; // This move hasn't happened yet
      
      let pageType: 'start' | 'target' | 'visited' | 'current' | 'future';
      if (isTargetPage) {
        pageType = 'target';
      } else if (isCurrentPage && isViewing) {
        pageType = 'current';
      } else if (isFuture) {
        pageType = 'future';
      } else {
        pageType = 'visited';
      }

      pageHistory.push({
        title: move.to_page_title,
        type: pageType,
        step: moveIndex,
        moveIndex: moveIndex,
        isViewing
      });
    });

    // Create page elements
    pageHistory.forEach(page => {
      const pageElement = this.createInteractivePageElement(page);
      container.appendChild(pageElement);
    });

    if (pageHistory.length === 0) {
      container.innerHTML = '<div style="color: #64748b; font-style: italic; padding: 1rem; text-align: center;">No pages visited yet</div>';
    }
  }

  private updateProgressBar(state: any): void {
    const progressContainer = this.elements.get('progress-bar-container');
    const progressFill = this.elements.get('progress-bar-fill');

    if (!progressContainer || !progressFill) return;

    // Show/hide progress bar based on game state
    if (state.status === 'not_started' || !state.initialOptimalDistance) {
      progressContainer.style.display = 'none';
      return;
    }

    progressContainer.style.display = 'block';

    const initialDistance = state.initialOptimalDistance;
    const currentDistance = state.currentDistance || initialDistance;

    // Calculate progress with baseline: start at 2%, 100% at target
    const baselinePercent = 1; // Start with 1% visible progress (just enough to see)
    const progressRatio = (initialDistance - currentDistance) / initialDistance;
    const progressPercent = baselinePercent + (progressRatio * (100 - baselinePercent));

    // Remove existing color classes
    progressFill.classList.remove('negative');
    
    // Determine behavior based on progress
    if (progressRatio < 0) {
      // Negative progress - extend upward beyond container with red color
      progressFill.classList.add('negative');
      
      // Calculate how much to extend above the container
      const negativePercent = Math.abs(progressRatio) * 100;
      const totalHeight = baselinePercent + negativePercent;
      const negativeTop = -negativePercent; // Push the bar upward
      
      progressFill.style.height = `${totalHeight}%`;
      progressFill.style.top = `${negativeTop}%`;
      
    } else {
      // Positive or zero progress - normal green behavior from baseline
      progressFill.style.height = `${Math.max(baselinePercent, progressPercent)}%`;
      progressFill.style.top = '0%';
    }

    console.log(`📊 Vertical Progress: ${currentDistance}/${initialDistance} (${(progressRatio * 100).toFixed(1)}%) - Display: ${progressPercent.toFixed(1)}%`);
  }

  private createInteractivePageElement(page: {
    title: string, 
    type: 'start' | 'target' | 'visited' | 'current' | 'future', 
    step?: number,
    moveIndex: number,
    isViewing: boolean
  }): HTMLElement {
    const pageElement = document.createElement('div');
    
    // Base classes
    let classes = `page-item ${page.type} clickable`;
    
    // Add viewing indicator if this is the currently viewed state
    if (page.isViewing) {
      classes += ' viewing';
    }
    
    pageElement.className = classes;
    
    // Create the page number/label
    let pageLabel = '';
    if (page.type === 'start') {
      pageLabel = 'Start (Page 0)';
    } else if (page.type === 'target') {
      pageLabel = `Target (Page ${page.step})`;
    } else if (page.type === 'current') {
      pageLabel = `Page ${page.step} (Current)`;
    } else if (page.type === 'future') {
      pageLabel = `Page ${page.step} (Future)`;
    } else {
      pageLabel = `Page ${page.step}`;
    }
    
    // Create Wikipedia URL for reference (shown on right-click or ctrl+click)
    const wikipediaUrl = `https://en.wikipedia.org/wiki/${encodeURIComponent(page.title.replace(/ /g, '_'))}`;
    
    pageElement.innerHTML = `
      <div class="page-content">
        <div class="page-number">${pageLabel}</div>
        <div class="page-title">${page.title}</div>
      </div>
    `;

    // Add click handler for stepping to this move
    pageElement.addEventListener('click', (event) => {
      event.preventDefault();
      this.handlePageHistoryClick(page.moveIndex);
    });

    // Add right-click or ctrl+click to open Wikipedia page
    pageElement.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      window.open(wikipediaUrl, '_blank', 'noopener,noreferrer');
    });

    pageElement.addEventListener('click', (event) => {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        window.open(wikipediaUrl, '_blank', 'noopener,noreferrer');
      }
    });

    // Store move index for easy access
    pageElement.dataset.moveIndex = page.moveIndex.toString();
    
    return pageElement;
  }

  private handlePageHistoryClick(moveIndex: number): void {
    // Emit event to main app to handle the step-to-move action
    if (this.onStepToMove) {
      this.onStepToMove(moveIndex);
    }
  }

  private updateGraphVisibility(state: GameState): void {
    const loadingState = this.elements.get('loading-state');
    const graphCanvas = this.elements.get('graph-canvas');

    if (!loadingState || !graphCanvas) return;

    if (state.status === 'not_started') {
      // Show loading state
      loadingState.style.display = 'flex';
      loadingState.textContent = 'Click "Start New Game" to begin';
      graphCanvas.style.display = 'none';
    } else if (state.status === 'in_progress' || state.status === 'finished') {
      // Show graph
      loadingState.style.display = 'none';
      graphCanvas.style.display = 'block';
    }
  }

  // =============================================================================
  // Loading States
  // =============================================================================

  updateLoadingState(message: string): void {
    const loadingState = this.elements.get('loading-state');
    if (loadingState) {
      loadingState.textContent = message;
    }
  }

  showGameStarting(): void {
    const loadingState = this.elements.get('loading-state');
    const graphCanvas = this.elements.get('graph-canvas');

    if (loadingState && graphCanvas) {
      loadingState.style.display = 'flex';
      loadingState.textContent = 'Starting new game...';
      graphCanvas.style.display = 'none';
    }
  }

  // =============================================================================
  // Error Handling
  // =============================================================================

  showError(message: string, duration: number = 5000): void {
    const errorDisplay = this.elements.get('error-display');
    const errorMessage = this.elements.get('error-message');

    if (errorDisplay && errorMessage) {
      errorMessage.textContent = message;
      errorDisplay.style.display = 'block';

      // Auto-hide after duration
      setTimeout(() => {
        this.hideError();
      }, duration);
    }
  }

  hideError(): void {
    const errorDisplay = this.elements.get('error-display');
    if (errorDisplay) {
      errorDisplay.style.display = 'none';
    }
  }

  // =============================================================================
  // Button State Management
  // =============================================================================

  setButtonLoading(buttonId: string, loading: boolean, loadingText?: string): void {
    const button = this.elements.get(buttonId) as HTMLButtonElement;
    if (!button) return;

    if (loading) {
      button.disabled = true;
      if (loadingText) {
        button.dataset.originalText = button.textContent || '';
        button.textContent = loadingText;
      }
    } else {
      button.disabled = false;
      if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
        delete button.dataset.originalText;
      }
    }
  }

  // =============================================================================
  // Event Listener Setup
  // =============================================================================

  setupEventListeners(handlers: {
    onStartGame: () => void;
    onStepBackward?: () => void;
    onStepForward?: () => void;
    onEnterLiveMode?: () => void;
    onStepToMove?: (moveIndex: number) => void;
  }): void {
    // Store the step-to-move handler
    this.onStepToMove = handlers.onStepToMove;
    
    // Start game button
    const startGameBtn = this.elements.get('start-game-btn');
    if (startGameBtn) {
      startGameBtn.addEventListener('click', handlers.onStartGame);
    }

    // Stepping controls
    const stepBackwardBtn = this.elements.get('step-backward-btn');
    if (stepBackwardBtn && handlers.onStepBackward) {
      stepBackwardBtn.addEventListener('click', handlers.onStepBackward);
    }

    const stepForwardBtn = this.elements.get('step-forward-btn');
    if (stepForwardBtn && handlers.onStepForward) {
      stepForwardBtn.addEventListener('click', handlers.onStepForward);
    }

    const liveModeBtn = this.elements.get('live-mode-btn');
    if (liveModeBtn && handlers.onEnterLiveMode) {
      liveModeBtn.addEventListener('click', handlers.onEnterLiveMode);
    }

    console.log('✅ UI event listeners setup');
  }

  // =============================================================================
  // Stepping Controls
  // =============================================================================

  updateSteppingControls(currentMoveIndex: number, viewingMoveIndex: number, renderingMode: 'live' | 'stepping', canStepForward: boolean, canStepBackward: boolean): void {
    // Update step info
    const stepInfo = this.elements.get('step-info');
    if (stepInfo) {
      if (renderingMode === 'live') {
        stepInfo.textContent = `Live Mode (Page ${currentMoveIndex})`;
      } else {
        stepInfo.textContent = `Viewing Page ${viewingMoveIndex} of ${currentMoveIndex}`;
      }
    }

    // Update button states
    const stepBackwardBtn = this.elements.get('step-backward-btn') as HTMLButtonElement;
    if (stepBackwardBtn) {
      stepBackwardBtn.disabled = !canStepBackward;
    }

    const stepForwardBtn = this.elements.get('step-forward-btn') as HTMLButtonElement;
    if (stepForwardBtn) {
      stepForwardBtn.disabled = !canStepForward;
    }

    // Update live mode button
    const liveModeBtn = this.elements.get('live-mode-btn') as HTMLButtonElement;
    if (liveModeBtn) {
      liveModeBtn.textContent = renderingMode === 'live' ? '🔴 Live' : '🔴 Go Live';
      liveModeBtn.disabled = renderingMode === 'live';
    }

    // Show/hide stepping controls based on game state
    const steppingControls = this.elements.get('stepping-controls');
    if (steppingControls) {
      steppingControls.style.display = currentMoveIndex >= 0 ? 'flex' : 'none';
    }
  }

  showSteppingMode(): void {
    const steppingControls = this.elements.get('stepping-controls');
    if (steppingControls) {
      steppingControls.style.display = 'flex';
    }
  }

  hideSteppingMode(): void {
    const steppingControls = this.elements.get('stepping-controls');
    if (steppingControls) {
      steppingControls.style.display = 'none';
    }
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  resetGameUI(): void {
    // Reset to initial state
    this.updateGameState({
      gameId: null,
      status: 'not_started',
      startPage: null,
      targetPage: null,
      currentPage: null,
      moves: [],
      optimalPaths: [],
      currentDistance: null,
      totalMoves: 0,
      success: null
    });
  }

  // For debugging
  debugElements(): void {
    console.log('🐛 UI Elements:', Array.from(this.elements.keys()));
  }
} 