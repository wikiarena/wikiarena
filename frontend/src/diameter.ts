import * as d3 from "d3";

import "./styles.css";

import { formatInteger } from "./lib/format";

interface PriorWorkLink {
  title: string;
  url: string;
}

interface HistogramBin {
  distance: number;
  count: number;
  shareOfReachablePairs: number;
}

interface RandomPairHistogram {
  sampleSize: number;
  seed: number;
  reachablePairs: number;
  unreachablePairs: number;
  reachableShare: number;
  histogram: HistogramBin[];
}

interface WavefrontLayer {
  distance: number;
  frontierSize: number;
  newPagesDiscovered: number;
  linksScanned: number;
  cumulativePages: number;
  cumulativeLinksScanned: number;
  targetOnFrontier: boolean;
}

interface SnapshotData {
  snapshotId: string;
  nodeCount: number;
  edgeCount: number;
  witness: {
    sourceTitle: string;
    targetTitle: string;
    distance: number;
    pagesVisited: number;
    linksScanned: number;
    pathTitles: string[];
    solverUrl: string;
  };
  wavefront: {
    originTitle: string;
    targetTitle: string;
    direction: "outgoing" | "incoming";
    targetDistance: number;
    reachablePages: number;
    linksScanned: number;
    layers: WavefrontLayer[];
  };
}

interface DiameterExplorerData {
  generatedAt: string;
  methodNote: string;
  snapshots: SnapshotData[];
  randomPairHistogram: RandomPairHistogram;
  priorWork: PriorWorkLink[];
}

type FrontierScale = "log" | "linear";

interface WavefrontMapDot {
  x: number;
  y: number;
  radius: number;
  distance: number;
  frontierSize: number;
  isSource: boolean;
  isTarget: boolean;
  isLargestFrontier: boolean;
  opacity: number;
}

const compactFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const wavefrontColors = [
  "#2f9e44",
  "#16a3a3",
  "#2f6f8f",
  "#7b5ba6",
  "#d64a2f",
];

function getRequiredElement<T extends HTMLElement | SVGSVGElement>(id: string): T {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`Missing required element: ${id}`);
  }
  return element as T;
}

