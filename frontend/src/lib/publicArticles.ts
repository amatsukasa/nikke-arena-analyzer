import "server-only";
import type { ArticleSummary, PublishedArticle } from "./articles";

const backend = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function readPublishedArticle(id: string): Promise<PublishedArticle | null> {
  const response = await fetch(`${backend}/api/articles/${id}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Published article lookup failed");
  return response.json();
}

export async function listPublishedGuides(): Promise<ArticleSummary[]> {
  const response = await fetch(`${backend}/api/articles/guides`, { cache: "no-store" });
  if (!response.ok) throw new Error("Published guide listing failed");
  return response.json();
}
