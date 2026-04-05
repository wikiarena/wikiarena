import type { SolveResponse } from "./api";

interface GraphNode {
  id: string;
  title: string;
  level: number;
  incomingNodeIds: Set<string>;
  outgoingNodeIds: Set<string>;
  x: number;
  y: number;
  isAnchor: boolean;
}

interface GraphEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
}

interface PathGraphModel {
  width: number;
  height: number;
  nodesById: Map<string, GraphNode>;
  edgesById: Map<string, GraphEdge>;
  levels: string[][];
}

const HORIZONTAL_MARGIN = 88;
const VERTICAL_MARGIN = 68;
const MIN_GRAPH_WIDTH = 620;
const NODE_RADIUS = 15;
const EDGE_OFFSET_PX = NODE_RADIUS + 1;
const ROW_GAP_PX = 118;
const COLUMN_GAP_PX = 118;
const ARROW_MARKER_ID = "path-graph-arrowhead";

export function renderPathGraph(containerElement: HTMLElement, solveResponse: SolveResponse): void {
  const pathGraphModel = buildPathGraphModel(solveResponse.paths);

  if (pathGraphModel.edgesById.size === 0 && pathGraphModel.nodesById.size === 0) {
    containerElement.innerHTML = "";
    return;
  }

  containerElement.innerHTML = buildGraphMarkup(pathGraphModel);
  installGraphInteractions(containerElement, pathGraphModel);
  centerGraphShell(containerElement);
}

function buildPathGraphModel(paths: string[][]): PathGraphModel {
  const nodesById = new Map<string, GraphNode>();
  const edgesById = new Map<string, GraphEdge>();
  const levelNodeIds: string[][] = [];

  for (const path of paths) {
    for (let levelIndex = 0; levelIndex < path.length; levelIndex += 1) {
      const title = path[levelIndex];
      const nodeId = makeNodeId(levelIndex, title);
      if (!nodesById.has(nodeId)) {
        while (levelNodeIds.length <= levelIndex) {
          levelNodeIds.push([]);
        }
        levelNodeIds[levelIndex].push(nodeId);
        nodesById.set(nodeId, {
          id: nodeId,
          title,
          level: levelIndex,
          incomingNodeIds: new Set<string>(),
          outgoingNodeIds: new Set<string>(),
          x: 0,
          y: 0,
          isAnchor: false,
        });
      }

      if (levelIndex === path.length - 1) {
        continue;
      }

      const sourceNodeId = nodeId;
      const targetNodeId = makeNodeId(levelIndex + 1, path[levelIndex + 1]);
      const edgeId = `${sourceNodeId}->${targetNodeId}`;
      if (!edgesById.has(edgeId)) {
        edgesById.set(edgeId, {
          id: edgeId,
          sourceNodeId,
          targetNodeId,
        });
      }
    }
  }

  for (const edge of edgesById.values()) {
    const sourceNode = nodesById.get(edge.sourceNodeId);
    const targetNode = nodesById.get(edge.targetNodeId);
    if (sourceNode === undefined || targetNode === undefined) {
      continue;
    }
    sourceNode.outgoingNodeIds.add(targetNode.id);
    targetNode.incomingNodeIds.add(sourceNode.id);
  }

  const orderedLevels = orderLevels(levelNodeIds, nodesById);
  const maxRowWidth = Math.max(...orderedLevels.map((levelNodeIdsForRow) => levelNodeIdsForRow.length));
  const width = Math.max(
    MIN_GRAPH_WIDTH,
    HORIZONTAL_MARGIN * 2 + Math.max(0, maxRowWidth - 1) * COLUMN_GAP_PX,
  );
  const height = Math.max(
    260,
    VERTICAL_MARGIN * 2 + Math.max(0, orderedLevels.length - 1) * ROW_GAP_PX,
  );

  orderedLevels.forEach((levelNodeIdsForRow, levelIndex) => {
    const rowY = orderedLevels.length === 1
      ? height / 2
      : VERTICAL_MARGIN + levelIndex * ((height - VERTICAL_MARGIN * 2) / (orderedLevels.length - 1));
    const rowContentWidth = Math.max(0, levelNodeIdsForRow.length - 1) * COLUMN_GAP_PX;
    const rowStartX = (width - rowContentWidth) / 2;

    levelNodeIdsForRow.forEach((nodeId, nodeIndex) => {
      const node = nodesById.get(nodeId);
      if (node === undefined) {
        return;
      }
      node.x = rowStartX + nodeIndex * COLUMN_GAP_PX;
      node.y = rowY;
      node.isAnchor = levelIndex === 0 || levelIndex === orderedLevels.length - 1;
    });
  });

  return {
    width,
    height,
    nodesById,
    edgesById,
    levels: orderedLevels,
  };
}

