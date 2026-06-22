const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('../config/db');

// サインアップ（新規ユーザー登録）
exports.register = async (req, res) => {
  const { email, password, inviteCode } = req.body;

  if (!email || !password || !inviteCode) {
    return res.status(400).json({ message: 'すべてのフィールドを入力してください。' });
  }

  // 招待コードの検証
  const expectedInviteCode = process.env.REGISTRATION_INVITE_CODE || 'INVITE2026';
  if (inviteCode !== expectedInviteCode) {
    return res.status(400).json({ message: '招待コードが正しくありません。' });
  }

  try {
    // 重複ユーザーの確認
    const userExists = await db.query('SELECT * FROM users WHERE email = $1', [email]);
    if (userExists.rows.length > 0) {
      return res.status(400).json({ message: 'このメールアドレスは既に登録されています。' });
    }

    // パスワードのハッシュ化
    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash(password, salt);

    // データベースへの登録
    const newUser = await db.query(
      'INSERT INTO users (email, password, role) VALUES ($1, $2, $3) RETURNING id, email, role, created_at',
      [email, hashedPassword, 'user']
    );

    return res.status(201).json({
      message: 'ユーザーの登録が完了しました。',
      user: newUser.rows[0]
    });
  } catch (err) {
    console.error('サインアップエラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// ログイン
exports.login = async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ message: 'メールアドレスとパスワードを入力してください。' });
  }

  try {
    // ユーザーの検索
    const userRes = await db.query('SELECT * FROM users WHERE email = $1', [email]);
    if (userRes.rows.length === 0) {
      return res.status(400).json({ message: 'メールアドレスまたはパスワードが正しくありません。' });
    }

    const user = userRes.rows[0];

    // BAN状態の確認
    if (user.is_banned) {
      return res.status(403).json({ message: 'このアカウントは利用停止（BAN）されています。' });
    }

    // パスワードの照合
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(400).json({ message: 'メールアドレスまたはパスワードが正しくありません。' });
    }

    // JWTトークンの生成
    const token = jwt.sign(
      { id: user.id, email: user.email, role: user.role },
      process.env.JWT_SECRET || 'fallback_secret',
      { expiresIn: '24h' }
    );

    return res.json({
      token,
      user: {
        id: user.id,
        email: user.email,
        role: user.role
      }
    });
  } catch (err) {
    console.error('ログインエラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// ログイン中ユーザー情報の取得
exports.me = async (req, res) => {
  try {
    // authMiddlewareで既にreq.userが設定されている
    return res.json({ user: req.user });
  } catch (err) {
    console.error('ユーザー情報取得エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};
