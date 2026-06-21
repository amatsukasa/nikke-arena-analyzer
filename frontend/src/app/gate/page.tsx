'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function GatePage() {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
	/* gate機能をいったん無効化する*/
      /*const response = await fetch('/api/auth/gate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'ロックの解除に失敗しました。');
      }
      */

      router.push('/');
      router.refresh();
    } catch (err: any) {
      setError(err.message || '通信エラーが発生しました。');
    } finally {
      setLoading(false);
    }
  };

  /*
  return (
    <div className="flex flex-col justify-center items-center min-h-screen bg-slate-950 text-slate-100 px-4">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl text-center">
        <div className="text-4xl mb-4">🔒</div>
        <h1 className="text-2xl font-bold text-slate-100">閲覧制限</h1>
        <p className="text-slate-400 text-sm mt-2 mb-6">
          このサイトは現在、関係者向けのテスト公開中です。閲覧するにはパスコードを入力してください。
        </p>
        
        {error && (
          <div className="bg-red-950/50 border border-red-800 text-red-300 px-4 py-3 rounded-lg text-sm mb-6 text-left">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="text-left">
            <label className="block text-slate-300 text-sm font-medium mb-2" htmlFor="passcode">
              パスコード
            </label>
            <input
              id="passcode"
              type="password"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-950 transition"
              placeholder="パスコードを入力"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </div>
          <button
            type="submit"
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-lg transition disabled:opacity-50"
            disabled={loading}
          >
            {loading ? '検証中...' : 'ロック解除'}
          </button>
        </form>
      </div>
    </div>
  );
  */
}
