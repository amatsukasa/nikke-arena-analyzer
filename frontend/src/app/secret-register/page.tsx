'use client';

import React, { useState } from 'react';
import Link from 'next/link';

export default function SecretRegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [providerName, setProviderName] = useState('');
  const [gameStartDate, setGameStartDate] = useState('');
  const [playServer, setPlayServer] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (!isReviewing) {
      setIsReviewing(true);
      return;
    }
    setLoading(true);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
      const response = await fetch(`${apiUrl}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          email, 
          password, 
          inviteCode: inviteCode,
          providerName: providerName,
          gameStartDate: gameStartDate || null,
          playServer: playServer || null
        }),
      });

      const contentType = response.headers.get('content-type');
      let data: any = {};

      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      } else {
        const rawText = await response.text();
        throw new Error(rawText || 'サーバーが予期しないエラーを返しました。バックエンドが起動しているか確認してください。');
      }

      if (!response.ok) {
        throw new Error(data.detail || data.message || '登録に失敗しました。');
      }

      setSuccess('登録依頼を送信しました。管理者の承認後、メールでお知らせします。');
      setIsReviewing(false);
    } catch (err: any) {
      setError(err.message || 'サーバーとの通信に失敗しました。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper flex items-center justify-center min-h-[80vh] px-4">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-100 flex items-center justify-center gap-2">
            📝 新規スタッフ登録
          </h1>
          <p className="text-slate-400 text-sm mt-2">
            関係者専用（招待コードが必要です）
          </p>
        </div>

        {error && (
          <div className="bg-red-950/50 border border-red-800 text-red-300 px-4 py-3 rounded-lg text-sm mb-6">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-emerald-950/50 border border-emerald-800 text-emerald-300 px-4 py-3 rounded-lg text-sm mb-6">
            {success}
          </div>
        )}

        {isReviewing && (
          <div className="mb-6 rounded-lg border border-indigo-800 bg-indigo-950/40 p-4 text-sm">
            <h2 className="mb-3 font-bold text-indigo-300">入力内容の確認</h2>
            <dl className="grid grid-cols-[7rem_1fr] gap-2">
              <dt className="text-slate-500">メール</dt><dd className="break-all">{email}</dd>
              <dt className="text-slate-500">指揮官名</dt><dd>{providerName}</dd>
              <dt className="text-slate-500">開始日</dt><dd>{gameStartDate}</dd>
              <dt className="text-slate-500">サーバー</dt><dd>{playServer}</dd>
            </dl>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="email">
              メールアドレス
            </label>
            <input
              id="email"
              type="email"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="password">
              パスワード
            </label>
            <input
              id="password"
              type="password"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              placeholder="任意のパスワード（8文字以上推奨）"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="providerName">
              提供者名 (表示名)
            </label>
            <input
              id="providerName"
              type="text"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              placeholder="例: 指揮官A (データ提供者の表記ゆれを防ぐための固定名)"
              value={providerName}
              onChange={(e) => setProviderName(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="gameStartDate">
              指揮官のゲーム開始日
            </label>
            <input
              id="gameStartDate"
              type="date"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              value={gameStartDate}
              onChange={(e) => setGameStartDate(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="playServer">
              プレイしているサーバー
            </label>
            <select
              id="playServer"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              value={playServer}
              onChange={(e) => setPlayServer(e.target.value)}
              required
            >
              <option value="" disabled>サーバーを選択</option>
              <option value="KR">韓国（KR）</option>
              <option value="JP">日本（JP）</option>
              <option value="GLOBAL">グローバル（ヨーロッパ）</option>
              <option value="NA">北米</option>
              <option value="SEA">東南アジア</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="inviteCode">
              招待コード
            </label>
            <input
              id="inviteCode"
              type="text"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              placeholder="管理者から共有された招待コードを入力"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={loading}
          >
            {loading ? '送信中...' : isReviewing ? '登録依頼を送信' : '入力内容を確認'}
          </button>
          {isReviewing && (
            <button
              type="button"
              onClick={() => setIsReviewing(false)}
              className="w-full rounded-lg border border-slate-700 py-3 font-medium text-slate-300 hover:bg-slate-800"
            >
              入力内容を修正
            </button>
          )}
        </form>

        <div className="text-center mt-6 text-sm text-slate-400">
          <p>
            既にアカウントをお持ちですか？{' '}
            <Link href="/secret-login" className="text-indigo-400 hover:underline">
              ログイン画面はこちら
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
