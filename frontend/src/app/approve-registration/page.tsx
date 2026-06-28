"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

function ApprovalContent() {
  const searchParams = useSearchParams();
  const userId = Number(searchParams.get("user"));
  const token = searchParams.get("token") || "";
  const [request, setRequest] = useState<any>(null);
  const [error, setError] = useState("");
  const [isApproving, setIsApproving] = useState(false);
  const [isApproved, setIsApproved] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    if (!userId || !token) {
      setError("承認リンクが正しくありません。");
      return;
    }
    fetch(
      `${apiUrl}/api/auth/registration-approval?user_id=${userId}&token=${encodeURIComponent(token)}`,
      { cache: "no-store" },
    )
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "登録依頼を確認できませんでした。");
        setRequest(data);
      })
      .catch(reason => setError(reason.message));
  }, [apiUrl, token, userId]);

  const approve = async () => {
    setIsApproving(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/auth/registration-approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId, token }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "承認できませんでした。");
      setIsApproved(true);
      setRequest(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "承認できませんでした。");
    } finally {
      setIsApproving(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-16 text-slate-200">
      <section className="mx-auto max-w-lg rounded-lg border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <h1 className="text-2xl font-bold">スタッフ登録依頼の確認</h1>

        {error && <p className="mt-6 rounded-md border border-red-800 bg-red-950/50 p-4 text-red-300">{error}</p>}
        {isApproved && (
          <div className="mt-6 space-y-4">
            <p className="rounded-md border border-emerald-800 bg-emerald-950/50 p-4 text-emerald-300">
              スタッフ登録を承認しました。
            </p>
            <Link href="/admin" className="inline-block text-indigo-400 hover:underline">管理者画面へ</Link>
          </div>
        )}

        {request && (
          <div className="mt-6 space-y-5">
            <dl className="grid grid-cols-[9rem_1fr] gap-3 rounded-md bg-slate-950/60 p-4 text-sm">
              <dt className="text-slate-500">メールアドレス</dt><dd className="break-all">{request.email}</dd>
              <dt className="text-slate-500">指揮官名</dt><dd>{request.provider_name || "未入力"}</dd>
              <dt className="text-slate-500">ゲーム開始日</dt><dd>{request.game_start_date || "未入力"}</dd>
              <dt className="text-slate-500">プレイサーバー</dt><dd>{request.play_server || "未入力"}</dd>
            </dl>
            <button
              type="button"
              onClick={approve}
              disabled={isApproving}
              className="w-full rounded-md bg-emerald-600 px-4 py-3 font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {isApproving ? "承認中..." : "このスタッフ登録を承認する"}
            </button>
            <p className="text-xs text-slate-500">承認すると、このリンクは再利用できません。</p>
          </div>
        )}
      </section>
    </main>
  );
}

export default function ApproveRegistrationPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-950 p-16 text-center text-slate-400">確認中...</main>}>
      <ApprovalContent />
    </Suspense>
  );
}
