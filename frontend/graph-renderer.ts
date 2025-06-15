import * as d3 from "d3";
import { GameState, GraphNode, GraphEdge, GraphData } from './types.js';

// =============================================================================
// Configuration
// =============================================================================

const MAX_OPTIMAL_PATHS_TO_RENDER = 2; // Limit for performance

// =============================================================================
// Graph Renderer - D3.js visualization for Wiki Arena games
// =============================================================================

export class GraphRenderer {
  private container: HTMLElement;
  private svg!: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  private width: number = 800;
  private height: number = 600;
  private simulation: d3.Simulation<GraphNode, GraphEdge> | null = null;
  
  // D3 selections for different graph elements
  private nodeGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private edgeGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  private pathGroup!: d3.Selection<SVGGElement, unknown, null, undefined>;
  
  // Current graph data - maintain stable references
  private nodes: GraphNode[] = [];
  private edges: GraphEdge[] = [];
  private nodeMap: Map<string, GraphNode> = new Map(); // For object constancy

  // Zoom behavior
  private zoom!: d3.ZoomBehavior<SVGSVGElement, unknown>;
  private g!: d3.Selection<SVGGElement, unknown, null, undefined>;

  constructor(containerId: string) {
    const container = document.getElementById(containerId);
    if (!container) {
      throw new Error(`Container element with id '${containerId}' not found`);
    }
    
    this.container = container;
    this.initializeSVG();
    this.setupZoom();
    console.log('✅ Graph renderer initialized');
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

    // Arrow marker for edges
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
      .attr('fill', '#475569');
  }

  // =============================================================================
  // Game State Updates
  // =============================================================================

  updateFromGameState(gameState: GameState): void {
    console.log('🗺️ Graph: Updating from game state');
    
    if (gameState.status === 'not_started') {
      this.clear();
      return;
    }

    // Build unified graph data including optimal paths
    const graphData = this.buildUnifiedGraphData(gameState);
    
    // Update the visualization with object constancy
    this.updateGraphWithConstancy(graphData);
  }

