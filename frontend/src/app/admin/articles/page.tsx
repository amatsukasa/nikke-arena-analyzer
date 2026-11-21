"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import LocalizedLink from "@/components/LocalizedLink";
import ArticleBody from "@/components/articles/ArticleBody";
import { useAuth } from "@/context/AuthContext";
import { useCharacterCatalog } from "@/hooks/useCharacterCatalog";
import { useI18n } from "@/i18n/I18nProvider";
import { articleHref, type AdminArticle, type AdminArticleSummary, type ArticleDraft, type ArticleKind } from "@/lib/articles";

const ArticleEditor = dynamic(() => import("@/components/articles/ArticleEditor"), { ssr: false });
const blank: ArticleDraft = {
  title: "", kind: "season", championship_id: null, character_ids: [],
  body: { type: "doc", content: [{ type: "paragraph" }] },
};

const field = "mt-1 block min-h-11 w-full rounded-lg border border-white/15 bg-slate-950 px-3 py-2 text-slate-100";
const button = "inline-flex min-h-11 items-center justify-center rounded-lg border border-white/15 px-4 py-2 text-sm font-semibold hover:bg-white/10 disabled:opacity-50";
const primary = `${button} bg-sky-700 text-white hover:bg-sky-600`;
const adminPage = "min-h-[calc(100dvh-4rem)] bg-slate-950 px-4 py-8 text-slate-100";
const endpoint = "/api/admin/articles";
type Championship = { id: number; name: string };
type Character = { id: number; name: string };

