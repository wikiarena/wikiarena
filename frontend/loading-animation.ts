interface LoadingNode {
  id: string;
  x: number;
  y: number;
  level: number;
}

interface LoadingEdge {
  from: string;
  to: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

export class LoadingAnimation {
  private container: HTMLElement;
  private nodes: LoadingNode[] = [];
  private edges: LoadingEdge[] = [];
  private currentStep: number = 0;
  private isAnimating: boolean = false;
  private animationTimer: number | null = null;
  
  private readonly ANIMATION_WIDTH = 200;
  private readonly ANIMATION_HEIGHT = 300;
  private readonly LEVELS = 6; // start(0) + 4 intermediate(1-4) + target(5)
  private readonly LEVEL_HEIGHT = this.ANIMATION_HEIGHT / (this.LEVELS - 1);
  private readonly NODE_RADIUS = 12;

  constructor(containerId: string) {
    const container = document.getElementById(containerId);
    if (!container) {
      throw new Error(`Container element with id '${containerId}' not found`);
    }
    this.container = container;
    this.initializeAnimation();
  }

  private initializeAnimation(): void {
    // Clear any existing content
    this.container.innerHTML = '';
    
    // Create the loading animation container
    const animationContainer = document.createElement('div');
    animationContainer.className = 'loading-animation-container';
    animationContainer.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: #0d1117;
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100;
    `;

    const animationWrapper = document.createElement('div');
    animationWrapper.style.cssText = `
      position: relative;
      width: ${this.ANIMATION_WIDTH + 80}px;
      height: ${this.ANIMATION_HEIGHT + 80}px;
    `;

    // Create SVG
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', (this.ANIMATION_WIDTH + 80).toString());
    svg.setAttribute('height', (this.ANIMATION_HEIGHT + 80).toString());
    svg.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
    `;

    // Create arrow marker
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'loading-arrowhead');
    marker.setAttribute('markerWidth', '8');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('refX', '7');
    marker.setAttribute('refY', '3');
    marker.setAttribute('orient', 'auto');

    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    polygon.setAttribute('points', '0 0, 8 3, 0 6');
    polygon.setAttribute('fill', 'white');

    marker.appendChild(polygon);
    defs.appendChild(marker);
    svg.appendChild(defs);

    animationWrapper.appendChild(svg);
    animationContainer.appendChild(animationWrapper);
    this.container.appendChild(animationContainer);

    // Initialize hidden
    this.hide();
    this.resetAnimation();
  }

  private clearAnimation(): void {
    const svg = this.container.querySelector('svg') as SVGSVGElement;
    if (!svg) return;

    // Remove all animation elements
    const existingNodes = svg.querySelectorAll('.loading-node');
    const existingEdges = svg.querySelectorAll('.loading-edge');
    
    existingNodes.forEach(node => node.remove());
    existingEdges.forEach(edge => edge.remove());
  }

  private resetAnimation(): void {
    // Clear any existing animation elements first
    this.clearAnimation();
    
    const startNode: LoadingNode = {
      id: 'start',
      x: this.ANIMATION_WIDTH / 2,
      y: 0,
      level: 0
    };
    
    const targetNode: LoadingNode = {
      id: 'target',
      x: this.ANIMATION_WIDTH / 2,
      y: this.ANIMATION_HEIGHT,
      level: 5
    };

    this.nodes = [startNode, targetNode];
    this.edges = [];
    this.currentStep = 0;
    
    // Slight delay to ensure DOM is ready
    setTimeout(() => {
      this.renderNodes();
      this.renderEdges();
    }, 50);
  }

  private getRandomX(): number {
    const margin = 40;
    return margin + Math.random() * (this.ANIMATION_WIDTH - 2 * margin);
  }

  private calculateEdgePoints(fromNode: LoadingNode, toNode: LoadingNode) {
    const dx = toNode.x - fromNode.x;
    const dy = toNode.y - fromNode.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    
    if (length === 0) return { fromX: fromNode.x, fromY: fromNode.y, toX: toNode.x, toY: toNode.y };
    
    const unitX = dx / length;
    const unitY = dy / length;
    
    // Start point: edge of from-node circle
    const fromX = fromNode.x + unitX * this.NODE_RADIUS;
    const fromY = fromNode.y + unitY * this.NODE_RADIUS;
    
    // End point: edge of to-node circle  
    const toX = toNode.x - unitX * this.NODE_RADIUS;
    const toY = toNode.y - unitY * this.NODE_RADIUS;
    
    return { fromX, fromY, toX, toY };
  }

