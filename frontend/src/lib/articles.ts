import type { ReferenceScope } from "./seasonSummary";

export type ArticleKind = "season" | "guide";

export type ArticleMark = { type: string; attrs?: Record<string, unknown> };

export type ArticleNode = {
  type?: string;
  attrs?: Record<string, unknown>;
  content?: ArticleNode[];
  marks?: ArticleMark[];
  text?: string;
};

export type ArticleDraft = {
  kind: ArticleKind;
  championship_id: number | null;
  character_ids: number[];
  title: string;
  body: ArticleNode;
  reference_scope?: ReferenceScope;
};

export type ArticleSummary = {
  id: string;
  title: string;
  kind: ArticleKind;
  championship_id: number | null;
  published_at: string;
  updated_at: string;
};

export type PublishedArticle = ArticleSummary & Pick<ArticleDraft, "body" | "character_ids" | "reference_scope">;
export type SeasonArticles = { latest: PublishedArticle | null; earlier: ArticleSummary[] };

export type AdminArticle = {
  id: string;
  revision: number;
  draft: ArticleDraft;
  published_at: string | null;
  has_unpublished_changes: boolean;
};

export type AdminArticleSummary =
  Pick<AdminArticle, "id" | "published_at" | "has_unpublished_changes"> & Pick<ArticleDraft, "kind" | "title">;

export const articleHref = (id: string) => `/articles/${id}`;
export const articleImageSrc = (id: string) => `/api/articles/images/${id}`;
export const articleIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isArticleLink(href: string): boolean {
  if (href.length > 2048 || /[\\\s\x00-\x1f\x7f]/.test(href)) return false;
  if (href.startsWith("/") && !href.startsWith("//")) return true;
  try {
    const url = new URL(href);
    return /^https?:\/\//i.test(href) && !!url.hostname && !url.username && !url.password;
  } catch {
    return false;
  }
}