function ArticleForm({ initial, onBack }: { initial: AdminArticle | null; onBack: () => void }) {
  const { t } = useI18n();
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(() => initial?.draft ?? blank);
  const [championships, setChampionships] = useState<Championship[]>([]);
  const [titlesError, setTitlesError] = useState(false);
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState(false);
  const [pending, setPending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/championships", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Championship lookup failed");
        setChampionships(await response.json());
      })
      .catch(() => { if (!controller.signal.aborted) setTitlesError(true); });
    return () => controller.abort();
  }, []);

  function change(update: Partial<ArticleDraft>) {
    setDirty(true);
    setNotice("");
    setDraft(current => ({ ...current, ...update }));
  }

  async function save(publish: boolean) {
    setNotice("");
    setError("");
    if (publish && (!draft.title.trim() || (draft.kind === "season" && !draft.championship_id))) {
      setError(t("articles.publishRequired"));
      return;
    }
    setPending(true);
    try {
      const response = await fetch(saved ? `${endpoint}/${saved.id}` : endpoint, {
        method: saved ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft, publish, ...(saved ? { revision: saved.revision } : {}) }),
      });
      if (!response.ok) {
        const key = response.status === 409 ? "articles.conflict" : publish && response.status === 422 ? "articles.publishRequired" : "articles.saveError";
        setError(t(key));
        return;
      }
      setSaved(await response.json());
      setDirty(false);
      setNotice(t(publish ? "articles.publishedNotice" : "articles.savedNotice"));
    } catch {
      setError(t("articles.saveError"));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={button} disabled={pending || uploading} onClick={() => {
          if (!dirty || window.confirm(t("articles.discardChanges"))) onBack();
        }}>{t("articles.backToList")}</button>
        {saved?.published_at && (
          <LocalizedLink href={articleHref(saved.id)} target="_blank" rel="noopener noreferrer" className="text-sm text-sky-300 underline">
            {t("articles.permalink")}
          </LocalizedLink>
        )}
      </div>
      <fieldset disabled={pending} className="min-w-0 space-y-5">
        <div hidden={preview} className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="block text-sm">
              {t("articles.kind")}
              <select className={field} aria-label={t("articles.kind")} value={draft.kind} onChange={event => change({
                kind: event.target.value as ArticleKind, championship_id: null, character_ids: [],
              })}>
                <option value="season">{t("articles.season")}</option>
                <option value="guide">{t("articles.guide")}</option>
              </select>
            </label>
            {draft.kind === "season" && (
              <label className="block text-sm">
                {t("articles.championship")}
                <select className={field} aria-label={t("articles.championship")} value={draft.championship_id ?? ""} onChange={event => change({
                  championship_id: Number(event.target.value) || null,
                })}>
                  <option value="">{t("articles.selectChampionship")}</option>
                  {championships.map(championship => <option key={championship.id} value={championship.id}>
                    {championship.name} (#{championship.id})
                  </option>)}
                </select>
                {titlesError && <span role="alert" className="text-rose-300">{t("articles.loadError")}</span>}
              </label>
            )}
          </div>
          {draft.kind === "guide" && (
            <RelatedCharacters selected={draft.character_ids} search={search} setSearch={setSearch}
              setSelected={character_ids => change({ character_ids })} />
          )}
          <label className="block text-sm">
            {t("articles.title")}
            <input className={field} maxLength={200} value={draft.title} onChange={event => change({ title: event.target.value })} />
          </label>
          <ArticleEditor initialBody={draft.body} disabled={pending} onChange={body => change({ body })} onUploadState={setUploading} />
        </div>
        {preview && (
          <section aria-label={t("articles.preview")} className="space-y-4 rounded-xl border border-white/15 bg-slate-900 p-4">
            <h2 className="break-words text-2xl font-bold">{draft.title || t("articles.untitled")}</h2>
            <ArticleBody body={draft.body} />
          </section>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={button} disabled={uploading} onClick={() => void save(false)}>{t("articles.saveDraft")}</button>
          <button type="button" className={button} disabled={uploading} onClick={() => setPreview(!preview)}>{t(preview ? "articles.backToEdit" : "articles.preview")}</button>
          <button type="button" className={primary} disabled={uploading} onClick={() => void save(true)}>
            {t(saved?.published_at ? "articles.publishUpdate" : "articles.publish")}
          </button>
        </div>
      </fieldset>
      {notice && <p role="status" className="text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="text-rose-300">{error}</p>}
    </section>
  );
}

function RelatedCharacters({ selected, search, setSearch, setSelected }: {
  selected: number[]; search: string; setSearch: (value: string) => void; setSelected: (ids: number[]) => void;
}) {
  const { t } = useI18n();
  const [error, setError] = useState(false);
  const { characters } = useCharacterCatalog<Character>(() => setError(true));
  const query = search.trim().toLocaleLowerCase();
  const visible = characters.filter(character => character.name.toLocaleLowerCase().includes(query));
  return (
    <fieldset className="min-w-0 space-y-2 rounded-xl border border-white/15 p-3">
      <legend className="px-1 text-sm font-medium">{t("articles.characters")}</legend>
      <input type="search" className={field} aria-label={t("articles.searchCharacters")} placeholder={t("articles.searchCharacters")}
        value={search} onChange={event => setSearch(event.target.value)} />
      <div className="flex flex-wrap gap-2">
        {characters.filter(character => selected.includes(character.id)).map(character => (
          <button key={character.id} type="button" className={button}
            aria-label={t("articles.removeCharacter", { name: character.name })}
            onClick={() => setSelected(selected.filter(id => id !== character.id))}>{character.name} ×</button>
        ))}
      </div>
      {error && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
      <div className="grid max-h-44 grid-cols-1 gap-x-2 overflow-y-auto sm:grid-cols-2">
        {visible.map(character => (
          <label key={character.id} className="flex min-h-11 min-w-0 items-center gap-2 break-words px-1 text-sm">
            <input type="checkbox" checked={selected.includes(character.id)} onChange={event => setSelected(
              event.target.checked ? [...selected, character.id] : selected.filter(id => id !== character.id),
            )} />
            <span>{character.name}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function ArticleAdminPage() {
  const { t } = useI18n();
  const { user, isLoading } = useAuth();
  const [articles, setArticles] = useState<AdminArticleSummary[]>();
  const [form, setForm] = useState<AdminArticle | null>();
  const [listVersion, refreshList] = useState(0);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    fetch(endpoint, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) {
          if (!controller.signal.aborted) setError(response.status === 401 || response.status === 403 ? "articles.forbidden" : "articles.loadError");
          return;
        }
        const list = await response.json();
        if (!controller.signal.aborted) setArticles(list);
      })
      .catch(() => { if (!controller.signal.aborted) setError("articles.loadError"); });
    return () => controller.abort();
  }, [isAdmin, listVersion]);

  async function open(id: string) {
    setError("");
    setOpening(true);
    try {
      const response = await fetch(`${endpoint}/${id}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Draft lookup failed");
      setForm(await response.json());
    } catch {
      setError("articles.loadError");
    } finally {
      setOpening(false);
    }
  }

  if (isLoading) return <main className={adminPage}><p role="status">{t("articles.loading")}</p></main>;
  if (!isAdmin) return <main className={adminPage}><p role="alert">{t("articles.forbidden")}</p></main>;
  return (
    <main className={adminPage}>
      <div className="mx-auto max-w-4xl space-y-5">
        <LocalizedLink href="/admin" className="text-sm text-sky-300 underline">{t("articles.backToAdmin")}</LocalizedLink>
        <h1 className="text-3xl font-bold">{t("articles.admin")}</h1>
        {error && <p role="alert" className="text-rose-300">{t(error)}</p>}
        {form !== undefined ? (
          <ArticleForm key={form?.id ?? "new"} initial={form} onBack={() => {
            setForm(undefined);
            setArticles(undefined);
            refreshList(version => version + 1);
          }} />
        ) : articles ? (
          <section className="space-y-4">
            <button type="button" className={primary} onClick={() => setForm(null)} disabled={opening}>{t("articles.new")}</button>
            {!articles.length && <p className="text-slate-400">{t("articles.noDrafts")}</p>}
            <ul className="divide-y divide-white/10">
              {articles.map(article => (
                <li key={article.id} className="min-w-0 py-2">
                  <button type="button" disabled={opening} onClick={() => void open(article.id)}
                    className="w-full min-w-0 rounded-lg px-2 py-3 text-left hover:bg-white/5 disabled:opacity-50">
                    <span className="block break-words font-semibold text-sky-300">{article.title || t("articles.untitled")}</span>
                    <span className="text-sm text-slate-400">{t(`articles.${article.kind}`)} · {
                      t(!article.published_at ? "articles.draft" : article.has_unpublished_changes ? "articles.updatedDraft" : "articles.published")
                    }</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : !error && <p role="status">{t("articles.loading")}</p>}
      </div>
    </main>
  );
}