  private buildUnifiedGraphData(gameState: GameState): GraphData {
    const tempNodeMap = new Map<string, GraphNode>();
    const edges: GraphEdge[] = [];

    // Helper function to normalize page titles for consistent matching
    // Based on Wikipedia's actual title handling and wiki_helpers.py
    const normalizeTitle = (title: string | undefined | null): string => {
      if (!title || typeof title !== 'string') {
        console.warn('⚠️ Graph: Invalid title passed to normalizeTitle:', title);
        return 'unknown-page';
      }
      
      // Step 1: Basic cleanup
      let normalized = title.trim();
      
      // Step 2: Replace spaces with underscores (Wikipedia internal format)
      normalized = normalized.replace(/\s+/g, '_');
      
      // Step 3: Wikipedia's case rule: First character case-sensitive, rest case-insensitive
      // This means "Computer Science" and "Computer science" should both become "Computer_science"
      if (normalized.length > 0) {
        // Keep first character as-is, lowercase the rest
        normalized = normalized.charAt(0) + normalized.slice(1).toLowerCase();
      }
      
      return normalized;
    };

    console.log('🔍 Graph: Building unified graph data');
    console.log('🔍 Start page:', gameState.startPage);
    console.log('🔍 Target page:', gameState.targetPage);
    console.log('🔍 Optimal paths:', gameState.optimalPaths);

    // Helper function to get or create a node with object constancy
    const getOrCreateNode = (pageTitle: string, defaultType: GraphNode['type']): GraphNode => {
      // Validate input
      if (!pageTitle || typeof pageTitle !== 'string') {
        console.warn('⚠️ Graph: Invalid pageTitle passed to getOrCreateNode:', pageTitle);
        pageTitle = 'Unknown Page';
      }
      
      const normalizedTitle = normalizeTitle(pageTitle);
      
      // Check if we already have this node in our stable nodeMap
      if (this.nodeMap.has(normalizedTitle)) {
        const existingNode = this.nodeMap.get(normalizedTitle)!;
        
        // IMPORTANT: Don't override special node types (start/target) with regular types
        const oldType = existingNode.type;
        if (oldType === 'start' || oldType === 'target') {
          if (defaultType !== 'start' && defaultType !== 'target') {
            // Keep the special type, don't downgrade it
          } else {
            existingNode.type = defaultType;
          }
        } else {
          existingNode.type = defaultType;
        }
        
        // Update other properties but preserve position
        existingNode.title = pageTitle; // Keep original title for display
        tempNodeMap.set(normalizedTitle, existingNode);
        
        if (oldType !== existingNode.type) {
          console.log(`🔄 Graph: Node type changed: "${pageTitle}" ${oldType} -> ${existingNode.type}`);
        }
        
        return existingNode;
      }
      
      // Create new node with initial positioning
      const node: GraphNode = {
        id: normalizedTitle,
        title: pageTitle, // Keep original title for display
        type: defaultType,
        // Set initial positions for start/target nodes
        x: defaultType === 'start' || defaultType === 'target' ? this.width * 0.5 : 
           this.getNewNodePosition().x,
        y: defaultType === 'start' ? 40 : // Top center with padding from top edge
           defaultType === 'target' ? this.height - 40 : // Bottom center with padding from bottom edge
           this.getNewNodePosition().y,
        // Set fixed positions for pinning in force simulation
        fx: defaultType === 'start' || defaultType === 'target' ? this.width * 0.5 : undefined,
        fy: defaultType === 'start' ? 40 : // Fix start node at top
            defaultType === 'target' ? this.height - 40 : undefined
      };
      
      tempNodeMap.set(normalizedTitle, node);
      console.log(`➕ Graph: Created new node: "${pageTitle}" (${normalizedTitle}) type: ${defaultType}`);
      return node;
    };

    // Add start node (highest priority)
    if (gameState.startPage && typeof gameState.startPage === 'string') {
      getOrCreateNode(gameState.startPage, 'start');
    } else {
      console.warn('⚠️ Graph: No valid start page found:', gameState.startPage);
    }

    // Add target node (highest priority)
    if (gameState.targetPage && typeof gameState.targetPage === 'string') {
      getOrCreateNode(gameState.targetPage, 'target');
    }

    // Add move nodes and edges
    gameState.moves.forEach((move) => {
      // Skip invalid moves
      if (!move.from_page_title || !move.to_page_title) {
        console.warn('⚠️ Graph: Invalid move data:', move);
        return;
      }
      
      // Ensure source node exists
      getOrCreateNode(move.from_page_title, 'move');
      
      // Create or update destination node
      const destNode = getOrCreateNode(move.to_page_title, 'move');
      destNode.moveNumber = move.step;
      destNode.quality = (move as any).quality || 'neutral';

      // Add edge for this move (using normalized titles for references)
      edges.push({
        id: `move-${move.step}`,
        source: normalizeTitle(move.from_page_title),
        target: normalizeTitle(move.to_page_title),
        type: 'move',
        moveNumber: move.step
      });
    });

    // Add optimal path nodes and edges (limit to first 5 for performance)
    if (gameState.optimalPaths && gameState.optimalPaths.length > 0) {
      const pathsToRender = gameState.optimalPaths.slice(0, MAX_OPTIMAL_PATHS_TO_RENDER);
      
      if (gameState.optimalPaths.length > MAX_OPTIMAL_PATHS_TO_RENDER) {
        console.log(`🎯 Graph: Rendering ${MAX_OPTIMAL_PATHS_TO_RENDER} out of ${gameState.optimalPaths.length} optimal paths for performance`);
      }
      
      pathsToRender.forEach((path, pathIndex) => {
        // Optimal paths are now always string[] format
        if (!Array.isArray(path)) {
          console.warn('⚠️ Graph: Invalid path format, expected string[]:', path);
          return;
        }
        
        const pages = path;
        
        pages.forEach((page, pageIndex) => {
          // Skip invalid pages
          if (!page || typeof page !== 'string') {
            console.warn('⚠️ Graph: Invalid page in optimal path:', page);
            return;
          }
          
          // Get or create node (but don't override start/target/move types)
          const normalizedPage = normalizeTitle(page);
          const existingNode = tempNodeMap.get(normalizedPage);
          if (!existingNode) {
            getOrCreateNode(page, 'optimal_path');
          }
          
          // Add edge to next page in path
          if (pageIndex < pages.length - 1) {
            const nextPage = pages[pageIndex + 1];
            
            // Skip if next page is invalid
            if (!nextPage || typeof nextPage !== 'string') {
              console.warn('⚠️ Graph: Invalid next page in optimal path:', nextPage);
              return;
            }
            
            edges.push({
              id: `optimal-${pathIndex}-${pageIndex}`,
              source: normalizeTitle(page),
              target: normalizeTitle(nextPage),
              type: 'optimal_path'
            });
          }
        });
      });
    }

    return { 
      nodes: Array.from(tempNodeMap.values()), 
      edges 
    };
  }

