import { notFound } from "next/navigation";
import { PublishedArticleView } from "@/components/articles/PublishedArticles";
import { articleIdPattern } from "@/lib/articles";
import { readPublishedArticle } from "@/lib/publicArticles";

export default async function ArticlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!articleIdPattern.test(id)) notFound();
  const article = await readPublishedArticle(id);
  if (!article) notFound();
  return (
    <main className="min-h-[calc(100dvh-4rem)] bg-slate-950 px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-3xl">
        <PublishedArticleView article={article} />
      </div>
    </main>
  );
}
