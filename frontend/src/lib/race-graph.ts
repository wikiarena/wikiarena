import * as d3 from "d3";

import type { ParticipantTrack, RaceViewState } from "./race-types";

interface PageNode extends d3.SimulationNodeDatum {
  pageTitle: string;
  type: "start" | "target" | "visited";
  distanceToTarget?: number | null;
  visits: Array<{
    runId: string;
    moveIndex: number;
    distanceChange?: number | null;
  }>;
  currentRunIds: string[];
}

interface NavigationEdge {
  id: string;
  runId: string;
  sourcePageTitle: string;
  targetPageTitle: string;
  moveIndex: number;
  distanceChange?: number | null;
}

interface PageGraphData {
  pages: PageNode[];
  edges: NavigationEdge[];
  colorMap: Map<string, string>;
}

interface OrbitSystem {
  centerX: number;
  centerY: number;
  startX: number;
  startY: number;
  startDistance: number;
  orbitRadius(distance: number): number;
}

interface GraphAnchors {
  targetX: number;
  targetY: number;
  startX: number;
  startY: number;
}

const renderers = new WeakMap<HTMLElement, RaceGraphRenderer>();

export function renderRaceGraph(container: HTMLElement, state: RaceViewState): void {
  let renderer = renderers.get(container);
  if (renderer === undefined) {
    renderer = new RaceGraphRenderer(container);
    renderers.set(container, renderer);
  }
  renderer.update(buildPageGraphData(state));
}

class RaceGraphRenderer {
  private readonly container: HTMLElement;
  private readonly svg: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  private readonly rootGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
  private readonly orbitGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
  private readonly edgeGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
  private readonly nodeGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
  private readonly zoom: d3.ZoomBehavior<SVGSVGElement, unknown>;
  private simulation: d3.Simulation<PageNode, undefined> | null = null;
  private pages: PageNode[] = [];
  private edges: NavigationEdge[] = [];
  private pageMap = new Map<string, PageNode>();
  private colorMap = new Map<string, string>();
  private orbitSystem: OrbitSystem | null = null;
  private viewportWidth = 900;
  private viewportHeight = 680;
  private width = 1800;
  private height = 1360;

