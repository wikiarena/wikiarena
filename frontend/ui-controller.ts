import { Task, GameSequence, ConnectionStatus, RenderingMode } from './types.js';
import { playerColorService } from './player-color-service.js';

// =============================================================================
// UI Controller - Handles all DOM updates and user interactions
// =============================================================================

export class UIController {
  private elements: Map<string, HTMLElement> = new Map();
  private onStepToMove?: (moveIndex: number) => void;
  private onEnterLiveMode?: () => void;
  private selectedGameId: string | null = null; // For game switching in info panel

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
      'task-info',
      'start-page',
      'target-page',
      'shortest-path-length',
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
      // Progress bars container
      'progress-bars-container',
      // Page step slider
      'page-step-slider-container',
      'page-step-slider'
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
  // Task State Updates
  // =============================================================================

  updateTask(task: Task, steppingInfo?: {
    currentPageIndex: number;
    viewingPageIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    console.log('🖥️ UI: Updating with new task state');

    // Update task info panel
    this.updateTaskInfo(task);

    // Update progress bars for all games (pass stepping info)
    this.updateProgressBars(task, steppingInfo);

    // Update game-specific info panel (for selected game)
    this.updateGameInfoPanel(task);

    // Update page history for selected game with stepping info
    this.updatePageHistory(task, steppingInfo);

    // Update graph visibility
    this.updateGraphVisibility(task);

    // Update stepping controls if stepping info provided
    if (steppingInfo) {
      this.updateSteppingControls(
        steppingInfo.currentPageIndex,
        steppingInfo.viewingPageIndex,
        steppingInfo.renderingMode,
        steppingInfo.canStepForward,
        steppingInfo.canStepBackward
      );
    }

    // Update page step slider
    this.updatePageStepSlider(task, steppingInfo);
  }

  private updateTaskInfo(task: Task): void {
    const updates = [
      ['start-page', task.startPage || '-'],
      ['target-page', task.targetPage || '-'],
      ['shortest-path-length', task.shortestPathLength?.toString() || '-']
    ];

    updates.forEach(([elementId, value]) => {
      const element = this.elements.get(elementId);
      if (element) {
        element.textContent = value;
      }
    });
  }

  private updateProgressBars(task: Task, steppingInfo?: {
    currentPageIndex: number;
    viewingPageIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    const container = this.elements.get('progress-bars-container');
    if (!container) return;

    if (task.games.size === 0 || !task.shortestPathLength) {
      container.style.display = 'none';
      return;
    }

    container.style.display = 'flex';

    // Get existing progress bars
    const existingBars = new Map<string, HTMLElement>();
    Array.from(container.children).forEach(bar => {
      const gameId = bar.getAttribute('data-game-id');
      if (gameId) {
        existingBars.set(gameId, bar as HTMLElement);
      }
    });

    // Update or create progress bars for each game
    task.games.forEach((gameSequence, gameId) => {
      const existingBar = existingBars.get(gameId);
      
      if (existingBar) {
        // Update existing progress bar (this enables smooth transitions)
        this.updateHorizontalProgressBar(
          existingBar,
          gameSequence, 
          task.shortestPathLength!, 
          gameId,
          steppingInfo
        );
        existingBars.delete(gameId); // Mark as processed
      } else {
        // Create new progress bar
        const playerColor = playerColorService.getColorForGame(gameId);
        const progressBar = this.createHorizontalProgressBar(
          gameSequence, 
          task.shortestPathLength!, 
          playerColor,
          gameId,
          steppingInfo
        );
        container.appendChild(progressBar);
      }
    });

    // Remove progress bars for games that no longer exist
    existingBars.forEach(bar => {
      bar.remove();
    });
  }

  // Utility function to find most recent page state with valid distanceToTarget
  private findMostRecentValidDistance(gameSequence: GameSequence, maxIndex: number): number | undefined {
    // Iterate backwards from maxIndex to find the most recent valid distance
    for (let i = maxIndex; i >= 0; i--) {
      const pageState = gameSequence.pageStates[i];
      if (pageState && pageState.distanceToTarget !== undefined) {
        console.log(`📏 Using distance from page ${i}: ${pageState.pageTitle} (distance: ${pageState.distanceToTarget}) for game ${gameSequence.gameId}`);
        return pageState.distanceToTarget;
      }
    }
    
    console.log(`⚠️ No valid distance found for game ${gameSequence.gameId} up to index ${maxIndex}`);
    return undefined;
  }

  private createHorizontalProgressBar(
    gameSequence: GameSequence, 
    initialDistance: number, 
    color: string, 
    gameId: string,
    steppingInfo?: {
      currentPageIndex: number;
      viewingPageIndex: number;
      renderingMode: RenderingMode;
      canStepForward: boolean;
      canStepBackward: boolean;
    }
  ): HTMLElement {
    const progressBarContainer = document.createElement('div');
    progressBarContainer.className = 'horizontal-progress-bar';
    progressBarContainer.setAttribute('data-game-id', gameId);

    // Determine which page state to use based on stepping mode
    let targetPageStateIndex: number;
    let currentDistance: number | undefined;

    if (steppingInfo && steppingInfo.renderingMode === 'stepping') {
      // In stepping mode, use viewing index but limit to what's available for this game
      targetPageStateIndex = Math.min(steppingInfo.viewingPageIndex, gameSequence.pageStates.length - 1);
    } else {
      // In live mode, use the most recent page state
      targetPageStateIndex = gameSequence.pageStates.length - 1;
    }

    // Get distance with fallback logic
    if (targetPageStateIndex >= 0) {
      const targetPageState = gameSequence.pageStates[targetPageStateIndex];
      currentDistance = targetPageState?.distanceToTarget;
      
      // If current distance is undefined, find the most recent valid one
      if (currentDistance === undefined) {
        currentDistance = this.findMostRecentValidDistance(gameSequence, targetPageStateIndex);
      }
    }

    // Fallback to initial distance if still no valid distance found
    if (currentDistance === undefined) {
      currentDistance = initialDistance;
    }

    // Calculate progress with baseline: start at 2%, 100% at target
    const baselinePercent = 1; // Start with 2% visible progress
    const progressRatio = (initialDistance - currentDistance) / initialDistance;
    const progressPercent = baselinePercent + (progressRatio * (100 - baselinePercent));

    // Create progress fill
    const progressFill = document.createElement('div');
    progressFill.className = 'horizontal-progress-fill';
    
    // CSS transitions are handled in the stylesheet, no need to set inline
    
    // Handle negative progress (going backwards/leftward from start)
    if (progressRatio < 0) {
      progressFill.classList.add('negative');
      
      // Calculate how far left to extend for negative progress
      const negativePercent = Math.abs(progressRatio) * 100;
      const negativeLeft = -negativePercent; // Push the bar leftward beyond container
      
      progressFill.style.left = `${negativeLeft}%`;
      progressFill.style.width = `${baselinePercent + negativePercent}%`;
      
      // Position robot emoji at the leftward edge (negative position)
      var indicatorPosition = negativeLeft;
    } else {
      // Normal positive progress
      progressFill.style.left = '0%';
      progressFill.style.width = `${Math.max(baselinePercent, progressPercent)}%`;
      
      // Position indicator at the end of the progress fill
      var indicatorPosition = Math.max(baselinePercent, progressPercent);
    }
    
    progressFill.style.background = color;

    // Create player indicator (provider icon at current progress)
    const playerIndicator = document.createElement('div');
    playerIndicator.className = 'horizontal-progress-indicator';
    
    // Create and set the provider icon
    const iconImg = document.createElement('img');
    iconImg.src = playerColorService.getIconForGame(gameId);
    iconImg.alt = `${playerColorService.getDisplayName(gameId)} icon`;
    iconImg.style.width = '20px';
    iconImg.style.height = '20px';
    iconImg.style.display = 'block';
    
    playerIndicator.appendChild(iconImg);
    
    // Add smooth transition for icon position
    playerIndicator.style.transition = 'left 0.8s ease';
    playerIndicator.style.left = `${indicatorPosition}%`;

    // Create trophy at the end
    const trophy = document.createElement('div');
    trophy.className = 'horizontal-progress-target';
    trophy.textContent = '🏆';

    // // Create status indicator (small dot showing game state)
    // const statusIndicator = document.createElement('div');
    // statusIndicator.className = 'horizontal-progress-status';
    // statusIndicator.style.backgroundColor = gameSequence.status === 'in_progress' ? '#10b981' : 
    //                                        gameSequence.status === 'finished' ? '#f59e0b' : '#64748b';

    progressBarContainer.appendChild(progressFill);
    progressBarContainer.appendChild(playerIndicator);
    progressBarContainer.appendChild(trophy);
    // progressBarContainer.appendChild(statusIndicator);

    // Make progress bar clickable to select this game
    progressBarContainer.style.cursor = 'pointer';
    progressBarContainer.addEventListener('click', () => {
      this.selectGame(gameId);
    });

    return progressBarContainer;
  }

  private updateHorizontalProgressBar(
    progressBarContainer: HTMLElement,
    gameSequence: GameSequence, 
    initialDistance: number, 
    gameId: string,
    steppingInfo?: {
      currentPageIndex: number;
      viewingPageIndex: number;
      renderingMode: RenderingMode;
      canStepForward: boolean;
      canStepBackward: boolean;
    }
  ): void {
    // Find existing elements within the progress bar
    const progressFill = progressBarContainer.querySelector('.horizontal-progress-fill') as HTMLElement;
    const playerIndicator = progressBarContainer.querySelector('.horizontal-progress-indicator') as HTMLElement;
    
    if (!progressFill || !playerIndicator) {
      console.warn('Could not find progress bar elements to update');
      return;
    }

    // Determine which page state to use based on stepping mode (same logic as create)
    let targetPageStateIndex: number;
    let currentDistance: number | undefined;

    if (steppingInfo && steppingInfo.renderingMode === 'stepping') {
      targetPageStateIndex = Math.min(steppingInfo.viewingPageIndex, gameSequence.pageStates.length - 1);
    } else {
      targetPageStateIndex = gameSequence.pageStates.length - 1;
    }

    // Get distance with fallback logic
    if (targetPageStateIndex >= 0) {
      const targetPageState = gameSequence.pageStates[targetPageStateIndex];
      currentDistance = targetPageState?.distanceToTarget;
      
      if (currentDistance === undefined) {
        currentDistance = this.findMostRecentValidDistance(gameSequence, targetPageStateIndex);
      }
    }

    if (currentDistance === undefined) {
      currentDistance = initialDistance;
    }

    // Calculate progress (same logic as create)
    const baselinePercent = 1;
    const progressRatio = (initialDistance - currentDistance) / initialDistance;
    const progressPercent = baselinePercent + (progressRatio * (100 - baselinePercent));

    // Get player color
    const color = playerColorService.getColorForGame(gameId);

    // Update progress fill with smooth transition
    if (progressRatio < 0) {
      progressFill.classList.add('negative');
      
      const negativePercent = Math.abs(progressRatio) * 100;
      const negativeLeft = -negativePercent;
      
      progressFill.style.left = `${negativeLeft}%`;
      progressFill.style.width = `${baselinePercent + negativePercent}%`;
      
      var indicatorPosition = negativeLeft;
    } else {
      progressFill.classList.remove('negative');
      progressFill.style.left = '0%';
      progressFill.style.width = `${Math.max(baselinePercent, progressPercent)}%`;
      
      var indicatorPosition = Math.max(baselinePercent, progressPercent);
    }
    
    progressFill.style.background = color;

    // Update player indicator position with smooth transition
    playerIndicator.style.left = `${indicatorPosition}%`;
  }

  private selectGame(gameId: string): void {
    this.selectedGameId = gameId;
    console.log(`🎮 Selected game: ${gameId}`);
    // Trigger re-render of game-specific panels
    // This will be called by the main app when it detects the selection change
  }

  getSelectedGameId(): string | null {
    return this.selectedGameId;
  }

  private updateGameInfoPanel(task: Task): void {
    // Select the first game if none is selected
    if (!this.selectedGameId && task.games.size > 0) {
      this.selectedGameId = Array.from(task.games.keys())[0];
    }

    const selectedGame = this.selectedGameId ? task.games.get(this.selectedGameId) : null;
    if (!selectedGame) return;

    const currentPageState = selectedGame.pageStates[selectedGame.pageStates.length - 1];

    // Update info panel with selected game's data
    const taskInfoElement = this.elements.get('task-info');
    if (taskInfoElement) {
      taskInfoElement.innerHTML = `
        <h3>Game Info (${this.selectedGameId?.slice(-6)})</h3>
        <div class="info-item">
          <span class="info-label">Game ID:</span>
          <span class="info-value">${selectedGame.gameId.slice(-6)}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Status:</span>
          <span class="info-value">${this.formatGameStatus(selectedGame)}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Current Page:</span>
          <span class="info-value">${currentPageState?.pageTitle || '-'}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Moves:</span>
          <span class="info-value">${selectedGame.pageStates.length - 1}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Distance:</span>
          <span class="info-value">${currentPageState?.distanceToTarget?.toString() || '-'}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Optimal Paths:</span>
          <span class="info-value">${currentPageState?.optimalPaths?.length || 0}</span>
        </div>
      `;
    }
  }

  private formatGameStatus(gameSequence: GameSequence): string {
    switch (gameSequence.status) {
      case 'not_started':
        return 'Not Started';
      case 'in_progress':
        return 'In Progress';
      case 'finished':
        const currentPageState = gameSequence.pageStates[gameSequence.pageStates.length - 1];
        return currentPageState?.isTargetPage ? 'Completed!' : 'Failed';
      default:
        return 'Unknown';
    }
  }

  private updatePageHistory(task: Task, steppingInfo?: {
    currentPageIndex: number;
    viewingPageIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    const container = this.elements.get('moves-container');
    if (!container) return;

    // Clear existing content
    container.innerHTML = '';

    const selectedGame = this.selectedGameId ? task.games.get(this.selectedGameId) : null;
    if (!selectedGame) {
      container.innerHTML = '<div style="color: #64748b; font-style: italic; padding: 1rem; text-align: center;">No game selected</div>';
      return;
    }

    // Get viewing info for proper visual indicators
    const viewingPageIndex = steppingInfo?.viewingPageIndex ?? -1;
    const currentPageIndex = steppingInfo?.currentPageIndex ?? -1;

    // Build page history for selected game
    const pageHistory: Array<{
      title: string, 
      type: 'start' | 'target' | 'visited' | 'current' | 'future', 
      step?: number,
      moveIndex: number,
      isViewing: boolean
    }> = [];
    
    selectedGame.pageStates.forEach((pageState, index) => {
      const isCurrentPage = index === selectedGame.pageStates.length - 1;
      const isViewing = viewingPageIndex === index;
      const isFuture = index > currentPageIndex;
      
      let pageType: 'start' | 'target' | 'visited' | 'current' | 'future';
      if (pageState.isTargetPage) {
        pageType = 'target';
      } else if (isCurrentPage && isViewing) {
        pageType = 'current';
      } else if (isFuture) {
        pageType = 'future';
      } else if (pageState.isStartPage) {
        pageType = 'start';
      } else {
        pageType = 'visited';
      }

      pageHistory.push({
        title: pageState.pageTitle,
        type: pageType,
        step: pageState.moveIndex,
        moveIndex: index, // Use array index for stepping
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

  private updateGraphVisibility(task: Task): void {
    const loadingState = this.elements.get('loading-state');
    const graphCanvas = this.elements.get('graph-canvas');

    if (!loadingState || !graphCanvas) return;

    if (task.games.size === 0) {
      // Show loading state
      loadingState.style.display = 'flex';
      loadingState.textContent = 'Click "Start New Game" to begin';
      graphCanvas.style.display = 'none';
    } else {
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
    // Store the handlers
    this.onStepToMove = handlers.onStepToMove;
    this.onEnterLiveMode = handlers.onEnterLiveMode;
    
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

    // Setup slider event listeners
    this.setupSliderEventListeners();

    console.log('✅ UI event listeners setup');
  }

  // =============================================================================
  // Page Step Slider
  // =============================================================================

  private updatePageStepSlider(task: Task, steppingInfo?: {
    currentPageIndex: number;
    viewingPageIndex: number;
    renderingMode: RenderingMode;
    canStepForward: boolean;
    canStepBackward: boolean;
  }): void {
    const sliderContainer = this.elements.get('page-step-slider-container');
    const slider = this.elements.get('page-step-slider') as HTMLInputElement;
    
    if (!sliderContainer || !slider) return;

    // Show/hide slider based on game state
    if (task.games.size === 0 || task.currentPageIndex < 0) {
      sliderContainer.style.display = 'none';
      return;
    }

    sliderContainer.style.display = 'flex';

    // Calculate the maximum page index across all games
    const maxPageIndex = task.currentPageIndex;
    
    // Update slider properties
    slider.min = '0';
    slider.max = maxPageIndex.toString();
    slider.disabled = maxPageIndex === 0;

    // Set slider value based on viewing mode
    if (steppingInfo) {
      if (steppingInfo.renderingMode === 'live') {
        slider.value = maxPageIndex.toString();
      } else {
        slider.value = steppingInfo.viewingPageIndex.toString();
      }
    }

    // Update handle width proportionally to number of steps
    this.updateSliderHandleWidth(slider, maxPageIndex);
  }

  private updateSliderHandleWidth(slider: HTMLInputElement, maxPageIndex: number): void {
    // Calculate proportional width: if max is 0 (only 1 position), width = 100%
    // if max is 1 (2 positions), width = 50%, if max is 2 (3 positions), width = 33.33%, etc.
    const totalPositions = maxPageIndex + 1;
    const handleWidthPercent = Math.max(5, 100 / totalPositions); // Minimum 5% width for usability
    
    // Get the slider container to get its pixel width
    const container = slider.parentElement;
    if (!container) return;
    
    const containerWidth = container.offsetWidth;
    const handleWidthPx = Math.max(20, (containerWidth * handleWidthPercent) / 100); // Minimum 20px for usability
    
    // Update CSS custom property for cross-browser handle width
    slider.style.setProperty('--thumb-width', `${handleWidthPx}px`);
    
    console.log(`🎚️ Updated slider handle: ${totalPositions} positions, ${handleWidthPercent.toFixed(1)}% width (${handleWidthPx}px)`);
  }

  private setupSliderEventListeners(): void {
    const slider = this.elements.get('page-step-slider') as HTMLInputElement;
    if (!slider) return;

    // Handle slider input (dragging)
    slider.addEventListener('input', (event) => {
      const value = parseInt((event.target as HTMLInputElement).value);
      this.handleSliderChange(value, false); // false = not final
    });

    // Handle slider change (final value when user releases)
    slider.addEventListener('change', (event) => {
      const value = parseInt((event.target as HTMLInputElement).value);
      this.handleSliderChange(value, true); // true = final
    });
  }

  private handleSliderChange(pageIndex: number, isFinal: boolean): void {
    // Get current max page index to determine if we're at the end
    const slider = this.elements.get('page-step-slider') as HTMLInputElement;
    if (!slider) return;

    const maxPageIndex = parseInt(slider.max);

    if (pageIndex === maxPageIndex && isFinal) {
      // User dragged to the far right - enter live mode
      if (this.onEnterLiveMode) {
        this.onEnterLiveMode();
      }
    } else {
      // User is stepping to a specific page
      if (this.onStepToMove) {
        this.onStepToMove(pageIndex);
      }
    }
  }

  // =============================================================================
  // Stepping Controls
  // =============================================================================

  updateSteppingControls(currentPageIndex: number, viewingPageIndex: number, renderingMode: 'live' | 'stepping', canStepForward: boolean, canStepBackward: boolean): void {
    // Update step info
    const stepInfo = this.elements.get('step-info');
    if (stepInfo) {
      if (renderingMode === 'live') {
        stepInfo.textContent = `Live Mode (Page ${currentPageIndex})`;
      } else {
        stepInfo.textContent = `Viewing Page ${viewingPageIndex} of ${currentPageIndex}`;
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
      steppingControls.style.display = currentPageIndex >= 0 ? 'flex' : 'none';
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

  resetTaskUI(): void {
    this.selectedGameId = null;
    
    // Hide progress bars
    const progressContainer = this.elements.get('progress-bars-container');
    if (progressContainer) {
      progressContainer.style.display = 'none';
      progressContainer.innerHTML = '';
    }

    // Clear task info
    this.updateTaskInfo({
      startPage: '',
      targetPage: '',
      shortestPathLength: undefined,
      games: new Map(),
      renderingMode: 'live',
      viewingPageIndex: -1,
      currentPageIndex: -1
    });
  }

  // For debugging
  debugElements(): void {
    console.log('🐛 UI Elements:', Array.from(this.elements.keys()));
  }
} 