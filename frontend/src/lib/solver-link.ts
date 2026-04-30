import type { SolvePathMode } from "./api";

export interface SolverLinkParams {
  startTitle: string;
  targetTitle: string;
  pathMode: SolvePathMode | null;
}

export interface SolverLinkArticlePair {
  startTitle: string;
  targetTitle: string;
}

const PATH_MODE_ALIASES: Record<string, SolvePathMode> = {
  "1": "single",
  one: "single",
  single: "single",
  all: "all_shortest",
  all_shortest: "all_shortest",
};

export function normalizeSolverLinkPathMode(value: string | null): SolvePathMode | null {
  if (value === null) {
    return null;
  }
  return PATH_MODE_ALIASES[value.trim().toLowerCase()] ?? null;
}

export function readSolverLinkParams(search: string): SolverLinkParams | null {
  const searchParams = new URLSearchParams(search);
  const startTitle = (searchParams.get("start") ?? searchParams.get("from") ?? "").trim();
  const targetTitle = (searchParams.get("target") ?? searchParams.get("to") ?? "").trim();

  if (!startTitle || !targetTitle) {
    return null;
  }

  return {
    startTitle,
    targetTitle,
    pathMode: normalizeSolverLinkPathMode(
      searchParams.get("mode") ?? searchParams.get("path_mode"),
    ),
  };
}

export function buildSolverLinkSearchParams(
  articlePair: SolverLinkArticlePair,
  pathMode: SolvePathMode,
): URLSearchParams {
  return new URLSearchParams({
    start: articlePair.startTitle,
    target: articlePair.targetTitle,
    mode: pathMode,
  });
}

export function buildSolverLinkUrl(
  currentUrl: string,
  articlePair: SolverLinkArticlePair,
  pathMode: SolvePathMode,
): string {
  const nextUrl = new URL(currentUrl);
  nextUrl.search = buildSolverLinkSearchParams(articlePair, pathMode).toString();
  return nextUrl.toString();
}
