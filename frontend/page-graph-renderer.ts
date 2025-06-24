import * as d3 from "d3";
import { PageGraphData, PageNode, NavigationEdge } from './types.js';
import { playerColorService } from './player-color-service.js';

// =============================================================================
// Physics Configuration Interface
// =============================================================================

interface PhysicsConfig {
  chargeStrength: number;
  linkDistance: number; 
  linkStrength: number; // For move edges (general)
  optimalPathLinkStrength: number; // For optimal path edges
  neutralMoveLinkStrength: number; // For moves with distanceChange = 0 (strong)
  progressMoveLinkStrength: number; // For moves with distanceChange != 0 (very weak)
  alphaDecay: number;
  velocityDecay: number;
  collisionRadius: number;
  centerStrength: number;
  // Solar System Physics
  orbitalStrength: number;      // 0-1: How strongly nodes stick to orbits
}

// =============================================================================
// Solar System Orbit Calculation
// =============================================================================

interface OrbitCalculation {
  centerX: number;
  centerY: number;
  startX: number;
  startY: number;
  startDistance: number;        // distanceToTarget of start node
  orbitRadius: (distance: number) => number;
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
    chargeStrength: 0, // Much weaker for solar system - just anti-overlap
    linkDistance: 80, // maybe 50
    linkStrength: 0.2, // Weaker links for moves - visual only (fallback)
    optimalPathLinkStrength: 0.05, // Even weaker for optimal paths - just visual hints
    neutralMoveLinkStrength: 0.2, // For moves with distanceChange = 0 (strong structural)
    progressMoveLinkStrength: 0.05, // For moves with distanceChange != 0 (very weak)
    alphaDecay: 0.01,
    velocityDecay: 0.6, // Higher damping for stable orbits
    collisionRadius: 25, // Smaller - let nodes get closer in orbits
    centerStrength: 0.0, // Disabled - using orbital force instead
    orbitalStrength: 0.8 // Strong orbital constraint
  };

  // Solar system calculation
  private orbitSystem: OrbitCalculation | null = null;
  
  // Game side assignment (left/right screen halves)
  private gameAssignments: Map<string, 'left' | 'right'> = new Map();

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
          <h4 style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 11px; text-transform: uppercase;">Solar System Forces</h4>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Orbital Strength: <span id="orbitalValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.orbitalStrength}</span>
            </label>
            <input type="range" id="orbitalSlider" min="0" max="1" step="0.1" value="${this.physicsConfig.orbitalStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">How strongly nodes stick to their orbits</div>
          </div>

        </div>
        
        <div class="control-section" style="margin-bottom: 12px;">
          <h4 style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 11px; text-transform: uppercase;">Classic Forces</h4>
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
              Move Link Strength: <span id="linkStrengthValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.linkStrength}</span>
            </label>
            <input type="range" id="linkStrengthSlider" min="0" max="1" step="0.05" value="${this.physicsConfig.linkStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">How strongly move edges pull nodes together</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Optimal Path Link Strength: <span id="optimalLinkStrengthValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.optimalPathLinkStrength}</span>
            </label>
            <input type="range" id="optimalLinkStrengthSlider" min="0" max="1" step="0.05" value="${this.physicsConfig.optimalPathLinkStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">How strongly optimal path edges pull nodes together</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Neutral Move Strength: <span id="neutralMoveStrengthValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.neutralMoveLinkStrength}</span>
            </label>
            <input type="range" id="neutralMoveStrengthSlider" min="0" max="1" step="0.05" value="${this.physicsConfig.neutralMoveLinkStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Strength for moves with distanceChange = 0 (strong structural)</div>
          </div>
          <div class="control-item" style="margin-bottom: 8px;">
            <label style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              Progress Move Strength: <span id="progressMoveStrengthValue" style="color: #f59e0b; font-weight: bold;">${this.physicsConfig.progressMoveLinkStrength}</span>
            </label>
            <input type="range" id="progressMoveStrengthSlider" min="0" max="0.1" step="0.01" value="${this.physicsConfig.progressMoveLinkStrength}" style="width: 100%;">
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Strength for moves with distanceChange != 0 (very weak)</div>
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
            margin-bottom: 6px;
          ">Reheat Simulation</button>
          <button id="toggleOrbitRingsBtn" style="
            width: 100%;
            padding: 6px;
            background: #6366f1;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
          ">Toggle Orbit Rings</button>
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

    // Orbital strength control
    const orbitalSlider = this.controlsContainer.querySelector('#orbitalSlider') as HTMLInputElement;
    const orbitalValue = this.controlsContainer.querySelector('#orbitalValue') as HTMLSpanElement;
    orbitalSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.orbitalStrength = value;
      orbitalValue.textContent = value.toString();
      this.updateSimulationForces();
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

    // Link strength control (move edges)
    const linkStrengthSlider = this.controlsContainer.querySelector('#linkStrengthSlider') as HTMLInputElement;
    const linkStrengthValue = this.controlsContainer.querySelector('#linkStrengthValue') as HTMLSpanElement;
    linkStrengthSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.linkStrength = value;
      linkStrengthValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Optimal path link strength control
    const optimalLinkStrengthSlider = this.controlsContainer.querySelector('#optimalLinkStrengthSlider') as HTMLInputElement;
    const optimalLinkStrengthValue = this.controlsContainer.querySelector('#optimalLinkStrengthValue') as HTMLSpanElement;
    optimalLinkStrengthSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.optimalPathLinkStrength = value;
      optimalLinkStrengthValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Neutral move strength control (distanceChange = 0)
    const neutralMoveStrengthSlider = this.controlsContainer.querySelector('#neutralMoveStrengthSlider') as HTMLInputElement;
    const neutralMoveStrengthValue = this.controlsContainer.querySelector('#neutralMoveStrengthValue') as HTMLSpanElement;
    neutralMoveStrengthSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.neutralMoveLinkStrength = value;
      neutralMoveStrengthValue.textContent = value.toString();
      this.updateSimulationForces();
    });

    // Progress move strength control (distanceChange != 0)
    const progressMoveStrengthSlider = this.controlsContainer.querySelector('#progressMoveStrengthSlider') as HTMLInputElement;
    const progressMoveStrengthValue = this.controlsContainer.querySelector('#progressMoveStrengthValue') as HTMLSpanElement;
    progressMoveStrengthSlider?.addEventListener('input', (e) => {
      const value = parseFloat((e.target as HTMLInputElement).value);
      this.physicsConfig.progressMoveLinkStrength = value;
      progressMoveStrengthValue.textContent = value.toString();
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

    // Toggle orbit rings button
    const toggleOrbitRingsBtn = this.controlsContainer.querySelector('#toggleOrbitRingsBtn') as HTMLButtonElement;
    toggleOrbitRingsBtn?.addEventListener('click', () => {
      const rings = this.pathGroup.selectAll('.orbital-ring');
      if (rings.empty()) {
        this.drawOrbitalRings();
      } else {
        rings.remove();
      }
    });
  }

  private updateSimulationForces(): void {
    if (!this.simulation || !this.orbitSystem) return;

    // Update classic forces
    this.simulation
      .force('charge', d3.forceManyBody().strength(this.physicsConfig.chargeStrength))
      .force('collision', d3.forceCollide()
        .radius(this.physicsConfig.collisionRadius)
        .strength(0.8))
      .alphaDecay(this.physicsConfig.alphaDecay)
      .velocityDecay(this.physicsConfig.velocityDecay);

    // Update link force if it exists (with strengths based on distanceChange and type)
    const linkForce = this.simulation.force('link') as d3.ForceLink<any, any>;
    if (linkForce) {
      linkForce
        .distance(this.physicsConfig.linkDistance)
        .strength((d: any) => {
          // Optimal path edges always use their own strength
          if (d.type === 'optimal_path') {
            return this.physicsConfig.optimalPathLinkStrength;
          }
          
          // For move edges, use distanceChange to determine strength
          if (d.distanceChange !== undefined) {
            if (d.distanceChange === 0) {
              // Neutral moves (same distance) get strong structural influence
              return this.physicsConfig.neutralMoveLinkStrength;
            } else {
              // Progress/regress moves get very weak influence
              return this.physicsConfig.progressMoveLinkStrength;
            }
          }
          
          // Fallback for moves without distanceChange data
          return this.physicsConfig.linkStrength;
        });
    }

    // Update solar system forces (these are the most important!)
    this.simulation
      .force('orbital', this.createOrbitalForce(this.orbitSystem));

    // Restart simulation with new parameters
    this.simulation.alpha(0.3).restart();
  }

  private resetLayout(): void {
    // Recalculate orbit system
    this.orbitSystem = this.calculateOrbitSystem();
    
    // Reset all nodes to default positions and clear fixed positions
    this.pages.forEach(page => {
      const newPos = this.getSmartSpawnPosition(page);
      page.x = newPos.x;
      page.y = newPos.y;
      
      // Only keep fixed positions for start/target in solar system
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
  // Solar System Orbit Calculation
  // =============================================================================

  private calculateOrbitSystem(): OrbitCalculation {
    // Find start and target nodes
    const startNode = this.pages.find(p => p.type === 'start');
    const targetNode = this.pages.find(p => p.type === 'target');
    
    if (!startNode || !targetNode) {
      // Fallback to center positions if nodes don't exist yet
      const centerX = this.width / 2;
      const centerY = this.height * 0.8;
      const startX = this.width / 2;
      const startY = this.height * 0.2;
      
      return {
        centerX,
        centerY,
        startX,
        startY,
        startDistance: 4,
        orbitRadius: (distance: number) => distance * 60
      };
    }
    
    // Use actual node positions (they can be dragged around!)
    const centerX = targetNode.x || this.width / 2;
    const centerY = targetNode.y || this.height / 2;
    const startX = startNode.x || this.width / 2;
    const startY = startNode.y || this.height * 0.1;
    
    // Calculate actual distance from start to target nodes
    const totalPixelDistance = Math.sqrt(
      Math.pow(startX - centerX, 2) + Math.pow(startY - centerY, 2)
    );
    
    // Get the maximum orbit number from start node (with fallback)
    const startDistance = startNode.distanceToTarget || 4;
    
    // Calculate orbit spacing - divide available space by number of orbits
    // Ensure minimum spacing to prevent overlapping orbits
    const orbitSpacing = Math.max(30, totalPixelDistance / startDistance);
    
    return {
      centerX,
      centerY,
      startX,
      startY,
      startDistance,
      orbitRadius: (distance: number) => {
        // Distance 0 = center (target), distance 1 = first orbit out, etc.
        return distance * orbitSpacing;
      }
    };
  }

  private createOrbitalForce(orbitSystem: OrbitCalculation) {
    const self = this;
    return function(alpha: number) {
      self.pages.forEach((node: PageNode) => {
        // Skip fixed nodes (start and target)
        if (node.type === 'target' || node.type === 'start') return;
        
        if (node.distanceToTarget !== undefined) {
          const targetRadius = orbitSystem.orbitRadius(node.distanceToTarget);
          
          const currentRadius = Math.sqrt(
            Math.pow((node.x || 0) - orbitSystem.centerX, 2) + 
            Math.pow((node.y || 0) - orbitSystem.centerY, 2)
          );
          
          // Calculate radial error (how far off the correct orbit)
          const radiusError = targetRadius - currentRadius;
          const forceStrength = alpha * self.physicsConfig.orbitalStrength;
          
          if (currentRadius > 0) {
            // Unit vector pointing from center to node
            const directionX = ((node.x || 0) - orbitSystem.centerX) / currentRadius;
            const directionY = ((node.y || 0) - orbitSystem.centerY) / currentRadius;
            
            // Apply radial force (positive = outward, negative = inward)
            // Cast to any to access D3 simulation properties
            (node as any).vx = ((node as any).vx || 0) + directionX * radiusError * forceStrength;
            (node as any).vy = ((node as any).vy || 0) + directionY * radiusError * forceStrength;
          }
        }
      });
    };
  }

  private createSelectiveCollisionForce() {
    const self = this;
    return function(alpha: number) {
      // Filter to only non-optimal-path nodes for collision detection
      const collisionNodes = self.pages.filter(node => node.type !== 'optimal_path');
      
      // Apply collision detection only between non-optimal-path nodes
      for (let i = 0; i < collisionNodes.length; i++) {
        const nodeA = collisionNodes[i];
        const aX = nodeA.x || 0;
        const aY = nodeA.y || 0;
        const aRadius = self.physicsConfig.collisionRadius;
        
        for (let j = i + 1; j < collisionNodes.length; j++) {
          const nodeB = collisionNodes[j];
          const bX = nodeB.x || 0;
          const bY = nodeB.y || 0;
          const bRadius = self.physicsConfig.collisionRadius;
          
          // Calculate distance between nodes
          const dx = bX - aX;
          const dy = bY - aY;
          const distance = Math.sqrt(dx * dx + dy * dy);
          const minDistance = aRadius + bRadius;
          
          // If nodes are overlapping, push them apart
          if (distance < minDistance && distance > 0) {
            const overlap = minDistance - distance;
            const force = overlap * alpha * 0.8; // 0.8 = collision strength
            
            // Unit vector from A to B
            const unitX = dx / distance;
            const unitY = dy / distance;
            
            // Apply equal and opposite forces
            const forceX = unitX * force * 0.5;
            const forceY = unitY * force * 0.5;
            
            // Cast to any to access D3 simulation properties
            (nodeA as any).vx = ((nodeA as any).vx || 0) - forceX;
            (nodeA as any).vy = ((nodeA as any).vy || 0) - forceY;
            (nodeB as any).vx = ((nodeB as any).vx || 0) + forceX;
            (nodeB as any).vy = ((nodeB as any).vy || 0) + forceY;
          }
        }
      }
    };
  }

  // =============================================================================
  // Orbital Ring Visualization
  // =============================================================================

  private drawOrbitalRings(): void {
    if (!this.orbitSystem) return;

    // Clear existing orbital rings
    this.pathGroup.selectAll('.orbital-ring').remove();

    // Find all unique distances that have nodes
    const distances = new Set<number>();
    this.pages.forEach(page => {
      if (page.distanceToTarget !== undefined) {
        distances.add(page.distanceToTarget);
      }
    });

    // Add a few extra orbits beyond the maximum for context
    const startDistance = Math.max(...Array.from(distances));
    for (let i = startDistance + 1; i <= startDistance + 3; i++) {
      distances.add(i);
    }

    // Draw orbital rings
    distances.forEach(distance => {
      if (distance === 0) return; // Skip center (target)
      
      const radius = this.orbitSystem!.orbitRadius(distance);
      
      this.pathGroup.append('circle')
        .attr('class', 'orbital-ring')
        .attr('cx', this.orbitSystem!.centerX)
        .attr('cy', this.orbitSystem!.centerY)
        .attr('r', radius)
        .attr('fill', 'none')
        .attr('stroke', '#374151')
        .attr('stroke-width', 1)
        .attr('stroke-opacity', 0.8)
        .attr('stroke-dasharray', '3,3');
    });

    console.log(`🌍 Drew ${distances.size - 1} orbital rings (excluding center)`);
  }

  // =============================================================================
  // Game Side Assignment System
  // =============================================================================

  private assignGameToSide(gameId: string): 'left' | 'right' {
    if (this.gameAssignments.has(gameId)) {
      return this.gameAssignments.get(gameId)!;
    }

    // Assign games to alternate sides
    const existingGames = Array.from(this.gameAssignments.keys());
    const leftGames = existingGames.filter(id => this.gameAssignments.get(id) === 'left');
    const rightGames = existingGames.filter(id => this.gameAssignments.get(id) === 'right');

    // Assign to the side with fewer games, or left if equal
    const side = leftGames.length <= rightGames.length ? 'left' : 'right';
    this.gameAssignments.set(gameId, side);

    console.log(`🎮 Assigned game ${gameId} to ${side} side`);
    return side;
  }

  private getGameSide(page: PageNode): 'left' | 'right' | 'center' {
    if (page.type === 'start' || page.type === 'target') {
      return 'center'; // Start/target stay in center
    }

    if (page.type === 'optimal_path') {
      return 'center'; // Optimal path nodes are not constrained to sides
    }

    // For visited nodes, use the first visit's game ID
    if (page.visits && page.visits.length > 0) {
      const primaryGameId = page.visits[0].gameId;
      return this.assignGameToSide(primaryGameId);
    }

    // Fallback to center for unknown node types
    return 'center';
  }

  private createSideConstraintForce() {
    const self = this;
    return function(alpha: number) {
      self.pages.forEach((node: PageNode) => {
        if (node.type === 'start' || node.type === 'target') return; // Skip anchors
        
        const gameSide = self.getGameSide(node);
        if (gameSide === 'center') return; // Skip center nodes
        
        const centerX = self.width / 2;
        const currentX = node.x || 0;
        
        // Apply horizontal constraint force
        if (gameSide === 'left' && currentX > centerX) {
          // Node is on wrong side, push it left
          (node as any).vx = ((node as any).vx || 0) - (currentX - centerX) * alpha * 0.3;
        } else if (gameSide === 'right' && currentX < centerX) {
          // Node is on wrong side, push it right
          (node as any).vx = ((node as any).vx || 0) + (centerX - currentX) * alpha * 0.3;
        }
      });
    };
  }

  // =============================================================================
  // Smart Node Positioning for Solar System
  // =============================================================================

  private getSmartSpawnPosition(page: PageNode): { x: number; y: number } {
    // Ensure we have an orbit system calculated
    if (!this.orbitSystem) {
      this.orbitSystem = this.calculateOrbitSystem();
    }
    
    switch (page.type) {
      case 'target':
        return { 
          x: this.orbitSystem.centerX, 
          y: this.orbitSystem.centerY 
        };
        
      case 'start':
        return { 
          x: this.orbitSystem.startX, 
          y: this.orbitSystem.startY 
        };
        
      case 'visited':
        if (page.distanceToTarget !== undefined) {
          const radius = this.orbitSystem.orbitRadius(page.distanceToTarget);
          const gameSide = this.getGameSide(page);
          
          let spawnAngle: number;
          if (gameSide === 'left') {
            // Left side: angles from 90° to 270° (left half of circle)
            spawnAngle = Math.PI/2 + Math.random() * Math.PI;
          } else if (gameSide === 'right') {
            // Right side: angles from -90° to 90° (right half of circle)
            spawnAngle = -Math.PI/2 + Math.random() * Math.PI;
          } else {
            // Center: any angle
            spawnAngle = Math.random() * 2 * Math.PI;
          }
          
          return {
            x: this.orbitSystem.centerX + radius * Math.cos(spawnAngle),
            y: this.orbitSystem.centerY + radius * Math.sin(spawnAngle)
          };
        }
        
        // Visited nodes without distance spawn in corners based on game side
        const gameSide = this.getGameSide(page);
        if (gameSide === 'left') {
          return { 
            x: this.width * 0.1, 
            y: this.height * 0.9 
          };
        } else if (gameSide === 'right') {
          return { 
            x: this.width * 0.9, 
            y: this.height * 0.9 
          };
        } else {
          return { 
            x: this.orbitSystem.centerX + (Math.random() - 0.5) * 100, 
            y: this.orbitSystem.centerY + (Math.random() - 0.5) * 100 
          };
        }

      case 'optimal_path':
        return { x: this.width / 2, y: this.height / 2 };
      default:
        return { x: this.width / 2, y: this.height / 2 };
    }
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
    
    // Draw orbital rings for visualization
    this.drawOrbitalRings();
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
        
        // Update type and visits array
        existingPage.type = newPage.type;
        existingPage.visits = newPage.visits;
        
        newPageMap.set(newPage.pageTitle, existingPage);
      } else {
        // New page - use smart spawn positioning
        const initialPos = this.getSmartSpawnPosition(newPage);
        const pageWithPosition: PageNode = {
          ...newPage,
          x: initialPos.x,
          y: initialPos.y,
          // Set fixed positions for anchor nodes (start/target) in solar system
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
     console.log('🔄 Creating solar system force simulation');

     // Stop existing simulation
     if (this.simulation) {
       this.simulation.stop();
     }

     // Calculate orbit system
     this.orbitSystem = this.calculateOrbitSystem();
     console.log('🌌 Orbit system calculated:', {
       center: `(${this.orbitSystem.centerX}, ${this.orbitSystem.centerY})`,
       startDistance: this.orbitSystem.startDistance,
       exampleRadius: `distance 2 = ${this.orbitSystem.orbitRadius(2)}px`
     });

     // Transform edges to D3 link format
     const links = this.edges.map(edge => ({
       source: edge.sourcePageTitle,
       target: edge.targetPageTitle,
       ...edge
     }));

     this.simulation = d3.forceSimulation(this.pages)
       // Light charge force - just for anti-overlap
       .force('charge', d3.forceManyBody()
         .strength(this.physicsConfig.chargeStrength)) // -80
      
       // Link force with strength based on distanceChange and edge type
       .force('link', d3.forceLink(links)
         .id((d: any) => d.pageTitle)
         .distance(this.physicsConfig.linkDistance)
         .strength((d: any) => {
           // Optimal path edges always use their own strength
           if (d.type === 'optimal_path') {
             return this.physicsConfig.optimalPathLinkStrength;
           }
           
           // For move edges, use distanceChange to determine strength
           if (d.distanceChange !== undefined) {
             if (d.distanceChange === 0) {
               // Neutral moves (same distance) get strong structural influence
               return this.physicsConfig.neutralMoveLinkStrength;
             } else {
               // Progress/regress moves get very weak influence
               return this.physicsConfig.progressMoveLinkStrength;
             }
           }
           
           // Fallback for moves without distanceChange data
           return this.physicsConfig.linkStrength;
         }))
      
              // Light collision detection - completely exclude optimal path nodes
      .force('collision', this.createSelectiveCollisionForce())
      
       // PRIMARY FORCE: Orbital constraint
       .force('orbital', this.createOrbitalForce(this.orbitSystem))
       
       // TERTIARY FORCE: Side constraint (keep games on their assigned sides)
       .force('sideConstraint', this.createSideConstraintForce())
      
       // Simulation parameters - higher damping for stable orbits
       .alphaDecay(this.physicsConfig.alphaDecay)
       .velocityDecay(this.physicsConfig.velocityDecay); // 0.6

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

    // Start simulation with moderate energy
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
          .attr('stroke-width', d.type === 'start' || d.type === 'target' ? 5 : 4);
      })
      .on('drag', (event, d) => {
        d.x = event.x;
        d.y = event.y;
        
        // For start/target nodes (anchors), update fixed positions
        if (d.type === 'start' || d.type === 'target') {
          d.fx = event.x;
          d.fy = event.y;
          
          // Recalculate orbit system when start/target nodes move
          this.orbitSystem = this.calculateOrbitSystem();
          this.drawOrbitalRings();
          
          // Update the simulation forces with new orbit system
          if (this.simulation) {
            this.simulation
              .force('orbital', this.createOrbitalForce(this.orbitSystem));
          }
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
          .attr('stroke-width', 3);
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

    // Add circles to new pages (will be replaced with pie charts if multi-visit)
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

    // First, handle circle updates for non-pie chart, non-target, and non-start nodes
    const circleNodes = pageUpdate.filter((d: PageNode) => 
      !(d.type === 'visited' && this.needsPieChart(d)) && d.type !== 'target' && d.type !== 'start');
    circleNodes.select('circle')
      .attr('r', (d: PageNode) => this.getPageRadius(d))
      .attr('fill', (d: PageNode) => this.getPageColor(d))
      // .attr('stroke', (d: PageNode) => this.getPageStroke(d))
      // .attr('stroke-width', 3)

    // Remove special elements from circle nodes
    circleNodes.selectAll('.pie-slice').remove();
    circleNodes.selectAll('.target-ring').remove();
    circleNodes.selectAll('.start-triangle').remove();

    // Then handle pie chart nodes
    const pieNodes = pageUpdate.filter((d: PageNode) => d.type === 'visited' && this.needsPieChart(d));
    pieNodes.each((d: PageNode, i: number, nodes: ArrayLike<SVGGElement>) => {
      const nodeGroup = d3.select(nodes[i]);
      const radius = this.getPageRadius(d);
      
      // Remove circle and any existing elements
      nodeGroup.select('circle').remove();
      nodeGroup.selectAll('.pie-slice').remove();
      nodeGroup.selectAll('.target-ring').remove();
      nodeGroup.selectAll('.start-triangle').remove();
      
      // Create pie chart
      this.createPieChart(nodeGroup as any, d, radius);
    });

    // Finally, handle target node with concentric rings
    const targetNodes = pageUpdate.filter((d: PageNode) => d.type === 'target');
    targetNodes.each((d: PageNode, i: number, nodes: ArrayLike<SVGGElement>) => {
      const nodeGroup = d3.select(nodes[i]);
      const radius = this.getPageRadius(d);
      
      // Remove circle and any existing elements
      nodeGroup.select('circle').remove();
      nodeGroup.selectAll('.pie-slice').remove();
      nodeGroup.selectAll('.target-ring').remove();
      nodeGroup.selectAll('.start-triangle').remove();
      
      // Create target rings
      this.createTargetRings(nodeGroup as any, d, radius);
    });

    // Handle start nodes with play button triangle
    const startNodes = pageUpdate.filter((d: PageNode) => d.type === 'start');
    startNodes.each((d: PageNode, i: number, nodes: ArrayLike<SVGGElement>) => {
      const nodeGroup = d3.select(nodes[i]);
      const radius = this.getPageRadius(d);
      
      // Remove circle and any existing elements
      nodeGroup.select('circle').remove();
      nodeGroup.selectAll('.pie-slice').remove();
      nodeGroup.selectAll('.target-ring').remove();
      nodeGroup.selectAll('.start-triangle').remove();
      
      // Create start triangle
      this.createStartTriangle(nodeGroup as any, d, radius);
    });

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
  // Pie Chart Helpers
  // =============================================================================

  /**
   * Check if a node has visits from multiple different players
   */
  private needsPieChart(pageNode: PageNode): boolean {
    if (pageNode.visits.length < 2) return false;
    
    // Check if all visits are from the same player
    const firstGameId = pageNode.visits[0].gameId;
    return pageNode.visits.some(visit => visit.gameId !== firstGameId);
  }

  /**
   * Calculate pie chart data for a multi-visit node
   */
  private calculatePieData(pageNode: PageNode): Array<{gameId: string, count: number, percentage: number, color: string}> {
    // Count visits per player
    const visitCounts = new Map<string, number>();
    pageNode.visits.forEach(visit => {
      visitCounts.set(visit.gameId, (visitCounts.get(visit.gameId) || 0) + 1);
    });

    const totalVisits = pageNode.visits.length;
    
    // Convert to pie data with colors
    return Array.from(visitCounts.entries()).map(([gameId, count]) => ({
      gameId,
      count,
      percentage: (count / totalVisits) * 100,
      color: playerColorService.getColorForGame(gameId)
    }));
  }

  /**
   * Create a pie chart node for multi-visit nodes
   */
  private createPieChart(nodeGroup: d3.Selection<SVGGElement, PageNode, any, any>, pageNode: PageNode, radius: number): void {
    const pieData = this.calculatePieData(pageNode);
    
    // Create pie and arc generators
    const pie = d3.pie<{gameId: string, count: number, percentage: number, color: string}>()
      .value(d => d.count)
      .sort(null); // Keep original order
    
    const arc = d3.arc<d3.PieArcDatum<{gameId: string, count: number, percentage: number, color: string}>>()
      .innerRadius(0)
      .outerRadius(radius);

    // Create pie slices (no stroke - seamless color transitions)
    nodeGroup.selectAll('.pie-slice')
      .data(pie(pieData))
      .enter()
      .append('path')
      .attr('class', 'pie-slice')
      .attr('d', arc)
      .attr('fill', d => d.data.color);

    console.log(`🥧 Created pie chart for ${pageNode.pageTitle} with ${pieData.length} slices:`, 
      pieData.map(d => `${d.gameId}: ${d.count} visits (${d.percentage.toFixed(1)}%)`));
  }

  /**
   * Create target rings for target nodes (like a target emoji)
   * Creates 4 concentric rings: white center, red, white, red (outermost)
   */
  private createTargetRings(nodeGroup: d3.Selection<SVGGElement, PageNode, any, any>, pageNode: PageNode, radius: number): void {
    // Define the ring structure: from outermost to innermost
    const rings = [
      { radius: radius, color: '#dc2626' },      // Outermost ring - red
      { radius: radius * 0.75, color: '#ffffff' }, // Second ring - white
      { radius: radius * 0.5, color: '#dc2626' },  // Third ring - red
      { radius: radius * 0.25, color: '#ffffff' }  // Center - white
    ];

    // Create each ring as a circle
    rings.forEach((ring, index) => {
      nodeGroup.append('circle')
        .attr('class', 'target-ring')
        .attr('r', ring.radius)
        .attr('fill', ring.color)
        .attr('stroke', index === 0 ? '#991b1b' : 'none') // Only stroke the outermost ring
        .attr('stroke-width', index === 0 ? 2 : 0);
    });

    console.log(`🎯 Created target rings for ${pageNode.pageTitle} with ${rings.length} concentric circles`);
  }

  /**
   * Create start triangle for start nodes (like a play button)
   * Creates a right-pointing triangle with green fill and darker green stroke
   */
  private createStartTriangle(nodeGroup: d3.Selection<SVGGElement, PageNode, any, any>, pageNode: PageNode, radius: number): void {
    // Create a circular background first for better visibility
    nodeGroup.append('circle')
      .attr('class', 'start-triangle')
      .attr('r', radius)
      .attr('fill', '#065f46') // Dark green background
      .attr('stroke', '#059669') // Lighter green stroke
      .attr('stroke-width', 3);

    // Calculate triangle points for a right-pointing triangle (play button style)
    // Triangle should be centered and sized to fit nicely within the circle
    const triangleSize = radius * 0.8; // Make triangle 60% of the circle radius
    
    // Right-pointing triangle points (tip pointing right)
    const points = [
      [-triangleSize * 0.5, -triangleSize * 0.6], // Top left
      [-triangleSize * 0.5, triangleSize * 0.6],  // Bottom left  
      [triangleSize * 0.7, 0]                     // Right tip (slightly offset for better proportions)
    ];

    // Create the triangle path
    const trianglePath = `M${points[0][0]},${points[0][1]} L${points[1][0]},${points[1][1]} L${points[2][0]},${points[2][1]} Z`;
    
    nodeGroup.append('path')
      .attr('class', 'start-triangle')
      .attr('d', trianglePath)
      .attr('fill', '#10b981') // Bright green triangle
      .attr('stroke', '#059669') // Medium green stroke
      .attr('stroke-width', 2);

    // Ensure distance text appears on top by moving it to the end (re-appending)
    const distanceText = nodeGroup.select('.distance-text');
    if (!distanceText.empty()) {
      // Remove and re-add to put it on top
      const textContent = distanceText.text();
      const fontSize = distanceText.style('font-size');
      const display = distanceText.style('display');
      
      distanceText.remove();
      
      nodeGroup.append('text')
        .attr('class', 'distance-text')
        .attr('text-anchor', 'middle')
        .attr('dy', '0.35em')
        .style('fill', 'white')
        .style('font-weight', 'bold')
        .style('pointer-events', 'none')
        .style('text-shadow', '1px 1px 2px rgba(0,0,0,0.8)') // Add text shadow for better visibility
        .text(textContent)
        .style('font-size', fontSize)
        .style('display', display);
    }

    console.log(`▶️ Created start triangle for ${pageNode.pageTitle} with play button style`);
  }

  // =============================================================================
  // Page Styling
  // =============================================================================

  private getPageRadius(page: PageNode): number {
    switch (page.type) {
      case 'start':
      case 'target':
        return 30;
      case 'visited':
        return 20;
      case 'optimal_path':
        return 15;
      default:
        return 18;
    }
  }

  private getPageColor(page: PageNode): string {
    // Use the PlayerColorService for all node coloring
    return playerColorService.getNodeColor(page);
  }

  private getPageStroke(page: PageNode): string {
    switch (page.type) {
      case 'start':
        return '#059669';
      case 'target':
        return '#d97706';
      case 'visited':
        // Use first visit for stroke (in multi-game, first visit takes precedence)
        const firstVisit = page.visits[0];
        return this.getVisitedPageStroke(firstVisit?.distanceChange);
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
      return '#eab308';
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
      return '#eab308'; // Yellow - stayed same distance
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
    this.pathGroup.selectAll('*').remove(); // This includes orbital rings
    this.pages = [];
    this.edges = [];
    this.pageMap.clear();
    this.orbitSystem = null;
    this.gameAssignments.clear(); // Reset game side assignments
    
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

  debugPieCharts(): void {
    console.log('🥧 Pie Chart Debug Info:');
    const multiVisitNodes = this.pages.filter(page => this.needsPieChart(page));
    
    console.log(`Found ${multiVisitNodes.length} nodes with multiple player visits:`);
    multiVisitNodes.forEach(node => {
      const pieData = this.calculatePieData(node);
      console.log(`- ${node.pageTitle}:`, pieData);
    });
    
    if (multiVisitNodes.length === 0) {
      console.log('No multi-visit nodes found. To test pie charts, you need nodes visited by multiple players.');
    }
  }

  debugSolarSystem(): void {
    console.log('🌌 Solar System Debug Info:');
    if (!this.orbitSystem) {
      console.log('No orbit system calculated yet.');
      return;
    }
    
    console.log('Orbit system:', {
      center: `(${this.orbitSystem.centerX}, ${this.orbitSystem.centerY})`,
      start: `(${this.orbitSystem.startX}, ${this.orbitSystem.startY})`,
      startDistance: this.orbitSystem.startDistance,
      dynamicDistance: Math.sqrt(
        Math.pow(this.orbitSystem.startX - this.orbitSystem.centerX, 2) +
        Math.pow(this.orbitSystem.startY - this.orbitSystem.centerY, 2)
      ).toFixed(1) + 'px'
    });
    
    // Group nodes by orbit
    const orbits = new Map<number, PageNode[]>();
    this.pages.forEach(page => {
      if (page.distanceToTarget !== undefined) {
        if (!orbits.has(page.distanceToTarget)) {
          orbits.set(page.distanceToTarget, []);
        }
        orbits.get(page.distanceToTarget)!.push(page);
      }
    });
    
    console.log('Nodes by orbit:');
    Array.from(orbits.keys()).sort((a, b) => a - b).forEach(distance => {
      const nodes = orbits.get(distance)!;
      const radius = this.orbitSystem!.orbitRadius(distance);
      console.log(`- Orbit ${distance} (radius ${radius.toFixed(1)}px): ${nodes.length} nodes`);
      nodes.forEach(node => {
        const actualRadius = Math.sqrt(
          Math.pow((node.x || 0) - this.orbitSystem!.centerX, 2) +
          Math.pow((node.y || 0) - this.orbitSystem!.centerY, 2)
        );
        console.log(`  - ${node.pageTitle} (${node.type}): actual radius ${actualRadius.toFixed(1)}px`);
             });
     });
   }

   debugGameAssignments(): void {
     console.log('🎮 Game Side Assignments:');
     console.log('Current assignments:', Object.fromEntries(this.gameAssignments));
     
     // Show nodes by side
     const leftNodes = this.pages.filter(p => this.getGameSide(p) === 'left');
     const rightNodes = this.pages.filter(p => this.getGameSide(p) === 'right');
     const centerNodes = this.pages.filter(p => this.getGameSide(p) === 'center');
     
     console.log(`Left side (${leftNodes.length} nodes):`, leftNodes.map(n => n.pageTitle));
     console.log(`Right side (${rightNodes.length} nodes):`, rightNodes.map(n => n.pageTitle));
     console.log(`Center (${centerNodes.length} nodes):`, centerNodes.map(n => n.pageTitle));
   }
 }  