function orderLevels(levelNodeIds: string[][], nodesById: Map<string, GraphNode>): string[][] {
  const orderedLevels = levelNodeIds.map((rowNodeIds) => [...rowNodeIds].sort((leftNodeId, rightNodeId) => {
    const leftNode = nodesById.get(leftNodeId);
    const rightNode = nodesById.get(rightNodeId);
    return (leftNode?.title ?? "").localeCompare(rightNode?.title ?? "");
  }));

  if (orderedLevels.length <= 2) {
    return orderedLevels;
  }

  for (let iterationIndex = 0; iterationIndex < 3; iterationIndex += 1) {
    let didChangeLevelOrder = false;

    for (let levelIndex = 1; levelIndex < orderedLevels.length - 1; levelIndex += 1) {
      const nextLevelOrder = sortLevelByBarycenter(
        orderedLevels[levelIndex],
        nodesById,
        new Map(orderedLevels[levelIndex - 1].map((nodeId, nodeIndex) => [nodeId, nodeIndex])),
        "incoming",
      );

      if (!doNodeOrdersMatch(orderedLevels[levelIndex], nextLevelOrder)) {
        orderedLevels[levelIndex] = nextLevelOrder;
        didChangeLevelOrder = true;
      }
    }

    for (let levelIndex = orderedLevels.length - 2; levelIndex >= 1; levelIndex -= 1) {
      const nextLevelOrder = sortLevelByBarycenter(
        orderedLevels[levelIndex],
        nodesById,
        new Map(orderedLevels[levelIndex + 1].map((nodeId, nodeIndex) => [nodeId, nodeIndex])),
        "outgoing",
      );

      if (!doNodeOrdersMatch(orderedLevels[levelIndex], nextLevelOrder)) {
        orderedLevels[levelIndex] = nextLevelOrder;
        didChangeLevelOrder = true;
      }
    }

    if (!didChangeLevelOrder) {
      break;
    }
  }

  return orderedLevels;
}

function sortLevelByBarycenter(
  levelNodeIds: string[],
  nodesById: Map<string, GraphNode>,
  referenceOrder: Map<string, number>,
  direction: "incoming" | "outgoing",
): string[] {
  const barycenterScores = new Map(
    levelNodeIds.map((nodeId) => [nodeId, computeBarycenterScore(nodeId, nodesById, referenceOrder, direction)]),
  );

  return [...levelNodeIds].sort((leftNodeId, rightNodeId) => {
    const leftScore = barycenterScores.get(leftNodeId) ?? Number.POSITIVE_INFINITY;
    const rightScore = barycenterScores.get(rightNodeId) ?? Number.POSITIVE_INFINITY;
    if (leftScore !== rightScore) {
      return leftScore - rightScore;
    }
    return compareTitles(leftNodeId, rightNodeId, nodesById);
  });
}

function doNodeOrdersMatch(leftNodeIds: string[], rightNodeIds: string[]): boolean {
  if (leftNodeIds.length !== rightNodeIds.length) {
    return false;
  }

  for (let nodeIndex = 0; nodeIndex < leftNodeIds.length; nodeIndex += 1) {
    if (leftNodeIds[nodeIndex] !== rightNodeIds[nodeIndex]) {
      return false;
    }
  }

  return true;
}

function computeBarycenterScore(
  nodeId: string,
  nodesById: Map<string, GraphNode>,
  referenceOrder: Map<string, number>,
  direction: "incoming" | "outgoing",
): number {
  const node = nodesById.get(nodeId);
  if (node === undefined) {
    return Number.POSITIVE_INFINITY;
  }

  const relatedNodeIds = direction === "incoming"
    ? [...node.incomingNodeIds]
    : [...node.outgoingNodeIds];
  if (relatedNodeIds.length === 0) {
    return Number.POSITIVE_INFINITY;
  }

  let total = 0;
  let count = 0;
  for (const relatedNodeId of relatedNodeIds) {
    const order = referenceOrder.get(relatedNodeId);
    if (order === undefined) {
      continue;
    }
    total += order;
    count += 1;
  }

  if (count === 0) {
    return Number.POSITIVE_INFINITY;
  }
  return total / count;
}