  // =============================================================================
  // Object Constancy - Smooth Updates
  // =============================================================================

  private updateGraphWithConstancy(graphData: GraphData): void {
    console.log('🔄 Graph: Updating with object constancy');
    
    // Identify new nodes for smooth animation
    const newNodeIds = new Set<string>();
    const currentNodeIds = new Set(this.nodes.map(n => n.id));
    
    graphData.nodes.forEach(node => {
      if (!currentNodeIds.has(node.id)) {
        newNodeIds.add(node.id);
        console.log('➕ New node detected:', node.title);
      }
    });

    // Update our stable node map and arrays
    this.updateStableNodeReferences(graphData);

    // Update edges
    this.edges = graphData.edges;

    // Render with constancy - existing nodes maintain positions
    this.renderNodesWithConstancy(newNodeIds);
    this.renderEdges();

    // Only apply gentle simulation to new nodes
    this.applyGentleSimulation(newNodeIds);
  }

  private updateStableNodeReferences(graphData: GraphData): void {
    // Create new node map from incoming data
    const newNodeMap = new Map<string, GraphNode>();
    
    graphData.nodes.forEach(newNode => {
      if (this.nodeMap.has(newNode.id)) {
        // Keep existing node but update properties (preserve position)
        const existingNode = this.nodeMap.get(newNode.id)!;
        existingNode.title = newNode.title;
        existingNode.type = newNode.type;
        existingNode.moveNumber = newNode.moveNumber;
        existingNode.quality = newNode.quality;
        // Don't update x, y, fx, fy - preserve positions for constancy
        newNodeMap.set(newNode.id, existingNode);
      } else {
        // New node - use the provided positioning
        newNodeMap.set(newNode.id, newNode);
      }
    });

    // Update our stable references
    this.nodeMap = newNodeMap;
    this.nodes = Array.from(newNodeMap.values());
  }

  private getNewNodePosition(): { x: number; y: number } {
    // Position new nodes near the center with some randomness
    // They'll be animated to their proper position by the gentle simulation
    const centerX = this.width / 2;
    const centerY = this.height / 2;
    const spread = 100;
    
    return {
      x: centerX + (Math.random() - 0.5) * spread,
      y: centerY + (Math.random() - 0.5) * spread
    };
  }

