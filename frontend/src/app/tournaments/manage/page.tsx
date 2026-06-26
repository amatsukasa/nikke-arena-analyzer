"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Trophy, PlusCircle, ChevronRight, Trash2, X, ShieldAlert, Edit2, LogOut } from "lucide-react";
import { useAuth } from "../../../context/AuthContext";

interface Tournament {
  id: number;
  name: string;
  date: string;
  start_date: string;
  owner_name?: string;
  championship_id?: number;
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
  
  useEffect(() => {
    // 登録されたTournament（対戦データグループ）一覧を取得
    fetch("/api/tournaments")
      .then(res => res.json())
      .then(data => setTournaments(data))
      .catch(err => console.error(err));

    // 管理者画面で登録された大会タイトル（Championship）一覧を取得
    fetch("/api/championships")
      .then(res => res.json())
      .then(data => setChampionships(data))
      .catch(err => console.error(err));
  }, []);

  const openCreateModal = () => {
    setEditTournamentId(null);
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
    setEditTournamentId(t.id);
    setSelectedChampionshipId(t.championship_id ? t.championship_id.toString() : "");
    setNewOwnerName(t.owner_name || "");
    setNewDate(t.date ? t.date.split('T')[0] : new Date().toISOString().split('T')[0]);
    setNewStartDate(t.start_date ? t.start_date.split('T')[0] : "");
    setIsModalOpen(true);
  };

  const handleSave = () => {
    if (!selectedChampionshipId) {
      alert("大会名称（大会タイトル）を選択してください。まだ登録されていない場合は、管理者画面から登録してください。");
      return;
    }
    
    const champId = parseInt(selectedChampionshipId);
    const selectedChamp = championships.find(c => c.id === champId);

    const body = {
      name: selectedChamp ? selectedChamp.name : "",
      date: newDate || null,
      start_date: newStartDate || null,
      owner_name: newOwnerName || null,
      championship_id: champId,
      season: selectedChamp ? selectedChamp.name : "" // 表示用などに格納
    };

    if (editTournamentId) {
      // 編集モード
      fetch(`/api/tournaments/${editTournamentId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(() => window.location.reload());
    } else {
      // 新規作成モード
      fetch("/api/tournaments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(() => window.location.reload());
    }
  };

  const handleDelete = (e: React.MouseEvent, id: number) => {
    e.preventDefault(); // リンクへの遷移を防ぐ
    if (!window.confirm("この大会を削除してもよろしいですか？")) return;

    fetch(`/api/tournaments/${id}`, {
      method: "DELETE",
    }).then(() => window.location.reload());
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
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-slate-100">大会一覧</h2>
            <div className="flex items-center space-x-3">
              <Link
                href="/"
                className="flex items-center space-x-2 px-4 py-2 bg-white/5 hover:bg-white/10 ring-1 ring-white/10 rounded-full font-bold transition-all text-slate-400 hover:text-white"
              >
                <span className="text-sm">ダッシュボードへ戻る</span>
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
                <Link key={t.id} href={`/tournament/${t.championship_id || t.id}`}>
                  <div className="flex items-center justify-between p-5 bg-white/5 hover:bg-white/10 ring-1 ring-white/5 hover:ring-white/20 transition-all rounded-xl group/item">
                    <div>
                      <div className="text-lg font-bold text-slate-200 group-hover/item:text-blue-400 transition-colors">{t.name}</div>
                      {t.date && (
                        <div className="text-xs text-slate-500 mt-1">開催日: {t.date.split('T')[0]}</div>
                      )}
                    </div>
                    <div className="flex items-center space-x-4">
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
              <button 
                onClick={handleSave}
                disabled={championships.length === 0}
                className="w-full py-3 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl font-bold text-white shadow-lg transition-all hover:shadow-blue-500/25 active:scale-95 disabled:opacity-50"
              >
                {editTournamentId ? "更新する" : "作成する"}
              </button>
            </div>
          </div>
        </div>
      )}

    </main>
  );
}
