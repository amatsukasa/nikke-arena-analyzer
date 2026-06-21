const db = require('../config/db');

// 大会データと分析結果の取得（一般公開・認証不要）
exports.getTournaments = async (req, res) => {
  try {
    // 全大会データを取得
    const result = await db.query(
      `SELECT t.*, u.email as creator_email 
       FROM tournaments t 
       LEFT JOIN users u ON t.created_by = u.id 
       ORDER BY t.created_at DESC`
    );
    
    const tournaments = result.rows;

    // 簡単な分析・集計ロジック
    // 各チームの勝利回数をカウント
    const teamStats = {};
    tournaments.forEach(t => {
      // 勝利チームのカウント
      if (t.winner_team) {
        if (!teamStats[t.winner_team]) {
          teamStats[t.winner_team] = { win: 0, lose: 0 };
        }
        teamStats[t.winner_team].win += 1;
      }
      // 敗北チームのカウント
      if (t.loser_team) {
        if (!teamStats[t.loser_team]) {
          teamStats[t.loser_team] = { win: 0, lose: 0 };
        }
        teamStats[t.loser_team].lose += 1;
      }
    });

    // 勝率の計算
    const analytics = Object.keys(teamStats).map(teamName => {
      const stats = teamStats[teamName];
      const totalMatches = stats.win + stats.lose;
      const winRate = totalMatches > 0 ? ((stats.win / totalMatches) * 100).toFixed(1) : 0;
      return {
        team: teamName,
        win: stats.win,
        lose: stats.lose,
        total: totalMatches,
        winRate: parseFloat(winRate)
      };
    }).sort((a, b) => b.winRate - a.winRate || b.total - a.total); // 勝率順、同値は総試合数順

    return res.json({
      tournaments,
      analytics
    });
  } catch (err) {
    console.error('大会データ取得エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};

// 大会データの新規登録（認証が必要）
exports.createTournament = async (req, res) => {
  const { name, stage, winner_team, loser_team, championship_id } = req.body;

  if (!name || !stage || !winner_team || !loser_team) {
    return res.status(400).json({ message: 'すべての必須項目を入力してください。' });
  }

  try {
    const result = await db.query(
      `INSERT INTO tournaments (name, stage, winner_team, loser_team, created_by, championship_id)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING *`,
      [name, stage, winner_team, loser_team, req.user ? req.user.id : null, championship_id || null]
    );

    return res.status(201).json({
      message: '大会データを登録しました。',
      tournament: result.rows[0]
    });
  } catch (err) {
    console.error('大会データ登録エラー:', err);
    return res.status(500).json({ message: 'サーバーエラーが発生しました。' });
  }
};