  constructor(container: HTMLElement) {
    this.container = container;
    this.container.innerHTML = "";
    this.measure();
    this.svg = d3.select(this.container).append("svg")
      .attr("class", "race-physics-svg")
      .attr("width", this.viewportWidth)
      .attr("height", this.viewportHeight);
    this.rootGroup = this.svg.append("g");
    this.orbitGroup = this.rootGroup.append("g").attr("class", "race-orbits");
    this.edgeGroup = this.rootGroup.append("g").attr("class", "race-edges");
    this.nodeGroup = this.rootGroup.append("g").attr("class", "race-nodes");
    this.zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.35, 3])
      .on("zoom", (event) => {
        this.rootGroup.attr("transform", event.transform);
      });
    this.svg.call(this.zoom);
    this.centerInitialView();
  }

  update(data: PageGraphData): void {
    this.colorMap = data.colorMap;
    this.edges = data.edges;
    const previousPages = new Map(this.pageMap);
    const nextPages = new Map<string, PageNode>();
    for (const page of data.pages) {
      const previousPage = previousPages.get(page.pageTitle);
      if (previousPage !== undefined) {
        previousPage.type = page.type;
        previousPage.distanceToTarget = page.distanceToTarget;
        previousPage.visits = page.visits;
        previousPage.currentRunIds = page.currentRunIds;
        nextPages.set(page.pageTitle, previousPage);
      } else {
        const positionedPage = { ...page, ...this.spawnPosition(page, nextPages) };
        if (positionedPage.type === "start" || positionedPage.type === "target") {
          positionedPage.fx = positionedPage.x;
          positionedPage.fy = positionedPage.y;
        }
        nextPages.set(page.pageTitle, positionedPage);
      }
    }
    this.pageMap = nextPages;
    this.pages = [...nextPages.values()].sort((left, right) => this.nodeRenderOrder(left) - this.nodeRenderOrder(right));
    this.orbitSystem = this.calculateOrbitSystem();
    this.renderOrbits();
    this.renderEdges();
    this.renderNodes();
    this.restartSimulation();
  }

  private measure(): void {
    const rect = this.container.getBoundingClientRect();
    this.viewportWidth = Math.max(640, rect.width || 900);
    this.viewportHeight = Math.max(560, rect.height || 680);
    this.width = this.viewportWidth * 2;
    this.height = this.viewportHeight * 2;
  }

  private centerInitialView(): void {
    const transform = d3.zoomIdentity
      .translate(this.viewportWidth / 2 - this.width / 2, this.viewportHeight / 2 - this.height / 2)
      .scale(1);
    this.svg.call(this.zoom.transform, transform);
  }

  private calculateOrbitSystem(): OrbitSystem {
    const startNode = this.pages.find((page) => page.type === "start");
    const targetNode = this.pages.find((page) => page.type === "target");
    const centerX = targetNode?.x ?? this.width / 2;
    const centerY = targetNode?.y ?? this.height * 0.62;
    const startX = startNode?.x ?? this.width / 2;
    const startY = startNode?.y ?? this.height * 0.23;
    const startDistance = Math.max(1, startNode?.distanceToTarget ?? 4);
    const totalPixelDistance = Math.hypot(startX - centerX, startY - centerY);
    const orbitSpacing = Math.max(36, totalPixelDistance / startDistance);
    return {
      centerX,
      centerY,
      startX,
      startY,
      startDistance,
      orbitRadius: (distance: number) => distance * orbitSpacing,
    };
  }

  private spawnPosition(page: PageNode, positionedPages: Map<string, PageNode>): { x: number; y: number } {
    const orbitSystem = this.orbitSystem ?? this.calculateFallbackOrbitSystem();
    if (page.type === "target") {
      return { x: orbitSystem.centerX, y: orbitSystem.centerY };
    }
    if (page.type === "start") {
      return { x: orbitSystem.startX, y: orbitSystem.startY };
    }
    const firstVisit = page.visits[0];
    const parentEdge = this.edges.find((edge) => edge.runId === firstVisit?.runId && edge.targetPageTitle === page.pageTitle && edge.moveIndex === firstVisit.moveIndex);
    const parentNode = parentEdge === undefined ? undefined : positionedPages.get(parentEdge.sourcePageTitle) ?? this.pageMap.get(parentEdge.sourcePageTitle);
    if (parentNode?.x !== undefined && parentNode.y !== undefined) {
      const distanceToCenter = Math.hypot(orbitSystem.centerX - parentNode.x, orbitSystem.centerY - parentNode.y) || 1;
      const unitX = (orbitSystem.centerX - parentNode.x) / distanceToCenter;
      const unitY = (orbitSystem.centerY - parentNode.y) / distanceToCenter;
      const spacing = orbitSystem.orbitRadius(1);
      const playerIndex = [...this.colorMap.keys()].indexOf(firstVisit.runId);
      const isCounterClockwise = playerIndex === -1 || playerIndex % 2 === 0;
      return {
        x: parentNode.x + (isCounterClockwise ? -unitY : unitY) * spacing,
        y: parentNode.y + (isCounterClockwise ? unitX : -unitX) * spacing,
      };
    }
    return { x: this.width / 2, y: this.height / 2 };
  }

  private calculateFallbackOrbitSystem(): OrbitSystem {
    const anchors = this.calculateGraphAnchors();
    return {
      centerX: anchors.targetX,
      centerY: anchors.targetY,
      startX: anchors.startX,
      startY: anchors.startY,
      startDistance: 4,
      orbitRadius: (distance: number) => distance * 64,
    };
  }

  private calculateGraphAnchors(): GraphAnchors {
    const visibleLeft = this.width / 4;
    const visibleTop = this.height / 4;
    const centerScreenX = this.viewportWidth / 2;
    const hudTop = document.querySelector<HTMLElement>(".race-result-hud")?.getBoundingClientRect().top ?? this.viewportHeight - 120;
    const moveListsBottom = document.querySelector<HTMLElement>(".player-dropdowns-container")?.getBoundingClientRect().bottom ?? 104;
    const targetScreenY = clamp(hudTop - 72, this.viewportHeight * 0.42, this.viewportHeight - 150);
    const startScreenY = clamp(this.viewportHeight * 0.24, moveListsBottom + 44, targetScreenY - 220);
    return {
      targetX: visibleLeft + centerScreenX,
      targetY: visibleTop + targetScreenY,
      startX: visibleLeft + centerScreenX,
      startY: visibleTop + startScreenY,
    };
  }

  private restartSimulation(): void {
    if (this.simulation !== null) {
      this.simulation.stop();
    }
    if (this.orbitSystem === null) {
      return;
    }
    const links = this.edges.map((edge) => ({
      source: edge.sourcePageTitle,
      target: edge.targetPageTitle,
      ...edge,
    }));
    this.simulation = d3.forceSimulation(this.pages)
      .force("charge", d3.forceManyBody<PageNode>().strength(0).distanceMax(500))
      .force("link", d3.forceLink<PageNode, d3.SimulationLinkDatum<PageNode>>(links)
        .id((node) => node.pageTitle)
        .distance(60)
        .strength((edge) => this.linkStrength(edge as unknown as NavigationEdge)))
      .force("collision", d3.forceCollide<PageNode>().radius((node) => this.pageRadius(node)).strength(0.8))
      .force("orbital", this.orbitalForce(this.orbitSystem))
      .alphaDecay(0.01)
      .velocityDecay(0.6)
      .on("tick", () => this.tick());
    this.simulation.alpha(0.5).restart();
  }

  private orbitalForce(orbitSystem: OrbitSystem): (alpha: number) => void {
    return (alpha: number) => {
      for (const node of this.pages) {
        if (node.type === "start" || node.type === "target" || node.distanceToTarget === undefined || node.distanceToTarget === null) {
          continue;
        }
        const currentRadius = Math.hypot((node.x ?? 0) - orbitSystem.centerX, (node.y ?? 0) - orbitSystem.centerY);
        if (currentRadius <= 0) {
          continue;
        }
        const targetRadius = orbitSystem.orbitRadius(node.distanceToTarget);
        const radiusError = targetRadius - currentRadius;
        const forceStrength = alpha * 0.8;
        node.vx = (node.vx ?? 0) + (((node.x ?? 0) - orbitSystem.centerX) / currentRadius) * radiusError * forceStrength;
        node.vy = (node.vy ?? 0) + (((node.y ?? 0) - orbitSystem.centerY) / currentRadius) * radiusError * forceStrength;
      }
    };
  }

  private tick(): void {
    const margin = 60;
    const bounds = this.calculateNodeBounds(margin);
    for (const page of this.pages) {
      page.x = Math.max(bounds.left, Math.min(bounds.right, page.x ?? 0));
      page.y = Math.max(bounds.top, Math.min(bounds.bottom, page.y ?? 0));
    }
    this.nodeGroup.selectAll<SVGGElement, PageNode>(".race-node")
      .attr("transform", (node) => `translate(${node.x ?? 0},${node.y ?? 0})`);
    this.updateEdgePositions();
  }

  private calculateNodeBounds(margin: number): { left: number; right: number; top: number; bottom: number } {
    if (this.orbitSystem === null) {
      return { left: margin, right: this.width - margin, top: margin, bottom: this.height - margin };
    }
    const maxDistance = Math.max(this.orbitSystem.startDistance + 1, ...this.pages.map((page) => page.distanceToTarget ?? 0));
    const radius = this.orbitSystem.orbitRadius(maxDistance) + margin * 2;
    return {
      left: this.orbitSystem.centerX - radius,
      right: this.orbitSystem.centerX + radius,
      top: this.orbitSystem.centerY - radius,
      bottom: this.orbitSystem.centerY + radius,
    };
  }

  private renderOrbits(): void {
    if (this.orbitSystem === null) {
      return;
    }
    const maxDistance = Math.max(this.orbitSystem.startDistance + 1, ...this.pages.map((page) => page.distanceToTarget ?? 0));
    const distances = Array.from({ length: maxDistance }, (_, index) => index + 1);
    const rings = this.orbitGroup.selectAll<SVGCircleElement, number>(".race-orbit-ring").data(distances, (distance) => String(distance));
    rings.exit().remove();
    rings.enter().append("circle").attr("class", "race-orbit-ring").merge(rings)
      .attr("cx", this.orbitSystem.centerX)
      .attr("cy", this.orbitSystem.centerY)
      .attr("r", (distance) => this.orbitSystem?.orbitRadius(distance) ?? 0);
  }

  private renderNodes(): void {
    const nodes = this.nodeGroup.selectAll<SVGGElement, PageNode>(".race-node").data(this.pages, (node) => node.pageTitle);
    nodes.exit().transition().duration(250).style("opacity", 0).remove();
    const entered = nodes.enter().append("g")
      .attr("class", "race-node")
      .style("opacity", 0)
      .call(this.dragBehavior());
    entered.append("circle").attr("class", "race-node-circle");
    entered.append("g").attr("class", "race-node-pie");
    entered.append("text").attr("class", "race-node-distance").attr("text-anchor", "middle").attr("dy", "0.35em");
    entered.append("text").attr("class", "race-node-title").attr("text-anchor", "middle");
    entered.transition().duration(350).style("opacity", 1);
    const merged = entered.merge(nodes);
    merged.sort((left, right) => this.nodeRenderOrder(left) - this.nodeRenderOrder(right));
    merged.classed("is-current-page", (node) => node.currentRunIds.length > 0);
    merged.select<SVGCircleElement>(".race-node-circle")
      .attr("r", (node) => this.pageRadius(node))
      .attr("fill", (node) => this.pageColor(node))
      .style("display", (node) => this.needsPie(node) || node.type === "target" ? "none" : null);
    merged.each((node, index, groups) => this.renderPieOrTarget(d3.select(groups[index]), node));
    merged.select<SVGTextElement>(".race-node-distance")
      .text((node) => node.type === "target" ? "" : String(node.distanceToTarget ?? "?"))
      .style("font-size", (node) => `${Math.max(10, Math.min(16, this.pageRadius(node) * 0.6))}px`);
    merged.select<SVGTextElement>(".race-node-title")
      .text((node) => node.pageTitle)
      .attr("dy", (node) => -(this.pageRadius(node) + 8));
  }

  private renderPieOrTarget(group: d3.Selection<SVGGElement, PageNode, null, undefined>, node: PageNode): void {
    const pieGroup = group.select<SVGGElement>(".race-node-pie");
    pieGroup.selectAll("*").remove();
    const radius = this.pageRadius(node);
    if (node.type === "target") {
      [1, 0.72, 0.46, 0.22].forEach((scale, index) => {
        pieGroup.append("circle")
          .attr("r", radius * scale)
          .attr("fill", index % 2 === 0 ? "#d00000" : "#ffffff")
          .attr("stroke", "none")
          .attr("stroke-width", 0);
      });
      if (node.currentRunIds.length > 0) {
        pieGroup.append("circle")
          .attr("class", "race-current-node-ring")
          .attr("r", radius + 2)
          .attr("fill", "none");
      }
      return;
    }
    if (!this.needsPie(node)) {
      return;
    }
    const counts = d3.rollups(node.visits, (visits) => visits.length, (visit) => visit.runId);
    const pie = d3.pie<[string, number]>().value((entry) => entry[1]).sort(null).endAngle(-2 * Math.PI);
    const arc = d3.arc<d3.PieArcDatum<[string, number]>>().innerRadius(0).outerRadius(radius);
    pieGroup.selectAll("path").data(pie(counts)).enter().append("path")
      .attr("d", arc)
      .attr("fill", (slice) => this.colorMap.get(slice.data[0]) ?? "#64748b")
      .attr("stroke", "none");
    if (node.currentRunIds.length > 0) {
      pieGroup.append("circle")
        .attr("class", "race-current-node-ring")
        .attr("r", radius + 2)
        .attr("fill", "none");
    }
  }

  private renderEdges(): void {
    const edges = this.edgeGroup.selectAll<SVGLineElement, NavigationEdge>(".race-edge").data(this.edges, (edge) => edge.id);
    edges.exit().remove();
    edges.enter().append("line").attr("class", "race-edge").merge(edges)
      .attr("stroke", (edge) => this.distanceColor(edge.distanceChange))
      .attr("stroke-width", 3)
      .attr("marker-end", "url(#race-arrow)");

    if (this.svg.select("#race-arrow").empty()) {
      const defs = this.svg.append("defs");
      defs.append("marker")
        .attr("id", "race-arrow")
        .attr("viewBox", "0 0 10 10")
        .attr("refX", 8)
        .attr("refY", 5)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M 0 0 L 10 5 L 0 10 z")
        .attr("fill", "context-stroke");
    }
  }

  private updateEdgePositions(): void {
    this.edgeGroup.selectAll<SVGLineElement, NavigationEdge>(".race-edge")
      .attr("x1", (edge) => this.edgePoint(edge, true).x)
      .attr("y1", (edge) => this.edgePoint(edge, true).y)
      .attr("x2", (edge) => this.edgePoint(edge, false).x)
      .attr("y2", (edge) => this.edgePoint(edge, false).y);
  }

  private edgePoint(edge: NavigationEdge, sourcePoint: boolean): { x: number; y: number } {
    const source = this.pageMap.get(edge.sourcePageTitle);
    const target = this.pageMap.get(edge.targetPageTitle);
    if (source === undefined || target === undefined) {
      return { x: 0, y: 0 };
    }
    const from = sourcePoint ? source : target;
    const to = sourcePoint ? target : source;
    const radius = this.pageRadius(from) + (sourcePoint ? 0 : 2);
    const dx = (to.x ?? 0) - (from.x ?? 0);
    const dy = (to.y ?? 0) - (from.y ?? 0);
    const length = Math.hypot(dx, dy) || 1;
    return {
      x: (from.x ?? 0) + (dx / length) * radius,
      y: (from.y ?? 0) + (dy / length) * radius,
    };
  }

  private dragBehavior(): d3.DragBehavior<SVGGElement, PageNode, PageNode | d3.SubjectPosition> {
    return d3.drag<SVGGElement, PageNode>()
      .on("start", (_event, node) => {
        this.simulation?.alphaTarget(0.3).restart();
        node.fx = node.x;
        node.fy = node.y;
      })
      .on("drag", (event, node) => {
        node.fx = event.x;
        node.fy = event.y;
        if (node.type === "start" || node.type === "target") {
          node.x = event.x;
          node.y = event.y;
          this.orbitSystem = this.calculateOrbitSystem();
          this.renderOrbits();
          if (this.orbitSystem !== null) {
            this.simulation?.force("orbital", this.orbitalForce(this.orbitSystem));
          }
        }
      })
      .on("end", (_event, node) => {
        this.simulation?.alphaTarget(0);
        if (node.type !== "start" && node.type !== "target") {
          node.fx = undefined;
          node.fy = undefined;
        }
      });
  }

  private pageRadius(page: PageNode): number {
    if (page.type === "target") {
      return 30;
    }
    return 20 * Math.max(1, Math.sqrt(page.visits.length));
  }

  private pageColor(page: PageNode): string {
    const runId = page.visits[0]?.runId;
    return runId === undefined ? "#ffffff" : this.colorMap.get(runId) ?? "#64748b";
  }

  private needsPie(page: PageNode): boolean {
    if (page.visits.length < 2) {
      return false;
    }
    return page.visits.some((visit) => visit.runId !== page.visits[0]?.runId);
  }

  private nodeRenderOrder(page: PageNode): number {
    const latestVisit = Math.max(-1, ...page.visits.map((visit) => visit.moveIndex));
    const typeBoost = page.type === "target" ? 0.2 : page.type === "start" ? -0.2 : 0;
    return latestVisit + typeBoost;
  }

  private linkStrength(edge: NavigationEdge): number {
    return edge.distanceChange === 0 ? 0.2 : 0.1;
  }

  private distanceColor(distanceChange?: number | null): string {
    if (distanceChange === undefined || distanceChange === null) {
      return "#64748b";
    }
    if (distanceChange > 0) {
      return "#00843d";
    }
    if (distanceChange === 0) {
      return "#ffb000";
    }
    return "#d00000";
  }
}

