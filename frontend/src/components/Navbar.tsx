'use client';

import React from 'react';
import Link from 'next/link';
import { useAuth } from '../context/AuthContext';

export const Navbar: React.FC = () => {
  const { user, logout } = useAuth();

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <Link href="/" className="navbar-logo">
          🏆 大会ダッシュボード
        </Link>
        <div className="navbar-links">
          {user ? (
            <>
              <Link href="/tournament/register" className="nav-link">
                📝 データ登録
              </Link>
              {user.role === 'admin' && (
                <Link href="/admin" className="nav-link admin-link">
                  ⚙️ 管理者ページ
                </Link>
              )}
              <span className="user-email">{user.email} ({user.role === 'admin' ? '管理者' : '登録スタッフ'})</span>
              <button onClick={logout} className="logout-btn">
                ログアウト
              </button>
            </>
          ) : (
            // 未ログイン時はナビゲーションにログイン・登録リンクを表示しない（隠しURL運用のための設計）
            <span className="guest-badge">公開閲覧モード</span>
          )}
        </div>
      </div>
    </nav>
  );
};
export default Navbar;
