import type { SolvePathMode } from "./api";

export type SolverResultView = "timeline" | "graph";

export function getSolverResultView(pathMode: SolvePathMode): SolverResultView {
  return pathMode === "all_shortest" ? "graph" : "timeline";
}

export function getSolverResultTitle(pathMode: SolvePathMode): string {
  return pathMode === "all_shortest" ? "Shortest Paths" : "Shortest Path";
}
