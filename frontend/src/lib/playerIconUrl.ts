export function playerIconUrl(url: string | null | undefined, revision = 0): string | null {
  if (!url) return null;
  if (!revision || url.includes("?")) return url;
  return `${url}?v=${revision}`;
}