  private renderNodesWithConstancy(newNodeIds: Set<string>): void {
    // Debug: Check if start node is in our nodes array
    const startNodes = this.nodes.filter(n => n.type === 'start');
    console.log(`🎨 Graph: Rendering ${this.nodes.length} nodes, including ${startNodes.length} start nodes:`, 
                startNodes.map(n => `${n.title} (${n.id})`));
    
    // Bind data to node elements with stable key function
    const nodeSelection = this.nodeGroup
      .selectAll<SVGGElement, GraphNode>('.node')
      .data(this.nodes, (d: GraphNode) => d.id);

    // Remove exiting nodes with smooth transition
    nodeSelection.exit()
      .transition()
      .duration(300)
      .style('opacity', 0)
      .remove();

    // Create new node groups
    const nodeEnter = nodeSelection.enter()
      .append('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .style('opacity', 0) // Start invisible for smooth fade-in
      .attr('transform', (d: GraphNode) => `translate(${d.x},${d.y})`)
      .call(this.setupNodeInteractions.bind(this));

    // Add circles to new nodes
    nodeEnter.append('circle');
    
    // Add labels to new nodes
    nodeEnter.append('text');

    // Animate new nodes in
    nodeEnter
      .filter((d: GraphNode) => newNodeIds.has(d.id))
      .transition()
      .duration(500)
      .style('opacity', 1);

    // Merge enter and update selections
    const nodeUpdate = nodeEnter.merge(nodeSelection);

    // Update circle properties (no transition for existing nodes)
    nodeUpdate.select('circle')
      .attr('r', (d: GraphNode) => this.getNodeRadius(d))
      .attr('fill', (d: GraphNode) => this.getNodeColor(d))
      .attr('stroke', (d: GraphNode) => this.getNodeStroke(d))
      .attr('stroke-width', 3)
      .style('filter', (d: GraphNode) => d.type === 'start' || d.type === 'target' ? 'drop-shadow(0 0 10px rgba(255,255,255,0.5))' : 'none');

    // Update text labels
    nodeUpdate.select('text')
      .text((d: GraphNode) => this.getNodeLabel(d))
      .attr('text-anchor', 'middle')
      .attr('dy', -30)
      .style('fill', '#e2e8f0')
      .style('font-size', '12px')
      .style('font-weight', 'bold')
      .style('text-shadow', '1px 1px 2px rgba(0,0,0,0.8)');

    // Ensure existing nodes remain visible
    nodeUpdate
      .filter((d: GraphNode) => !newNodeIds.has(d.id))
      .style('opacity', 1);
  }

  private applyGentleSimulation(newNodeIds: Set<string>): void {
    // Only restart simulation if we have new nodes or no simulation exists
    if (newNodeIds.size === 0 && this.simulation) {
      return; // No new nodes, no need to restart simulation
    }

    console.log('🔄 Applying gentle simulation for', newNodeIds.size, 'new nodes');

    // Create or update force simulation with reduced intensity
    this.simulation = d3.forceSimulation(this.nodes)
      .force('link', d3.forceLink(this.edges)
        .id((d: any) => d.id)
        .distance(120)
        .strength(0.3)) // Reduced strength for gentler movement
      .force('charge', d3.forceManyBody()
        .strength(-200)) // Reduced repulsion
      .force('center', d3.forceCenter(this.width / 2, this.height / 2))
      .force('collision', d3.forceCollide(35))
      // Gentle positioning forces
      .force('position', d3.forceX().strength((d: any) => {
        // Strong constraint for start/target, weak for existing nodes, medium for new
        if (d.type === 'start' || d.type === 'target') return 0.8;
        if (newNodeIds.has(d.id)) return 0.1; // Gentle pull for new nodes
        return 0.01; // Very weak for existing nodes
      }).x(this.width / 2))
      .force('positionY', d3.forceY().strength((d: any) => {
        if (d.type === 'start' || d.type === 'target') return 1.0;
        if (newNodeIds.has(d.id)) return 0.1; // Gentle pull for new nodes
        return 0.01; // Very weak for existing nodes
      }).y((d: any) => {
        if (d.type === 'start') return 40;
        if (d.type === 'target') return this.height - 40;
        return this.height / 2;
      }));

    // Set up tick handler with gentle movement
    this.simulation.on('tick', () => {
      // Enforce fixed positions for special nodes
      this.nodes.forEach(node => {
        if (node.type === 'target') {
          node.x = this.width / 2;
          node.y = this.height - 40;
          node.fx = this.width / 2;
          node.fy = this.height - 40;
        } else if (node.type === 'start') {
          node.x = this.width / 2;
          node.y = 40;
          node.fx = this.width / 2;
          node.fy = 40;
        }
      });
      
      // Smooth position updates
      this.nodeGroup.selectAll<SVGGElement, GraphNode>('.node')
        .attr('transform', (d: GraphNode) => `translate(${d.x},${d.y})`);

      // Update edge positions
      this.updateEdgePositions();
    });

    // Gentle restart - lower alpha for smoother movement
    this.simulation.alpha(0.3).restart();
    
    // Stop simulation sooner to reduce unnecessary movement
    this.simulation.on('end', () => {
      console.log('✅ Gentle simulation completed');
    });
  }

  // =============================================================================
  // Graph Rendering
  // =============================================================================

  private renderEdges(): void {
    // Bind data to edge elements
    const edgeSelection = this.edgeGroup
      .selectAll<SVGLineElement, GraphEdge>('.edge')
      .data(this.edges, (d: GraphEdge) => d.id);

    // Remove exiting edges
    edgeSelection.exit().remove();

    // Create new edges
    const edgeEnter = edgeSelection.enter()
      .append('line')
      .attr('class', 'edge');

    // Merge enter and update selections
    const edgeUpdate = edgeEnter.merge(edgeSelection);

    // Update edge properties based on type
    edgeUpdate
      .attr('stroke', (d: GraphEdge) => d.type === 'optimal_path' ? '#64748b' : '#64748b')
      .attr('stroke-width', (d: GraphEdge) => d.type === 'optimal_path' ? 2 : 3)
      .attr('stroke-opacity', (d: GraphEdge) => d.type === 'optimal_path' ? 0.4 : 0.9)
      .attr('stroke-dasharray', (d: GraphEdge) => d.type === 'optimal_path' ? '5,5' : 'none')
      .style('marker-end', 'url(#arrowhead)');
  }

  private updateEdgePositions(): void {
    this.edgeGroup.selectAll<SVGLineElement, GraphEdge>('.edge')
      .attr('x1', (d: GraphEdge) => (d.source as any).x)
      .attr('y1', (d: GraphEdge) => (d.source as any).y)
      .attr('x2', (d: GraphEdge) => (d.target as any).x)
      .attr('y2', (d: GraphEdge) => (d.target as any).y);
  }

  // =============================================================================
  // Node Styling
  // =============================================================================

  private getNodeRadius(node: GraphNode): number {
    switch (node.type) {
      case 'start':
      case 'target':
        return 25;
      case 'move':
        return 20;
      case 'optimal_path':
        return 15;
      default:
        return 18;
    }
  }

  private getNodeColor(node: GraphNode): string {
    switch (node.type) {
      case 'start':
        return 'url(#start-gradient)';
      case 'target':
        return 'url(#target-gradient)';
      case 'move':
        return this.getMoveNodeColor(node.quality);
      case 'optimal_path':
        return '#374151';
      default:
        return '#64748b';
    }
  }

  private getMoveNodeColor(quality?: string): string {
    switch (quality) {
      case 'good':
        return '#10b981'; // Green
      case 'bad':
        return '#ef4444'; // Red
      case 'neutral':
      default:
        return '#64748b'; // Gray
    }
  }

  private getNodeStroke(node: GraphNode): string {
    switch (node.type) {
      case 'start':
        return '#059669';
      case 'target':
        return '#d97706';
      case 'move':
        return this.getMoveNodeStroke(node.quality);
      default:
        return '#475569';
    }
  }

  private getMoveNodeStroke(quality?: string): string {
    switch (quality) {
      case 'good':
        return '#059669';
      case 'bad':
        return '#dc2626';
      case 'neutral':
      default:
        return '#475569';
    }
  }

  private getNodeLabel(node: GraphNode): string {
    let label = node.title // this.truncateLabel(node.title, 12);
    
    // if (node.type === 'start') {
    //   label = `🏁 ${label}`;
    // } else if (node.type === 'target') {
    //   label = `🎯 ${label}`;
    // } else if (node.type === 'move') {
    //   label = `${label}`;
    // }
    
    return label;
  }

  // =============================================================================
  // Interactions
  // =============================================================================

  private setupNodeInteractions(selection: d3.Selection<SVGGElement, GraphNode, SVGGElement, unknown>): void {
    selection
      .on('mouseover', this.handleNodeHover.bind(this))
      .on('mouseout', this.handleNodeUnhover.bind(this))
      .on('click', this.handleNodeClick.bind(this));
  }

  private handleNodeHover(_event: MouseEvent, node: GraphNode): void {
    // Highlight connected edges
    this.edgeGroup.selectAll('.edge')
      .style('stroke-opacity', (d: any) => 
        (d.source as any).id === node.id || (d.target as any).id === node.id ? 1 : 0.2
      );

    console.log('Hovering node:', node.title);
  }

  private handleNodeUnhover(): void {
    // Reset edge opacity
    this.edgeGroup.selectAll('.edge')
      .style('stroke-opacity', 0.9);
  }

  private handleNodeClick(_event: MouseEvent, node: GraphNode): void {
    console.log('Clicked node:', node.title, node.type);
  }


  // =============================================================================
  // Public API
  // =============================================================================

  clear(): void {
    this.nodeGroup.selectAll('*').remove();
    this.edgeGroup.selectAll('*').remove();
    this.pathGroup.selectAll('*').remove();
    this.nodes = [];
    this.edges = [];
    this.nodeMap.clear(); // Clear stable references
    
    if (this.simulation) {
      this.simulation.stop();
    }
  }

  resize(): void {
    const rect = this.container.getBoundingClientRect();
    const newWidth = rect.width || window.innerWidth;
    const newHeight = rect.height || window.innerHeight;
    
    // Only resize if dimensions actually changed
    if (newWidth !== this.width || newHeight !== this.height) {
      const oldWidth = this.width;
      const oldHeight = this.height;
      
      this.width = newWidth;
      this.height = newHeight;

      this.svg
        .attr('width', this.width)
        .attr('height', this.height);

      // Update start/target node positions to maintain their fixed positions
      this.nodes.forEach(node => {
        if (node.type === 'start') {
          node.x = this.width * 0.5;
          node.y = 40;
          node.fx = this.width * 0.5; // Update fixed x position
          node.fy = 40; // Update fixed y position
        } else if (node.type === 'target') {
          node.x = this.width * 0.5;
          node.y = this.height - 40;
          node.fx = this.width * 0.5; // Update fixed x position
          node.fy = this.height - 40; // Update fixed y position
        } else if (node.x !== undefined && node.y !== undefined && oldWidth > 0 && oldHeight > 0) {
          // Scale other nodes proportionally
          node.x = (node.x / oldWidth) * this.width;
          node.y = (node.y / oldHeight) * this.height;
        }
      });

      // Update center force if simulation exists
      if (this.simulation) {
        this.simulation
          .force('center', d3.forceCenter(this.width / 2, this.height / 2))
          .alpha(0.3)
          .restart();
      }
    }
  }

  centerGraph(): void {
    if (this.nodes.length === 0) return;

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
      minX: Math.min(...this.nodes.map(n => n.x || 0)),
      maxX: Math.max(...this.nodes.map(n => n.x || 0)),
      minY: Math.min(...this.nodes.map(n => n.y || 0)),
      maxY: Math.max(...this.nodes.map(n => n.y || 0))
    };
  }
}
