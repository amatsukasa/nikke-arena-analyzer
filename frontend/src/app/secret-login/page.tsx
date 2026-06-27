'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '../../context/AuthContext';

export default function SecretLoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // バックエンドのポートを元のPython版(8000)に合わせる
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
      const response = await fetch(`${apiUrl}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // 追加
        body: JSON.stringify({ email, password }),
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
        throw new Error(data.detail || data.message || 'ログインに失敗しました。');
      }

      // AuthContextにトークンとユーザー情報を保存
      login(data.token || data.access_token, data.user);
      
      // リダイレクト先があればそこへ、無ければスタッフ入口へ
      const searchParams = new URLSearchParams(window.location.search);
      const requestedRedirect = searchParams.get('redirect');
      const redirectUrl = requestedRedirect?.startsWith('/') && !requestedRedirect.startsWith('//')
        ? requestedRedirect
        : '/staff';
      window.location.href = redirectUrl;
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
            🔑 関係者ログイン
          </h1>
          <p className="text-slate-400 text-sm mt-2">
            NIKKE Arena Analyzer 登録・管理スタッフ専用
          </p>
        </div>

        {error && (
          <div className="bg-red-950/50 border border-red-800 text-red-300 px-4 py-3 rounded-lg text-sm mb-6">
            {error}
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
              placeholder="パスワードを入力"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={loading}
          >
            {loading ? 'ログイン中...' : 'ログイン'}
          </button>
        </form>

        <div className="text-center mt-6 text-sm text-slate-400">
          <p>
            アカウントをお持ちでないですか？{' '}
            <Link href="/secret-register" className="text-indigo-400 hover:underline">
              スタッフ登録はこちら
            </Link>
          </p>
          <div className="mt-4">
            <Link href="/" className="text-slate-500 hover:text-slate-300 text-xs">
              ← ダッシュボード（公開表示）に戻る
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
