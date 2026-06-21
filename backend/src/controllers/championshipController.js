const db = require('../config/db');

// 大会（イベント）一覧の取得（一般公開・認証不要）
// 日付の降順で取得します
exports.getChampionships = async (req, res) => {
  try {
    const result = await db.query(
      `SELECT c.*, u.email as creator_email 
       FROM championships c 
       LEFT JOIN users u ON c.created_by = u.id 
       ORDER BY c.date DESC, c.created_at DESC`
    );
    return res.json(result.rows);
  } catch (err) {
    console.error('大会一覧取得エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// 大会（イベント）の新規登録（要認証）
exports.createChampionship = async (req, res) => {
  const { name, date, start_date, owner_name } = req.body;

  if (!name || !date || !start_date) {
    return res.status(400).json({ message: '大会名、開催日、開始日は必須項目です。' });
  }

  try {
    const result = await db.query(
      `INSERT INTO championships (name, date, start_date, owner_name, created_by)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING *`,
      [name, date, start_date, owner_name || null, req.user ? req.user.id : null]
    );

    return res.status(201).json({
      message: '大会を登録しました。',
      championship: result.rows[0]
    });
  } catch (err) {
    console.error('大会登録エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// 大会の更新（要認証）
exports.updateChampionship = async (req, res) => {
  const { id } = req.params;
  const { name, date, start_date, owner_name } = req.body;

  if (!name || !date || !start_date) {
    return res.status(400).json({ message: '大会名、開催日、開始日は必須項目です。' });
  }

  try {
    const result = await db.query(
      `UPDATE championships 
       SET name = $1, date = $2, start_date = $3, owner_name = $4
       WHERE id = $5
       RETURNING *`,
      [name, date, start_date, owner_name || null, id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ message: '該当する大会が見つかりません。' });
    }

    return res.json({
      message: '大会情報を更新しました。',
      championship: result.rows[0]
    });
  } catch (err) {
    console.error('大会更新エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// 大会の削除（要認証）
exports.deleteChampionship = async (req, res) => {
  const { id } = req.params;

  try {
    const result = await db.query(
      `DELETE FROM championships WHERE id = $1 RETURNING *`,
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ message: '該当する大会が見つかりません。' });
    }

    return res.json({
      message: '大会を削除しました。',
      championship: result.rows[0]
    });
  } catch (err) {
    console.error('大会削除エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};
