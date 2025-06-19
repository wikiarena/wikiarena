import * as d3 from "d3";
import { PageGraphData, PageNode, NavigationEdge } from './types.js';

// =============================================================================
// Physics Configuration Interface
// =============================================================================

interface PhysicsConfig {
  chargeStrength: number;
  linkDistance: number; 
  linkStrength: number;
  alphaDecay: number;
  velocityDecay: number;
  collisionRadius: number;
  centerStrength: number;
}

// =============================================================================
// Enhanced Page Graph Renderer with Interactive Physics
// =============================================================================

export class PageGraphRenderer {
  private container: HTMLElement;
  private svg!: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  private width: number = 800;
  private height: number = 600;
  private simulation: d3.Simulation<PageNode, undefined> | null = null;
  
  // D3 selections for different graph elements
  private nodeGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private edgeGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private pathGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  
  // Current graph data - maintain stable references
  private pages: PageNode[] = [];
  private edges: NavigationEdge[] = [];
  private pageMap: Map<string, PageNode> = new Map(); // For object constancy

  // Zoom behavior
  private zoom!: d3.ZoomBehavior<SVGSVGElement, unknown>;
  private g!: d3.Selection<SVGGElement, unknown, null, undefined>;

  // Enhanced physics configuration with sensible defaults
  private physicsConfig: PhysicsConfig = {
    chargeStrength: -300,
    linkDistance: 80,
    linkStrength: 2,
    alphaDecay: 0.01,
    velocityDecay: 0.5,
    collisionRadius: 40,
    centerStrength: 0.0
  };

  // Physics controls UI elements
  private controlsContainer?: HTMLElement;
  private debugButton?: HTMLElement;
  private controlsVisible: boolean = false;

  constructor(containerId: string) {
    const container = document.getElementById(containerId);
    if (!container) {
      throw new Error(`Container element with id '${containerId}' not found`);
    }
    
    this.container = container;
    this.initializeSVG();
    this.setupZoom();
    this.createDebugButton();
    console.log('✅ Enhanced Page Graph Renderer initialized with interactive physics');
  }

  // =============================================================================
  // Initialization
  // =============================================================================

  private initializeSVG(): void {
    // Clear any existing SVG
    d3.select(this.container).selectAll('*').remove();

    // Get container dimensions - ensure we have full viewport dimensions
    const rect = this.container.getBoundingClientRect();
    this.width = rect.width || window.innerWidth;
    this.height = rect.height || window.innerHeight;

    // Create main SVG
    this.svg = d3.select(this.container)
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .style('background-color', '#020617')
      .style('cursor', 'grab');

    // Create main group for zoom/pan
    this.g = this.svg.append('g');

    // Create groups in proper layering order (bottom to top)
    this.pathGroup = this.g.append('g').attr('class', 'optimal-paths');
    this.edgeGroup = this.g.append('g').attr('class', 'edges');
    this.nodeGroup = this.g.append('g').attr('class', 'nodes');

    // Add pattern definitions for different node types
    this.setupNodePatterns();
  }

