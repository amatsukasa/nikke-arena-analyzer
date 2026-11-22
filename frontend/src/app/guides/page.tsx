import { GuideList } from "@/components/articles/PublishedArticles";
import { listPublishedGuides } from "@/lib/publicArticles";

export default async function GuidesPage() {
  return <GuideList articles={await listPublishedGuides()} />;
}
