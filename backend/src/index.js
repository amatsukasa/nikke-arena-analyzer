const express = require('express');
const cors = require('cors');
require('dotenv').config();
const { initDb } = require('./config/db');

// ルートのインポート
const authRoutes = require('./routes/authRoutes');
const adminRoutes = require('./routes/adminRoutes');
const dashboardRoutes = require('./routes/dashboardRoutes');

const app = express();
const PORT = process.env.PORT || 5000;

// CORSの設定
// フロントエンドのURLを環境変数から読み込み、アクセスを許可します
const allowedOrigins = [
  process.env.CLIENT_URL || 'http://localhost:3000'
];

app.use(cors({
  origin: function (origin, callback) {
    // モバイルアプリやcurlからのリクエストなど、originがない場合は許可する
    if (!origin) return callback(null, true);
    if (allowedOrigins.indexOf(origin) === -1) {
      const msg = 'CORSポリシーにより、このオリジンからのアクセスは許可されていません。';
      return callback(new Error(msg), false);
    }
    return callback(null, true);
  },
  credentials: true
}));

// ボディパーサー
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// データベースの初期化
initDb();

// ヘルスチェック用エンドポイント
app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date() });
});

// APIルーティングの適用
app.use('/api/auth', authRoutes);
app.use('/api/admin', adminRoutes);
app.use('/api/tournaments', dashboardRoutes);

// グローバルエラーハンドラー
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    message: 'サーバー内部でエラーが発生しました。',
    error: process.env.NODE_ENV === 'development' ? err.message : {}
  });
});

// サーバー起動
app.listen(PORT, () => {
  console.log(`サーバーがポート ${PORT} で起動しました。`);
});
