const db = require('../config/db');

// ユーザー一覧の取得 (パスワードは除外)
exports.getUsers = async (req, res) => {
  try {
    const result = await db.query(
      'SELECT id, email, role, is_banned, created_at FROM users ORDER BY id ASC'
    );
    return res.json(result.rows);
  } catch (err) {
    console.error('ユーザー一覧取得エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// ユーザーのBAN（アカウント停止）
exports.banUser = async (req, res) => {
  const { id } = req.params;

  // 自分自身をBANするのを防ぐ
  if (parseInt(id) === req.user.id) {
    return res.status(400).json({ message: '自分自身をアカウント停止することはできません。' });
  }

  try {
    const result = await db.query(
      'UPDATE users SET is_banned = true WHERE id = $1 RETURNING id, email, is_banned',
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'ユーザーが見つかりません。' });
    }

    return res.json({
      message: 'ユーザーをアカウント停止（BAN）しました。',
      user: result.rows[0]
    });
  } catch (err) {
    console.error('BANエラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// ユーザーのBAN解除
exports.unbanUser = async (req, res) => {
  const { id } = req.params;

  try {
    const result = await db.query(
      'UPDATE users SET is_banned = false WHERE id = $1 RETURNING id, email, is_banned',
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'ユーザーが見つかりません。' });
    }

    return res.json({
      message: 'ユーザーのアカウント停止を解除しました。',
      user: result.rows[0]
    });
  } catch (err) {
    console.error('BAN解除エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// ユーザーのロール変更（admin <-> user）
exports.updateUserRole = async (req, res) => {
  const { id } = req.params;
  const { role } = req.body;

  if (role !== 'user' && role !== 'admin') {
    return res.status(400).json({ message: '無効なロールです。user または admin を指定してください。' });
  }

  // 自分自身のロールを変更するのを防ぐ
  if (parseInt(id) === req.user.id) {
    return res.status(400).json({ message: '自分自身の権限を変更することはできません。' });
  }

  try {
    const result = await db.query(
      'UPDATE users SET role = $1 WHERE id = $2 RETURNING id, email, role',
      [role, id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ message: 'ユーザーが見つかりません。' });
    }

    return res.json({
      message: `ユーザーの権限を ${role} に変更しました。`,
      user: result.rows[0]
    });
  } catch (err) {
    console.error('ロール変更エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};
