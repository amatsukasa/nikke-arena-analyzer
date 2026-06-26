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

interface AdminCharacter {
  char_id: number;
  char_name: string;
  rarity: string;
  element: string | null;
  manufacturer: string | null;
  burst_phase: string | null;
  weapon: string | null;
  class_type: string | null;
  has_template: boolean;
  template_count: number;
  image_url: string | null;
}

export default function AdminPage() {
  const { user: currentUser, token, isLoading, apiFetch } = useAuth();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<'users' | 'characters' | 'championships'>('users');

  // ユーザー管理用ステート
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);

  // キャラクター管理用ステート
  const [characters, setCharacters] = useState<AdminCharacter[]>([]);
  const [charsLoading, setCharsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRarity, setFilterRarity] = useState('');
  const [filterClass, setFilterClass] = useState('');

  // 大会タイトル(Championship)管理用ステート
  const [championships, setChampionships] = useState<any[]>([]);
  const [champsLoading, setChampsLoading] = useState(false);
  const [isChampModalOpen, setIsChampModalOpen] = useState(false);
  const [champModalMode, setChampModalMode] = useState<'create' | 'edit'>('create');
  const [editingChampId, setEditingChampId] = useState<number | null>(null);
  const [formChampName, setFormChampName] = useState('');
  const [formChampDate, setFormChampDate] = useState('');

  // 共通エラー・メッセージ
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  // 新規追加・編集モーダル用ステート
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingCharId, setEditingCharId] = useState<number | null>(null);

  // フォームステート
  const [formName, setFormName] = useState('');
  const [formRarity, setFormRarity] = useState('SSR');
  const [formClassType, setFormClassType] = useState('火力型');
  const [formElement, setFormElement] = useState('灼熱');
  const [formManufacturer, setFormManufacturer] = useState('エリシオン');
  const [formBurstPhase, setFormBurstPhase] = useState('3');
  const [formWeapon, setFormWeapon] = useState('AR');

  const rarities = ['SSR', 'SR', 'R'];
  const classTypes = ['火力型', '支援型', '防御型'];
  const elements = ['灼熱', '水冷', '風圧', '鉄甲', '電撃'];
  const manufacturers = ['エリシオン', 'ミシリス', 'テトラ', 'ピルグリム', 'アブノーマル'];
  const burstPhases = ['1', '2', '3', 'A'];
  const weapons = ['AR', 'SR', 'SG', 'RL', 'SMG', 'MG'];

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
        fetchCharacters();
        fetchChampionships();
      }
    }
  }, [isLoading, token, currentUser, router]);

  const fetchChampionships = async () => {
    setChampsLoading(true);
    try {
      const response = await fetch('/api/championships');
      if (!response.ok) {
        throw new Error('大会タイトル一覧の取得に失敗しました。');
      }
      const data = await response.json();
      setChampionships(data);
    } catch (err: any) {
      setError(err.message || '大会タイトルの取得に失敗しました。');
    } finally {
      setChampsLoading(false);
    }
  };

  const handleChampSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const payload = {
      name: formChampName.trim(),
      date: formChampDate || null,
      start_date: null,
      owner_name: null
    };

    try {
      let response;
      if (champModalMode === 'create') {
        response = await apiFetch(`${apiUrl}/api/championships`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      } else {
        response = await apiFetch(`${apiUrl}/api/championships/${editingChampId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || '大会タイトルの保存に失敗しました。');
      }

      setMessage(champModalMode === 'create' ? '大会タイトルを新規追加しました。' : '大会タイトルを更新しました。');
      setIsChampModalOpen(false);
      fetchChampionships();
    } catch (err: any) {
      setError(err.message || 'エラーが発生しました。');
    }
  };

  const handleDeleteChamp = async (id: number, name: string) => {
    if (!window.confirm(`「${name}」を削除してもよろしいですか？\n※この大会に関連する対戦データやプレイヤー情報などもすべて削除されます。`)) {
      return;
    }
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
      const response = await apiFetch(`${apiUrl}/api/championships/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '削除に失敗しました。');
      }
      setMessage(`「${name}」を削除しました。`);
      fetchChampionships();
    } catch (err: any) {
      setError(err.message || '削除中にエラーが発生しました。');
    }
  };

  const openChampModal = (mode: 'create' | 'edit', champ?: any) => {
    setChampModalMode(mode);
    setError('');
    setMessage('');
    if (mode === 'edit' && champ) {
      setEditingChampId(champ.id);
      setFormChampName(champ.name);
      setFormChampDate(champ.date ? champ.date.split('T')[0] : '');
    } else {
      setEditingChampId(null);
      setFormChampName('');
      setFormChampDate(new Date().toISOString().split('T')[0]);
    }
    setIsChampModalOpen(true);
  };

  const fetchUsers = async () => {
    setUsersLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    try {
      const response = await apiFetch(`${apiUrl}/api/auth/users`);
      if (!response.ok) {
        throw new Error('ユーザー一覧の取得に失敗しました。');
      }
      const data = await response.json();
      setUsers(data);
    } catch (err: any) {
      setError(err.message || '通信エラーが発生しました。');
    } finally {
      setUsersLoading(false);
    }
  };

  const fetchCharacters = async () => {
    setCharsLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    try {
      const response = await apiFetch(`${apiUrl}/api/admin/all-characters`);
      if (!response.ok) {
        throw new Error('キャラクター一覧の取得に失敗しました。');
      }
      const data = await response.json();
      setCharacters(data);
    } catch (err: any) {
      setError(err.message || 'キャラクターデータの取得に失敗しました。');
    } finally {
      setCharsLoading(false);
    }
  };

  const handleBanToggle = async (userId: number, isBanned: boolean) => {
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const action = isBanned ? 'unban' : 'ban';

    try {
      const response = await apiFetch(`${apiUrl}/api/auth/users/${userId}/${action}`, {
        method: 'PUT',
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || '操作に失敗しました。');
      }

      setMessage(data.message || '操作が成功しました。');
      fetchUsers();
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
      const response = await apiFetch(`${apiUrl}/api/auth/users/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role: newRole }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.message || '権限変更に失敗しました。');
      }

      setMessage(data.message || '権限を変更しました。');
      fetchUsers();
    } catch (err: any) {
      setError(err.message || 'エラーが発生しました。');
    }
  };

  // キャラクター作成・編集モーダルを開く
  const openModal = (mode: 'create' | 'edit', char?: AdminCharacter) => {
    setModalMode(mode);
    setError('');
    setMessage('');
    if (mode === 'edit' && char) {
      setEditingCharId(char.char_id);
      setFormName(char.char_name);
      setFormRarity(char.rarity);
      setFormClassType(char.class_type || '火力型');
      setFormElement(char.element || '灼熱');
      setFormManufacturer(char.manufacturer || 'エリシオン');
      setFormBurstPhase(char.burst_phase || '3');
      setFormWeapon(char.weapon || 'AR');
    } else {
      setEditingCharId(null);
      setFormName('');
      setFormRarity('SSR');
      setFormClassType('火力型');
      setFormElement('灼熱');
      setFormManufacturer('エリシオン');
      setFormBurstPhase('3');
      setFormWeapon('AR');
    }
    setIsModalOpen(true);
  };

  // キャラクターの追加・編集処理送信
  const handleCharacterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const payload = {
      name: formName,
      rarity: formRarity,
      class_type: formClassType,
      element: formElement,
      manufacturer: formManufacturer,
      burst_phase: formBurstPhase,
      weapon: formWeapon,
    };

    try {
      let response;
      if (modalMode === 'create') {
        response = await apiFetch(`${apiUrl}/api/characters`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      } else {
        response = await apiFetch(`${apiUrl}/api/characters/${editingCharId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'キャラクターの保存に失敗しました。');
      }

      setMessage(modalMode === 'create' ? 'キャラクターを新規登録しました。' : 'キャラクター情報を更新しました。');
      setIsModalOpen(false);
      fetchCharacters();
    } catch (err: any) {
      setError(err.message || 'エラーが発生しました。');
    }
  };

  // キャラクターの削除
  const handleDeleteCharacter = async (charId: number, charName: string) => {
    if (!window.confirm(`「${charName}」を完全に削除してもよろしいですか？\n※関連するアリーナ分析用テンプレート画像もすべて削除されます。この操作は取り消せません。`)) {
      return;
    }
    setError('');
    setMessage('');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
      const response = await apiFetch(`${apiUrl}/api/characters/${charId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '削除に失敗しました。');
      }
      setMessage(`「${charName}」を削除しました。`);
      fetchCharacters();
    } catch (err: any) {
      setError(err.message || '削除中にエラーが発生しました。');
    }
  };

  // キャラクター絞り込みフィルタ処理
  const filteredCharacters = characters.filter((c) => {
    const matchSearch = c.char_name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchRarity = filterRarity ? c.rarity === filterRarity : true;
    const matchClass = filterClass ? c.class_type === filterClass : true;
    return matchSearch && matchRarity && matchClass;
  });

  if (isLoading) {
    return (
      <div className="flex flex-col justify-center items-center h-screen bg-slate-950 text-slate-100 gap-4">
        <div className="animate-spin rounded-full h-10 w-10 border-4 border-slate-800 border-t-indigo-500"></div>
        <p className="text-slate-400 text-sm">システムデータをロード中...</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 画面ヘッダー */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl mb-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">⚙️ 管理者専用ポータル</h1>
            <p className="text-slate-400 text-sm mt-1">
              スタッフアカウント管理およびキャラクターのデータベース管理を行います。
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
              onClick={() => {
                if (activeTab === 'users') fetchUsers();
                else if (activeTab === 'characters') fetchCharacters();
                else fetchChampionships();
              }}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2 rounded-lg text-sm transition animate-pulse"
            >
              🔄 最新情報に更新
            </button>
          </div>
        </div>

        {/* タブ切り替えバー */}
        <div className="flex border-b border-slate-800 mt-6 gap-2">
          <button
            onClick={() => {
              setActiveTab('users');
              setError('');
              setMessage('');
            }}
            className={`px-5 py-2.5 font-medium text-sm transition relative ${
              activeTab === 'users' ? 'text-indigo-400 border-b-2 border-indigo-500 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            👥 ユーザー管理
          </button>
          <button
            onClick={() => {
              setActiveTab('characters');
              setError('');
              setMessage('');
            }}
            className={`px-5 py-2.5 font-medium text-sm transition relative ${
              activeTab === 'characters' ? 'text-indigo-400 border-b-2 border-indigo-500 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            🛡️ キャラクター管理
          </button>
          <button
            onClick={() => {
              setActiveTab('championships');
              setError('');
              setMessage('');
            }}
            className={`px-5 py-2.5 font-medium text-sm transition relative ${
              activeTab === 'championships' ? 'text-indigo-400 border-b-2 border-indigo-500 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            🏆 大会タイトル管理
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

      {/* --- タブ内容1: ユーザー管理 --- */}
      {activeTab === 'users' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl">
          <h2 className="text-lg font-bold text-slate-100 mb-4">登録スタッフアカウント一覧</h2>
          {usersLoading ? (
            <div className="text-center py-8 text-slate-400 text-sm">ユーザー情報を読み込み中...</div>
          ) : (
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
          )}
        </div>
      )}

      {/* --- タブ内容2: キャラクター管理 --- */}
      {activeTab === 'characters' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl">
          {/* コントロールパネル */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
            <div className="flex flex-wrap items-center gap-3 flex-1">
              <input
                type="text"
                placeholder="🔍 キャラクター名で検索..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-full md:w-64 transition"
              />
              <select
                value={filterRarity}
                onChange={(e) => setFilterRarity(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500 transition"
              >
                <option value="">全てのレア度</option>
                {rarities.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              <select
                value={filterClass}
                onChange={(e) => setFilterClass(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500 transition"
              >
                <option value="">全てのクラス</option>
                {classTypes.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <button
                onClick={() => openModal('create')}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2.5 rounded-lg text-sm transition flex items-center gap-2 shadow-lg shadow-indigo-900/30 w-full md:w-auto justify-center"
              >
                ➕ キャラクター新規追加
              </button>
            </div>
          </div>

          {charsLoading ? (
            <div className="text-center py-8 text-slate-400 text-sm">キャラクターデータを取得中...</div>
          ) : (
            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800">
                    <th className="p-4 w-16">画像</th>
                    <th className="p-4">名前</th>
                    <th className="p-4">レア度</th>
                    <th className="p-4">クラス</th>
                    <th className="p-4">バースト</th>
                    <th className="p-4">属性</th>
                    <th className="p-4">メーカー</th>
                    <th className="p-4">武器</th>
                    <th className="p-4">テンプレート数</th>
                    <th className="p-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {filteredCharacters.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="p-8 text-center text-slate-500">
                        該当するキャラクターが見つかりません。
                      </td>
                    </tr>
                  ) : (
                    filteredCharacters.map((c) => (
                      <tr key={c.char_id} className="hover:bg-slate-900/50 transition">
                        <td className="p-4">
                          <div className="w-10 h-10 rounded-full border border-slate-700 overflow-hidden bg-slate-950 flex items-center justify-center">
                            {c.image_url ? (
                              <img
                                src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${c.image_url}`}
                                alt={c.char_name}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  // 画像読み込み失敗時は代替テキストを表示
                                  (e.target as HTMLElement).style.display = 'none';
                                }}
                              />
                            ) : (
                              <span className="text-slate-500 text-xs font-bold">{c.char_name.substring(0, 2)}</span>
                            )}
                          </div>
                        </td>
                        <td className="p-4 font-semibold text-slate-200">{c.char_name}</td>
                        <td className="p-4">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            c.rarity === 'SSR' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                            c.rarity === 'SR' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' :
                            'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                          }`}>
                            {c.rarity}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            c.class_type === '火力型' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                            c.class_type === '支援型' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                            'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                          }`}>
                            {c.class_type || '未設定'}
                          </span>
                        </td>
                        <td className="p-4 text-slate-300 font-semibold">{c.burst_phase ? `B${c.burst_phase}` : '-'}</td>
                        <td className="p-4 text-slate-400">{c.element || '-'}</td>
                        <td className="p-4 text-slate-400 text-xs">{c.manufacturer || '-'}</td>
                        <td className="p-4 text-slate-400">{c.weapon || '-'}</td>
                        <td className="p-4">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            c.template_count > 0 ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'bg-slate-800 text-slate-500'
                          }`}>
                            {c.template_count} 枚
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => openModal('edit', c)}
                              className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3 py-1.5 rounded transition"
                            >
                              編集
                            </button>
                            <button
                              onClick={() => handleDeleteCharacter(c.char_id, c.char_name)}
                              className="bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/40 text-xs font-medium px-3 py-1.5 rounded transition"
                            >
                              削除
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* --- タブ内容3: 大会タイトル管理 --- */}
      {activeTab === 'championships' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
            <h2 className="text-lg font-bold text-slate-100">大会タイトル一覧</h2>
            <button
              onClick={() => openChampModal('create')}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2.5 rounded-lg text-sm transition flex items-center gap-2 shadow-lg shadow-indigo-900/30 justify-center"
            >
              ➕ 大会タイトル新規追加
            </button>
          </div>

          {champsLoading ? (
            <div className="text-center py-8 text-slate-400 text-sm">大会タイトルをロード中...</div>
          ) : (
            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800">
                    <th className="p-4 w-24">ID</th>
                    <th className="p-4">大会タイトル名称</th>
                    <th className="p-4">開催日</th>
                    <th className="p-4">登録日時</th>
                    <th className="p-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {championships.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-slate-500">
                        大会タイトルが登録されていません。
                      </td>
                    </tr>
                  ) : (
                    championships.map((champ) => (
                      <tr key={champ.id} className="hover:bg-slate-900/50 transition">
                        <td className="p-4">{champ.id}</td>
                        <td className="p-4 font-semibold text-slate-200">{champ.name}</td>
                        <td className="p-4 text-slate-300">
                          {champ.date ? champ.date.split('T')[0] : '未設定'}
                        </td>
                        <td className="p-4 text-slate-500">
                          {new Date(champ.created_at).toLocaleDateString('ja-JP')} {new Date(champ.created_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => openChampModal('edit', champ)}
                              className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3 py-1.5 rounded transition"
                            >
                              編集
                            </button>
                            <button
                              onClick={() => handleDeleteChamp(champ.id, champ.name)}
                              className="bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/40 text-xs font-medium px-3 py-1.5 rounded transition"
                            >
                              削除
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* --- 大会タイトル追加・編集用モーダル --- */}
      {isChampModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl text-slate-100 my-8">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800 mb-6">
              <h3 className="text-lg font-bold text-slate-200">
                {champModalMode === 'create' ? '🏆 新規大会タイトル登録' : '🏆 大会タイトル情報編集'}
              </h3>
              <button
                onClick={() => setIsChampModalOpen(false)}
                className="text-slate-400 hover:text-slate-200 transition text-xl font-bold"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleChampSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-1.5">大会タイトル名称 *</label>
                <input
                  type="text"
                  required
                  value={formChampName}
                  onChange={(e) => setFormChampName(e.target.value)}
                  placeholder="例: 第1回 アリーナ記念大会"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-1.5">開催日 *</label>
                <input
                  type="date"
                  required
                  value={formChampDate}
                  onChange={(e) => setFormChampDate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-800 mt-6">
                <button
                  type="button"
                  onClick={() => setIsChampModalOpen(false)}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium px-4 py-2 rounded-lg text-sm transition"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-5 py-2 rounded-lg text-sm transition shadow-lg shadow-indigo-900/30"
                >
                  保存する
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- キャラクター追加・編集用モーダル --- */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl text-slate-100 my-8">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800 mb-6">
              <h3 className="text-lg font-bold text-slate-200">
                {modalMode === 'create' ? '➕ 新規キャラクター登録' : '📝 キャラクター情報編集'}
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-200 transition text-xl font-bold"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleCharacterSubmit} className="space-y-5">
              {/* 名前 */}
              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-1.5">キャラクター名 *</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="例: レッドフード"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              {/* レア度 & クラス */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">レア度</label>
                  <select
                    value={formRarity}
                    onChange={(e) => setFormRarity(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {rarities.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">クラス</label>
                  <select
                    value={formClassType}
                    onChange={(e) => setFormClassType(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {classTypes.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 属性 & バースト段階 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">属性 (コード)</label>
                  <select
                    value={formElement}
                    onChange={(e) => setFormElement(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {elements.map((el) => (
                      <option key={el} value={el}>{el}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">バースト段階</label>
                  <select
                    value={formBurstPhase}
                    onChange={(e) => setFormBurstPhase(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {burstPhases.map((b) => (
                      <option key={b} value={b}>{b === 'A' ? 'All (全段階)' : `I${'I'.repeat(parseInt(b) - 1)}`}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 製造会社 & 武器 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">企業 (メーカー)</label>
                  <select
                    value={formManufacturer}
                    onChange={(e) => setFormManufacturer(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {manufacturers.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-300 mb-1.5">武器種</label>
                  <select
                    value={formWeapon}
                    onChange={(e) => setFormWeapon(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                  >
                    {weapons.map((w) => (
                      <option key={w} value={w}>{w}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-800 mt-6">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium px-4 py-2 rounded-lg text-sm transition"
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-5 py-2 rounded-lg text-sm transition shadow-lg shadow-indigo-900/30"
                >
                  保存する
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
