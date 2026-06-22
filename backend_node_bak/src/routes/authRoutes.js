const express = require('express');
const router = express.Router();
const authController = require('../controllers/authController');
const { isAuthenticated } = require('../middleware/authMiddleware');

// 新規ユーザー登録 (招待コード検証あり)
router.post('/register', authController.register);

// ログイン
router.post('/login', authController.login);

// 現在のユーザー情報取得 (認証が必要)
router.get('/me', isAuthenticated, authController.me);

module.exports = router;
