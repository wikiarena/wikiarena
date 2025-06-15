import { GameState, ConnectionStatus } from './types.js';

// =============================================================================
// UI Controller - Handles all DOM updates and user interactions
// =============================================================================

export class UIController {
  private elements: Map<string, HTMLElement> = new Map();

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
      'error-message'
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

  updateGameState(state: GameState): void {
    console.log('🖥️ UI: Updating with new game state');

    // Update game info panel
    this.updateGameInfo(state);

    // Update page history
    this.updatePageHistory(state);

    // Update graph visibility
    this.updateGraphVisibility(state);
  }

  private updateGameInfo(state: GameState): void {
    const updates = [
      ['game-id', state.gameId || '-'],
      ['game-status', this.formatGameStatus(state)],
      ['start-page', state.startPage || '-'],
      ['target-page', state.targetPage || '-'],
      ['current-page', state.currentPage || '-'],
      ['move-count', state.totalMoves.toString()],
      ['optimal-distance', state.currentOptimalDistance?.toString() || '-'],
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

  private updatePageHistory(state: GameState): void {
    const container = this.elements.get('moves-container');
    if (!container) return;

    // Clear existing content
    container.innerHTML = '';

    // Build page history - start with start page, then all move destinations
    const pageHistory: Array<{title: string, type: 'start' | 'target' | 'visited' | 'current', step?: number}> = [];
    
    // Add start page
    if (state.startPage) {
      pageHistory.push({
        title: state.startPage,
        type: state.currentPage === state.startPage ? 'current' : 'start'
      });
    }

    // Add pages from moves
    state.moves.forEach((move, index) => {
      const isCurrentPage = move.to_page_title === state.currentPage;
      const isTargetPage = move.to_page_title === state.targetPage;
      
      let pageType: 'start' | 'target' | 'visited' | 'current';
      if (isCurrentPage) {
        pageType = 'current';
      } else if (isTargetPage) {
        pageType = 'target';
      } else {
        pageType = 'visited';
      }

      pageHistory.push({
        title: move.to_page_title,
        type: pageType,
        step: index + 1
      });
    });

    // Create page elements
    pageHistory.forEach(page => {
      const pageElement = this.createPageElement(page);
      container.appendChild(pageElement);
    });

    if (pageHistory.length === 0) {
      container.innerHTML = '<div style="color: #64748b; font-style: italic; padding: 1rem; text-align: center;">No pages visited yet</div>';
    }
  }

  private createPageElement(page: {title: string, type: 'start' | 'target' | 'visited' | 'current', step?: number}): HTMLElement {
    const pageElement = document.createElement('div');
    pageElement.className = `page-item ${page.type}`;
    
    // Create Wikipedia URL - encode the title properly for Wikipedia URLs
    const wikipediaUrl = `https://en.wikipedia.org/wiki/${encodeURIComponent(page.title.replace(/ /g, '_'))}`;
    
    // Create the page number/label
    let pageLabel = '';
    if (page.type === 'start') {
      pageLabel = 'Start';
    } else if (page.type === 'target') {
      pageLabel = 'Target';
    } else if (page.type === 'current') {
      pageLabel = `Step ${page.step} (Current)`;
    } else {
      pageLabel = `Step ${page.step}`;
    }
    
    pageElement.innerHTML = `
      <a href="${wikipediaUrl}" target="_blank" rel="noopener noreferrer" class="page-link">
        <div class="page-number">${pageLabel}</div>
        <div class="page-title">${page.title}</div>
      </a>
    `;

    return pageElement;
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
  }): void {
    // Start game button
    const startGameBtn = this.elements.get('start-game-btn');
    if (startGameBtn) {
      startGameBtn.addEventListener('click', handlers.onStartGame);
    }

    console.log('✅ UI event listeners setup');
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
      currentOptimalDistance: null,
      totalMoves: 0,
      success: null
    });
  }

  // For debugging
  debugElements(): void {
    console.log('🐛 UI Elements:', Array.from(this.elements.keys()));
  }
} 