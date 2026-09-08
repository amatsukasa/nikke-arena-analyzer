"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import CharacterSearchSelect from "../CharacterSearchSelect";
import { useCharacterCatalog } from "../../hooks/useCharacterCatalog";

type SearchCharacter = {
  id: number;
  name: string;
  rarity: string;
  usage_count?: number;
  image_url?: string;
};

type Template = {
  filename: string;
  character_id: number;
  generation: number;
  size_bytes: number;
  sha256: string;
  registered_at: string;
  active: boolean;
  representative: boolean;
};
type CharacterGroup = {
  character_id: number;
  character_name: string;
  active: Template[];
  quarantined: Template[];
  pending_count: number;
  representative_url: string | null;
};
type Review = {
  id: number;
  status: string;
  predicted_character_id: number;
  corrected_character_id: number;
  matched_template_filename: string;
  corrected_template_filename: string | null;
  similarity: number | null;
  tournament_id: number;
  player_id: number | null;
  seed_number: number | null;
  champion_slot: number | null;
  round_number: number;
  position: number;
  created_at: string;
};

const TEMPLATE_PAGE_SIZE = 30;
const REVIEW_PAGE_SIZE = 15;

export default function CharacterTemplatesAdmin({
  embedded = false,
  initialCharacterFilter = null,
}: {
  embedded?: boolean;
  initialCharacterFilter?: { id: number; name: string } | null;
}) {
  const { user, token, isLoading, apiFetch } = useAuth();
  const router = useRouter();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [groups, setGroups] = useState<CharacterGroup[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [tab, setTab] = useState<"pending" | "active" | "quarantine">(
    initialCharacterFilter ? "active" : "pending",
  );
  const [draftQuery, setDraftQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [characterFilter, setCharacterFilter] = useState(initialCharacterFilter);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reassigning, setReassigning] = useState<{
    characterId: number;
    characterName: string;
    filename: string;
  } | null>(null);
  const [targetCharacterId, setTargetCharacterId] = useState<number | null>(null);
  const loadController = useRef<AbortController | null>(null);
  const isComposing = useRef(false);
  const { characters } = useCharacterCatalog<SearchCharacter>(() =>
    setError("Character候補を取得できませんでした。"),
  );

  const load = useCallback(async () => {
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    setLoading(true);
    setError("");
    try {
      if (tab === "pending") {
        const response = await apiFetch(
          `${apiUrl}/api/admin/character-template-reviews?status=pending&offset=${(page - 1) * REVIEW_PAGE_SIZE}&limit=${REVIEW_PAGE_SIZE}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("要確認一覧を取得できませんでした。");
        const body = await response.json();
        setReviews(body.reviews ?? []);
        setGroups([]);
        setTotalItems(body.total ?? 0);
      } else {
        const params = new URLSearchParams({
          state: tab,
          offset: String((page - 1) * TEMPLATE_PAGE_SIZE),
          limit: String(TEMPLATE_PAGE_SIZE),
          query: appliedQuery,
        });
        if (characterFilter) params.set("character_id", String(characterFilter.id));
        const response = await apiFetch(
          `${apiUrl}/api/admin/character-templates?${params}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("テンプレート情報を取得できませんでした。");
        const body = await response.json();
        setGroups(body.characters ?? []);
        setReviews([]);
        setTotalItems(body.total ?? 0);
      }
    } catch (reason) {
      if (controller.signal.aborted) return;
      setError(
        reason instanceof Error ? reason.message : "取得に失敗しました。",
      );
    } finally {
      if (loadController.current === controller) {
        loadController.current = null;
        setLoading(false);
      }
    }
  }, [apiFetch, apiUrl, appliedQuery, characterFilter, page, tab]);

  useEffect(() => {
    if (isLoading) return;
    if (!token) router.replace("/secret-login");
    else if (user?.role !== "admin") router.replace("/staff");
    else void load();
    return () => {
      loadController.current?.abort();
      loadController.current = null;
    };
  }, [isLoading, token, user, router, load]);

  const templateEntries = useMemo(
    () => groups.flatMap((group) =>
      (tab === "active" ? group.active : group.quarantined).map((template) => ({ group, template })),
    ),
    [groups, tab],
  );
  const pageSize = tab === "pending" ? REVIEW_PAGE_SIZE : TEMPLATE_PAGE_SIZE;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const visibleReviews = reviews;
  const visibleTemplates = templateEntries;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);
  const run = async (key: string, url: string, options: RequestInit): Promise<boolean> => {
    if (busy) return false;
    setBusy(key);
    setError("");
    try {
      const response = await apiFetch(`${apiUrl}${url}`, options);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "操作に失敗しました。");
      }
      await load();
      return true;
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "操作に失敗しました。",
      );
      return false;
    } finally {
      setBusy("");
    }
  };

  const applySearch = () => {
    setPage(1);
    setAppliedQuery(draftQuery);
  };
  const clearSearch = () => {
    setDraftQuery("");
    setAppliedQuery("");
    setCharacterFilter(null);
    setPage(1);
  };

  if (isLoading)
    return (
      <main
        className={
          embedded
            ? "rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-100 shadow-2xl"
            : "min-h-screen bg-slate-950 p-6 text-slate-100"
        }
      >
        読み込み中…
      </main>
    );
  return (
    <main
      className={
        embedded
          ? "rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-100 shadow-2xl"
          : "min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-8"
      }
    >
      <div className={embedded ? "space-y-5" : "mx-auto max-w-6xl space-y-5"}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className={embedded ? "text-lg font-bold" : "text-2xl font-bold"}>
              Characterテンプレート管理
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              無効化は復元可能です。完全削除は無効化済み画像だけが対象です。
            </p>
          </div>
          {!embedded && (
            <button
              className="rounded border border-slate-600 px-4 py-2"
              onClick={() => router.push("/admin")}
            >
              管理画面へ戻る
            </button>
          )}
        </div>
        {error && (
          <div
            role="alert"
            className="rounded border border-red-700 bg-red-950/50 p-3 text-red-200"
          >
            {error}
          </div>
        )}
        <div className="flex gap-2 overflow-x-auto">
          {(
            [
              ["pending", "要確認"],
              ["active", "Character別テンプレート"],
              ["quarantine", "無効化済み"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => { setPage(1); setTab(id); }}
              className={`whitespace-nowrap rounded px-4 py-2 ${tab === id ? "bg-indigo-600" : "bg-slate-800"}`}
            >
              {label}
            </button>
          ))}
        </div>
        {tab === "pending" ? (
          <section className="grid gap-4">
            {reviews.length === 0 && (
              <p className="text-slate-400">要確認はありません。</p>
            )}
            {visibleReviews.map((review) => (
              <article
                key={review.id}
                className="rounded-xl border border-amber-700/50 bg-slate-900 p-4"
              >
                <div className="grid gap-4 sm:grid-cols-[1fr_auto_1fr]">
                  <TemplateThumb
                    url={`/api/admin/character-templates/assets/active/${review.matched_template_filename}`}
                    label={`予測 Character ${review.predicted_character_id}`}
                  />
                  <div className="self-center text-center">→</div>
                  <TemplateThumb
                    url={
                      review.corrected_template_filename
                        ? `/api/admin/character-templates/assets/active/${review.corrected_template_filename}`
                        : ""
                    }
                    label={`修正 Character ${review.corrected_character_id}`}
                  />
                </div>
                <p className="mt-3 text-sm text-slate-400">
                  一致度:{" "}
                  {review.similarity == null
                    ? "不明"
                    : `${(review.similarity * 100).toFixed(1)}%`}{" "}
                  / 大会 {review.tournament_id} / R{review.round_number}-
                  {review.position}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    disabled={!!busy}
                    className="rounded bg-emerald-700 px-3 py-2"
                    onClick={() =>
                      window.confirm(
                        `この画像を予測Character ${review.predicted_character_id} のまま維持しますか？\n\n解析結果が正しく、利用者による修正が誤りだった場合に選びます。元のテンプレートは移動・無効化されません。`,
                      ) &&
                      void run(
                        `keep-${review.id}`,
                        `/api/admin/character-template-reviews/${review.id}/resolve`,
                        {
                          method: "POST",
                          body: JSON.stringify({ action: "keep" }),
                        },
                      )
                    }
                  >
                    元のCharacterのまま維持
                  </button>
                  <button
                    disabled={!!busy}
                    className="rounded bg-indigo-700 px-3 py-2"
                    onClick={() =>
                      window.confirm(
                        `Character ${review.predicted_character_id} から修正先Character ${review.corrected_character_id} へ移しますか？\n同じ画像が既にある場合は重複登録しません。`,
                      ) &&
                      void run(
                        `move-${review.id}`,
                        `/api/admin/character-template-reviews/${review.id}/resolve`,
                        {
                          method: "POST",
                          body: JSON.stringify({
                            action: "reassign",
                            target_character_id: review.corrected_character_id,
                          }),
                        },
                      )
                    }
                  >
                    修正先Characterへ移す
                  </button>
                  <button
                    disabled={!!busy}
                    className="rounded bg-amber-700 px-3 py-2"
                    onClick={() =>
                      window.confirm(
                        "この画像をどのCharacterにも使わず無効化しますか？\n照合対象から外れますが、後から復元できます。",
                      ) &&
                      void run(
                        `disable-review-${review.id}`,
                        `/api/admin/character-template-reviews/${review.id}/resolve`,
                        {
                          method: "POST",
                          body: JSON.stringify({ action: "disable" }),
                        },
                      )
                    }
                  >
                    どのCharacterにも使わず無効化
                  </button>
                </div>
              </article>
            ))}
          </section>
        ) : (
          <section className="space-y-4">
            {characterFilter && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-indigo-500/40 bg-indigo-950/30 p-3 text-sm">
                <span>絞り込み中: {characterFilter.name}（ID {characterFilter.id}）</span>
                <button type="button" onClick={clearSearch} className="rounded bg-slate-700 px-3 py-1">
                  絞り込み解除
                </button>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <input
                aria-label="Character名またはIDで検索"
                value={draftQuery}
                onChange={(event) => setDraftQuery(event.target.value)}
                onCompositionStart={() => { isComposing.current = true; }}
                onCompositionEnd={() => { isComposing.current = false; }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.nativeEvent.isComposing && !isComposing.current) applySearch();
                }}
                placeholder="名前またはIDで検索"
                className="min-w-64 flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2"
              />
              <button type="button" onClick={applySearch} className="rounded bg-indigo-600 px-4 py-2">検索</button>
              <button type="button" onClick={clearSearch} className="rounded bg-slate-700 px-4 py-2">クリア</button>
            </div>
            {loading ? (
              <p className="text-slate-400">読み込み中…</p>
            ) : templateEntries.length === 0 && (
              <p className="text-slate-400">
                該当するテンプレートはありません。
              </p>
            )}
            <div
              aria-busy={loading}
              className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
            {visibleTemplates.map(({ group, template }) => (
              <article
                key={template.filename}
                className="rounded-xl border border-slate-800 bg-slate-900 p-4"
              >
                <h2 className="font-bold">
                  {group.character_name}{" "}
                  <span className="text-sm text-slate-400">
                    ID {group.character_id} / 有効 {group.active.length} / 無効{" "}
                    {group.quarantined.length} / 要確認 {group.pending_count}
                  </span>
                </h2>
                <div className="mt-3 min-w-0 rounded border border-slate-700 p-2">
                        <TemplateThumb
                          url={`/api/admin/character-templates/assets/${tab === "active" ? "active" : "quarantine"}/${template.filename}`}
                          label={`${group.character_name} ${template.filename}`}
                        />
                        <p
                          className="mt-1 truncate text-xs"
                          title={template.filename}
                        >
                          {template.filename}
                        </p>
                        <p className="text-xs text-slate-400">
                          世代 {template.generation} /{" "}
                          {(template.size_bytes / 1024).toFixed(1)}KB
                          {template.representative ? " / 代表" : ""}
                        </p>
                        {tab === "active" ? (
                          <div className="mt-2 grid gap-2">
                            <button
                              disabled={!!busy}
                              className="rounded bg-indigo-700 py-1 text-sm"
                              onClick={() => {
                                setTargetCharacterId(null);
                                setReassigning({
                                  characterId: group.character_id,
                                  characterName: group.character_name,
                                  filename: template.filename,
                                });
                              }}
                            >
                              正しいCharacterへ移す
                            </button>
                            <button
                              disabled={!!busy}
                              className="rounded bg-amber-700 py-1 text-sm"
                              onClick={() =>
                                window.confirm(
                                  "この画像をテンプレートとして無効化しますか？\n照合対象から外れますが、後から復元できます。",
                                ) &&
                                void run(
                                  `disable-${template.filename}`,
                                  `/api/admin/character-templates/${group.character_id}/${template.filename}/disable`,
                                  { method: "POST", body: "{}" },
                                )
                              }
                            >
                              テンプレートとして無効化
                            </button>
                          </div>
                        ) : (
                          <div className="mt-2 grid gap-2">
                            <button
                              disabled={!!busy}
                              className="rounded bg-emerald-700 py-1 text-sm"
                              onClick={() =>
                                window.confirm(
                                  "この画像をテンプレートとして復元しますか？\n再び照合と代表画像の候補になります。",
                                ) && void run(
                                  `restore-${template.filename}`,
                                  `/api/admin/character-templates/${group.character_id}/${template.filename}/restore`,
                                  { method: "POST" },
                                )
                              }
                            >
                              復元
                            </button>
                            <button
                              disabled={!!busy}
                              className="rounded bg-red-800 py-1 text-sm"
                              onClick={() =>
                                window.confirm(
                                  "完全削除すると復元できません。本当に削除しますか？",
                                ) &&
                                window.confirm(
                                  "最終確認：完全削除しますか？",
                                ) &&
                                void run(
                                  `delete-${template.filename}`,
                                  `/api/admin/character-templates/${group.character_id}/${template.filename}?confirm=DELETE`,
                                  { method: "DELETE" },
                                )
                              }
                            >
                              完全削除
                            </button>
                          </div>
                        )}
                </div>
              </article>
            ))}
            </div>
          </section>
        )}
        <Pagination
          page={page}
          totalPages={totalPages}
          totalItems={totalItems}
          pageSize={pageSize}
          onPage={setPage}
        />
        {reassigning && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="template-reassign-title"
          >
            <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
              <h2 id="template-reassign-title" className="text-lg font-bold">
                正しいCharacterへ移す
              </h2>
              <p className="mt-2 text-sm text-slate-300">
                現在: {reassigning.characterName}（ID {reassigning.characterId}）
              </p>
              <label className="mt-5 block text-sm font-semibold" htmlFor="template-reassign-character">
                正しいCharacterを名前で検索
              </label>
              <CharacterSearchSelect
                id="template-reassign-character"
                value={targetCharacterId}
                onChange={setTargetCharacterId}
                characters={characters.filter((character) => character.id !== 9999)}
                allowUnknown={false}
                allowEmpty={false}
                placeholder="移動先Characterを選択"
                className="mt-2"
              />
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  disabled={!!busy}
                  onClick={() => {
                    setReassigning(null);
                    setTargetCharacterId(null);
                  }}
                  className="rounded border border-slate-600 px-4 py-2 text-slate-200 disabled:opacity-50"
                >
                  キャンセル
                </button>
                <button
                  type="button"
                  disabled={!!busy || targetCharacterId == null || targetCharacterId === reassigning.characterId}
                  onClick={async () => {
                    const target = characters.find((character) => character.id === targetCharacterId);
                    if (!target || !window.confirm(
                      `${reassigning.characterName}（ID ${reassigning.characterId}）の画像を${target.name}（ID ${target.id}）へ移しますか？\n同じ画像が既にある場合は重複登録しません。`,
                    )) return;
                    const succeeded = await run(
                      `reassign-${reassigning.filename}`,
                      `/api/admin/character-templates/${reassigning.characterId}/${reassigning.filename}/reassign`,
                      {
                        method: "POST",
                        body: JSON.stringify({ target_character_id: target.id }),
                      },
                    );
                    if (succeeded) {
                      setReassigning(null);
                      setTargetCharacterId(null);
                    }
                  }}
                  className="rounded bg-indigo-600 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  選択したCharacterへ移す
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function TemplateThumb({
  url,
  label,
}: {
  url: string;
  label: string;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [url]);
  return (
    <div>
      <p className="mb-1 text-sm font-semibold">{label}</p>
      {url && !failed ? (
        <img
          src={url}
          alt={label}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="aspect-square w-full rounded bg-slate-800 object-cover"
        />
      ) : (
        <div className="aspect-square rounded bg-slate-800 p-3 text-sm text-slate-400">
          画像なし
        </div>
      )}
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  totalItems,
  pageSize,
  onPage,
}: {
  page: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  if (totalItems <= pageSize) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, totalItems);
  return (
    <nav
      aria-label="テンプレート一覧のページ移動"
      className="mt-6 flex flex-wrap items-center justify-center gap-3"
    >
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className="rounded border border-slate-600 px-4 py-2 disabled:opacity-40"
      >
        前へ
      </button>
      <span className="text-sm text-slate-300">
        {first}～{last} / {totalItems}件（{page} / {totalPages}ページ）
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        className="rounded border border-slate-600 px-4 py-2 disabled:opacity-40"
      >
        次へ
      </button>
    </nav>
  );
}
