import { getApiBaseUrl, getWebSocketBaseUrl } from "./api";
import type { RaceStateResponse, StoredRaceEvent } from "./race-types";

export async function loadRaceState(raceId: string): Promise<RaceStateResponse> {
  const response = await fetch(`${getApiBaseUrl()}/v1/races/${encodeURIComponent(raceId)}`);
  if (!response.ok) {
    throw new Error(`Race load failed with status ${response.status}`);
  }
  return (await response.json()) as RaceStateResponse;
}

export function connectRaceStream(options: {
  raceId: string;
  afterSequence: number;
  onEvent: (event: StoredRaceEvent) => void;
  onStatus: (status: string) => void;
}): WebSocket {
  const params = new URLSearchParams({
    after_sequence: String(options.afterSequence),
  });
  const socket = new WebSocket(`${getWebSocketBaseUrl()}/v1/races/${encodeURIComponent(options.raceId)}/stream?${params.toString()}`);
  socket.addEventListener("open", () => options.onStatus("connected"));
  socket.addEventListener("close", () => options.onStatus("disconnected"));
  socket.addEventListener("error", () => options.onStatus("error"));
  socket.addEventListener("message", (message) => {
    const parsed = JSON.parse(message.data as string) as StoredRaceEvent | { type: string };
    if ("stream_sequence" in parsed) {
      options.onEvent(parsed);
    }
  });
  return socket;
}