function buildPageGraphData(state: RaceViewState): PageGraphData {
  const metadata = state.metadata;
  if (metadata === null) {
    return { pages: [], edges: [], colorMap: new Map() };
  }
  const pages = new Map<string, PageNode>();
  const edges: NavigationEdge[] = [];
  const colorMap = new Map<string, string>();
  const viewingPageIndex = state.renderingMode === "live" ? Number.POSITIVE_INFINITY : state.viewingPageIndex;

  for (const track of state.tracksByRunId.values()) {
    colorMap.set(track.runId, track.color);
    addVisit(pages, metadata.start_title, "start", track, 0, undefined, distanceFor(track, metadata.start_title));
    const visibleMoves = track.moves.filter((candidate) => candidate.moveIndex <= viewingPageIndex);
    for (const move of track.moves.filter((candidate) => candidate.moveIndex <= viewingPageIndex)) {
      const distanceChange = move.distanceBefore !== undefined && move.distanceAfter !== undefined && move.distanceBefore !== null && move.distanceAfter !== null
        ? move.distanceBefore - move.distanceAfter
        : undefined;
      addVisit(pages, move.toPageTitle, move.toPageTitle === metadata.target_title ? "target" : "visited", track, move.moveIndex, distanceChange, move.distanceAfter ?? distanceFor(track, move.toPageTitle));
      edges.push({
        id: `${track.runId}-${move.moveIndex}`,
        runId: track.runId,
        sourcePageTitle: move.fromPageTitle,
        targetPageTitle: move.toPageTitle,
        moveIndex: move.moveIndex,
        distanceChange,
      });
    }
    markCurrentPage(pages, track.runId, visibleMoves.at(-1)?.toPageTitle ?? metadata.start_title);
  }

  if (!pages.has(metadata.target_title)) {
    pages.set(metadata.target_title, {
      pageTitle: metadata.target_title,
      type: "target",
      distanceToTarget: 0,
      visits: [],
      currentRunIds: [],
    });
  }

  return { pages: [...pages.values()], edges, colorMap };
}

