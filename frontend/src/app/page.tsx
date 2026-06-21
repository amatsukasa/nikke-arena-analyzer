'use client';

import React, { useEffect, useState } from 'react';

interface Tournament {
  id: number;
  name: string;
  stage: string;
  winner_team: string;
  loser_team: string;
  creator_email: string | null;
  created_at: string;
}

interface AnalyticsItem {
  team: string;
  win: number;
  lose: number;
  total: number;
  winRate: number;
}

export default function DashboardPage() {
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchDashboardData = async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';
    try {
      const response = await fetch(`${apiUrl}/api/tournaments`);
      if (!response.ok) {
        throw new Error('データの取得に失敗しました。');
      }
      const data = await response.json();
      setTournaments(data.tournaments || []);
      setAnalytics(data.analytics || []);
    } catch (err: any) {
      setError(err.message || 'データ取得エラー');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  if (loading) {
    return (
      <div className="loading-screen" style={{ height: '50vh' }}>
        <div className="spinner"></div>
        <p>ダッシュボードデータを読み込み中...</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: '40px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '10px', background: 'linear-gradient(135deg, #fff 0%, #a5b4fc 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          📊 大会分析ダッシュボード
        </h1>
        <p style={{ color: 'var(--text-muted)' }}>
          リアルタイムで集計されたチーム別の勝率分析と、最新の大会戦績を確認できます。
        </p>
      </div>

      {error && <div className="error-msg">{error}</div>}

      <div className="dashboard-grid">
        {/* 左カラム: 最新の戦績テーブル */}
        <div className="card">
          <h2 className="section-title">⚔️ 最新の対戦結果</h2>
          {tournaments.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📂</div>
              <p>登録されている大会データがありません。</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>大会名</th>
                    <th>ステージ</th>
                    <th>WIN</th>
                    <th>LOSE</th>
                    <th>登録日</th>
                  </tr>
                </thead>
                <tbody>
                  {tournaments.map((t) => (
                    <tr key={t.id}>
                      <td style={{ fontWeight: '500' }}>{t.name}</td>
                      <td>{t.stage}</td>
                      <td>
                        <span className="badge-win">{t.winner_team}</span>
                      </td>
                      <td>
                        <span className="badge-lose">{t.loser_team}</span>
                      </td>
                      <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        {new Date(t.created_at).toLocaleDateString('ja-JP')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 右カラム: 勝率ランキング */}
        <div className="card">
          <h2 className="section-title">🔥 チーム勝率ランキング</h2>
          {analytics.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📈</div>
              <p>分析する戦績データが不足しています。</p>
            </div>
          ) : (
            <div className="stat-card-list">
              {analytics.map((item, index) => (
                <div className="stat-item" key={item.team}>
                  <div>
                    <div className="stat-team-name">
                      <span style={{ color: index === 0 ? '#F59E0B' : index === 1 ? '#94A3B8' : index === 2 ? '#B45309' : 'var(--text-muted)', marginRight: '10px' }}>
                        #{index + 1}
                      </span>
                      {item.team}
                    </div>
                    <div className="stat-matches">
                      {item.win}勝 / {item.lose}敗 (計 {item.total}戦)
                    </div>
                  </div>
                  <div className="stat-winrate">{item.winRate}%</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
