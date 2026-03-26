const integerFormatter = new Intl.NumberFormat("en-US");

export function formatInteger(value: number): string {
  return integerFormatter.format(value);
}

export function formatDurationMs(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }
  if (value >= 100) {
    return `${value.toFixed(0)} ms`;
  }
  if (value >= 10) {
    return `${value.toFixed(1)} ms`;
  }
  return `${value.toFixed(2)} ms`;
}

export function formatDumpDate(dumpDate: string): string {
  if (!/^\d{8}$/.test(dumpDate)) {
    return dumpDate;
  }

  const year = dumpDate.slice(0, 4);
  const month = dumpDate.slice(4, 6);
  const day = dumpDate.slice(6, 8);
  return `${year}-${month}-${day}`;
}
