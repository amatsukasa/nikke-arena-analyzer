'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';

interface User {
  id: number;
  email: string;
  role: string;
  is_banned: boolean;
  created_at: string;
}

export default function AdminPage() {
  const { user: currentUser, token, isLoading, apiFetch } = useAuth();
  const router = useRouter();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  // 認証と管理者権限のガード
  useEffect(() => {
    if (!isLoading) {
      if (!token) {
        router.push('/secret-login');
      } else if (currentUser?.role !== 'admin') {
        alert('管理者権限が必要です。');
        router.push('/');
      } else {
        fetchUsers();
      }
    }
  }, [isLoading, token, currentUser, router]);

  const fetchUsers = async () => {
    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    try {
      const response = await apiFetch(`${apiUrl}/api/admin/users`);
      if (!response.ok) {
        throw new Error('ユーザー一覧の取得に失敗しました。');
      }
      const data = await response.json();
      setUsers(data);
    } catch (err: any) {
      setError(err.message || '通信エラーが発生しました。');
    } finally {
      setLoading(false);
    }
  };

  const handleBanToggle = async (userId: number, isBanned: boolean) => {
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const action = isBanned ? 'unban' : 'ban';

    try {
      const response = await apiFetch(`${apiUrl}/api/admin/users/${userId}/${action}`, {
        method: 'PUT',
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || '操作に失敗しました。');
      }

      setMessage(data.message || '操作が成功しました。');
      fetchUsers(); // 一覧の更新
    } catch (err: any) {
      setError(err.message || 'エラーが発生しました。');
    }
  };

  const handleRoleToggle = async (userId: number, currentRole: string) => {
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const newRole = currentRole === 'admin' ? 'user' : 'admin';

    if (!window.confirm(`権限を ${newRole === 'admin' ? '管理者' : '一般スタッフ'} に変更してもよろしいですか？`)) {
      return;
    }

    try {
      const response = await apiFetch(`${apiUrl}/api/admin/users/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role: newRole }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || '権限変更に失敗しました。');
      }

      setMessage(data.message || '権限を変更しました。');
      fetchUsers(); // 一覧の更新
    } catch (err: any) {
      setError(err.message || 'エラーが発生しました。');
    }
  };

  if (isLoading || loading) {
    return (
      <div className="flex flex-col justify-center items-center h-screen bg-slate-950 text-slate-100 gap-4">
        <div className="animate-spin rounded-full h-10 w-10 border-4 border-slate-800 border-t-indigo-500"></div>
        <p className="text-slate-400 text-sm">ユーザーデータをロード中...</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">⚙️ 管理者専用ポータル</h1>
            <p className="text-slate-400 text-sm mt-1">
              登録されたスタッフのアカウント管理、権限の変更、および利用制限を行います。
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => router.push('/')}
              className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium px-4 py-2 rounded-lg text-sm transition"
            >
              ← ダッシュボードへ
            </button>
            <button
              onClick={fetchUsers}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2 rounded-lg text-sm transition"
            >
              🔄 一覧更新
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-950/50 border border-red-800 text-red-300 px-4 py-3 rounded-lg text-sm mb-6">
            {error}
          </div>
        )}
        {message && (
          <div className="bg-emerald-950/50 border border-emerald-800 text-emerald-300 px-4 py-3 rounded-lg text-sm mb-6">
            {message}
          </div>
        )}

        <div className="overflow-x-auto border border-slate-800 rounded-lg">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800">
                <th className="p-4">ID</th>
                <th className="p-4">メールアドレス</th>
                <th className="p-4">権限</th>
                <th className="p-4">ステータス</th>
                <th className="p-4">登録日</th>
                <th className="p-4 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {users.map((u) => {
                const isSelf = u.id === currentUser?.id;
                return (
                  <tr key={u.id} className="hover:bg-slate-900/50 transition">
                    <td className="p-4">{u.id}</td>
                    <td className="p-4 font-medium text-slate-200">
                      {u.email} {isSelf && <span className="text-indigo-400 text-xs ml-1">(あなた)</span>}
                    </td>
                    <td className="p-4">
                      <span className={`px-2.5 py-1 rounded text-xs font-semibold ${
                        u.role === 'admin' 
                          ? 'bg-amber-950/50 text-amber-400 border border-amber-800/30' 
                          : 'bg-indigo-950/50 text-indigo-400 border border-indigo-800/30'
                      }`}>
                        {u.role === 'admin' ? '管理者' : '登録スタッフ'}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className={`px-2.5 py-1 rounded text-xs font-semibold ${
                        u.is_banned 
                          ? 'bg-red-950/50 text-red-400 border border-red-800/30' 
                          : 'bg-emerald-950/50 text-emerald-400 border border-emerald-800/30'
                      }`}>
                        {u.is_banned ? 'アカウント停止中' : 'アクティブ'}
                      </span>
                    </td>
                    <td className="p-4 text-slate-500">
                      {new Date(u.created_at).toLocaleDateString('ja-JP')}
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleRoleToggle(u.id, u.role)}
                          className="bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium px-3 py-1.5 rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
                          disabled={isSelf}
                          title={isSelf ? '自分の権限は変更できません' : '権限を切り替えます'}
                        >
                          権限切替
                        </button>
                        <button
                          onClick={() => handleBanToggle(u.id, u.is_banned)}
                          className={`text-xs font-medium px-3 py-1.5 rounded transition disabled:opacity-40 disabled:cursor-not-allowed ${
                            u.is_banned 
                              ? 'bg-emerald-600 hover:bg-emerald-700 text-white' 
                              : 'bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/40'
                          }`}
                          disabled={isSelf}
                          title={isSelf ? '自分自身を停止することはできません' : u.is_banned ? '停止を解除します' : 'アカウントを停止します'}
                        >
                          {u.is_banned ? '解除' : 'BAN'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
