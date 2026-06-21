const jwt = require('jsonwebtoken');
const db = require('../config/db');

// JWT認証とBANステータス確認ミドルウェア
const isAuthenticated = async (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1]; // Bearer <token>

  if (!token) {
    return res.status(401).json({ message: '認証トークンが必要です。' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET || 'fallback_secret');
    
    // トークンに記録されたユーザーIDから最新のユーザー情報を取得し、BANされていないか確認
    const userRes = await db.query('SELECT id, email, role, is_banned FROM users WHERE id = $1', [decoded.id]);
    
    if (userRes.rows.length === 0) {
      return res.status(404).json({ message: 'ユーザーが見つかりません。' });
    }

    const user = userRes.rows[0];

    if (user.is_banned) {
      return res.status(403).json({ message: 'このアカウントは停止（BAN）されています。' });
    }

    // リクエストオブジェクトにユーザー情報を格納
    req.user = user;
    next();
  } catch (err) {
    console.error('トークン検証エラー:', err);
    return res.status(401).json({ message: 'トークンが無効または有効期限切れです。' });
  }
};

// 特定のロールを要求する認可ミドルウェア
const requireRole = (requiredRole) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ message: '認証が必要です。' });
    }

    if (req.user.role !== requiredRole) {
      return res.status(403).json({ message: 'この操作を実行する権限がありません。' });
    }

    next();
  };
};

module.exports = {
  isAuthenticated,
  requireRole
};
