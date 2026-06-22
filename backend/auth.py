"""
認証ユーティリティ
- パスワードハッシュ（bcrypt）
- JWTトークン生成・検証
- FastAPI Depends として使う現在ユーザー取得関数
- ロール確認（contributor / admin）
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Cookie, Header, status
from jose import JWTError, jwt
import bcrypt as _bcrypt
from sqlalchemy.orm import Session

from database import get_db
import models

# ---------- 設定 ----------
SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-secret-key-CHANGE-IN-PRODUCTION")
ALGORITHM    = "HS256"
TOKEN_EXPIRE_DAYS = 7           # ユーザーJWT有効期限
GATE_EXPIRE_DAYS  = 7           # ゲートCookie有効期限
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")
INVITE_CODE   = os.environ.get("INVITE_CODE", "")

# ---------- パスワード ----------
def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


# ---------- JWT ----------
def create_access_token(data: dict, expires_days: int = TOKEN_EXPIRE_DAYS) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expires_days)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_gate_token() -> str:
    """ダッシュボード閲覧用ゲートトークン（ユーザー情報なし）"""
    return create_access_token({"type": "gate"}, expires_days=GATE_EXPIRE_DAYS)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ---------- 現在ユーザー取得 ----------
def get_current_user_optional(
    auth_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[models.AppUser]:
    """ログイン済みユーザーを返す（未ログインなら None）"""
    token = auth_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id: int = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    user = db.query(models.AppUser).filter(models.AppUser.id == int(user_id)).first()
    if not user or user.is_banned:
        return None
    return user


def get_current_user(
    user: Optional[models.AppUser] = Depends(get_current_user_optional),
) -> models.AppUser:
    """ログイン済みユーザーを返す（未ログインなら 401）"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ログインが必要です",
        )
    return user


def require_admin(
    user: models.AppUser = Depends(get_current_user),
) -> models.AppUser:
    """管理者のみアクセス可（それ以外は 403）"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です",
        )
    return user


def verify_gate_cookie(
    site_session: Optional[str] = Cookie(default=None),
) -> bool:
    """ゲートCookieの検証（ダッシュボード閲覧チェック用）"""
    if not site_session:
        return False
    try:
        payload = decode_token(site_session)
        return payload.get("type") == "gate"
    except JWTError:
        return False