'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function SecretRegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
      const response = await fetch(`${apiUrl}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password, inviteCode: inviteCode }),// invite_codeをバックエンドのinviteCodeに合わせる 
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

      setSuccess('スタッフ登録が完了しました！ログイン画面へ遷移します...');
      setTimeout(() => {
        router.push('/secret-login');
      }, 2000);
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
            {loading ? '登録処理中...' : 'アカウント登録'}
          </button>
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