function formatCompact(value: number): string {
  return compactFormatter.format(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function colorForDistance(distance: number, targetDistance: number): string {
  if (targetDistance <= 0) {
    return wavefrontColors[0];
  }
  const scaledPosition = Math.min(0.999, Math.max(0, distance / targetDistance));
  const colorIndex = Math.floor(scaledPosition * (wavefrontColors.length - 1));
  const localPosition = (scaledPosition * (wavefrontColors.length - 1)) - colorIndex;
  return d3.interpolateRgb(
    wavefrontColors[colorIndex],
    wavefrontColors[colorIndex + 1],
  )(localPosition);
}

function getLargestFrontierLayer(layers: WavefrontLayer[]): WavefrontLayer {
  return layers.reduce(
    (largestLayer, layer) => layer.frontierSize > largestLayer.frontierSize ? layer : largestLayer,
    layers[0],
  );
}

function visibleBarY(
  value: number,
  y: (input: number) => number,
  chartBottom: number,
): number {
  if (value <= 0) {
    return chartBottom;
  }
  return Math.min(chartBottom - 2, y(value));
}

function visibleBarHeight(
  value: number,
  y: (input: number) => number,
  chartBottom: number,
): number {
  if (value <= 0) {
    return 0;
  }
  return chartBottom - visibleBarY(value, y, chartBottom);
}

function buildDenseHistogramBins(histogram: RandomPairHistogram): HistogramBin[] {
  const binByDistance = new Map(
    histogram.histogram.map((bin) => [bin.distance, bin]),
  );
  const maxDistance = d3.max(histogram.histogram, (bin) => bin.distance) ?? 0;
  return d3.range(1, maxDistance + 1).map((distance) => (
    binByDistance.get(distance) ?? {
      distance,
      count: 0,
      shareOfReachablePairs: 0,
    }
  ));
}

function renderSnapshotTabs(
  data: DiameterExplorerData,
  selectedSnapshot: SnapshotData,
  onSelect: (snapshot: SnapshotData) => void,
): void {
  const tabsElement = getRequiredElement<HTMLElement>("diameter-snapshot-tabs");
  tabsElement.innerHTML = data.snapshots
    .map((snapshot) => {
      const isSelected = snapshot.snapshotId === selectedSnapshot.snapshotId;
      return `
        <button class="path-mode-button diameter-tab${isSelected ? " is-active" : ""}" type="button" data-snapshot-id="${escapeHtml(snapshot.snapshotId)}" aria-pressed="${isSelected}">
          ${escapeHtml(snapshot.snapshotId.replace("enwiki-", ""))}
        </button>
      `;
    })
    .join("");

  for (const buttonElement of tabsElement.querySelectorAll<HTMLButtonElement>("button[data-snapshot-id]")) {
    buttonElement.addEventListener("click", () => {
      const snapshot = data.snapshots.find(
        (candidate) => candidate.snapshotId === buttonElement.dataset.snapshotId,
      );
      if (snapshot !== undefined) {
        onSelect(snapshot);
      }
    });
  }
}

function renderSnapshotSummary(snapshot: SnapshotData, methodNote: string): void {
  getRequiredElement<HTMLElement>("diameter-hero-distance").textContent =
    `${snapshot.witness.distance} click lower bound`;
  const solverLinkElement = getRequiredElement<HTMLAnchorElement>("diameter-solver-link");
  solverLinkElement.href = snapshot.witness.solverUrl;
  const largestFrontierLayer = getLargestFrontierLayer(snapshot.wavefront.layers);

  getRequiredElement<HTMLElement>("diameter-metrics").innerHTML = `
    <div class="diameter-metric">
      <span class="meta-card-label">witness distance</span>
      <strong>${snapshot.witness.distance}</strong>
      <span class="note-copy">exact shortest path for this pair</span>
    </div>
    <div class="diameter-metric">
      <span class="meta-card-label">graph size</span>
      <strong>${formatCompact(snapshot.nodeCount)} pages</strong>
      <span class="note-copy">${formatCompact(snapshot.edgeCount)} directed links</span>
    </div>
    <div class="diameter-metric">
      <span class="meta-card-label">largest frontier</span>
      <strong>${formatCompact(largestFrontierLayer.frontierSize)} pages</strong>
      <span class="note-copy">distance ${largestFrontierLayer.distance}</span>
    </div>
    <div class="diameter-metric">
      <span class="meta-card-label">reachable from source</span>
      <strong>${formatCompact(snapshot.wavefront.reachablePages)} pages</strong>
      <span class="note-copy">${formatCompact(snapshot.wavefront.linksScanned)} links scanned</span>
    </div>
  `;

  getRequiredElement<HTMLElement>("diameter-method-note").textContent = methodNote;
  getRequiredElement<HTMLElement>("diameter-witness-summary").textContent =
    `Witness pair: ${snapshot.witness.sourceTitle} to ${snapshot.witness.targetTitle}. The solver link opens the full ${snapshot.witness.pathTitles.length}-page shortest path.`;
}

function renderWavefrontMap(snapshot: SnapshotData): void {
  const svgElement = getRequiredElement<SVGSVGElement>("wavefront-map");
  const svg = d3.select(svgElement);
  svg.selectAll("*").remove();

  const width = 920;
  const height = 430;
  const centerX = 304;
  const centerY = 216;
  const cloudLayers = snapshot.wavefront.layers.filter((layer) => layer.distance <= 10);
  const tailLayers = snapshot.wavefront.layers.filter((layer) => layer.distance > 10);
  const largestFrontierLayer = getLargestFrontierLayer(snapshot.wavefront.layers);
  const targetDistance = snapshot.wavefront.targetDistance;
  const dots: WavefrontMapDot[] = [];
  const tailDots: WavefrontMapDot[] = [];

  svg.append("rect")
    .attr("class", "diameter-wavefront-map-bg")
    .attr("x", 0)
    .attr("y", 0)
    .attr("width", width)
    .attr("height", height);

  for (const ringDistance of [2, 4, 6, 8, 10]) {
    svg.append("ellipse")
      .attr("class", "diameter-wavefront-ring")
      .attr("cx", centerX)
      .attr("cy", centerY)
      .attr("rx", 22 + (ringDistance * 19))
      .attr("ry", 16 + (ringDistance * 13))
      .append("title")
      .text(`distance ${ringDistance}`);
  }

  for (const layer of cloudLayers) {
    if (layer.distance === 0) {
      dots.push({
        x: centerX,
        y: centerY,
        radius: 8,
        distance: 0,
        frontierSize: layer.frontierSize,
        isSource: true,
        isTarget: layer.targetOnFrontier,
        isLargestFrontier: false,
        opacity: 1,
      });
      continue;
    }

    const dotCount = Math.max(
      1,
      Math.min(
        42,
        Math.round(Math.log10(layer.frontierSize + 1) * 6),
      ),
    );
    const radiusX = 22 + (layer.distance * 19);
    const radiusY = 16 + (layer.distance * 13);
    const startAngle = -Math.PI * 0.92;
    const angleSpan = Math.PI * 1.84;
    for (let index = 0; index < dotCount; index += 1) {
      const ratio = dotCount === 1 ? 0.5 : index / (dotCount - 1);
      const angle = startAngle + (angleSpan * ratio);
      const wobble = (((index * 37) + (layer.distance * 13)) % 17) - 8;
      dots.push({
        x: centerX + ((radiusX + wobble) * Math.cos(angle)),
        y: centerY + ((radiusY + (wobble * 0.65)) * Math.sin(angle)),
        radius: Math.max(3, Math.min(6.5, Math.log10(layer.frontierSize + 1) * 0.9)),
        distance: layer.distance,
        frontierSize: layer.frontierSize,
        isSource: false,
        isTarget: layer.targetOnFrontier,
        isLargestFrontier: layer.distance === largestFrontierLayer.distance,
        opacity: layer.distance === largestFrontierLayer.distance ? 0.9 : 0.72,
      });
    }
  }

  const tailStartX = 548;
  const tailEndX = 850;
  for (const [index, layer] of tailLayers.entries()) {
    const ratio = tailLayers.length <= 1 ? 1 : index / (tailLayers.length - 1);
    const dot = {
      x: tailStartX + ((tailEndX - tailStartX) * ratio),
      y: centerY + (Math.sin(index * 0.72) * 34),
      radius: layer.targetOnFrontier ? 7 : 3.5,
      distance: layer.distance,
      frontierSize: layer.frontierSize,
      isSource: false,
      isTarget: layer.targetOnFrontier,
      isLargestFrontier: false,
      opacity: layer.targetOnFrontier ? 1 : 0.74,
    };
    dots.push(dot);
    tailDots.push(dot);
  }

  const tailLine = d3.line<WavefrontMapDot>()
    .x((dot) => dot.x)
    .y((dot) => dot.y)
    .curve(d3.curveCatmullRom.alpha(0.6));

  svg.append("path")
    .datum(tailDots)
    .attr("class", "diameter-wavefront-tail-line")
    .attr("d", tailLine);

  svg.selectAll<SVGCircleElement, WavefrontMapDot>(".diameter-wavefront-dot")
    .data(dots)
    .join("circle")
    .attr("class", (dot) => [
      "diameter-wavefront-dot",
      dot.isSource ? "is-source" : "",
      dot.isTarget ? "is-target" : "",
      dot.isLargestFrontier ? "is-largest-frontier" : "",
    ].filter(Boolean).join(" "))
    .attr("cx", (dot) => dot.x)
    .attr("cy", (dot) => dot.y)
    .attr("r", (dot) => dot.radius)
    .attr("fill", (dot) => colorForDistance(dot.distance, targetDistance))
    .attr("opacity", (dot) => dot.opacity)
    .append("title")
    .text((dot) => `distance ${dot.distance}: ${formatInteger(dot.frontierSize)} page${dot.frontierSize === 1 ? "" : "s"}`);

  const targetLayer = snapshot.wavefront.layers.find((layer) => layer.targetOnFrontier);
  svg.append("text")
    .attr("class", "diameter-wavefront-label")
    .attr("x", centerX - 42)
    .attr("y", centerY + 34)
    .text("source");

  svg.append("text")
    .attr("class", "diameter-wavefront-label")
    .attr("x", 510)
    .attr("y", 92)
    .text(`largest frontier: distance ${largestFrontierLayer.distance}, ${formatCompact(largestFrontierLayer.frontierSize)} pages`);

  svg.append("text")
    .attr("class", "diameter-wavefront-label is-target")
    .attr("x", 714)
    .attr("y", 306)
    .text(`target at distance ${targetLayer?.distance ?? targetDistance}`);

  svg.append("text")
    .attr("class", "diameter-wavefront-caption")
    .attr("x", 46)
    .attr("y", 392)
    .text("compressed BFS map: dots are buckets of pages at the same click distance; the long tail is one page wide near the end");
}

function renderWavefrontChart(snapshot: SnapshotData, scaleMode: FrontierScale): void {
  const svgElement = getRequiredElement<SVGSVGElement>("wavefront-chart");
  const svg = d3.select(svgElement);
  svg.selectAll("*").remove();

  const width = 920;
  const height = 380;
  const margin = {
    top: 28,
    right: 30,
    bottom: 54,
    left: 76,
  };
  const layers = snapshot.wavefront.layers;
  const chartBottom = height - margin.bottom;
  const chartRight = width - margin.right;
  const maxFrontier = d3.max(layers, (layer) => layer.frontierSize) ?? 1;
  const x = d3.scaleBand<number>()
    .domain(layers.map((layer) => layer.distance))
    .range([margin.left, chartRight])
    .padding(0.14);
  const y = scaleMode === "log"
    ? d3.scaleLog()
      .domain([1, maxFrontier])
      .range([chartBottom, margin.top])
      .nice()
    : d3.scaleLinear()
      .domain([0, maxFrontier])
      .range([chartBottom, margin.top])
      .nice();
  const logTickValues = [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000].filter(
    (tickValue) => tickValue <= maxFrontier,
  );
  const gridAxis = d3.axisLeft(y)
    .tickSize(-(chartRight - margin.left))
    .tickFormat(() => "");
  const yAxis = d3.axisLeft(y)
    .tickFormat((value) => formatCompact(Number(value)));
  if (scaleMode === "log") {
    gridAxis.tickValues(logTickValues);
    yAxis.tickValues(logTickValues);
  } else {
    gridAxis.ticks(5);
    yAxis.ticks(5);
  }

  svg.append("g")
    .attr("class", "diameter-chart-grid")
    .attr("transform", `translate(${margin.left},0)`)
    .call(gridAxis);

  svg.append("g")
    .attr("class", "diameter-chart-axis")
    .attr("transform", `translate(0,${chartBottom})`)
    .call(d3.axisBottom(x).tickValues(layers.filter((layer) => layer.distance % 5 === 0 || layer.targetOnFrontier || layer.distance <= 2).map((layer) => layer.distance)));

  svg.append("g")
    .attr("class", "diameter-chart-axis")
    .attr("transform", `translate(${margin.left},0)`)
    .call(yAxis);

  svg.selectAll<SVGRectElement, WavefrontLayer>(".wavefront-bar")
    .data(layers)
    .join("rect")
    .attr("class", (layer) => `diameter-bar wavefront-bar${layer.targetOnFrontier ? " is-target" : ""}`)
    .attr("x", (layer) => x(layer.distance) ?? margin.left)
    .attr("y", (layer) => visibleBarY(layer.frontierSize, y, chartBottom))
    .attr("width", x.bandwidth())
    .attr("height", (layer) => visibleBarHeight(layer.frontierSize, y, chartBottom))
    .append("title")
    .text((layer) => (
      `distance ${layer.distance}: ${formatInteger(layer.frontierSize)} pages, ${formatInteger(layer.linksScanned)} links scanned`
    ));

  const targetLayer = layers.find((layer) => layer.targetOnFrontier);
  if (targetLayer !== undefined) {
    const targetX = (x(targetLayer.distance) ?? margin.left) + (x.bandwidth() / 2);
    const targetY = visibleBarY(targetLayer.frontierSize, y, chartBottom);
    svg.append("line")
      .attr("class", "diameter-target-line")
      .attr("x1", targetX)
      .attr("x2", targetX)
      .attr("y1", margin.top)
      .attr("y2", chartBottom);
    svg.append("text")
      .attr("class", "diameter-chart-callout")
      .attr("x", Math.max(margin.left + 8, targetX - 118))
      .attr("y", Math.max(margin.top + 18, targetY - 14))
      .text(`target at distance ${targetLayer.distance}`);
  }

  svg.append("text")
    .attr("class", "diameter-chart-label")
    .attr("x", width / 2)
    .attr("y", height - 12)
    .attr("text-anchor", "middle")
    .text("click distance from witness source");

  svg.append("text")
    .attr("class", "diameter-chart-label")
    .attr("x", 18)
    .attr("y", height / 2)
    .attr("text-anchor", "middle")
    .attr("transform", `rotate(-90,18,${height / 2})`)
    .text(`frontier pages, ${scaleMode} scale`);

  getRequiredElement<HTMLElement>("wavefront-summary").textContent =
    `${formatCompact(snapshot.wavefront.reachablePages)} pages are reachable from ${snapshot.wavefront.originTitle}; one-page layers are drawn with a minimum height.`;
}

function renderHistogramChart(histogram: RandomPairHistogram): void {
  const svgElement = getRequiredElement<SVGSVGElement>("distance-histogram-chart");
  const svg = d3.select(svgElement);
  svg.selectAll("*").remove();

  const width = 920;
  const height = 380;
  const margin = {
    top: 28,
    right: 30,
    bottom: 54,
    left: 76,
  };
  const bins = buildDenseHistogramBins(histogram);
  const chartBottom = height - margin.bottom;
  const chartRight = width - margin.right;
  const maxCount = d3.max(bins, (bin) => bin.count) ?? 1;
  const x = d3.scaleBand<number>()
    .domain(bins.map((bin) => bin.distance))
    .range([margin.left, chartRight])
    .padding(0.18);
  const y = d3.scaleLog()
    .domain([1, maxCount])
    .range([chartBottom, margin.top])
    .nice();

  svg.append("g")
    .attr("class", "diameter-chart-grid")
    .attr("transform", `translate(${margin.left},0)`)
    .call(
      d3.axisLeft(y)
        .tickValues([1, 10, 100, 1_000, 10_000])
        .tickSize(-(chartRight - margin.left))
        .tickFormat(() => ""),
    );

  svg.append("g")
    .attr("class", "diameter-chart-axis")
    .attr("transform", `translate(0,${chartBottom})`)
    .call(d3.axisBottom(x));

  svg.append("g")
    .attr("class", "diameter-chart-axis")
    .attr("transform", `translate(${margin.left},0)`)
    .call(
      d3.axisLeft(y)
        .tickValues([1, 10, 100, 1_000, 10_000])
        .tickFormat((value) => formatCompact(Number(value))),
    );

  svg.selectAll<SVGRectElement, HistogramBin>(".histogram-bar")
    .data(bins)
    .join("rect")
    .attr("class", "diameter-bar histogram-bar")
    .attr("x", (bin) => x(bin.distance) ?? margin.left)
    .attr("y", (bin) => visibleBarY(bin.count, y, chartBottom))
    .attr("width", x.bandwidth())
    .attr("height", (bin) => visibleBarHeight(bin.count, y, chartBottom))
    .append("title")
    .text((bin) => (
      `distance ${bin.distance}: ${formatInteger(bin.count)} pairs (${formatPercent(bin.shareOfReachablePairs)} of reachable pairs)`
    ));

  svg.append("text")
    .attr("class", "diameter-chart-label")
    .attr("x", width / 2)
    .attr("y", height - 12)
    .attr("text-anchor", "middle")
    .text("shortest path length");

  svg.append("text")
    .attr("class", "diameter-chart-label")
    .attr("x", 18)
    .attr("y", height / 2)
    .attr("text-anchor", "middle")
    .attr("transform", `rotate(-90,18,${height / 2})`)
    .text("random pairs, log scale");

  const modalBin = bins.reduce((bestBin, bin) => bin.count > bestBin.count ? bin : bestBin, bins[0]);
  getRequiredElement<HTMLElement>("histogram-summary").textContent =
    `${formatInteger(histogram.sampleSize)} random pairs, ${formatPercent(histogram.reachableShare)} reachable; the mode is distance ${modalBin.distance}.`;
}

function renderPriorWork(priorWork: PriorWorkLink[]): void {
  getRequiredElement<HTMLElement>("diameter-prior-work").innerHTML = priorWork
    .map((item) => `<a class="diameter-reference" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`)
    .join("");
}

function updateFrontierScaleButtons(scaleMode: FrontierScale): void {
  for (const buttonElement of document.querySelectorAll<HTMLButtonElement>(".diameter-scale-button[data-scale]")) {
    const isSelected = buttonElement.dataset.scale === scaleMode;
    buttonElement.classList.toggle("is-active", isSelected);
    buttonElement.setAttribute("aria-pressed", String(isSelected));
  }
}

function renderSnapshot(
  data: DiameterExplorerData,
  snapshot: SnapshotData,
  scaleMode: FrontierScale,
  onSnapshotSelect: (snapshot: SnapshotData) => void,
): void {
  renderSnapshotTabs(data, snapshot, onSnapshotSelect);
  renderSnapshotSummary(snapshot, data.methodNote);
  renderWavefrontMap(snapshot);
  renderWavefrontChart(snapshot, scaleMode);
  updateFrontierScaleButtons(scaleMode);
}

async function initializeDiameterPage(): Promise<void> {
  const response = await fetch("/data/diameter-explorer.json");
  if (!response.ok) {
    throw new Error(`Failed to load diameter data: ${response.status}`);
  }
  const data = await response.json() as DiameterExplorerData;
  let selectedSnapshot = data.snapshots[data.snapshots.length - 1];
  let frontierScale: FrontierScale = "log";
  if (selectedSnapshot === undefined) {
    throw new Error("Diameter data does not include any snapshots.");
  }

  const rerenderSnapshot = () => {
    renderSnapshot(
      data,
      selectedSnapshot,
      frontierScale,
      (nextSnapshot) => {
        selectedSnapshot = nextSnapshot;
        rerenderSnapshot();
      },
    );
  };

  for (const buttonElement of document.querySelectorAll<HTMLButtonElement>(".diameter-scale-button[data-scale]")) {
    buttonElement.addEventListener("click", () => {
      const nextScale = buttonElement.dataset.scale;
      if (nextScale === "log" || nextScale === "linear") {
        frontierScale = nextScale;
        rerenderSnapshot();
      }
    });
  }

  rerenderSnapshot();
  renderHistogramChart(data.randomPairHistogram);
  renderPriorWork(data.priorWork);
}

void initializeDiameterPage();