  private renderNodes(): void {
    const svg = this.container.querySelector('svg') as SVGSVGElement;
    if (!svg) return;

    // Only add new nodes, don't clear existing ones
    this.nodes.forEach(node => {
      // Check if this node already exists
      const existingNode = svg.querySelector(`[data-node-id="${node.id}"]`);
      if (existingNode) return; // Skip if already rendered

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.classList.add('loading-node');
      circle.setAttribute('data-node-id', node.id); // Add identifier for tracking
      circle.setAttribute('cx', (node.x + 40).toString());
      circle.setAttribute('cy', (node.y + 40).toString());
      circle.setAttribute('r', this.NODE_RADIUS.toString());
      circle.setAttribute('fill', 'transparent');
      circle.setAttribute('stroke', 'white');
      circle.setAttribute('stroke-width', '2');
      circle.style.opacity = '0';
      circle.style.transition = 'opacity 0.5s ease';

      svg.appendChild(circle);

      // Animate node in
      setTimeout(() => {
        circle.style.opacity = '1';
      }, 100);
    });
  }

  private renderEdges(): void {
    const svg = this.container.querySelector('svg') as SVGSVGElement;
    if (!svg) return;

    // Only add new edges, don't clear existing ones
    this.edges.forEach((edge, index) => {
      const edgeId = `${edge.from}-${edge.to}`;
      
      // Check if this edge already exists
      const existingEdge = svg.querySelector(`[data-edge-id="${edgeId}"]`);
      if (existingEdge) return; // Skip if already rendered

      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.classList.add('loading-edge');
      line.setAttribute('data-edge-id', edgeId); // Add identifier for tracking
      line.setAttribute('x1', (edge.fromX + 40).toString());
      line.setAttribute('y1', (edge.fromY + 40).toString());
      line.setAttribute('x2', (edge.toX + 40).toString());
      line.setAttribute('y2', (edge.toY + 40).toString());
      line.setAttribute('stroke', 'white');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('marker-end', 'url(#loading-arrowhead)');
      line.style.opacity = '0';
      line.style.transition = 'opacity 0.5s ease';

      svg.appendChild(line);

      // Animate edge in
      setTimeout(() => {
        line.style.opacity = '1';
      }, 100);
    });
  }

  private animateStep(): void {
    if (this.currentStep >= 5) return;

    if (this.currentStep < 4) {
      // Add intermediate node
      const newNode: LoadingNode = {
        id: `step-${this.currentStep + 1}`,
        x: this.getRandomX(),
        y: (this.currentStep + 1) * this.LEVEL_HEIGHT,
        level: this.currentStep + 1
      };

      this.nodes.push(newNode);

      // Add edge
      if (this.currentStep === 0) {
        // Edge from start to first intermediate node
        const startNode = this.nodes.find(n => n.id === 'start')!;
        const edgePoints = this.calculateEdgePoints(startNode, newNode);
        this.edges.push({
          from: 'start',
          to: newNode.id,
          ...edgePoints
        });
      } else {
        // Edge from previous intermediate node to current intermediate node
        const prevNode = this.nodes.find(n => n.level === this.currentStep)!;
        const edgePoints = this.calculateEdgePoints(prevNode, newNode);
        this.edges.push({
          from: prevNode.id,
          to: newNode.id,
          ...edgePoints
        });
      }
    } else if (this.currentStep === 4) {
      // Final edge from last intermediate node to target
      const lastNode = this.nodes.find(n => n.level === 4)!;
      const targetNode = this.nodes.find(n => n.id === 'target')!;
      const edgePoints = this.calculateEdgePoints(lastNode, targetNode);
      
      this.edges.push({
        from: lastNode.id,
        to: 'target',
        ...edgePoints
      });
    }

    this.currentStep++;
    this.renderNodes();
    this.renderEdges();
  }

  public start(): void {
    // Stop any existing animation first
    this.stop();
    
    // Reset to clean state
    this.resetAnimation();
    this.isAnimating = true;
    
    const animate = () => {
      if (this.isAnimating && this.currentStep < 5) {
        this.animateStep();
        this.animationTimer = window.setTimeout(animate, 300); // step speed
      } else if (this.currentStep >= 5) {
        // Auto-restart after a brief pause for seamless looping
        this.animationTimer = window.setTimeout(() => {
          if (this.isAnimating) { // Only restart if still animating
            this.start();
          }
        }, 500); // pause between loops
      }
    };

    // Start animation after a brief delay
    this.animationTimer = window.setTimeout(animate, 100);
  }

  public stop(): void {
    this.isAnimating = false;
    if (this.animationTimer) {
      clearTimeout(this.animationTimer);
      this.animationTimer = null;
    }
  }

  public show(): void {
    const animationContainer = this.container.querySelector('.loading-animation-container') as HTMLElement;
    if (animationContainer) {
      animationContainer.style.display = 'flex';
    }
  }

  public hide(): void {
    const animationContainer = this.container.querySelector('.loading-animation-container') as HTMLElement;
    if (animationContainer) {
      animationContainer.style.display = 'none';
    }
    this.stop();
    
    // Reset to initial state to prevent ghost frames when showing again
    this.resetAnimation();
  }

  public destroy(): void {
    this.stop();
    this.container.innerHTML = '';
  }
} 