function compareTitles(leftNodeId: string, rightNodeId: string, nodesById: Map<string, GraphNode>): number {
  const leftNode = nodesById.get(leftNodeId);
  const rightNode = nodesById.get(rightNodeId);
  return (leftNode?.title ?? "").localeCompare(rightNode?.title ?? "");
}

function buildGraphMarkup(pathGraphModel: PathGraphModel): string {
  const defsMarkup = `
    <defs>
      <marker
        id="${ARROW_MARKER_ID}"
        markerWidth="12"
        markerHeight="12"
        refX="10"
        refY="6"
        orient="auto"
        markerUnits="userSpaceOnUse"
      >
        <path d="M 0 1 L 10 6 L 0 11 L 3 6 z" fill="context-stroke" />
      </marker>
    </defs>
  `;

  const edgeMarkup = [...pathGraphModel.edgesById.values()]
    .map((edge) => {
      const sourceNode = pathGraphModel.nodesById.get(edge.sourceNodeId);
      const targetNode = pathGraphModel.nodesById.get(edge.targetNodeId);
      if (sourceNode === undefined || targetNode === undefined) {
        return "";
      }
      const edgeGeometry = computeEdgeGeometry(sourceNode, targetNode);
      return `
        <line
          class="path-graph-edge"
          data-edge-id="${escapeAttribute(edge.id)}"
          data-source-node-id="${escapeAttribute(sourceNode.id)}"
          data-target-node-id="${escapeAttribute(targetNode.id)}"
          x1="${edgeGeometry.x1}"
          y1="${edgeGeometry.y1}"
          x2="${edgeGeometry.x2}"
          y2="${edgeGeometry.y2}"
          marker-end="url(#${ARROW_MARKER_ID})"
        />
      `;
    })
    .join("");

  const nodeMarkup = [...pathGraphModel.nodesById.values()]
    .sort((leftNode, rightNode) => leftNode.level - rightNode.level || leftNode.x - rightNode.x)
    .map((node) => {
      const labelY = node.y - NODE_RADIUS - 14;
      return `
        <g class="path-graph-node" data-node-id="${escapeAttribute(node.id)}" tabindex="0">
          <line class="path-graph-label-stem${node.isAnchor ? " is-visible" : ""}" x1="${node.x}" y1="${node.y - NODE_RADIUS}" x2="${node.x}" y2="${labelY + 5}" />
          <text
            class="path-graph-label${node.isAnchor ? " is-anchor is-visible" : ""}"
            data-label-for-node-id="${escapeAttribute(node.id)}"
            x="${node.x}"
            y="${labelY}"
            text-anchor="middle"
          >${escapeHtml(node.title)}</text>
          <circle
            class="path-graph-node-circle"
            cx="${node.x}"
            cy="${node.y}"
            r="${NODE_RADIUS}"
          />
        </g>
      `;
    })
    .join("");

  return `
    <div class="path-graph-shell">
      <svg
        class="path-graph-svg"
        width="${pathGraphModel.width}"
        height="${pathGraphModel.height}"
        viewBox="0 0 ${pathGraphModel.width} ${pathGraphModel.height}"
        role="img"
        aria-label="Graph of all returned shortest Wikipedia paths"
      >
        ${defsMarkup}
        <g class="path-graph-edges">${edgeMarkup}</g>
        <g class="path-graph-nodes">${nodeMarkup}</g>
      </svg>
    </div>
  `;
}

function computeEdgeGeometry(sourceNode: GraphNode, targetNode: GraphNode): {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
} {
  const deltaX = targetNode.x - sourceNode.x;
  const deltaY = targetNode.y - sourceNode.y;
  const distance = Math.hypot(deltaX, deltaY) || 1;
  const unitX = deltaX / distance;
  const unitY = deltaY / distance;

  return {
    x1: sourceNode.x + unitX * EDGE_OFFSET_PX,
    y1: sourceNode.y + unitY * EDGE_OFFSET_PX,
    x2: targetNode.x - unitX * EDGE_OFFSET_PX,
    y2: targetNode.y - unitY * EDGE_OFFSET_PX,
  };
}

