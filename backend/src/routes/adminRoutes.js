const express = require('express');
const router = express.Router();
const adminController = require('../controllers/adminController');
const { isAuthenticated, requireRole } = require('../middleware/authMiddleware');

// 全てのルートで認証と管理者権限が必要
router.use(isAuthenticated);
router.use(requireRole('admin'));

// ユーザー一覧取得
router.get('/users', adminController.getUsers);

// ユーザーのBAN/解除
router.put('/users/:id/ban', adminController.banUser);
router.put('/users/:id/unban', adminController.unbanUser);

// ユーザーのロール変更
router.put('/users/:id/role', adminController.updateUserRole);

module.exports = router;
