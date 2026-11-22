"use client";

import type { ReactNode } from "react";
import { articleIdPattern, articleImageSrc, isArticleLink, type ArticleNode } from "@/lib/articles";
import { useI18n } from "@/i18n/I18nProvider";

export const articleTypography = "min-w-0 break-words leading-relaxed [&_p]:my-3 [&_p]:whitespace-pre-wrap [&_h2]:mb-2 [&_h2]:mt-6 [&_h2]:text-xl [&_h2]:font-bold [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_a]:text-sky-300 [&_a]:underline [&_a]:[overflow-wrap:anywhere]";

export function ArticleImage({ id, caption }: { id: string; caption: string }) {
  const { t } = useI18n();
  if (!articleIdPattern.test(id)) return null;
  const src = articleImageSrc(id);
  return (
    <figure className="my-5 min-w-0">
      <a href={src} target="_blank" rel="noopener noreferrer" aria-label={t("articles.openImage")} className="inline-block max-w-full">
        {/* The original WebP remains available at its full size for reading screenshot text. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={caption || t("articles.image")} loading="lazy" decoding="async"
          className="block h-auto max-w-full rounded-lg border border-white/10" />
      </a>
      {caption && <figcaption className="mt-2 whitespace-pre-wrap text-sm text-slate-400">{caption}</figcaption>}
    </figure>
  );
}

function renderNode(node: ArticleNode): ReactNode {
  switch (node.type) {
    case "doc": return renderChildren(node);
    case "paragraph": return <p>{renderChildren(node)}</p>;
    case "heading": return <h2>{renderChildren(node)}</h2>;
    case "bulletList": return <ul>{renderChildren(node)}</ul>;
    case "listItem": return <li>{renderChildren(node)}</li>;
    case "hardBreak": return <br />;
    case "articleImage": return <ArticleImage id={String(node.attrs?.imageId ?? "")} caption={String(node.attrs?.caption ?? "")} />;
    case "text":
      return (node.marks ?? []).reduce<ReactNode>((text, mark) => {
        const href = mark.attrs?.href;
        if (mark.type === "bold") return <strong>{text}</strong>;
        if (mark.type === "link" && typeof href === "string" && isArticleLink(href)) {
          // Direct navigation lets the existing Details screen read every query parameter on mount.
          return <a href={href}>{text}</a>;
        }
        return text;
      }, node.text);
    default: return null;
  }
}

function renderChildren(node: ArticleNode) {
  return node.content?.map((child, index) => <ArticleNodeView key={index} node={child} />);
}

function ArticleNodeView({ node }: { node: ArticleNode }) {
  return renderNode(node);
}

export default function ArticleBody({ body }: { body: ArticleNode }) {
  return <div className={articleTypography}>{renderNode(body)}</div>;
}
