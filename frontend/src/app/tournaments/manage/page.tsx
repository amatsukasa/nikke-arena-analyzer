"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Trophy, PlusCircle, ChevronRight, Trash2, X, ShieldAlert, Edit2, LogOut, UserRound, Globe2, LockKeyhole } from "lucide-react";
import { useAuth } from "../../../context/AuthContext";

interface Tournament {
  id: number;
  name: string;
  date: string;
  start_date: string;
  owner_name?: string;
  championship_id?: number;
  publication_status: "draft" | "published";
  published_at?: string | null;
}

interface PublicationReadiness {
  player_count: number;
  complete_player_count: number;
  incomplete_player_count: number;
  unresolved_slot_count: number;
  match_count: number;
  can_publish: boolean;
  warnings: string[];
}

export default function Home() {
  const { user, logout } = useAuth();
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [championships, setChampionships] = useState<any[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editTournamentId, setEditTournamentId] = useState<number | null>(null);
  const [selectedChampionshipId, setSelectedChampionshipId] = useState<string>("");
  const [newOwnerName, setNewOwnerName] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newStartDate, setNewStartDate] = useState("");
  const [saveError, setSaveError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [publicationUpdatingId, setPublicationUpdatingId] = useState<number | null>(null);

  const loadTournaments = async () => {
    const res = await fetch(`/api/tournaments?mine=true&_=${Date.now()}`, {
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
      }
    });
    if (!res.ok) {
      throw new Error("大会一覧の取得に失敗しました。");
    }
    const data = await res.json();
    setTournaments(data);
  };

  const loadChampionships = async () => {
    const res = await fetch("/api/championships", { cache: "no-store" });
    if (!res.ok) {
      throw new Error("大会タイトル一覧の取得に失敗しました。");
    }
    const data = await res.json();
    setChampionships(data);
  };
  
  useEffect(() => {
    // 登録されたTournament（対戦データグループ）一覧を取得
    loadTournaments()
      .catch(err => console.error(err));

    // 管理者画面で登録された大会タイトル（Championship）一覧を取得
    loadChampionships()
      .catch(err => console.error(err));
  }, []);

  const openCreateModal = () => {
    setEditTournamentId(null);
    setSaveError("");
    if (championships.length > 0) {
      setSelectedChampionshipId(championships[0].id.toString());
    } else {
      setSelectedChampionshipId("");
    }
    setNewOwnerName("");
    setNewDate(new Date().toISOString().split('T')[0]);
    setNewStartDate("");
    setIsModalOpen(true);
  };

  const openEditModal = (e: React.MouseEvent, t: any) => {
    e.preventDefault();
    setSaveError("");
    setEditTournamentId(t.id);
    setSelectedChampionshipId(t.championship_id ? t.championship_id.toString() : "");
    setNewOwnerName(t.owner_name || "");
    setNewDate(t.date ? t.date.split('T')[0] : new Date().toISOString().split('T')[0]);
    setNewStartDate(t.start_date ? t.start_date.split('T')[0] : "");
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!selectedChampionshipId) {
      alert("大会名称（大会タイトル）を選択してください。まだ登録されていない場合は、管理者画面から登録してください。");
      return;
    }
    setSaveError("");
    setIsSaving(true);
    try {
      const champId = parseInt(selectedChampionshipId);
      const selectedChamp = championships.find(c => c.id === champId);
      const body = {
        name: selectedChamp ? selectedChamp.name : "",
        date: newDate || null,
        start_date: newStartDate || null,
        owner_name: newOwnerName || null,
        championship_id: champId,
        season: selectedChamp ? selectedChamp.name : ""
      };
      const url = editTournamentId
        ? `/api/tournaments/${editTournamentId}`
        : "/api/tournaments";
      const response = await fetch(url, {
        method: editTournamentId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = data.detail || data.message;
        throw new Error(typeof detail === "string" ? detail : "大会の保存に失敗しました。");
      }

      setTournaments(prev => editTournamentId
        ? prev.map(tournament => tournament.id === data.id ? data : tournament)
        : [data, ...prev.filter(tournament => tournament.id !== data.id)]
      );
      setIsModalOpen(false);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "大会の保存に失敗しました。");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.preventDefault(); // リンクへの遷移を防ぐ
    if (!window.confirm("この大会を削除してもよろしいですか？")) return;

    const response = await fetch(`/api/tournaments/${id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      alert(data.detail || data.message || "Failed to delete tournament.");
      return;
    }
    setTournaments(prev => prev.filter(t => t.id !== id));
  };

  const handlePublicationToggle = async (e: React.MouseEvent, tournament: Tournament) => {
    e.preventDefault();
    e.stopPropagation();
    const isPublished = tournament.publication_status === "published";
    setPublicationUpdatingId(tournament.id);

    try {
      if (!isPublished) {
        const readinessResponse = await fetch(`/api/tournaments/${tournament.id}/publication`, {
          cache: "no-store",
        });
        const publication = await readinessResponse.json().catch(() => ({}));
        if (!readinessResponse.ok) {
          throw new Error(publication.detail || publication.message || "公開状態を確認できませんでした。");
        }

        const readiness = publication.readiness as PublicationReadiness;
        const summary = [
          `登録プレイヤー: ${readiness.player_count}人`,
          `編成登録完了: ${readiness.complete_player_count}人`,
          `編成未完了: ${readiness.incomplete_player_count}人`,
          `未確定のキャラクター枠: ${readiness.unresolved_slot_count}件`,
          `対戦結果: ${readiness.match_count}件`,
        ];
        if (readiness.warnings?.length) {
          summary.push("", "確認事項:", ...readiness.warnings.map(warning => `・${warning}`));
        }
        if (!readiness.can_publish) {
          window.alert(`まだ公開できません。\n\n${summary.join("\n")}\n\n未完了の編成を確認してください。`);
          return;
        }
        if (!window.confirm(`この大会をトップページに公開しますか？\n\n${summary.join("\n")}`)) {
          return;
        }
      } else if (!window.confirm("この大会を非公開に戻しますか？\nトップページと集計結果から表示されなくなります。")) {
        return;
      }

      const response = await fetch(`/api/tournaments/${tournament.id}/publication`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ published: !isPublished }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.message || "公開状態を変更できませんでした。");
      }
      setTournaments(previous => previous.map(item => (
        item.id === tournament.id
          ? {
              ...item,
              publication_status: data.publication_status,
              published_at: data.published_at,
            }
          : item
      )));
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "公開状態を変更できませんでした。");
    } finally {
      setPublicationUpdatingId(null);
    }
  };

  return (
    <main className="p-6 md:p-12 max-w-5xl mx-auto">
      <div className="flex items-center space-x-4 mb-10">
        <div className="p-3 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl shadow-lg shadow-purple-500/20">
          <Trophy size={32} className="text-white" />
        </div>
        <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400 tracking-tight">
          NIKKE Arena Analyzer
        </h1>
      </div>

      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-purple-600 rounded-3xl blur opacity-25 group-hover:opacity-40 transition duration-1000"></div>
        <div className="relative bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 p-8 rounded-2xl shadow-2xl">
          <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center gap-4 mb-6">
            <h2 className="text-2xl font-bold text-slate-100">大会一覧</h2>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/account"
                className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                title="アカウント情報"
              >
                <UserRound size={18} />
              </Link>
              {user && user.role === 'admin' && (
                <Link
                  href="/admin"
                  className="flex items-center space-x-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 ring-1 ring-white/10 rounded-full font-bold transition-all text-slate-300 hover:text-white"
                >
                  <ShieldAlert size={16} />
                  <span className="text-sm">管理者画面へ</span>
                </Link>
              )}
              <button 
                onClick={openCreateModal}
                className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-400 hover:to-indigo-500 rounded-full font-bold shadow-lg transition-all active:scale-95 text-white"
              >
                <PlusCircle size={18} />
                <span>新規大会を作成</span>
              </button>
              <button 
                onClick={logout}
                className="flex items-center space-x-2 px-4 py-2 bg-red-650 hover:bg-red-500 ring-1 ring-red-500/20 text-red-400 hover:text-white rounded-full font-bold shadow-lg transition-all active:scale-95"
              >
                <LogOut size={16} />
                <span className="text-sm">ログアウト</span>
              </button>
            </div>
          </div>

          {tournaments.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <p>まだ大会が登録されていません。</p>
              <p className="text-sm mt-2">右上のボタンから最初の大会を作成してください。</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {tournaments.map(t => (
                <Link key={t.id} href={`/tournament/${t.id}`}>
                  <div className="flex items-center justify-between p-5 bg-white/5 hover:bg-white/10 ring-1 ring-white/5 hover:ring-white/20 transition-all rounded-xl group/item">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-lg font-bold text-slate-200 group-hover/item:text-blue-400 transition-colors">{t.name}</div>
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-bold ring-1 ${
                          t.publication_status === "published"
                            ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"
                            : "bg-amber-500/10 text-amber-300 ring-amber-500/30"
                        }`}>
                          {t.publication_status === "published" ? <Globe2 size={12} /> : <LockKeyhole size={12} />}
                          {t.publication_status === "published" ? "公開中" : "下書き"}
                        </span>
                      </div>
                      {t.date && (
                        <div className="text-xs text-slate-500 mt-1">開催日: {t.date.split('T')[0]}</div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center space-x-2 sm:space-x-4">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={t.publication_status === "published"}
                        disabled={publicationUpdatingId === t.id}
                        onClick={(e) => handlePublicationToggle(e, t)}
                        className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3 text-sm font-bold ring-1 transition-all disabled:cursor-wait disabled:opacity-50 ${
                          t.publication_status === "published"
                            ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30 hover:bg-emerald-500/25"
                            : "bg-slate-800 text-slate-300 ring-white/10 hover:bg-slate-700 hover:text-white"
                        }`}
                        title={t.publication_status === "published" ? "非公開に戻す" : "公開前の登録状況を確認する"}
                      >
                        {t.publication_status === "published" ? <Globe2 size={16} /> : <LockKeyhole size={16} />}
                        <span className="hidden sm:inline">
                          {publicationUpdatingId === t.id
                            ? "更新中"
                            : t.publication_status === "published" ? "公開中" : "公開する"}
                        </span>
                      </button>
                      <button 
                        onClick={(e) => openEditModal(e, t)}
                        className="p-2 text-slate-500 hover:text-blue-400 hover:bg-blue-400/10 rounded-lg transition-all"
                        title="大会情報を編集"
                      >
                        <Edit2 size={18} />
                      </button>
                      <button 
                        onClick={(e) => handleDelete(e, t.id)}
                        className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                        title="大会を削除"
                      >
                        <Trash2 size={18} />
                      </button>
                      <ChevronRight className="text-slate-600 group-hover/item:text-blue-400 group-hover/item:translate-x-1 transition-all" />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* カスタムポップアップ (Modal) */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 ring-1 ring-white/10 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-6 border-b border-white/5">
              <h3 className="text-xl font-bold text-slate-100">{editTournamentId ? "大会情報の編集" : "新規大会の作成"}</h3>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">大会名称 (大会タイトル)</label>
                {championships.length === 0 ? (
                  <div className="text-sm text-amber-500 bg-amber-500/10 p-3 rounded-lg border border-amber-500/25 mb-4">
                    大会タイトルが登録されていません。先に管理者画面の「大会タイトル管理」から登録してください。
                  </div>
                ) : (
                  <select 
                    value={selectedChampionshipId}
                    onChange={(e) => setSelectedChampionshipId(e.target.value)}
                    className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all mb-4"
                  >
                    <option value="" disabled>-- 大会タイトルを選択 --</option>
                    {championships.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} {c.date ? `(${c.date.split('T')[0]})` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              {saveError && (
                <div role="alert" className="text-sm text-red-300 bg-red-950/40 border border-red-800 rounded-lg p-3">
                  {saveError}
                </div>
              )}
              <button 
                onClick={handleSave}
                disabled={championships.length === 0 || isSaving}
                className="w-full py-3 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl font-bold text-white shadow-lg transition-all hover:shadow-blue-500/25 active:scale-95 disabled:opacity-50"
              >
                {isSaving ? "保存中..." : editTournamentId ? "更新する" : "作成する"}
              </button>
            </div>
          </div>
        </div>
      )}

    </main>
  );
}
