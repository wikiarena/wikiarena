import { Task, GameSequence, ConnectionStatus, RenderingMode } from './types.js';
import { playerColorService } from './player-color-service.js';

// =============================================================================
// UI Controller - Handles all DOM updates and user interactions
// =============================================================================

export class RaceHUDController {
  private elements: Map<string, HTMLElement> = new Map();
  private onStepToMove?: (moveIndex: number) => void;
  private onEnterLiveMode?: () => void;

  constructor() {
    this.initializeElements();
  }

  // =============================================================================
  // Element Management
  // =============================================================================

  private initializeElements(): void {
    const elementIds = [
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
        console.warn(`⚠️ RaceHUDController: Element not found: ${id}`);
      }
    });

    console.log(`✅ Race HUD Controller initialized with ${this.elements.size} elements`);
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
    // Update progress bars for all games (pass stepping info)
    this.updateProgressBars(task, steppingInfo);

    // Update page step slider
    this.updatePageStepSlider(task, steppingInfo);
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
        return pageState.distanceToTarget;
      }
    }
    
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
    
    // Handle negative progress (going backwards/leftward from start)
    if (progressRatio < 0) {
      progressFill.classList.add('negative');
      
      const negativePercent = Math.abs(progressRatio) * 100;
      const negativeLeft = -negativePercent; // Push the bar leftward beyond container
      
      progressFill.style.left = `${negativeLeft}%`;
      progressFill.style.width = `${baselinePercent + negativePercent}%`;
      
      var indicatorPosition = negativeLeft;
    } else {
      // Normal positive progress
      progressFill.style.left = '0%';
      progressFill.style.width = `${Math.max(baselinePercent, progressPercent)}%`;
      
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
    
    playerIndicator.style.transition = 'left 0.8s ease';
    playerIndicator.style.left = `${indicatorPosition}%`;

    // Create trophy at the end
    const trophy = document.createElement('div');
    trophy.className = 'horizontal-progress-target';
    trophy.textContent = '🏆';

    progressBarContainer.appendChild(progressFill);
    progressBarContainer.appendChild(playerIndicator);
    progressBarContainer.appendChild(trophy);

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

  // =============================================================================
  // Event Listener Setup
  // =============================================================================

  setupEventListeners(handlers: {
    onStepToMove?: (moveIndex: number) => void;
  }): void {
    // Store the handlers
    this.onStepToMove = handlers.onStepToMove;
    
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
  // Utility Methods
  // =============================================================================

  resetTaskUI(): void {
    
    // Hide progress bars
    const progressContainer = this.elements.get('progress-bars-container');
    if (progressContainer) {
      progressContainer.style.display = 'none';
      progressContainer.innerHTML = '';
    }
  }

  // For debugging
  debugElements(): void {
    console.log('🐛 UI Elements:', Array.from(this.elements.keys()));
  }
} 