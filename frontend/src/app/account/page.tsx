"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Save, UserRound } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const SERVER_OPTIONS = [
  { value: "KR", label: "韓国（KR）" },
  { value: "JP", label: "日本（JP）" },
  { value: "GLOBAL", label: "グローバル（ヨーロッパ）" },
  { value: "NA", label: "北米" },
  { value: "SEA", label: "東南アジア" },
];

export default function AccountPage() {
  const { updateUser } = useAuth();
  const [email, setEmail] = useState("");
  const [providerName, setProviderName] = useState("");
  const [gameStartDate, setGameStartDate] = useState("");
  const [playServer, setPlayServer] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    fetch("/api/auth/me", { cache: "no-store" })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.message || "アカウント情報を取得できませんでした。");
        setEmail(data.email || "");
        setProviderName(data.provider_name || "");
        setGameStartDate(data.game_start_date || "");
        setPlayServer(data.play_server || "");
      })
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (newPassword !== confirmPassword) {
      setError("新しいパスワードが一致しません。");
      return;
    }

    setIsSaving(true);
    try {
      const response = await fetch("/api/auth/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          providerName,
          gameStartDate: gameStartDate || null,
          playServer: playServer || null,
          currentPassword,
          newPassword,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.message || "アカウント情報を更新できませんでした。");
      }
      updateUser(data.user);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSuccess("アカウント情報を更新しました。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "アカウント情報を更新できませんでした。");
    } finally {
      setIsSaving(false);
    }
  };

  const inputClass = "w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-3 text-slate-100 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-950 transition";

  return (
    <main className="min-h-screen px-4 py-8 md:py-12">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-600 rounded-lg">
              <UserRound size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold">アカウント情報</h1>
              <p className="text-sm text-slate-400 mt-1">登録情報とパスワードを変更できます</p>
            </div>
          </div>
          <Link href="/staff" className="p-2 text-slate-400 hover:text-white" title="大会一覧へ戻る">
            <ArrowLeft size={22} />
          </Link>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-lg p-6 md:p-8 space-y-6">
          {error && <div role="alert" className="p-3 bg-red-950/50 border border-red-800 rounded-lg text-sm text-red-300">{error}</div>}
          {success && <div role="status" className="p-3 bg-emerald-950/50 border border-emerald-800 rounded-lg text-sm text-emerald-300">{success}</div>}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-2">メールアドレス（ID）</label>
            <input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} className={inputClass} required disabled={isLoading} />
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <label htmlFor="providerName" className="block text-sm font-medium text-slate-300 mb-2">指揮官名</label>
              <input id="providerName" type="text" value={providerName} onChange={e => setProviderName(e.target.value)} className={inputClass} disabled={isLoading} />
            </div>
            <div>
              <label htmlFor="gameStartDate" className="block text-sm font-medium text-slate-300 mb-2">ゲーム開始日</label>
              <input id="gameStartDate" type="date" value={gameStartDate} onChange={e => setGameStartDate(e.target.value)} className={inputClass} disabled={isLoading} />
            </div>
          </div>

          <div>
            <label htmlFor="playServer" className="block text-sm font-medium text-slate-300 mb-2">プレイしているサーバー</label>
            <select id="playServer" value={playServer} onChange={e => setPlayServer(e.target.value)} className={inputClass} disabled={isLoading}>
              <option value="">未選択</option>
              {SERVER_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>

          <div className="border-t border-slate-800 pt-6">
            <h2 className="text-base font-semibold mb-4">パスワード変更</h2>
            <div className="space-y-4">
              <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} className={inputClass} placeholder="現在のパスワード" autoComplete="current-password" />
              <div className="grid md:grid-cols-2 gap-4">
                <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} className={inputClass} placeholder="新しいパスワード（8文字以上）" autoComplete="new-password" minLength={8} />
                <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} className={inputClass} placeholder="新しいパスワード（確認）" autoComplete="new-password" minLength={8} />
              </div>
            </div>
          </div>

          <button type="submit" disabled={isLoading || isSaving} className="w-full flex items-center justify-center gap-2 py-3 bg-blue-600 hover:bg-blue-500 rounded-lg font-bold disabled:opacity-50 transition">
            <Save size={18} />
            <span>{isSaving ? "保存中..." : "変更を保存"}</span>
          </button>
        </form>
      </div>
    </main>
  );
}
