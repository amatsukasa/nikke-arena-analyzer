const express = require('express');
const router = express.Router();
const dashboardController = require('../controllers/dashboardController');
const { isAuthenticated } = require('../middleware/authMiddleware');

// 大会データと分析結果の取得（一般公開 - 認証不要）
router.get('/', dashboardController.getTournaments);

// 大会データの登録（要ログイン）
router.post('/', isAuthenticated, dashboardController.createTournament);

module.exports = router;
