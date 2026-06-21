const { Pool } = require('pg');
require('dotenv').config();

const isProduction = process.env.NODE_ENV === 'production';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: isProduction ? { rejectUnauthorized: false } : false
});

// データベースの初期化（テーブル作成）
const initDb = async () => {
  const createUsersTableQuery = `
    CREATE TABLE IF NOT EXISTS users (
      id SERIAL PRIMARY KEY,
      email VARCHAR(255) UNIQUE NOT NULL,
      password VARCHAR(255) NOT NULL,
      role VARCHAR(50) DEFAULT 'user',
      is_banned BOOLEAN DEFAULT false,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
  `;

  const createTournamentsTableQuery = `
    CREATE TABLE IF NOT EXISTS tournaments (
      id SERIAL PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      stage VARCHAR(100) NOT NULL,
      winner_team VARCHAR(255) NOT NULL,
      loser_team VARCHAR(255) NOT NULL,
      created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
  `;

  try {
    const client = await pool.connect();
    console.log('データベースに接続しました。初期化処理を開始します...');
    
    // ユーザーテーブル作成
    await client.query(createUsersTableQuery);
    // 大会データテーブル作成
    await client.query(createTournamentsTableQuery);
    
    console.log('テーブルが準備されました。');
    
    // 管理者ユーザーの初期シードデータを作成
    const checkAdminQuery = `SELECT * FROM users WHERE role = 'admin' LIMIT 1;`;
    const res = await client.query(checkAdminQuery);
    if (res.rows.length === 0) {
      const bcrypt = require('bcryptjs');
      const hashedPassword = await bcrypt.hash('admin123', 10);
      
      const insertAdminQuery = `
        INSERT INTO users (email, password, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (email) DO NOTHING;
      `;
      await client.query(insertAdminQuery, ['admin@example.com', hashedPassword, 'admin']);
      console.log('初期管理者アカウント (admin@example.com / admin123) を作成しました。');
    }

    client.release();
  } catch (err) {
    console.error('データベース初期化エラー:', err);
  }
};

module.exports = {
  query: (text, params) => pool.query(text, params),
  pool,
  initDb
};
