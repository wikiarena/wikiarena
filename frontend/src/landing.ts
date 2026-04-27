import "./styles.css";

interface LeaderboardParticipant {
  participantId: string;
  displayName: string;
  rankingEligibleRuns: number;
  successes: number;
  totalEstimatedCostUsd: number | null;
  stepErrorRate: number | null;
  totalModelResponseTimeMs: number | null;
  elo: number | null;
}

interface LeaderboardData {
  participants: LeaderboardParticipant[];
}

const PARTICIPANT_LOGOS: Record<string, string> = {
  claude_sonnet_4_6: "./assets/providers/anthropic.svg",
  gpt_5_5: "./assets/providers/openai.svg",
};

const SVG_NS = "http://www.w3.org/2000/svg";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatPercent(numerator: number, denominator: number): string {
  if (denominator <= 0) {
    return "--";
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function formatRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatDuration(valueMs: number | null): string {
  if (valueMs === null || !Number.isFinite(valueMs)) {
    return "--";
  }
  const totalSeconds = Math.round(valueMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${seconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function renderLeaderboardLogo(participant: LeaderboardParticipant): string {
  const logoPath = PARTICIPANT_LOGOS[participant.participantId];
  if (logoPath === undefined) {
    return "";
  }
  return `<img class="leaderboard-provider-logo" src="${logoPath}" alt="" />`;
}

function renderHomeLeaderboard(data: LeaderboardData): void {
  const rows = document.getElementById("home-leaderboard-rows");
  if (!(rows instanceof HTMLElement)) {
    return;
  }
  rows.innerHTML = data.participants
    .map((participant, index) => `
      <div class="leaderboard-row" role="row">
        <span role="cell">${index + 1}</span>
        <span role="cell" class="leaderboard-model-cell">
          ${renderLeaderboardLogo(participant)}
          <strong>${escapeHtml(participant.displayName)}</strong>
        </span>
        <span role="cell">${participant.elo ?? "--"}</span>
        <span role="cell">${formatPercent(participant.successes, participant.rankingEligibleRuns)}</span>
        <span role="cell">${formatRate(participant.stepErrorRate)}</span>
        <span role="cell">${formatDuration(participant.totalModelResponseTimeMs)}</span>
      </div>
    `)
    .join("");
}

async function initializeHomeLeaderboard(): Promise<void> {
  const note = document.getElementById("home-leaderboard-note");
  const response = await fetch("/data/leaderboard.json");
  if (!response.ok) {
    throw new Error(`Failed to load leaderboard data: ${response.status}`);
  }
  renderHomeLeaderboard(await response.json() as LeaderboardData);
  note?.classList.add("hidden");
}

interface Point {
  x: number;
  y: number;
}

interface PreviewNode extends Point {
  id: string;
  level: number;
  title: string;
  isStart: boolean;
  isTarget: boolean;
}

interface PreviewGraph {
  nodes: PreviewNode[];
  edges: [string, string][];
  paths: string[][];
}

interface HomePreviewRace {
  startTitle: string;
  targetTitle: string;
  paths: string[][];
}

interface HomePreviewManifest {
  races: HomePreviewRace[];
}

function svgElement<K extends keyof SVGElementTagNameMap>(tag: K): SVGElementTagNameMap[K] {
  return document.createElementNS(SVG_NS, tag);
}

function setAttributes(element: Element, attributes: Record<string, string>): void {
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, value);
  }
}

function drawCircle(parent: SVGElement, point: Point, radius: number, className: string): SVGCircleElement {
  const circle = svgElement("circle");
  setAttributes(circle, {
    class: className,
    cx: String(point.x),
    cy: String(point.y),
    r: String(radius),
  });
  parent.append(circle);
  return circle;
}

function drawTarget(parent: SVGElement, point: Point): void {
  [22, 16, 10, 5].forEach((radius, index) => {
    const circle = drawCircle(parent, point, radius, "home-preview-target-ring");
    circle.setAttribute("fill", index % 2 === 0 ? "#d00000" : "#ffffff");
  });
}

function shuffle<T>(values: T[]): T[] {
  return [...values].sort(() => Math.random() - 0.5);
}

function buildRealPreviewGraph(race: HomePreviewRace): PreviewGraph {
  const [leftPath, rightPath, ...backgroundPaths] = selectRealPreviewPaths(race.paths);
  const selectedPaths = [leftPath, rightPath, ...backgroundPaths].filter((path): path is string[] => path !== undefined);
  const nodesById = new Map<string, PreviewNode>();
  const edgeKeys = new Set<string>();
  const edges: [string, string][] = [];

  selectedPaths.forEach((path) => {
    path.forEach((title, level) => {
      const id = previewNodeId(level, title);
      if (!nodesById.has(id)) {
        nodesById.set(id, {
          id,
          title,
          level,
          isStart: level === 0,
          isTarget: level === path.length - 1,
          x: 0,
          y: 0,
        });
      }
      if (level >= path.length - 1) {
        return;
      }
      const nextId = previewNodeId(level + 1, path[level + 1] ?? "");
      const edgeKey = `${id}->${nextId}`;
      if (!edgeKeys.has(edgeKey)) {
        edgeKeys.add(edgeKey);
        edges.push([id, nextId]);
      }
    });
  });

  const nodes = [...nodesById.values()];
  positionRealPreviewNodes(nodes);
  return {
    nodes,
    edges,
    paths: selectedPaths.slice(0, 2).map((path) => path.map((title, level) => previewNodeId(level, title))),
  };
}

function selectRealPreviewPaths(paths: string[][]): string[][] {
  const leftPath = paths[Math.floor(Math.random() * paths.length)] ?? paths[0];
  if (leftPath === undefined) {
    return [];
  }
  const differentFirstHopPaths = paths.filter((path) => path[1] !== leftPath[1]);
  const rightPool = differentFirstHopPaths.length > 0 ? differentFirstHopPaths : paths;
  const rightPath = rightPool[Math.floor(Math.random() * rightPool.length)] ?? paths[1] ?? leftPath;
  const backgroundPaths = shuffle(paths)
    .filter((path) => path !== leftPath && path !== rightPath)
    .slice(0, 2);
  return [leftPath, rightPath, ...backgroundPaths];
}

function positionRealPreviewNodes(nodes: PreviewNode[]): void {
  const levels = [...new Set(nodes.map((node) => node.level))].sort((left, right) => left - right);
  levels.forEach((level, levelIndex) => {
    const rowNodes = nodes
      .filter((node) => node.level === level)
      .sort((left, right) => left.title.localeCompare(right.title));
    const y = levels.length === 1 ? 178 : 54 + levelIndex * (252 / (levels.length - 1));
    rowNodes.forEach((node, index) => {
      node.x = rowNodes.length === 1 ? 260 : 72 + index * (376 / (rowNodes.length - 1));
      node.y = y;
    });
  });
}

function previewNodeId(level: number, title: string): string {
  return `${level}:${title}`;
}

function edgeEndpoints(from: Point, to: Point, offset: number): { from: Point; to: Point } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  const unitX = dx / length;
  const unitY = dy / length;
  return {
    from: { x: from.x + unitX * offset, y: from.y + unitY * offset },
    to: { x: to.x - unitX * offset, y: to.y - unitY * offset },
  };
}

function positionRunner(runner: SVGCircleElement, point: Point): void {
  runner.setAttribute("cx", String(point.x));
  runner.setAttribute("cy", String(point.y));
}

async function loadHomePreviewManifest(): Promise<HomePreviewRace[]> {
  const response = await fetch("/data/home-preview-races.json");
  if (!response.ok) {
    throw new Error(`Failed to load home preview races: ${response.status}`);
  }
  const manifest = await response.json() as HomePreviewManifest;
  return manifest.races.filter((race) => race.paths.length >= 2);
}

async function initializeRacePreview(): Promise<void> {
  const svg = document.getElementById("home-race-preview");
  if (!(svg instanceof SVGSVGElement)) {
    return;
  }
  const markerId = `home-preview-arrow-${Math.random().toString(36).slice(2)}`;
  const realPreviewRaces = await loadHomePreviewManifest();
  if (realPreviewRaces.length === 0) {
    return;
  }
  let graph = buildRealPreviewGraph(realPreviewRaces[0] as HomePreviewRace);
  let leftRunner: SVGCircleElement | null = null;
  let rightRunner: SVGCircleElement | null = null;
  let labelElements = new Map<string, SVGTextElement>();
  let edgeElements = new Map<string, SVGLineElement>();
  let tick = 0;
  let leftPath: string[] = [];
  let rightPath: string[] = [];

  const renderGraph = () => {
    svg.replaceChildren();
    labelElements = new Map<string, SVGTextElement>();
    edgeElements = new Map<string, SVGLineElement>();
    const defs = svgElement("defs");
    const marker = svgElement("marker");
    setAttributes(marker, {
      id: markerId,
      viewBox: "0 0 10 10",
      refX: "8",
      refY: "5",
      markerWidth: "6",
      markerHeight: "6",
      orient: "auto",
    });
    const markerPath = svgElement("path");
    setAttributes(markerPath, { d: "M 0 0 L 10 5 L 0 10 z", fill: "context-stroke" });
    marker.append(markerPath);
    defs.append(marker);
    svg.append(defs);

    for (const [fromId, toId] of graph.edges) {
      const from = graph.nodes.find((node) => node.id === fromId);
      const to = graph.nodes.find((node) => node.id === toId);
      if (from === undefined || to === undefined) {
        continue;
      }
      const points = edgeEndpoints(from, to, 18);
      const line = svgElement("line");
      setAttributes(line, {
        class: "home-preview-edge",
        x1: String(points.from.x),
        y1: String(points.from.y),
        x2: String(points.to.x),
        y2: String(points.to.y),
        "marker-end": `url(#${markerId})`,
      });
      svg.append(line);
      edgeElements.set(`${fromId}->${toId}`, line);
    }

    const start = graph.nodes.find((node) => node.isStart);
    graph.nodes.forEach((point) => {
      if (point.isTarget) {
        drawTarget(svg, point);
      } else {
        drawCircle(svg, point, point.isStart ? 17 : 12, point.isStart ? "home-preview-node start" : "home-preview-node");
      }
      const labelY = point.isTarget ? point.y + 34 : point.y - (point.isStart ? 28 : 20);
      const label = svgElement("text");
      setAttributes(label, {
        class: `home-preview-label${point.isStart || point.isTarget ? " is-revealed" : ""}${point.isTarget ? " target-label" : point.isStart ? " start-label" : ""}`,
        x: String(point.x),
        y: String(labelY),
        "text-anchor": "middle",
      });
      label.textContent = point.title === point.id ? "" : point.title;
      labelElements.set(point.id, label);
      svg.append(label);
    });
    leftRunner = drawCircle(svg, start ?? { x: 0, y: 0 }, 8, "home-preview-runner runner-openai");
    rightRunner = drawCircle(svg, start ?? { x: 0, y: 0 }, 8, "home-preview-runner runner-anthropic");
  };

  const startLoop = () => {
    const race = realPreviewRaces[Math.floor(Math.random() * realPreviewRaces.length)];
    if (race === undefined) {
      return;
    }
    graph = buildRealPreviewGraph(race);
    leftPath = graph.paths[0] ?? [];
    rightPath = graph.paths[1] ?? [];
    tick = 0;
    renderGraph();
  };

  const revealNode = (nodeId: string | undefined) => {
    if (nodeId === undefined) {
      return;
    }
    labelElements.get(nodeId)?.classList.add("is-revealed");
  };

  const highlightEdge = (path: string[], index: number) => {
    if (index <= 0) {
      return;
    }
    const sourceId = path[index - 1];
    const targetId = path[index];
    if (sourceId === undefined || targetId === undefined) {
      return;
    }
    window.setTimeout(() => {
      edgeElements.get(`${sourceId}->${targetId}`)?.classList.add("is-traversed");
    }, 540);
  };

  const advance = () => {
    if (tick >= Math.max(leftPath.length, rightPath.length)) {
      startLoop();
    }
    const leftNodeId = leftPath[Math.min(tick, leftPath.length - 1)];
    const rightNodeId = rightPath[Math.min(tick, rightPath.length - 1)];
    const leftPoint = graph.nodes.find((node) => node.id === leftNodeId);
    const rightPoint = graph.nodes.find((node) => node.id === rightNodeId);
    if (leftRunner !== null && leftPoint !== undefined) {
      positionRunner(leftRunner, leftPoint);
      revealNode(leftNodeId);
      highlightEdge(leftPath, Math.min(tick, leftPath.length - 1));
    }
    if (rightRunner !== null && rightPoint !== undefined) {
      positionRunner(rightRunner, rightPoint);
      revealNode(rightNodeId);
      highlightEdge(rightPath, Math.min(tick, rightPath.length - 1));
    }
    tick += 1;
  };

  startLoop();
  advance();
  window.setInterval(advance, 820);
}

initializeRacePreview().catch(() => {
  // The homepage can still render without the decorative preview.
});
initializeHomeLeaderboard().catch((error: unknown) => {
  const note = document.getElementById("home-leaderboard-note");
  if (note instanceof HTMLElement) {
    note.textContent = error instanceof Error ? error.message : "Failed to load leaderboard data.";
    note.classList.remove("hidden");
  }
});
