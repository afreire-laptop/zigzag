export const formatTime = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);