function installGraphInteractions(containerElement: HTMLElement, pathGraphModel: PathGraphModel): void {
  const nodeElements = [...containerElement.querySelectorAll<SVGGElement>(".path-graph-node")];
  const labelElementsByNodeId = new Map(
    [...containerElement.querySelectorAll<SVGTextElement>(".path-graph-label")].map((labelElement) => [
      labelElement.dataset.labelForNodeId ?? "",
      labelElement,
    ]),
  );
  const stemElementsByNodeId = new Map(
    nodeElements.map((nodeElement) => [
      nodeElement.dataset.nodeId ?? "",
      nodeElement.querySelector<SVGLineElement>(".path-graph-label-stem"),
    ]),
  );
  const edgeElements = [...containerElement.querySelectorAll<SVGLineElement>(".path-graph-edge")];

  const clearHighlightState = (): void => {
    for (const nodeElement of nodeElements) {
      nodeElement.classList.remove("is-active", "is-neighbor");
    }
    for (const edgeElement of edgeElements) {
      edgeElement.classList.remove("is-active");
    }
    for (const [nodeId, labelElement] of labelElementsByNodeId.entries()) {
      const node = pathGraphModel.nodesById.get(nodeId);
      const shouldStayVisible = node?.isAnchor ?? false;
      labelElement.classList.toggle("is-visible", shouldStayVisible);
      stemElementsByNodeId.get(nodeId)?.classList.toggle("is-visible", shouldStayVisible);
    }
  };

  const applyHighlightState = (hoveredNodeId: string): void => {
    clearHighlightState();

    const hoveredNode = pathGraphModel.nodesById.get(hoveredNodeId);
    if (hoveredNode === undefined) {
      return;
    }

    const neighborNodeIds = new Set<string>([
      ...hoveredNode.incomingNodeIds,
      ...hoveredNode.outgoingNodeIds,
    ]);

    for (const nodeElement of nodeElements) {
      const nodeId = nodeElement.dataset.nodeId ?? "";
      if (nodeId === hoveredNodeId) {
        nodeElement.classList.add("is-active");
      } else if (neighborNodeIds.has(nodeId)) {
        nodeElement.classList.add("is-neighbor");
      }

      if (nodeId === hoveredNodeId || neighborNodeIds.has(nodeId)) {
        labelElementsByNodeId.get(nodeId)?.classList.add("is-visible");
        stemElementsByNodeId.get(nodeId)?.classList.add("is-visible");
      }
    }

    for (const edgeElement of edgeElements) {
      const sourceNodeId = edgeElement.dataset.sourceNodeId ?? "";
      const targetNodeId = edgeElement.dataset.targetNodeId ?? "";
      if (sourceNodeId === hoveredNodeId || targetNodeId === hoveredNodeId) {
        edgeElement.classList.add("is-active");
      }
    }
  };

  for (const nodeElement of nodeElements) {
    const nodeId = nodeElement.dataset.nodeId ?? "";
    nodeElement.addEventListener("mouseenter", () => {
      applyHighlightState(nodeId);
    });
    nodeElement.addEventListener("focus", () => {
      applyHighlightState(nodeId);
    });
  }

  containerElement.addEventListener("mouseleave", clearHighlightState);
  containerElement.addEventListener("focusout", (event) => {
    const nextFocusedElement = event.relatedTarget;
    if (nextFocusedElement instanceof Node && containerElement.contains(nextFocusedElement)) {
      return;
    }
    clearHighlightState();
  });

  clearHighlightState();
}

function centerGraphShell(containerElement: HTMLElement): void {
  const shellElement = containerElement.querySelector<HTMLElement>(".path-graph-shell");
  if (shellElement === null) {
    return;
  }

  requestAnimationFrame(() => {
    shellElement.scrollLeft = Math.max(0, (shellElement.scrollWidth - shellElement.clientWidth) / 2);
  });
}

function makeNodeId(levelIndex: number, title: string): string {
  return `${levelIndex}:${title}`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttribute(value: string): string {
  return escapeHtml(value);
}