function clamp(value: number, min: number, max: number): number {
  if (min > max) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
}

function addVisit(
  pages: Map<string, PageNode>,
  pageTitle: string,
  type: PageNode["type"],
  track: ParticipantTrack,
  moveIndex: number,
  distanceChange: number | undefined,
  distanceToTarget: number | null | undefined,
): void {
  const page = pages.get(pageTitle) ?? {
    pageTitle,
    type,
    distanceToTarget,
    visits: [],
    currentRunIds: [],
  };
  if (page.type !== "target") {
    page.type = type === "target" ? "target" : page.type === "start" ? "start" : type;
  }
  if (distanceToTarget !== undefined) {
    page.distanceToTarget = distanceToTarget;
  }
  page.visits.push({ runId: track.runId, moveIndex, distanceChange });
  pages.set(pageTitle, page);
}

function markCurrentPage(pages: Map<string, PageNode>, runId: string, pageTitle: string): void {
  const page = pages.get(pageTitle);
  if (page === undefined) {
    return;
  }
  if (!page.currentRunIds.includes(runId)) {
    page.currentRunIds.push(runId);
  }
}

function distanceFor(track: ParticipantTrack, pageTitle: string): number | null | undefined {
  return track.solverFactsByPage.get(pageTitle)?.shortest_path_length;
}
