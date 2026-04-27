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
  private nodes: LoadingNode[] = [];
  private edges: LoadingEdge[] = [];
  private currentStep = 0;
  private isAnimating = false;
  private animationTimer: number | null = null;
  private readonly animationWidth: number;
  private readonly animationHeight: number;
  private readonly levels: number;
  private readonly levelHeight: number;
  private readonly nodeRadius = 12;
  private readonly stepTime: number;
  private readonly markerId: string;

  constructor(
    private readonly container: HTMLElement,
    width = 200,
    height = 300,
    levels = 6,
    stepTime = 300,
  ) {
    this.animationWidth = width;
    this.animationHeight = height;
    this.levels = levels;
    this.levelHeight = this.animationHeight / (this.levels - 1);
    this.stepTime = stepTime;
    this.markerId = `loading-arrowhead-${Math.random().toString(36).slice(2)}`;
    this.initializeAnimation();
  }

  start(): void {
    this.stop();
    this.show();
    this.resetAnimation();
    this.isAnimating = true;

    const animate = (): void => {
      if (this.isAnimating && this.currentStep < this.levels - 1) {
        this.animateStep();
        this.animationTimer = window.setTimeout(animate, this.stepTime);
      } else if (this.currentStep >= this.levels - 1) {
        this.animationTimer = window.setTimeout(() => {
          if (this.isAnimating) {
            this.start();
          }
        }, this.stepTime * 1.5);
      }
    };

    this.animationTimer = window.setTimeout(animate, 100);
  }

  stop(): void {
    this.isAnimating = false;
    if (this.animationTimer !== null) {
      window.clearTimeout(this.animationTimer);
      this.animationTimer = null;
    }
  }

  show(): void {
    const animationContainer = this.container.querySelector<HTMLElement>(".loading-animation-container");
    this.container.classList.remove("hidden");
    if (animationContainer !== null) {
      animationContainer.style.display = "flex";
    }
  }

  hide(): void {
    const animationContainer = this.container.querySelector<HTMLElement>(".loading-animation-container");
    if (animationContainer !== null) {
      animationContainer.style.display = "none";
    }
    this.container.classList.add("hidden");
    this.stop();
    this.clearAnimation();
    this.currentStep = 0;
  }

  destroy(): void {
    this.stop();
    this.container.innerHTML = "";
  }

  private initializeAnimation(): void {
    this.container.innerHTML = "";
    const animationContainer = document.createElement("div");
    animationContainer.className = "loading-animation-container";
    animationContainer.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(255, 255, 255, 0.86);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100;
    `;

    const animationWrapper = document.createElement("div");
    animationWrapper.style.cssText = `
      position: relative;
      width: ${this.animationWidth + 80}px;
      height: ${this.animationHeight + 80}px;
    `;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", (this.animationWidth + 80).toString());
    svg.setAttribute("height", (this.animationHeight + 80).toString());
    svg.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
    `;

    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", this.markerId);
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "6");
    marker.setAttribute("refX", "7");
    marker.setAttribute("refY", "3");
    marker.setAttribute("orient", "auto");

    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    polygon.setAttribute("points", "0 0, 8 3, 0 6");
    polygon.setAttribute("fill", "#111111");

    marker.appendChild(polygon);
    defs.appendChild(marker);
    svg.appendChild(defs);
    animationWrapper.appendChild(svg);
    animationContainer.appendChild(animationWrapper);
    this.container.appendChild(animationContainer);
    this.hide();
    this.resetAnimation();
  }

  private clearAnimation(): void {
    const svg = this.container.querySelector("svg");
    if (svg === null) {
      return;
    }
    svg.querySelectorAll('.loading-node:not([data-node-id="start"]):not([data-node-id="target"])').forEach((node) => node.remove());
    svg.querySelectorAll(".loading-edge").forEach((edge) => edge.remove());
  }

  private resetAnimation(): void {
    this.clearAnimation();
    const startNode: LoadingNode = {
      id: "start",
      x: this.animationWidth / 2,
      y: 0,
      level: 0,
    };
    const targetNode: LoadingNode = {
      id: "target",
      x: this.animationWidth / 2,
      y: this.animationHeight,
      level: this.levels - 1,
    };
    this.nodes = [startNode, targetNode];
    this.edges = [];
    this.currentStep = 0;
    window.setTimeout(() => {
      this.renderNodes();
      this.renderEdges();
    }, 50);
  }

  private getRandomX(): number {
    const margin = 40;
    return margin + Math.random() * (this.animationWidth - 2 * margin);
  }

  private calculateEdgePoints(fromNode: LoadingNode, toNode: LoadingNode): Omit<LoadingEdge, "from" | "to"> {
    const dx = toNode.x - fromNode.x;
    const dy = toNode.y - fromNode.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    if (length === 0) {
      return {
        fromX: fromNode.x,
        fromY: fromNode.y,
        toX: toNode.x,
        toY: toNode.y,
      };
    }
    const unitX = dx / length;
    const unitY = dy / length;
    return {
      fromX: fromNode.x + unitX * this.nodeRadius,
      fromY: fromNode.y + unitY * this.nodeRadius,
      toX: toNode.x - unitX * this.nodeRadius,
      toY: toNode.y - unitY * this.nodeRadius,
    };
  }

  private renderNodes(): void {
    const svg = this.container.querySelector("svg");
    if (svg === null) {
      return;
    }
    this.nodes.forEach((node) => {
      const existingNode = svg.querySelector(`[data-node-id="${node.id}"]`);
      if (existingNode !== null) {
        return;
      }
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.classList.add("loading-node");
      circle.setAttribute("data-node-id", node.id);
      circle.setAttribute("cx", (node.x + 40).toString());
      circle.setAttribute("cy", (node.y + 40).toString());
      circle.setAttribute("r", this.nodeRadius.toString());
      circle.setAttribute("fill", "transparent");
      circle.setAttribute("stroke", "#111111");
      circle.setAttribute("stroke-width", "2");
      circle.style.opacity = "0";
      circle.style.transition = "opacity 0.5s ease";
      svg.appendChild(circle);
      window.setTimeout(() => {
        circle.style.opacity = "1";
      }, 100);
    });
  }

  private renderEdges(): void {
    const svg = this.container.querySelector("svg");
    if (svg === null) {
      return;
    }
    this.edges.forEach((edge) => {
      const edgeId = `${edge.from}-${edge.to}`;
      const existingEdge = svg.querySelector(`[data-edge-id="${edgeId}"]`);
      if (existingEdge !== null) {
        return;
      }
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.classList.add("loading-edge");
      line.setAttribute("data-edge-id", edgeId);
      line.setAttribute("x1", (edge.fromX + 40).toString());
      line.setAttribute("y1", (edge.fromY + 40).toString());
      line.setAttribute("x2", (edge.toX + 40).toString());
      line.setAttribute("y2", (edge.toY + 40).toString());
      line.setAttribute("stroke", "#111111");
      line.setAttribute("stroke-width", "2");
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("marker-end", `url(#${this.markerId})`);
      line.style.opacity = "0";
      line.style.transition = "opacity 0.5s ease";
      svg.appendChild(line);
      window.setTimeout(() => {
        line.style.opacity = "1";
      }, 100);
    });
  }

  private animateStep(): void {
    if (this.currentStep >= this.levels - 1) {
      return;
    }
    if (this.currentStep < this.levels - 2) {
      const newNode: LoadingNode = {
        id: `step-${this.currentStep + 1}`,
        x: this.getRandomX(),
        y: (this.currentStep + 1) * this.levelHeight,
        level: this.currentStep + 1,
      };
      this.nodes.push(newNode);
      if (this.currentStep === 0) {
        const startNode = this.nodes.find((node) => node.id === "start");
        if (startNode !== undefined) {
          this.edges.push({
            from: "start",
            to: newNode.id,
            ...this.calculateEdgePoints(startNode, newNode),
          });
        }
      } else {
        const previousNode = this.nodes.find((node) => node.level === this.currentStep);
        if (previousNode !== undefined) {
          this.edges.push({
            from: previousNode.id,
            to: newNode.id,
            ...this.calculateEdgePoints(previousNode, newNode),
          });
        }
      }
    } else if (this.currentStep === this.levels - 2) {
      const lastNode = this.nodes.find((node) => node.level === this.levels - 2);
      const targetNode = this.nodes.find((node) => node.id === "target");
      if (lastNode !== undefined && targetNode !== undefined) {
        this.edges.push({
          from: lastNode.id,
          to: "target",
          ...this.calculateEdgePoints(lastNode, targetNode),
        });
      }
    }
    this.currentStep += 1;
    this.renderNodes();
    this.renderEdges();
  }
}
