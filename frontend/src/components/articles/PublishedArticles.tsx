"use client";

import LocalizedLink from "@/components/LocalizedLink";
import { useI18n } from "@/i18n/I18nProvider";
import { articleHref, type ArticleSummary, type PublishedArticle } from "@/lib/articles";
import ArticleBody from "./ArticleBody";
import { ReferenceScopeText } from "./ArticleReferenceScope";

function ArticleDates({ article }: { article: ArticleSummary }) {
  const { locale, t } = useI18n();
  const format = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "Asia/Tokyo" });
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-400">
      <span>{t("articles.publishedOn")} <time dateTime={article.published_at}>{format.format(new Date(article.published_at))}</time></span>
      <span>{t("articles.updatedOn")} <time dateTime={article.updated_at}>{format.format(new Date(article.updated_at))}</time></span>
    </div>
  );
}

export function PublishedArticleView({ article, inSummary = false, anchor }: { article: PublishedArticle; inSummary?: boolean; anchor?: string }) {
  const { t } = useI18n();
  const Title = inSummary ? "h3" : "h1";
  return (
    <article id={anchor} tabIndex={anchor ? -1 : undefined} className="min-w-0 scroll-mt-24 space-y-4">
      <header className="space-y-2">
        <Title lang="ja" className="break-words text-2xl font-bold text-slate-100 sm:text-3xl">
          {inSummary ? <LocalizedLink href={articleHref(article.id)} prefetch={false} className="hover:text-sky-300">{article.title}</LocalizedLink> : article.title}
        </Title>
        <ArticleDates article={article} />
        {article.reference_scope && <p className="text-sm text-slate-300"><ReferenceScopeText scope={article.reference_scope} /></p>}
      </header>
      <div lang="ja"><ArticleBody body={article.body} /></div>
      {inSummary && <LocalizedLink href={articleHref(article.id)} prefetch={false} className="inline-block py-2 text-sm text-sky-300 underline">{t("articles.permalink")}</LocalizedLink>}
    </article>
  );
}

export function PublishedArticleList({ articles }: { articles: ArticleSummary[] }) {
  const { t } = useI18n();
  if (!articles.length) return <p className="text-slate-400">{t("articles.noPublicArticles")}</p>;
  return (
    <ul className="divide-y divide-white/10">
      {articles.map(article => (
        <li key={article.id} className="space-y-1 py-3">
          <LocalizedLink href={articleHref(article.id)} prefetch={false} lang="ja" className="block break-words py-1 font-semibold text-sky-300 underline">{article.title}</LocalizedLink>
          <ArticleDates article={article} />
        </li>
      ))}
    </ul>
  );
}

export function GuideList({ articles }: { articles: ArticleSummary[] }) {
  const { t } = useI18n();
  return (
    <main className="min-h-[calc(100dvh-4rem)] bg-slate-950 px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-3xl font-bold">{t("articles.guide")}</h1>
        <PublishedArticleList articles={articles} />
      </div>
    </main>
  );
}
