'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../../context/AuthContext';

export default function RegisterTournamentPage() {
  const { user, token, isLoading, apiFetch } = useAuth();
  const router = useRouter();

  const [name, setName] = useState('');
  const [stage, setStage] = useState('決勝');
  const [winnerTeam, setWinnerTeam] = useState('');
  const [loserTeam, setLoserTeam] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // ログインしていない場合はログイン画面にリダイレクト
  useEffect(() => {
    if (!isLoading && !token) {
      router.push('/secret-login');
    }
  }, [isLoading, token, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);

    if (winnerTeam === loserTeam) {
      setError('勝利チームと敗北チームは異なるチームである必要があります。');
      setSubmitting(false);
      return;
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

    try {
      const response = await apiFetch(`${apiUrl}/api/tournaments`, {
        method: 'POST',
        body: JSON.stringify({
          name,
          stage,
          winner_team: winnerTeam,
          loser_team: loserTeam,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || '登録に失敗しました。');
      }

      setSuccess('大会データを登録しました！ダッシュボードに戻ります...');
      setTimeout(() => {
        router.push('/');
      }, 2000);
    } catch (err: any) {
      setError(err.message || '登録中にエラーが発生しました。');
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading || !token) {
    return (
      <div className="loading-screen" style={{ height: '50vh' }}>
        <div className="spinner"></div>
        <p>認証チェック中...</p>
      </div>
    );
  }

  return (
    <div className="auth-wrapper" style={{ maxWidth: '600px' }}>
      <div className="card">
        <h1 style={{ fontSize: '1.8rem', marginBottom: '10px', textAlign: 'center' }}>
          📝 大会データの新規登録
        </h1>
        <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginBottom: '30px' }}>
          対戦結果を入力してください。登録したデータは即座にダッシュボードに反映されます。
        </p>

        {error && <div className="error-msg">{error}</div>}
        {success && <div className="success-msg">{success}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="name">
              大会名 / イベント名
            </label>
            <input
              id="name"
              type="text"
              className="form-input"
              placeholder="例: 第1回 アリーナ記念大会"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="stage">
              大会ステージ
            </label>
            <select
              id="stage"
              className="form-input"
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              required
              style={{ backgroundColor: 'var(--bg-input)' }}
            >
              <option value="予選">予選</option>
              <option value="準々決勝">準々決勝</option>
              <option value="準決勝">準決勝</option>
              <option value="決勝">決勝</option>
              <option value="Best 16">Best 16</option>
              <option value="Best 8">Best 8</option>
            </select>
          </div>

          <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div>
              <label className="form-label" htmlFor="winnerTeam">
                🏆 勝利チーム / 選手
              </label>
              <input
                id="winnerTeam"
                type="text"
                className="form-input"
                placeholder="勝利チーム名"
                value={winnerTeam}
                onChange={(e) => setWinnerTeam(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="form-label" htmlFor="loserTeam">
                💀 敗北チーム / 選手
              </label>
              <input
                id="loserTeam"
                type="text"
                className="form-input"
                placeholder="敗北チーム名"
                value={loserTeam}
                onChange={(e) => setLoserTeam(e.target.value)}
                required
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '15px', marginTop: '30px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ flex: 1, padding: '12px' }}
              onClick={() => router.push('/')}
            >
              キャンセル
            </button>
            <button
              type="submit"
              className="btn btn-success"
              style={{ flex: 2, padding: '12px' }}
              disabled={submitting}
            >
              {submitting ? '登録中...' : 'データを登録する'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
