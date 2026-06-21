const express = require('express');
const router = express.Router();
const championshipController = require('../controllers/championshipController');
const { isAuthenticated } = require('../middleware/authMiddleware');

// 全大会一覧の取得（認証不要）
router.get('/', championshipController.getChampionships);

// 大会の新規登録（要認証）
router.post('/', isAuthenticated, championshipController.createChampionship);

// 大会情報の更新（要認証）
router.put('/:id', isAuthenticated, championshipController.updateChampionship);

// 大会の削除（要認証）
router.delete('/:id', isAuthenticated, championshipController.deleteChampionship);

module.exports = router;