  private setupZoom(): void {
    this.zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        this.g.attr('transform', event.transform);
      });

    this.svg.call(this.zoom);

    // Prevent context menu on right click
    this.svg.on('contextmenu', (event) => {
      event.preventDefault();
    });
  }

  private setupNodePatterns(): void {
    const defs = this.svg.append('defs');

    // Gradient for start node
    const startGradient = defs.append('radialGradient')
      .attr('id', 'start-gradient')
      .attr('cx', '50%')
      .attr('cy', '50%')
      .attr('r', '50%');
    
    startGradient.append('stop')
      .attr('offset', '0%')
      .attr('stop-color', '#10b981')
      .attr('stop-opacity', 1);
    
    startGradient.append('stop')
      .attr('offset', '100%')
      .attr('stop-color', '#065f46')
      .attr('stop-opacity', 1);

    // Gradient for target node
    const targetGradient = defs.append('radialGradient')
      .attr('id', 'target-gradient')
      .attr('cx', '50%')
      .attr('cy', '50%')
      .attr('r', '50%');
    
    targetGradient.append('stop')
      .attr('offset', '0%')
      .attr('stop-color', '#f59e0b')
      .attr('stop-opacity', 1);
    
    targetGradient.append('stop')
      .attr('offset', '100%')
      .attr('stop-color', '#92400e')
      .attr('stop-opacity', 1);

    // Single arrow marker that inherits stroke color
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 8)
      .attr('refY', 3)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,0 L0,6 L9,3 z')
      .attr('fill', 'context-stroke'); // Use the stroke color of the referencing element
  }

  // =============================================================================
  // Physics Controls UI
  // =============================================================================

  private createDebugButton(): void {
    // Create small debug button in bottom-right corner
    this.debugButton = document.createElement('button');
    this.debugButton.innerHTML = '🔧';
    this.debugButton.title = 'Toggle Physics Debug Controls';
    this.debugButton.style.cssText = `
      position: absolute;
      bottom: 20px;
      right: 20px;
      width: 40px;
      height: 40px;
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid #374151;
      border-radius: 50%;
      color: #94a3b8;
      font-size: 16px;
      cursor: pointer;
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
      backdrop-filter: blur(5px);
      transition: all 0.2s ease;
    `;

    // Hover effects
    this.debugButton.addEventListener('mouseenter', () => {
      this.debugButton!.style.background = 'rgba(15, 23, 42, 1)';
      this.debugButton!.style.color = '#f59e0b';
      this.debugButton!.style.transform = 'scale(1.1)';
    });

    this.debugButton.addEventListener('mouseleave', () => {
      this.debugButton!.style.background = 'rgba(15, 23, 42, 0.9)';
      this.debugButton!.style.color = '#94a3b8';
      this.debugButton!.style.transform = 'scale(1)';
    });

    // Toggle controls
    this.debugButton.addEventListener('click', () => {
      this.togglePhysicsControls();
    });

    this.container.style.position = 'relative';
    this.container.appendChild(this.debugButton);
  }

  private togglePhysicsControls(): void {
    if (this.controlsVisible) {
      this.hidePhysicsControls();
    } else {
      this.showPhysicsControls();
    }
  }

  private showPhysicsControls(): void {
    if (!this.controlsContainer) {
      this.createPhysicsControls();
    }
    if (this.controlsContainer) {
      this.controlsContainer.style.display = 'block';
    }
    this.controlsVisible = true;
  }

  private hidePhysicsControls(): void {
    if (this.controlsContainer) {
      this.controlsContainer.style.display = 'none';
    }
    this.controlsVisible = false;
  }

  private createPhysicsControls(): void {
    // Create controls container that overlays the graph (positioned top-left)
    this.controlsContainer = document.createElement('div');
    this.controlsContainer.className = 'physics-controls';
    this.controlsContainer.style.cssText = `
      position: absolute;
      top: 20px;
      left: 20px;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid #374151;
      border-radius: 8px;
      padding: 16px;
      color: #e2e8f0;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 12px;
      max-width: 280px;
      backdrop-filter: blur(10px);
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    `;

    // Insert the controls into the container
    this.container.style.position = 'relative';
    this.container.appendChild(this.controlsContainer);

    // Build the controls HTML
    this.controlsContainer.innerHTML = `
      <div class="controls-header" style="margin-bottom: 12px; font-weight: bold; color: #f8fafc; display: flex; justify-content: space-between; align-items: center;">
        🔧 Physics Debug Controls
        <button id="closePhysicsBtn" style="background: none; border: 1px solid #475569; color: #94a3b8; padding: 2px 6px; border-radius: 4px; cursor: pointer; font-size: 10px;">Close</button>
      </div>
      
      <div id="physicsControlsContent">
        <div class="control-section" style="margin-bottom: 12px;">
          <h4 style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 11px; text-transform: uppercase;">Node Forces</h4>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Charge Force: <span id="chargeValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.chargeStrength}</span>
            </label>
            <input type="range" id="chargeSlider" min="-1000" max="100" value="${this.physicsConfig.chargeStrength}" step="10" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Repulsion/attraction between nodes</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Collision Radius: <span id="collisionValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.collisionRadius}</span>
            </label>
            <input type="range" id="collisionSlider" min="10" max="60" value="${this.physicsConfig.collisionRadius}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Prevents node overlap</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Center Strength: <span id="centerValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.centerStrength}</span>
            </label>
            <input type="range" id="centerSlider" min="0" max="1" step="0.1" value="${this.physicsConfig.centerStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Pull toward canvas center</div>
          </div>
        </div>
        
        <div class="control-section" style="margin-bottom: 12px;">
          <h4 style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 11px; text-transform: uppercase;">Link Forces</h4>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Link Distance: <span id="linkDistanceValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.linkDistance}</span>
            </label>
            <input type="range" id="linkDistanceSlider" min="30" max="200" value="${this.physicsConfig.linkDistance}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Target distance between connected nodes</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Link Strength: <span id="linkStrengthValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.linkStrength}</span>
            </label>
            <input type="range" id="linkStrengthSlider" min="0" max="3" step="0.1" value="${this.physicsConfig.linkStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">How strongly links pull nodes together</div>
          </div>
        </div>
        
        <div class="control-section" style="margin-bottom: 12px;">
          <h4 style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 11px; text-transform: uppercase;">Simulation</h4>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Alpha Decay: <span id="alphaValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.alphaDecay}</span>
            </label>
            <input type="range" id="alphaSlider" min="0.005" max="0.1" step="0.005" value="${this.physicsConfig.alphaDecay}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">How quickly simulation cools down</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Velocity Decay: <span id="velocityValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.velocityDecay}</span>
            </label>
            <input type="range" id="velocitySlider" min="0.1" max="0.9" step="0.05" value="${this.physicsConfig.velocityDecay}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Friction/damping - higher = less bouncy</div>
          </div>
        </div>
        
        <div class="control-section">
          <button id="resetPhysicsBtn" style="
            width: 100%;
            padding: 8px;
            background: #059669;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 8px;
          ">Reset Layout</button>
          <button id="reheatBtn" style="
            width: 100%;
            padding: 6px;
            background: #dc2626;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
          ">Reheat Simulation</button>
        </div>
      </div>
    `;

    // Wire up event handlers for real-time updates
    this.setupPhysicsControlHandlers();
  }

  private setupPhysicsControlHandlers(): void {
    if (!this.controlsContainer) return;

    // Close button
    const closeBtn = this.controlsContainer.querySelector('#closePhysicsBtn') as HTMLButtonElement;
    closeBtn?.addEventListener('click', () => {
      this.hidePhysicsControls();
    });

    // Charge force control
    const chargeSlider = this.controlsContainer.querySelector('#chargeSlider') as HTMLInputElement;
    const chargeValue = this.controlsContainer.querySelector('#chargeValue') as HTMLSpanElement;
    chargeSlider?.addEventListener('input', (e) => {
      const value = parseInt((e.target as HTMLInputElement).value);
      this.physicsConfig.chargeStrength = value;
      chargeValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Collision radius control
    const collisionSlider = this.controlsContainer.querySelector('#collisionSlider') as HTMLInputElement;
    const collisionValue = this.controlsContainer.querySelector('#collisionValue') as HTMLSpanElement;
    collisionSlider?.addEventListener('input', (e) => {
      const value = parseInt((e.target as HTMLInputElement).value);
      this.physicsConfig.collisionRadius = value;
      collisionValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Center strength control
    const centerSlider = this.controlsContainer.querySelector('#centerSlider') as HTMLInputElement;
    const centerValue = this.controlsContainer.querySelector('#centerValue') as HTMLSpanElement;
    centerSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.centerStrength = value;
      centerValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Link distance control
    const linkDistanceSlider = this.controlsContainer.querySelector('#linkDistanceSlider') as HTMLInputElement;
    const linkDistanceValue = this.controlsContainer.querySelector('#linkDistanceValue') as HTMLSpanElement;
    linkDistanceSlider?.addEventListener('input', (e) => {
      const value = parseInt((e.target as HTMLInputElement).value);
      this.physicsConfig.linkDistance = value;
      linkDistanceValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Link strength control
    const linkStrengthSlider = this.controlsContainer.querySelector('#linkStrengthSlider') as HTMLInputElement;
    const linkStrengthValue = this.controlsContainer.querySelector('#linkStrengthValue') as HTMLSpanElement;
    linkStrengthSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.linkStrength = value;
      linkStrengthValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Alpha decay control
    const alphaSlider = this.controlsContainer.querySelector('#alphaSlider') as HTMLInputElement;
    const alphaValue = this.controlsContainer.querySelector('#alphaValue') as HTMLSpanElement;
    alphaSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.alphaDecay = value;
      alphaValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Velocity decay control  
    const velocitySlider = this.controlsContainer.querySelector('#velocitySlider') as HTMLInputElement;
    const velocityValue = this.controlsContainer.querySelector('#velocityValue') as HTMLSpanElement;
    velocitySlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.velocityDecay = value;
      velocityValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Reset layout button
    const resetBtn = this.controlsContainer.querySelector('#resetPhysicsBtn') as HTMLButtonElement;
    resetBtn?.addEventListener('click', () => {
      this.resetLayout();
    });

    // Reheat simulation button
    const reheatBtn = this.controlsContainer.querySelector('#reheatBtn') as HTMLButtonElement;
    reheatBtn?.addEventListener('click', () => {
      if (this.simulation) {
        this.simulation.alpha(1).restart();
      }
    });
  }

  private updateSimulationForces(): void {
    if (!this.simulation) return;

    // Update all forces with new configuration
    this.simulation
      .force('charge', d3.forceManyBody().strength(this.physicsConfig.chargeStrength))
      .force('collision', d3.forceCollide()
        .radius(this.physicsConfig.collisionRadius)
        .strength(0.8))
      .force('center', d3.forceCenter(this.width / 2, this.height / 2)
        .strength(this.physicsConfig.centerStrength))
      .alphaDecay(this.physicsConfig.alphaDecay)
      .velocityDecay(this.physicsConfig.velocityDecay);

    // Update link force if it exists
    const linkForce = this.simulation.force('link') as d3.ForceLink<any, any>;
    if (linkForce) {
      linkForce
        .distance(this.physicsConfig.linkDistance)
        .strength(this.physicsConfig.linkStrength);
    }

    // Restart simulation with new parameters
    this.simulation.alpha(0.3).restart();
  }

  private resetLayout(): void {
    // Reset all nodes to default positions and clear fixed positions
    this.pages.forEach(page => {
      const newPos = this.getSmartSpawnPosition(page);
      page.x = newPos.x;
      page.y = newPos.y;
      
      // Only keep fixed positions for start/target
      if (page.type === 'start' || page.type === 'target') {
        page.fx = newPos.x;
        page.fy = newPos.y;
      } else {
        page.fx = undefined;
        page.fy = undefined;
      }
    });

    // Restart simulation with full energy
    if (this.simulation) {
      this.simulation.alpha(1).restart();
    }
  }

  // =============================================================================
  // Smart Node Positioning
  // =============================================================================

  private getSmartSpawnPosition(page: PageNode): { x: number; y: number } {
    switch (page.type) {
      case 'start':
        return { x: this.width / 2, y: this.height * 0.15 };
        
      case 'target':
        return { x: this.width / 2, y: this.height * 0.85 };
        
      case 'visited':
        return this.getVisitedNodeSpawnPosition(page);
        
      case 'optimal_path':
        return this.getOptimalNodeSpawnPosition(page);
        
      default:
        return { x: this.width / 2, y: this.height / 2 };
    }
  }

  private getVisitedNodeSpawnPosition(page: PageNode): { x: number; y: number } {
    const startPos = { x: this.width / 2, y: this.height * 0.15 };
    const targetPos = { x: this.width / 2, y: this.height * 0.85 };
    
    // Create curved path from start to target using distance to target
    let progress = 0.5; // Default to middle if no distance info
    
    if (page.distanceToTarget !== undefined) {
      // Find max distance among all visited pages for normalization
      const visitedPages = this.pages.filter(p => p.type === 'visited');
      const maxDistance = Math.max(...visitedPages.map(p => p.distanceToTarget || 0));
      
      if (maxDistance > 0) {
        progress = 1 - (page.distanceToTarget / maxDistance);
      }
    }
    
    // Bezier curve with offset to the right
    const curveOffset = 100;
    const controlPoint = {
      x: (startPos.x + targetPos.x) / 2 + curveOffset,
      y: (startPos.y + targetPos.y) / 2
    };
    
    return this.calculateBezierPoint(startPos, controlPoint, targetPos, progress);
  }

  private getOptimalNodeSpawnPosition(page: PageNode): { x: number; y: number } {
    const startPos = { x: this.width / 2, y: this.height * 0.15 };
    const targetPos = { x: this.width / 2, y: this.height * 0.85 };
    
    // Position along straight line, offset to the left
    let progress = 0.5;
    
    if (page.distanceToTarget !== undefined) {
      // Find max distance among optimal path pages for normalization
      const optimalPages = this.pages.filter(p => p.type === 'optimal_path');
      const maxOptimalDistance = Math.max(...optimalPages.map(p => p.distanceToTarget || 0));
      
      if (maxOptimalDistance > 0) {
        progress = 1 - (page.distanceToTarget / maxOptimalDistance);
      }
    }
    
    const lineOffset = -120; // Offset to the left
    return {
      x: startPos.x + (targetPos.x - startPos.x) * progress + lineOffset,
      y: startPos.y + (targetPos.y - startPos.y) * progress
    };
  }

  private calculateBezierPoint(start: {x: number, y: number}, control: {x: number, y: number}, end: {x: number, y: number}, t: number): {x: number, y: number} {
    const invT = 1 - t;
    const x = invT * invT * start.x + 2 * invT * t * control.x + t * t * end.x;
    const y = invT * invT * start.y + 2 * invT * t * control.y + t * t * end.y;
    return { x, y };
  }

  // =============================================================================
  // Main Update Method
  // =============================================================================

  updateFromPageGraphData(pageGraphData: PageGraphData): void {
    console.log('🗺️ Enhanced Page Graph: Updating visualization with interactive physics');
    console.log('📊 Received pages:', pageGraphData.pages.map(p => `${p.pageTitle} (${p.type})`));
    
    if (pageGraphData.pages.length === 0) {
      this.clear();
      return;
    }

    // Identify new nodes for smart positioning
    const newNodeIds = new Set<string>();
    const currentNodeIds = new Set(this.pages.map(n => n.pageTitle));
    
    pageGraphData.pages.forEach(page => {
      if (!currentNodeIds.has(page.pageTitle)) {
        newNodeIds.add(page.pageTitle);
        console.log('➕ New page detected:', page.pageTitle, `(${page.type})`);
      }
    });

    // Update our stable page references and arrays
    this.updateStablePageReferences(pageGraphData);

    // Update edges
    this.edges = pageGraphData.edges;

    // Render with object constancy
    this.renderPagesWithConstancy(newNodeIds);
    this.renderEdges();

    // Create or update interactive simulation
    this.createInteractiveSimulation();
  }

  // =============================================================================
  // Object Constancy - Smooth Updates
  // =============================================================================

  private updateStablePageReferences(pageGraphData: PageGraphData): void {
    const newPageMap = new Map<string, PageNode>();
    
    pageGraphData.pages.forEach(newPage => {
      if (this.pageMap.has(newPage.pageTitle)) {
        // Keep existing page but update properties (preserve position)
        const existingPage = this.pageMap.get(newPage.pageTitle)!;
        existingPage.type = newPage.type;
        
        // Update data properties
        if (newPage.distanceToTarget !== undefined) {
          existingPage.distanceToTarget = newPage.distanceToTarget;
        }
        if (newPage.distanceChange !== undefined) {
          existingPage.distanceChange = newPage.distanceChange;
        }
        if (newPage.isCurrentlyViewing !== undefined) {
          existingPage.isCurrentlyViewing = newPage.isCurrentlyViewing;
        }
        
        newPageMap.set(newPage.pageTitle, existingPage);
      } else {
        // New page - use smart spawn positioning
        const initialPos = this.getSmartSpawnPosition(newPage);
        const pageWithPosition: PageNode = {
          ...newPage,
          x: initialPos.x,
          y: initialPos.y,
          // Set fixed positions for anchor nodes (start/target)
          fx: newPage.type === 'start' || newPage.type === 'target' ? initialPos.x : undefined,
          fy: newPage.type === 'start' || newPage.type === 'target' ? initialPos.y : undefined
        };
        
        newPageMap.set(newPage.pageTitle, pageWithPosition);
        console.log(`➕ Smart positioned new page: ${newPage.pageTitle} (${newPage.type}) at (${pageWithPosition.x}, ${pageWithPosition.y})`);
      }
    });

    this.pageMap = newPageMap;
    this.pages = Array.from(newPageMap.values());
  }

  // =============================================================================
  // Interactive Force Simulation
  // =============================================================================

     private createInteractiveSimulation(): d3.Simulation<PageNode, undefined> {
     console.log('🔄 Creating interactive force simulation');

     // Stop existing simulation
     if (this.simulation) {
       this.simulation.stop();
     }

     // Transform edges to D3 link format
     const links = this.edges.map(edge => ({
       source: edge.sourcePageTitle,
       target: edge.targetPageTitle,
       ...edge
     }));

     this.simulation = d3.forceSimulation(this.pages)
       // Link force - connects related pages  
       .force('link', d3.forceLink(links)
         .id((d: any) => d.pageTitle)
         .distance(this.physicsConfig.linkDistance)
         .strength(this.physicsConfig.linkStrength))
      
      // Charge force - nodes repel/attract each other
      .force('charge', d3.forceManyBody()
        .strength(this.physicsConfig.chargeStrength))
      
      // Collision detection - prevents overlap
      .force('collision', d3.forceCollide()
        .radius(this.physicsConfig.collisionRadius)
        .strength(0.8))
      
      // Center force - gentle pull toward center (exclude anchored nodes)
      .force('center', d3.forceCenter(this.width / 2, this.height / 2)
        .strength(this.physicsConfig.centerStrength))
      
      // Simulation parameters
      .alphaDecay(this.physicsConfig.alphaDecay)
      .velocityDecay(this.physicsConfig.velocityDecay);

    // Set up tick handler
    this.simulation.on('tick', () => {
      // Enforce canvas boundaries
      this.pages.forEach(page => {
        if (page.x !== undefined && page.y !== undefined) {
          page.x = Math.max(30, Math.min(this.width - 30, page.x));
          page.y = Math.max(30, Math.min(this.height - 30, page.y));
        }
      });
      
      // Update visual positions
      this.nodeGroup.selectAll<SVGGElement, PageNode>('.node')
        .attr('transform', (d: PageNode) => `translate(${d.x},${d.y})`);

      this.updateEdgePositions();
    });

    // Start simulation
    this.simulation.alpha(0.5).restart();
    
    return this.simulation;
  }

  // =============================================================================
  // Enhanced Drag Interactions
  // =============================================================================

  private setupEnhancedDragBehavior(): d3.DragBehavior<SVGGElement, PageNode, PageNode | d3.SubjectPosition> {
    const drag = d3.drag<SVGGElement, PageNode>()
      .on('start', (event, d) => {
        // Increase simulation energy for responsive dragging
        if (this.simulation) {
          this.simulation.alphaTarget(0.3).restart();
        }
        
        // Visual feedback
        d3.select(event.sourceEvent.currentTarget)
          .classed('dragging', true)
          .select('circle')
          .attr('stroke-width', d.type === 'start' || d.type === 'target' ? 5 : 4)
          .style('filter', 'drop-shadow(0 0 15px rgba(255,255,255,0.8))');
      })
      .on('drag', (event, d) => {
        d.x = event.x;
        d.y = event.y;
        
        // For start/target nodes (anchors), update fixed positions
        if (d.type === 'start' || d.type === 'target') {
          d.fx = event.x;
          d.fy = event.y;
        }
      })
      .on('end', (event, d) => {
        // Cool down simulation
        if (this.simulation) {
          this.simulation.alphaTarget(0);
        }
        
        // Release non-anchor nodes to physics
        if (d.type !== 'start' && d.type !== 'target') {
          d.fx = undefined;
          d.fy = undefined;
        }
        
        // Reset visual feedback
        d3.select(event.sourceEvent.currentTarget)
          .classed('dragging', false)
          .select('circle')
          .attr('stroke-width', 3)
          .style('filter', d.type === 'start' || d.type === 'target' ? 'drop-shadow(0 0 10px rgba(255,255,255,0.5))' : 'none');
      });
      
    return drag;
  }

  // =============================================================================
  // Graph Rendering with Object Constancy
  // =============================================================================

  private renderPagesWithConstancy(newPageIds: Set<string>): void {
    console.log(`🎨 Rendering ${this.pages.length} pages with enhanced physics`);
    
    // Bind data with stable key function
    const pageSelection = this.nodeGroup
      .selectAll<SVGGElement, PageNode>('.node')
      .data(this.pages, (d: PageNode) => d.pageTitle);

    // Remove exiting pages
    pageSelection.exit()
      .transition()
      .duration(300)
      .style('opacity', 0)
      .remove();

    // Create new page groups
    const pageEnter = pageSelection.enter()
      .append('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .style('opacity', 0)
      .attr('transform', (d: PageNode) => `translate(${d.x},${d.y})`)
      .call(this.setupEnhancedDragBehavior());

    // Add circles to new pages
    pageEnter.append('circle');
    
    // Add distance text
    pageEnter.append('text')
      .attr('class', 'distance-text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .style('fill', 'white')
      .style('font-weight', 'bold')
      .style('pointer-events', 'none');
    
    // Add title labels
    pageEnter.append('text')
      .attr('class', 'title-text');

    // Animate new pages in
    pageEnter
      .filter((d: PageNode) => newPageIds.has(d.pageTitle))
      .transition()
      .duration(500)
      .style('opacity', 1);

    // Merge and update all pages
    const pageUpdate = pageEnter.merge(pageSelection);

    // Update circle properties
    pageUpdate.select('circle')
      .attr('r', (d: PageNode) => this.getPageRadius(d))
      .attr('fill', (d: PageNode) => this.getPageColor(d))
      .attr('stroke', (d: PageNode) => this.getPageStroke(d))
      .attr('stroke-width', 3)
      .style('filter', (d: PageNode) => d.type === 'start' || d.type === 'target' ? 'drop-shadow(0 0 10px rgba(255,255,255,0.5))' : 'none');

    // Update distance text
    pageUpdate.select('.distance-text')
      .text((d: PageNode) => this.getDistanceText(d))
      .style('font-size', (d: PageNode) => this.getDistanceFontSize(d))
      .style('display', (d: PageNode) => d.distanceToTarget !== undefined ? 'block' : 'none');

    // Update title labels
    pageUpdate.select('.title-text')
      .text((d: PageNode) => this.getPageLabel(d))
      .attr('text-anchor', 'middle')
      .attr('dy', -35)
      .style('fill', '#e2e8f0')
      .style('font-size', '12px')
      .style('font-weight', 'bold')
      .style('text-shadow', '1px 1px 2px rgba(0,0,0,0.8)');

    // Ensure existing pages remain visible
    pageUpdate
      .filter((d: PageNode) => !newPageIds.has(d.pageTitle))
      .style('opacity', 1);
  }

  private renderEdges(): void {
    const edgeSelection = this.edgeGroup
      .selectAll<SVGLineElement, NavigationEdge>('.edge')
      .data(this.edges, (d: NavigationEdge) => d.id);

    edgeSelection.exit().remove();

    const edgeEnter = edgeSelection.enter()
      .append('line')
      .attr('class', 'edge');

    const edgeUpdate = edgeEnter.merge(edgeSelection);

    edgeUpdate
      .attr('stroke', (d: NavigationEdge) => this.getEdgeColor(d))
      .attr('stroke-width', (d: NavigationEdge) => this.getEdgeWidth(d))
      .attr('stroke-opacity', (d: NavigationEdge) => d.type === 'optimal_path' ? 0.4 : 0.9)
      .attr('stroke-dasharray', (d: NavigationEdge) => d.type === 'optimal_path' ? '5,5' : 'none')
      .style('marker-end', 'url(#arrowhead)');
  }

  private updateEdgePositions(): void {
    this.edgeGroup.selectAll<SVGLineElement, NavigationEdge>('.edge')
      .attr('x1', (d: NavigationEdge) => {
        const source = this.pageMap.get(d.sourcePageTitle);
        const target = this.pageMap.get(d.targetPageTitle);
        if (!source || !target) return 0;
        
        // Calculate edge start point at source node perimeter
        const sourceRadius = this.getPageRadius(source);
        const { x: startX } = this.calculateEdgeEndpoint(source, target, sourceRadius);
        return startX;
      })
      .attr('y1', (d: NavigationEdge) => {
        const source = this.pageMap.get(d.sourcePageTitle);
        const target = this.pageMap.get(d.targetPageTitle);
        if (!source || !target) return 0;
        
        // Calculate edge start point at source node perimeter
        const sourceRadius = this.getPageRadius(source);
        const { y: startY } = this.calculateEdgeEndpoint(source, target, sourceRadius);
        return startY;
      })
      .attr('x2', (d: NavigationEdge) => {
        const source = this.pageMap.get(d.sourcePageTitle);
        const target = this.pageMap.get(d.targetPageTitle);
        if (!source || !target) return 0;
        
        // Calculate edge end point at target node perimeter (add small offset for arrow visibility)
        const targetRadius = this.getPageRadius(target) + 2; // +2px for arrow visibility
        const { x: endX } = this.calculateEdgeEndpoint(target, source, targetRadius);
        return endX;
      })
      .attr('y2', (d: NavigationEdge) => {
        const source = this.pageMap.get(d.sourcePageTitle);
        const target = this.pageMap.get(d.targetPageTitle);
        if (!source || !target) return 0;
        
        // Calculate edge end point at target node perimeter (add small offset for arrow visibility)
        const targetRadius = this.getPageRadius(target) + 2; // +2px for arrow visibility
        const { y: endY } = this.calculateEdgeEndpoint(target, source, targetRadius);
        return endY;
      });
  }

  private calculateEdgeEndpoint(fromNode: PageNode, toNode: PageNode, radius: number): { x: number; y: number } {
    const fromX = fromNode.x || 0;
    const fromY = fromNode.y || 0;
    const toX = toNode.x || 0;
    const toY = toNode.y || 0;
    
    // Calculate the direction vector from fromNode to toNode
    const dx = toX - fromX;
    const dy = toY - fromY;
    const distance = Math.sqrt(dx * dx + dy * dy);
    
    // If nodes are at the same position, return the original position
    if (distance === 0) {
      return { x: fromX, y: fromY };
    }
    
    // Calculate unit vector
    const unitX = dx / distance;
    const unitY = dy / distance;
    
    // Calculate the point on the circle's edge
    const edgeX = fromX + unitX * radius;
    const edgeY = fromY + unitY * radius;
    
    return { x: edgeX, y: edgeY };
  }

  // =============================================================================
  // Page Styling
  // =============================================================================

  private getPageRadius(page: PageNode): number {
    switch (page.type) {
      case 'start':
      case 'target':
        return 25;
      case 'visited':
        return 20;
      case 'optimal_path':
        return 15;
      default:
        return 18;
    }
  }

  private getPageColor(page: PageNode): string {
    switch (page.type) {
      case 'start':
        return 'url(#start-gradient)';
      case 'target':
        return 'url(#target-gradient)';
      case 'visited':
        return this.getVisitedPageColor(page.distanceChange);
      case 'optimal_path':
        return '#374151';
      default:
        return '#64748b';
    }
  }

  private getVisitedPageColor(distanceChange?: number): string {
    if (distanceChange === undefined) {
      return '#64748b'; // Gray - unknown
    }
    
    if (distanceChange > 0) {
      return '#10b981'; // Green - got closer to target
    } else if (distanceChange === 0) {
      return '#f59e0b'; // Amber - stayed same distance
    } else if (distanceChange === -1) {
      return '#ef4444'; // Red - got further from target
    } else {
      return '#dc2626'; // Dark red - got much further from target
    }
  }

  private getPageStroke(page: PageNode): string {
    switch (page.type) {
      case 'start':
        return '#059669';
      case 'target':
        return '#d97706';
      case 'visited':
        return this.getVisitedPageStroke(page.distanceChange);
      default:
        return '#475569';
    }
  }

  private getVisitedPageStroke(distanceChange?: number): string {
    if (distanceChange === undefined) {
      return '#475569'; // Dark gray - unknown
    }
    
    if (distanceChange > 0) {
      return '#059669';
    } else if (distanceChange === 0) {
      return '#d97706';
    } else if (distanceChange === -1) {
      return '#dc2626';
    } else {
      return '#991b1b';
    }
  }

  private getPageLabel(page: PageNode): string {
    return page.pageTitle;
  }

  private getDistanceText(page: PageNode): string {
    if (page.distanceToTarget === undefined) {
      return '?';
    }
    return page.distanceToTarget.toString();
  }

  private getDistanceFontSize(page: PageNode): string {
    const radius = this.getPageRadius(page);
    const fontSize = Math.max(10, Math.min(16, radius * 0.6));
    return `${fontSize}px`;
  }

  private getEdgeColor(edge: NavigationEdge): string {
    if (edge.type === 'optimal_path') {
      return '#64748b';
    } else {
      return this.getMoveEdgeColor(edge.distanceChange);
    }
  }

  private getMoveEdgeColor(distanceChange?: number): string {
    if (distanceChange === undefined) {
      return '#64748b'; // Gray - unknown
    }
    
    if (distanceChange > 0) {
      return '#10b981'; // Green - got closer to target
    } else if (distanceChange === 0) {
      return '#f59e0b'; // Amber - stayed same distance
    } else if (distanceChange === -1) {
      return '#ef4444'; // Red - got further from target
    } else {
      return '#dc2626'; // Dark red - got much further from target
    }
  }

  private getEdgeWidth(edge: NavigationEdge): number {
    if (edge.type === 'optimal_path') {
      return 2;
    } else {
      return 3;
    }
  }



  // =============================================================================
  // Public API
  // =============================================================================

  clear(): void {
    this.nodeGroup.selectAll('*').remove();
    this.edgeGroup.selectAll('*').remove();
    this.pathGroup.selectAll('*').remove();
    this.pages = [];
    this.edges = [];
    this.pageMap.clear();
    
    if (this.simulation) {
      this.simulation.stop();
    }
  }

  destroy(): void {
    this.clear();
    
    // Remove physics controls
    if (this.controlsContainer && this.controlsContainer.parentNode) {
      this.controlsContainer.parentNode.removeChild(this.controlsContainer);
    }
    
    // Remove debug button
    if (this.debugButton && this.debugButton.parentNode) {
      this.debugButton.parentNode.removeChild(this.debugButton);
    }
  }

  resize(): void {
    const rect = this.container.getBoundingClientRect();
    const newWidth = rect.width || window.innerWidth;
    const newHeight = rect.height || window.innerHeight;
    
    if (newWidth !== this.width || newHeight !== this.height) {
      this.width = newWidth;
      this.height = newHeight;

      this.svg
        .attr('width', this.width)
        .attr('height', this.height);

      // Update center forces and restart simulation
      if (this.simulation) {
        this.simulation
          .force('center', d3.forceCenter(this.width / 2, this.height / 2))
          .alpha(0.3)
          .restart();
      }
    }
  }

  centerGraph(): void {
    if (this.pages.length === 0) return;

    const bounds = this.getGraphBounds();
    const fullWidth = bounds.maxX - bounds.minX;
    const fullHeight = bounds.maxY - bounds.minY;
    const centerX = bounds.minX + fullWidth / 2;
    const centerY = bounds.minY + fullHeight / 2;

    const scale = Math.min(
      this.width / (fullWidth + 100),
      this.height / (fullHeight + 100)
    );

    const transform = d3.zoomIdentity
      .translate(this.width / 2 - centerX * scale, this.height / 2 - centerY * scale)
      .scale(scale);

    this.svg.transition()
      .duration(750)
      .call(this.zoom.transform, transform);
  }

  private getGraphBounds(): { minX: number; maxX: number; minY: number; maxY: number } {
    return {
      minX: Math.min(...this.pages.map(n => n.x || 0)),
      maxX: Math.max(...this.pages.map(n => n.x || 0)),
      minY: Math.min(...this.pages.map(n => n.y || 0)),
      maxY: Math.max(...this.pages.map(n => n.y || 0))
    };
  }
} 