"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";

export default function GatePage() {
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // サーバーサイドで検証 → HttpOnly Cookie 発行（クライアント側での照合は行わない）
      const res = await fetch("/api/auth/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || "パスコードが正しくありません。");
        return;
      }
      router.push("/");
      router.refresh();
    } catch {
      setError("サーバーとの通信に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-slate-900/80 backdrop-blur-xl ring-1 ring-white/10 rounded-3xl shadow-2xl p-8">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-blue-500/20 ring-1 ring-blue-500/40 flex items-center justify-center mb-4">
            <Lock size={32} className="text-blue-400" />
          </div>
          <h1 className="text-2xl font-black text-white">閲覧制限</h1>
          <p className="text-slate-400 text-sm mt-2 text-center">
            このサイトは現在、関係者向けのテスト公開中です。<br />
            閲覧するにはパスコードを入力してください。
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 ring-1 ring-red-500/30 rounded-xl text-red-400 text-sm font-bold">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="passcode" className="block text-sm font-bold text-slate-400 mb-2">
              パスコード
            </label>
            <input
              id="passcode"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="パスコードを入力"
              required
              className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all placeholder:text-slate-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-400 hover:to-indigo-500 disabled:opacity-50 text-white rounded-xl font-bold transition-all shadow-lg"
          >
            {loading ? "確認中..." : "ロック解除"}
          </button>
        </form>
      </div>
    </div>
  );
}