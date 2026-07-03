from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Request, Response, Query, BackgroundTasks
import auth as auth_module
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database import engine, Base, get_db, SessionLocal
import models, schemas
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import asyncio
import contextlib
import shutil
import os
from pathlib import Path
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    title="NIKKE Arena Analysis API",
    description="API for extracting and analyzing NIKKE Arena data",
    version="1.0.0"
)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"

RESULT_SCORES = {
    "優勝": 1,
    "準優勝": 2,
    "ベスト4": 4,
    "ベスト8": 8,
    "ベスト16": 16,
    "ベスト32": 32,
    "ベスト64": 64,
    "不明": 999,
}


def _merge_char_position_stats(merged_chars, char_stat, cid):
    if "_pos_map" not in merged_chars[cid]:
        merged_chars[cid]["_pos_map"] = {p: {"count": 0, "wins": 0, "total": 0} for p in range(1, 6)}
    if "_team_pos_map" not in merged_chars[cid]:
        merged_chars[cid]["_team_pos_map"] = {p: {"count": 0, "wins": 0, "total": 0, "best_result": None} for p in range(1, 6)}
        
    for ps in (char_stat.get("position_stats") or []):
        pos = ps.get("position")
        if pos in merged_chars[cid]["_pos_map"]:
            merged_chars[cid]["_pos_map"][pos]["count"] += ps.get("count", 0)
            merged_chars[cid]["_pos_map"][pos]["wins"] += ps.get("wins", 0)
            merged_chars[cid]["_pos_map"][pos]["total"] += ps.get("total", 0)
            
    for tps in (char_stat.get("team_position_stats") or []):
        pos = tps.get("position")
        if pos in merged_chars[cid]["_team_pos_map"]:
            merged_chars[cid]["_team_pos_map"][pos]["count"] += tps.get("count", 0)
            merged_chars[cid]["_team_pos_map"][pos]["wins"] += tps.get("wins", 0)
            merged_chars[cid]["_team_pos_map"][pos]["total"] += tps.get("total", 0)
            cur_br = merged_chars[cid]["_team_pos_map"][pos]["best_result"]
            new_br = tps.get("best_result")
            if new_br and new_br != "不明" and new_br != "-":
                if not cur_br or RESULT_SCORES.get(new_br, 999) < RESULT_SCORES.get(cur_br, 999):
                    merged_chars[cid]["_team_pos_map"][pos]["best_result"] = new_br

def _finalize_char_position_stats(char):
    usage_count = char.get("count", 0)
    if usage_count > 0 and "_pos_map" in char and "_team_pos_map" in char:
        pos_stats = []
        for p in range(1, 6):
            data = char["_pos_map"][p]
            c_val = data["count"]
            w_val = data["wins"]
            t_val = data["total"]
            pct = round((c_val / usage_count) * 100, 1) if usage_count > 0 else 0.0
            wr = round((w_val / t_val) * 100, 1) if t_val > 0 else (0.0 if c_val > 0 else None)
            pos_stats.append({
                "position": p,
                "count": c_val,
                "pct": pct,
                "wins": w_val,
                "total": t_val,
                "win_rate": wr
            })
        char["position_stats"] = pos_stats
        
        team_pos_stats = []
        for p in range(1, 6):
            data = char["_team_pos_map"][p]
            c_val = data["count"]
            w_val = data["wins"]
            t_val = data["total"]
            pct = round((c_val / usage_count) * 100, 1) if usage_count > 0 else 0.0
            wr = round((w_val / t_val) * 100, 1) if t_val > 0 else (0.0 if c_val > 0 else None)
            team_pos_stats.append({
                "position": p,
                "count": c_val,
                "pct": pct,
                "wins": w_val,
                "total": t_val,
                "win_rate": wr,
                "best_result": data["best_result"]
            })
        char["team_position_stats"] = team_pos_stats
    else:
        char["position_stats"] = []
        char["team_position_stats"] = []
        
    char.pop("_pos_map", None)
    char.pop("_team_pos_map", None)

os.makedirs(UPLOAD_DIR, exist_ok=True)

from fastapi.staticfiles import StaticFiles
from services.image_processor import process_images
from services.character_templates import find_character_template
from services.registration_email import (
    send_registration_approved,
    send_registration_request,
)
from services.upload_cleanup import (
    cleanup_stale_uploads,
    delete_temporary_crop_urls,
    delete_tournament_player_icons,
    delete_upload_file,
    path_from_upload_url,
    stale_age_hours_from_env,
    PLAYER_ICONS_DIR,
    _is_within,
)
from fastapi.responses import FileResponse


IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
NO_STORE_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code >= 400:
                exc.headers = {
                    **(exc.headers or {}),
                    "Cache-Control": NO_STORE_CACHE_CONTROL,
                }
            raise
        except Exception as exc:
            raise StarletteHTTPException(
                status_code=500,
                detail="Static file error",
                headers={"Cache-Control": NO_STORE_CACHE_CONTROL},
            ) from exc

        if response.status_code >= 400:
            response.headers["Cache-Control"] = NO_STORE_CACHE_CONTROL
        return response

    def file_response(self, full_path: str, stat_result, scope, status_code: int = 200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        if response.status_code >= 400:
            response.headers["Cache-Control"] = NO_STORE_CACHE_CONTROL
        else:
            path_str = str(full_path)
            if "cropped" in path_str and "crop_" in path_str:
                response.headers["Cache-Control"] = NO_STORE_CACHE_CONTROL
            else:
                response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response


app.mount("/api/uploads", CachedStaticFiles(directory="uploads"), name="uploads")


@app.get("/api/char-icon/{char_id}.png")
def get_char_icon(char_id: int, db: Session = Depends(get_db)):
    """キャラクターの代表テンプレート画像を返す（旧形式・新形式両対応）"""
    char = db.query(models.Character).filter(models.Character.id == char_id).first()
    if not char:
        raise HTTPException(
            status_code=404,
            detail="Character not found",
            headers={"Cache-Control": NO_STORE_CACHE_CONTROL},
        )
    
    # DBに template_filename が保存されている場合は優先してチェック
    template_filename = getattr(char, "template_filename", None)
    if template_filename:
        tpl_path = Path(UPLOAD_DIR) / "templates" / template_filename
        if tpl_path.is_file():
            return FileResponse(
                tpl_path,
                media_type="image/png",
                headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
            )
        else:
            # ファイルが存在しない場合は一旦クリア
            char.template_filename = None
            try:
                db.commit()
            except Exception:
                db.rollback()

    # filesystem を探索 (char_{char_id}.png または char_{char_id}_*.png)
    template_path = find_character_template(UPLOAD_DIR, char_id)
    if template_path:
        try:
            char.template_filename = template_path.name
            char.is_template_available = True
            db.commit()
        except Exception:
            db.rollback()
        return FileResponse(
            template_path,
            media_type="image/png",
            headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
        )
    
    if getattr(char, "is_template_available", False) or getattr(char, "template_filename", None):
        try:
            char.is_template_available = False
            char.template_filename = None
            db.commit()
        except Exception:
            db.rollback()

    raise HTTPException(
        status_code=404,
        detail="Template not found",
        headers={"Cache-Control": NO_STORE_CACHE_CONTROL},
    )

@app.get("/")
def read_root():
    return {"message": "Welcome to NIKKE Arena Analysis API!"}


# ===== 初回起動時: 管理者アカウント自動作成 =====
from database import SessionLocal, Base
from scripts.init_db import init_db

_upload_cleanup_task = None


def run_stale_upload_cleanup():
    db = SessionLocal()
    try:
        referenced_icons = {
            icon_url
            for (icon_url,) in db.query(models.Player.icon_url).filter(
                models.Player.icon_url.isnot(None)
            ).all()
        }
        cleanup_stale_uploads(
            referenced_icons,
            max_age_hours=stale_age_hours_from_env(),
        )
    except Exception as error:
        print(f"[Cleanup] Scheduled cleanup failed: {error}")
    finally:
        db.close()


async def periodic_upload_cleanup():
    raw_interval = os.environ.get("UPLOAD_CLEANUP_INTERVAL_MINUTES", "60")
    try:
        interval_seconds = max(5, int(raw_interval)) * 60
    except ValueError:
        interval_seconds = 60 * 60
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(run_stale_upload_cleanup)


@app.on_event("startup")
async def startup_event():
    global _upload_cleanup_task
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE characters ADD COLUMN IF NOT EXISTS template_filename VARCHAR;"))
    except Exception as e:
        print(f"[Startup] template_filename カラム追加スキップまたはエラー: {e}")
    try:
        init_db()
        print("[Startup] データベース初期キャラクターデータをインポートしました")
    except Exception as e:
        print(f"[Startup] キャラクターの初期化に失敗: {e}")
        
    first_email    = os.environ.get("FIRST_ADMIN_EMAIL", "admin@example.com")
    first_password = os.environ.get("FIRST_ADMIN_PASSWORD", "admin123")
    db = SessionLocal()
    try:
        from datetime import date
        default_start_date = date(2022, 11, 4) # NIKKEリリース日
        
        existing = db.query(models.AppUser).filter(models.AppUser.email == first_email).first()
        if not existing:
            existing = db.query(models.AppUser).filter(
                models.AppUser.role == "admin"
            ).order_by(models.AppUser.id).first()
        if not existing:
            admin = models.AppUser(
                email=first_email,
                hashed_password=auth_module.hash_password(first_password),
                role="admin",
                provider_name="管理者",
                game_start_date=default_start_date,
                approval_status="active",
                approved_at=datetime.now(timezone.utc),
            )
            db.add(admin)
            db.commit()
            print(f"[Startup] 管理者アカウント作成: {first_email}")
        else:
            existing.role = "admin"
            existing.approval_status = "active"
            if not existing.provider_name:
                existing.provider_name = "管理者"
            if not existing.game_start_date:
                existing.game_start_date = default_start_date
            db.commit()
            print(f"[Startup] Existing admin preserved: {existing.email}")

    finally:
        db.close()
    await asyncio.to_thread(run_stale_upload_cleanup)
    _upload_cleanup_task = asyncio.create_task(periodic_upload_cleanup())


@app.on_event("shutdown")
async def shutdown_event():
    global _upload_cleanup_task
    if _upload_cleanup_task is not None:
        _upload_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _upload_cleanup_task
        _upload_cleanup_task = None


# ===== 認証エンドポイント =====

PLAY_SERVERS = {"KR", "JP", "GLOBAL", "NA", "SEA"}
EMPTY_SLOT_CHARACTER_ID = 9999


def serialize_app_user(user: models.AppUser):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "provider_name": user.provider_name,
        "game_start_date": str(user.game_start_date) if user.game_start_date else None,
        "play_server": user.play_server,
        "approval_status": user.approval_status,
    }


@app.post("/api/auth/gate")
def gate_login(body: dict, response: Response):
    """サイトパスコード検証 → HttpOnly Cookie 発行"""
    password = body.get("password", "")
    site_pw = auth_module.SITE_PASSWORD
    if not site_pw:
        # 環境変数未設定 = 制限なし（開発用）
        token = auth_module.create_gate_token()
        response.set_cookie("site_session", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return {"ok": True}
    if password != site_pw:
        raise HTTPException(status_code=401, detail="パスコードが正しくありません")
    token = auth_module.create_gate_token()
    response.set_cookie("site_session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"ok": True}


@app.post("/api/auth/login")
def user_login(body: dict, response: Response, db: Session = Depends(get_db)):
    """メール/パスワードでログイン → JWT Cookie 発行"""
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")
    user = db.query(models.AppUser).filter(models.AppUser.email == email).first()
    if not user or not auth_module.verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが正しくありません")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="このアカウントは停止されています")
    if user.approval_status != "active":
        raise HTTPException(
            status_code=403,
            detail="管理者による登録承認をお待ちください",
        )
    token = auth_module.create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie("auth_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"ok": True, "token": token, "user": serialize_app_user(user)}


@app.post("/api/auth/logout")
def user_logout(response: Response):
    """Cookie 削除"""
    response.delete_cookie("auth_token")
    response.delete_cookie("site_session")
    return {"ok": True}


@app.post("/api/auth/register")
def user_register(body: dict, db: Session = Depends(get_db)):
    """スタッフ登録依頼を作成し、管理者へ承認メールを送信する。"""
    email       = body.get("email", "").strip().lower()
    password    = body.get("password", "")
    invite_code = body.get("inviteCode", "").strip() # 余分なスペースをトリミング
    provider_name = body.get("providerName", "").strip() or None
    game_start_date = body.get("gameStartDate", "") or None
    play_server = body.get("playServer") or None
    
    expected_code = auth_module.INVITE_CODE.strip() if auth_module.INVITE_CODE else ""
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="メールとパスワードは必須です")
    if expected_code and invite_code != expected_code:
        raise HTTPException(status_code=400, detail="招待コードが正しくありません")
    existing = db.query(models.AppUser).filter(models.AppUser.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="そのメールアドレスは既に登録されています")
    if play_server not in PLAY_SERVERS and play_server is not None:
        raise HTTPException(status_code=400, detail="プレイしているサーバーが正しくありません")
    
    # 日付文字列のパース処理
    parsed_date = None
    if game_start_date:
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(game_start_date, "%Y-%m-%d").date()
        except ValueError as ve:
            print(f"[Debug Register] Date parsing error for '{game_start_date}': {ve}")
            raise HTTPException(status_code=400, detail="ゲーム開始日の日付フォーマットが正しくありません (YYYY-MM-DD)")

    user = models.AppUser(
        email=email,
        hashed_password=auth_module.hash_password(password),
        role="contributor",
        provider_name=provider_name,
        game_start_date=parsed_date,
        play_server=play_server,
        approval_status="pending",
        approval_requested_at=datetime.now(timezone.utc),
    )
    approval_token = secrets.token_urlsafe(32)
    user.approval_token_hash = hashlib.sha256(
        approval_token.encode("utf-8")
    ).hexdigest()
    try:
        db.add(user)
        db.flush()
        send_registration_request(user, approval_token)
        db.commit()
    except Exception as error:
        db.rollback()
        print(f"[Registration] Failed to send approval email: {error}")
        raise HTTPException(
            status_code=503,
            detail="登録依頼メールを送信できませんでした。時間をおいて再度お試しください",
        )
    return {
        "ok": True,
        "status": "pending",
        "message": "登録依頼を送信しました。管理者の承認をお待ちください",
    }


def get_pending_registration(
    user_id: int,
    token: str,
    db: Session,
) -> models.AppUser:
    user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
    if not user or user.approval_status != "pending" or not user.approval_token_hash:
        raise HTTPException(status_code=404, detail="有効な登録依頼が見つかりません")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(token_hash, user.approval_token_hash):
        raise HTTPException(status_code=404, detail="有効な登録依頼が見つかりません")
    requested_at = user.approval_requested_at
    if requested_at is None:
        raise HTTPException(status_code=410, detail="承認リンクの有効期限が切れています")
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - requested_at > timedelta(hours=72):
        raise HTTPException(status_code=410, detail="承認リンクの有効期限が切れています")
    return user


@app.get("/api/auth/registration-approval")
def inspect_registration_approval(
    user_id: int,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_pending_registration(user_id, token, db)
    return {
        "email": user.email,
        "provider_name": user.provider_name,
        "game_start_date": str(user.game_start_date) if user.game_start_date else None,
        "play_server": user.play_server,
    }


@app.post("/api/auth/registration-approval")
def approve_registration(
    body: dict,
    db: Session = Depends(get_db),
):
    user_id = body.get("userId")
    token = body.get("token", "")
    if not isinstance(user_id, int) or not token:
        raise HTTPException(status_code=400, detail="承認情報が不足しています")
    user = get_pending_registration(user_id, token, db)
    user.approval_status = "active"
    user.approved_at = datetime.now(timezone.utc)
    user.approval_token_hash = None
    db.commit()
    try:
        send_registration_approved(user)
    except Exception as error:
        print(f"[Registration] Approval notice email failed: {error}")
    return {"ok": True, "message": "スタッフ登録を承認しました"}


@app.get("/api/auth/me")
def get_me(current_user: models.AppUser = Depends(auth_module.get_current_user)):
    """現在ログイン中のユーザー情報"""
    return serialize_app_user(current_user)


@app.put("/api/auth/me")
def update_me(
    body: dict,
    current_user: models.AppUser = Depends(auth_module.get_current_user),
    db: Session = Depends(get_db),
):
    email = body.get("email", "").strip().lower()
    provider_name = body.get("providerName", "").strip() or None
    game_start_date = body.get("gameStartDate") or None
    play_server = body.get("playServer") or None
    current_password = body.get("currentPassword", "")
    new_password = body.get("newPassword", "")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="メールアドレスが正しくありません")
    duplicate = db.query(models.AppUser).filter(
        models.AppUser.email == email,
        models.AppUser.id != current_user.id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="そのメールアドレスは既に登録されています")
    if play_server not in PLAY_SERVERS and play_server is not None:
        raise HTTPException(status_code=400, detail="プレイしているサーバーが正しくありません")

    parsed_date = None
    if game_start_date:
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(game_start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="ゲーム開始日が正しくありません")

    if new_password:
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="新しいパスワードは8文字以上にしてください")
        if not auth_module.verify_password(current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="現在のパスワードが正しくありません")
        current_user.hashed_password = auth_module.hash_password(new_password)

    current_user.email = email
    current_user.provider_name = provider_name
    current_user.game_start_date = parsed_date
    current_user.play_server = play_server
    db.commit()
    db.refresh(current_user)
    return {"ok": True, "user": serialize_app_user(current_user)}


@app.get("/api/auth/users")
def list_users(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """ユーザー一覧（管理者のみ）"""
    users = db.query(models.AppUser).order_by(models.AppUser.created_at).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_banned": u.is_banned,
            "approval_status": u.approval_status,
            "provider_name": u.provider_name,
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@app.put("/api/auth/users/{user_id}/approval")
def change_user_approval(
    user_id: int,
    body: dict,
    current_admin: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    approval_status = body.get("status")
    if approval_status not in {"active", "rejected"}:
        raise HTTPException(status_code=400, detail="承認状態が正しくありません")
    user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    if user.id == current_admin.id and approval_status != "active":
        raise HTTPException(status_code=400, detail="自分自身を無効化できません")
    user.approval_status = approval_status
    user.approved_at = datetime.now(timezone.utc) if approval_status == "active" else None
    user.approved_by = current_admin.id if approval_status == "active" else None
    user.approval_token_hash = None
    db.commit()
    if approval_status == "active":
        try:
            send_registration_approved(user)
        except Exception as error:
            print(f"[Registration] Approval notice email failed: {error}")
    return {"ok": True, "approval_status": user.approval_status}


@app.put("/api/auth/users/{user_id}/role")
def change_user_role(
    user_id: int,
    body: dict,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """ロール変更（管理者のみ）"""
    user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    new_role = body.get("role")
    if new_role not in ("contributor", "admin"):
        raise HTTPException(status_code=400, detail="role は contributor または admin のみ有効です")
    user.role = new_role
    db.commit()
    return {"ok": True, "role": user.role}


@app.put("/api/auth/users/{user_id}/ban")
def ban_user(
    user_id: int,
    current_admin: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """BAN（管理者のみ、自分自身はBANできない）"""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="自分自身はBANできません")
    user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    user.is_banned = True
    db.commit()
    return {"ok": True}


@app.put("/api/auth/users/{user_id}/unban")
def unban_user(
    user_id: int,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """BAN解除（管理者のみ）"""
    user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    user.is_banned = False
    db.commit()
    return {"ok": True}


# ===== 認証ルート ここまで =====

from sqlalchemy import case, func

@app.get("/api/characters", response_model=List[schemas.Character])
def get_characters(db: Session = Depends(get_db)):
    # deck_teams の使用回数を集計
    usage_counts = {}
    for i in range(1, 6):
        col = getattr(models.DeckTeam, f"char{i}_id")
        counts = db.query(col, func.count(col)).group_by(col).all()
        for char_id, count in counts:
            if char_id:
                usage_counts[char_id] = usage_counts.get(char_id, 0) + count

    # SSR > SR > R 順、五十音順（名前順）
    rarity_order = case(
        (models.Character.rarity == 'SSR', 1),
        (models.Character.rarity == 'SR', 2),
        (models.Character.rarity == 'R', 3),
        else_=4
    )
    characters = db.query(models.Character).order_by(
        rarity_order,
        models.Character.name,
    ).all()
    res = []
    for character in characters:
        tpl_filename = getattr(character, "template_filename", None)
        is_avail = bool(
            getattr(character, "is_template_available", False)
            or getattr(character, "template_filename", None)
        )
        if is_avail:
            icon_url = f"/api/char-icon/{character.id}.png"
        else:
            icon_url = None
        res.append(
            schemas.Character.model_validate(character).model_copy(
                update={
                    "is_template_available": is_avail,
                    "template_filename": tpl_filename,
                    "icon_url": icon_url,
                    "usage_count": usage_counts.get(character.id, 0)
                }
            )
        )
    return res

@app.post("/api/characters")
def create_character(
    body: dict,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db)
):
    """新しいキャラクターを手動で追加する（管理者のみ）"""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="名前は必須です")
    # 重複チェック
    existing = db.query(models.Character).filter(models.Character.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"「{name}」は既に登録されています")
    new_char = models.Character(
        name=name,
        rarity=body.get("rarity", "SSR"),
        element=body.get("element"),
        manufacturer=body.get("manufacturer"),
        burst_phase=body.get("burst_phase"),
        weapon=body.get("weapon"),
        class_type=body.get("class_type"),
        is_template_available=False
    )
    db.add(new_char)
    db.commit()
    db.refresh(new_char)
    return {"ok": True, "character": {"id": new_char.id, "name": new_char.name}}


@app.put("/api/characters/{char_id}")
def update_character(
    char_id: int,
    body: dict,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db)
):
    """キャラクター情報を修正する（管理者のみ）"""
    if char_id == EMPTY_SLOT_CHARACTER_ID:
        raise HTTPException(status_code=400, detail="空枠は編集できません")
    char = db.query(models.Character).filter(models.Character.id == char_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    if "name" in body:
        char.name = body["name"]
    if "rarity" in body:
        char.rarity = body["rarity"]
    if "element" in body:
        char.element = body["element"]
    if "manufacturer" in body:
        char.manufacturer = body["manufacturer"]
    if "burst_phase" in body:
        char.burst_phase = body["burst_phase"]
    if "weapon" in body:
        char.weapon = body["weapon"]
    if "class_type" in body:
        char.class_type = body["class_type"]
    db.commit()
    db.refresh(char)
    return {"ok": True, "character": {"id": char.id, "name": char.name}}

@app.get("/api/admin/templates")
def get_templates_list(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """AI学習に使用しているテンプレート画像の一覧を返す"""
    template_dir = "uploads/templates"
    result = []
    if not os.path.exists(template_dir):
        return []
    for fname in sorted(os.listdir(template_dir)):
        if fname.startswith("char_") and fname.endswith(".png"):
            try:
                char_id = int(fname.split("_")[1].split(".")[0])
                char = db.query(models.Character).filter(models.Character.id == char_id).first()
                fpath = os.path.join(template_dir, fname)
                fsize = os.path.getsize(fpath)
                result.append({
                    "char_id": char_id,
                    "char_name": char.name if char else f"ID:{char_id}（未登録）",
                    "rarity": char.rarity if char else None,
                    "image_url": f"/api/uploads/templates/{fname}",
                    "file_size_kb": round(fsize / 1024, 1)
                })
            except Exception:
                pass
    return result

@app.delete("/api/admin/templates/{char_id}")
def delete_template(
    char_id: int,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """指定キャラクターの全テンプレート画像を削除する（旧形式+新形式）"""
    template_dir = "uploads/templates"
    deleted = 0
    # 旧形式
    old_path = f"uploads/templates/char_{char_id}.png"
    if os.path.exists(old_path):
        os.remove(old_path)
        deleted += 1
    # 新形式
    if os.path.exists(template_dir):
        for f in os.listdir(template_dir):
            if f.startswith(f"char_{char_id}_") and f.endswith(".png"):
                os.remove(os.path.join(template_dir, f))
                deleted += 1
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    char = db.query(models.Character).filter(models.Character.id == char_id).first()
    if char:
        char.is_template_available = False
        char.template_filename = None
        db.commit()
    return {"ok": True, "deleted_count": deleted}

@app.get("/api/admin/all-characters")
def get_all_characters_admin(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """全キャラクターをテンプレート有無フラグ付きで返す（管理者用）"""
    template_dir = "uploads/templates"
    # テンプレートが存在するキャラIDのセット
    template_ids = set()
    if os.path.exists(template_dir):
        for fname in os.listdir(template_dir):
            if fname.startswith("char_") and fname.endswith(".png"):
                try:
                    cid = int(fname.split("_")[1].split(".")[0])
                    template_ids.add(cid)
                except Exception:
                    pass

    # キャラごとのテンプレート数をカウント
    template_counts: dict[int, int] = {}
    for cid in template_ids:
        count = 0
        old_path = os.path.join(template_dir, f"char_{cid}.png")
        if os.path.exists(old_path):
            count += 1
        for f in os.listdir(template_dir):
            if f.startswith(f"char_{cid}_") and f.endswith(".png"):
                count += 1
        template_counts[cid] = count

    chars = db.query(models.Character).filter(
        models.Character.id != EMPTY_SLOT_CHARACTER_ID
    ).order_by(models.Character.name).all()
    result = []
    for c in chars:
        has_tpl = c.id in template_ids
        tpl_count = template_counts.get(c.id, 0)
        result.append({
            "char_id": c.id,
            "char_name": c.name,
            "rarity": c.rarity,
            "element": c.element,
            "manufacturer": c.manufacturer,
            "burst_phase": c.burst_phase,
            "weapon": c.weapon,
            "class_type": c.class_type,
            "has_template": has_tpl,
            "template_count": tpl_count,
            "image_url": f"/api/uploads/templates/{c.template_filename}" if getattr(c, "template_filename", None) else (f"/api/char-icon/{c.id}.png" if has_tpl else None),
        })
    return result

@app.delete("/api/characters/{char_id}")
def delete_character(
    char_id: int,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db)
):
    """キャラクターをDBから完全削除（テンプレートも削除、管理者のみ）"""
    if char_id == EMPTY_SLOT_CHARACTER_ID:
        raise HTTPException(status_code=400, detail="空枠は削除できません")
    char = db.query(models.Character).filter(models.Character.id == char_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    # テンプレートがあれば全て削除
    template_dir = "uploads/templates"
    old_path = os.path.join(template_dir, f"char_{char_id}.png")
    if os.path.exists(old_path):
        os.remove(old_path)
    if os.path.exists(template_dir):
        for f in os.listdir(template_dir):
            if f.startswith(f"char_{char_id}_") and f.endswith(".png"):
                os.remove(os.path.join(template_dir, f))
    db.delete(char)
    db.commit()
    return {"ok": True}

@app.post("/api/admin/merge-characters")
def merge_characters(
    body: dict,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """
    from_id（誤ったキャラ）の参照を to_id（正しいキャラ）に全DeckTeamで一括置換する。
    keep_source=True の場合、from_id のキャラレコードは削除しない（両者が別キャラとして存在し続ける場合）。
    """
    from_id    = body.get("from_id")
    to_id      = body.get("to_id")
    keep_source = body.get("keep_source", False)  # Trueなら元キャラを削除しない

    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_id と to_id が必要です")
    if EMPTY_SLOT_CHARACTER_ID in (from_id, to_id):
        raise HTTPException(status_code=400, detail="空枠はキャラクター統合の対象にできません")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="from_id と to_id が同じです")

    from_char = db.query(models.Character).filter(models.Character.id == from_id).first()
    to_char   = db.query(models.Character).filter(models.Character.id == to_id).first()
    if not from_char:
        raise HTTPException(status_code=404, detail=f"from_id={from_id} のキャラが見つかりません")
    if not to_char:
        raise HTTPException(status_code=404, detail=f"to_id={to_id} のキャラが見つかりません")

    # DeckTeam の char1_id〜char5_id を一括置換
    replaced = 0
    teams = db.query(models.DeckTeam).all()
    for team in teams:
        changed = False
        for col in ["char1_id", "char2_id", "char3_id", "char4_id", "char5_id"]:
            if getattr(team, col) == from_id:
                setattr(team, col, to_id)
                changed = True
        if changed:
            replaced += 1

    if not keep_source:
        # from_id のテンプレートがあれば削除
        fpath = f"uploads/templates/char_{from_id}.png"
        if os.path.exists(fpath):
            os.remove(fpath)
        # from_id のキャラレコードを削除
        db.delete(from_char)

    db.commit()

    return {
        "ok": True,
        "replaced_teams": replaced,
        "from_name": from_char.name,
        "to_name": to_char.name,
        "source_deleted": not keep_source
    }

@app.post("/api/tournaments", response_model=schemas.Tournament)
def create_tournament(
    tournament: schemas.TournamentBase, 
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user)
):
    # 登録データのベースを作成
    data = tournament.model_dump()
    
    # ログインユーザーから提供者名を取得
    data["owner_name"] = current_user.provider_name or "不明な提供者"
    
    # 作成者を記録
    data["created_by"] = current_user.id
    data["publication_status"] = "draft"
    data["published_at"] = None
    data["published_by"] = None
    
    # championship_id から名前などの情報を引き継ぐ
    if tournament.championship_id:
        championship = db.query(models.Championship).filter(models.Championship.id == tournament.championship_id).first()
        if championship:
            data["name"] = championship.name
            data["date"] = championship.date or tournament.date

    db_tournament = models.Tournament(**data)
    db.add(db_tournament)
    db.commit()
    db.refresh(db_tournament)
    return db_tournament

def require_tournament_manager(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser,
) -> models.Tournament:
    tournament = db.query(models.Tournament).filter(
        models.Tournament.id == tournament_id
    ).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if current_user.role != "admin" and tournament.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this tournament",
        )
    return tournament


def require_tournament_viewer(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    tournament = db.query(models.Tournament).filter(
        models.Tournament.id == tournament_id
    ).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.publication_status == "published":
        return tournament
    if current_user and (
        current_user.role == "admin" or tournament.created_by == current_user.id
    ):
        return tournament
    raise HTTPException(status_code=404, detail="Tournament not found")


def require_tournament_dashboard_viewer(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    tournament = require_tournament_viewer(tournament_id, db, current_user)
    # メンバー専用ダッシュボードの閲覧権限チェック:
    # 現時点では、ログイン・認証済みユーザーであることをチェック（管理者は常に許可）
    if not current_user:
        raise HTTPException(status_code=401, detail="認証が必要です。ログインしてください。")
    # TODO: 将来的には、ここで user_id または player_id が tournament の参加メンバーかどうかの判定を追加する
    return tournament


def get_published_tournament_ids(
    tournament_ids: List[int],
    db: Session,
) -> List[int]:
    if not tournament_ids:
        return []
    published_ids = {
        tournament_id
        for (tournament_id,) in db.query(models.Tournament.id).filter(
            models.Tournament.id.in_(set(tournament_ids)),
            models.Tournament.publication_status == "published",
        ).all()
    }
    return [
        tournament_id
        for tournament_id in tournament_ids
        if tournament_id in published_ids
    ]


def get_publication_readiness(tournament: models.Tournament, db: Session):
    players = db.query(models.Player).filter(
        models.Player.tournament_id == tournament.id
    ).all()
    complete_player_count = 0
    unresolved_slot_count = 0

    for player in players:
        deck_set = db.query(models.DeckSet).filter(
            models.DeckSet.player_id == player.id
        ).order_by(models.DeckSet.created_at.desc(), models.DeckSet.id.desc()).first()
        if not deck_set:
            continue
        teams = db.query(models.DeckTeam).filter(
            models.DeckTeam.deck_set_id == deck_set.id
        ).all()
        teams_by_number = {team.team_number: team for team in teams}
        player_complete = len(teams_by_number) == 5
        for team_number in range(1, 6):
            team = teams_by_number.get(team_number)
            if not team:
                unresolved_slot_count += 5
                player_complete = False
                continue
            slots = [
                team.char1_id,
                team.char2_id,
                team.char3_id,
                team.char4_id,
                team.char5_id,
            ]
            missing = sum(character_id is None for character_id in slots)
            unresolved_slot_count += missing
            if missing:
                player_complete = False
        if player_complete:
            complete_player_count += 1

    match_count = db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id
    ).count()
    player_count = len(players)
    warnings = []
    if player_count < 64:
        warnings.append(f"登録プレイヤーが64人未満です（{player_count}人）")
    if match_count == 0:
        warnings.append("対戦結果がまだ登録されていません")

    return {
        "player_count": player_count,
        "complete_player_count": complete_player_count,
        "incomplete_player_count": player_count - complete_player_count,
        "unresolved_slot_count": unresolved_slot_count,
        "match_count": match_count,
        "can_publish": (
            player_count > 0
            and complete_player_count == player_count
            and unresolved_slot_count == 0
        ),
        "warnings": warnings,
    }

@app.get("/api/tournaments", response_model=List[schemas.Tournament])
def get_tournaments(
    mine: bool = False,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    query = db.query(models.Tournament)
    if mine:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Login required")
        if current_user.role != "admin":
            query = query.filter(models.Tournament.created_by == current_user.id)
    else:
        query = query.filter(models.Tournament.publication_status == "published")
    tournaments = query.order_by(
        models.Tournament.created_at.desc(),
        models.Tournament.id.desc(),
    ).all()
    
    result = []
    for t in tournaments:
        t_schema = schemas.Tournament.model_validate(t)
        if t.creator:
            t_schema.creator_email = t.creator.email
        result.append(t_schema)

    if mine:
        return result
        
    return [
        t_schema.model_copy(
            update={"owner_name": None, "created_by": None, "creator_email": None}
        )
        for t_schema in result
    ]

@app.get("/api/tournaments/{tournament_id}", response_model=schemas.Tournament)
def get_tournament(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    return require_tournament_viewer(tournament_id, db, current_user)

@app.put("/api/tournaments/{tournament_id}", response_model=schemas.Tournament)
def update_tournament(
    tournament_id: int, 
    tournament: schemas.TournamentBase, 
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user)
):
    db_tournament = require_tournament_manager(tournament_id, db, current_user)
    
    # championship_id が更新されたら名前などを再同期
    if tournament.championship_id:
        championship = db.query(models.Championship).filter(models.Championship.id == tournament.championship_id).first()
        if championship:
            db_tournament.name = championship.name
            db_tournament.championship_id = tournament.championship_id
            db_tournament.date = championship.date or tournament.date
            
    db_tournament.season = tournament.season
    # 提供者情報が紐付け変更されることは原則ないが、ログイン中ユーザー情報で常に上書き保護
    db_tournament.owner_name = current_user.provider_name or db_tournament.owner_name
    db.commit()
    db.refresh(db_tournament)
    return db_tournament


@app.get("/api/tournaments/{tournament_id}/publication")
def get_tournament_publication(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    tournament = require_tournament_manager(tournament_id, db, current_user)
    return {
        "publication_status": tournament.publication_status,
        "published_at": tournament.published_at,
        "readiness": get_publication_readiness(tournament, db),
    }


@app.put("/api/tournaments/{tournament_id}/publication")
def update_tournament_publication(
    tournament_id: int,
    body: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    tournament = require_tournament_manager(tournament_id, db, current_user)
    publish = body.get("published") is True
    readiness = get_publication_readiness(tournament, db)

    if publish and not readiness["can_publish"]:
        raise HTTPException(
            status_code=400,
            detail="未完成の編成データがあるため公開できません",
        )

    # ステータスが変わった場合のみ処理
    status_changed = (tournament.publication_status == "published") != publish

    tournament.publication_status = "published" if publish else "draft"
    tournament.published_at = datetime.now(timezone.utc) if publish else None
    tournament.published_by = current_user.id if publish else None
    db.commit()
    db.refresh(tournament)
    
    if status_changed:
        if publish:
            background_tasks.add_task(recompute_snapshot, tournament_id, current_user.id)
        else:
            background_tasks.add_task(delete_snapshot, tournament_id)

    return {
        "ok": True,
        "publication_status": tournament.publication_status,
        "published_at": tournament.published_at,
        "published_by": tournament.published_by,
        "readiness": readiness,
    }

@app.delete("/api/tournaments/{tournament_id}")
def delete_tournament(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    db_tournament = require_tournament_manager(tournament_id, db, current_user)
    db.delete(db_tournament)
    db.commit()
    # 大会削除時に永続保存アイコンをクリーンアップ
    delete_tournament_player_icons(tournament_id)
    return {"ok": True}

# ==========================================
# 大会管理 (Championships) API
# ==========================================

@app.get("/api/championships", response_model=List[schemas.ChampionshipResponse])
def get_championships(db: Session = Depends(get_db)):
    return db.query(models.Championship).order_by(models.Championship.date.desc(), models.Championship.id.desc()).all()

@app.get("/api/championships/{id}", response_model=schemas.ChampionshipResponse)
def get_championship(id: int, db: Session = Depends(get_db)):
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    return db_championship

@app.post("/api/championships", response_model=schemas.ChampionshipResponse)
def create_championship(
    championship: schemas.ChampionshipCreate,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    data = championship.model_dump()
    data["created_by"] = current_user.id
    db_championship = models.Championship(**data)
    db.add(db_championship)
    db.commit()
    db.refresh(db_championship)
    return db_championship

@app.put("/api/championships/{id}", response_model=schemas.ChampionshipResponse)
def update_championship(
    id: int,
    championship: schemas.ChampionshipCreate,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    """大会シリーズ情報更新（ログイン必須）"""
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    db_championship.name = championship.name
    db_championship.date = championship.date
    db_championship.start_date = championship.start_date
    db_championship.owner_name = championship.owner_name
    if championship.date is not None:
        db.query(models.Tournament).filter(
            models.Tournament.championship_id == id
        ).update(
            {models.Tournament.date: championship.date},
            synchronize_session=False,
        )
    db.commit()
    db.refresh(db_championship)
    return db_championship

@app.delete("/api/championships/{id}")
def delete_championship(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    """大会シリーズ削除（ログイン必須）"""
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    db.delete(db_championship)
    db.commit()
    return {"ok": True}

@app.get("/api/championships/{id}/matches", response_model=List[schemas.Tournament])
def get_championship_matches(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    query = db.query(models.Tournament).filter(
        models.Tournament.championship_id == id
    )
    if current_user is None:
        query = query.filter(models.Tournament.publication_status == "published")
    elif current_user.role != "admin":
        query = query.filter(
            (models.Tournament.publication_status == "published")
            | (models.Tournament.created_by == current_user.id)
        )
    return query.order_by(models.Tournament.created_at.desc()).all()

@app.get("/api/tournaments/{tournament_id}/players", response_model=List[schemas.Player])
def get_players(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_tournament_viewer(tournament_id, db, current_user)
    return db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()

@app.get("/api/tournaments/{tournament_id}/players/{seed_number}/details")
def get_player_details(
    tournament_id: int,
    seed_number: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_tournament_viewer(tournament_id, db, current_user)
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number
    ).first()
    
    if not player:
        return {"player": None, "decks": []}
        
    deck_set = db.query(models.DeckSet).filter(models.DeckSet.player_id == player.id).first()
    if not deck_set:
        return {
            "player": {
                "id": player.id,
                "name": player.name,
                "seed_number": player.seed_number,
                "icon_url": player.icon_url,
            },
            "decks": [],
        }
        
    # Get matches where this player participated and the match was resolved
    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id,
        (models.Match.attacker_id == player.id) | (models.Match.defender_id == player.id),
        models.Match.winner_id.isnot(None)
    ).all()
    
    # Pre-calculate win/loss per team number
    team_stats = {1: {"wins": 0, "losses": 0}, 2: {"wins": 0, "losses": 0}, 3: {"wins": 0, "losses": 0}, 4: {"wins": 0, "losses": 0}, 5: {"wins": 0, "losses": 0}}
    
    for m in matches:
        for r in m.round_results:
            if r.winner_id == player.id:
                team_stats[r.round_number]["wins"] += 1
            else:
                team_stats[r.round_number]["losses"] += 1
                
    decks = []
    for team in deck_set.teams:
        char_ids = [c for c in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id] if c]
        stats = team_stats.get(team.team_number, {"wins": 0, "losses": 0})
        total = stats["wins"] + stats["losses"]
        win_rate = round((stats["wins"] / total * 100)) if total > 0 else 0
        
        canon_id = ",".join(map(str, sorted(char_ids)))
        
        decks.append({
            "team_number": team.team_number,
            "character_ids": char_ids,
            "canonical_id": canon_id,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": win_rate
        })
        
    # Ensure they are sorted by team_number
    decks.sort(key=lambda x: x["team_number"])
        
    return {
        "player": {
            "id": player.id,
            "name": player.name,
            "seed_number": player.seed_number,
            "icon_url": player.icon_url
        },
        "decks": decks
    }



def cleanup_replaced_player_icon(
    db: Session,
    player_id: int,
    previous_url: str | None,
    current_url: str | None,
):
    """
    プレイヤーアイコンが別URLに差し替えられたとき、旧ファイルを削除する。

    削除対象: uploads/cropped/player_icon_*.png（旧形式の一時保存ファイルのみ）
    削除しない: uploads/player_icons/ 配下（永続保存領域）
    """
    if not previous_url or previous_url == current_url:
        return
    still_referenced = db.query(models.Player.id).filter(
        models.Player.id != player_id,
        models.Player.icon_url == previous_url,
    ).first()
    path = path_from_upload_url(previous_url)
    if (
        not still_referenced
        and path is not None
        # 旧形式（uploads/cropped/player_icon_*.png）のみ削除対象
        # 永続保存先（uploads/player_icons/）は絶対に削除しない
        and path.name.startswith("player_icon_")
        and not _is_within(path, PLAYER_ICONS_DIR)
    ):
        delete_upload_file(path)



@app.post("/api/tournaments/{tournament_id}/players/{seed_number}")
async def update_player_info(
    tournament_id: int,
    seed_number: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    require_tournament_manager(tournament_id, db, current_user)
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number
    ).first()
    
    name = data.get("name")
    icon_url = data.get("icon_url")
    previous_icon_url = player.icon_url if player else None
    
    if not player:
        player = models.Player(
            tournament_id=tournament_id,
            seed_number=seed_number,
            name=name or f"Player {seed_number}",
            icon_url=icon_url
        )
        db.add(player)
    else:
        if name: player.name = name
        if icon_url: player.icon_url = icon_url
    
    db.commit()
    db.refresh(player)
    cleanup_replaced_player_icon(db, player.id, previous_icon_url, player.icon_url)
    return player

@app.post("/api/tournaments/{tournament_id}/teams")
async def save_teams(
    tournament_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    require_tournament_manager(tournament_id, db, current_user)
    temporary_crop_urls = [
        character.get("image_url")
        for team in data.get("teams", [])
        for character in team.get("characters", [])
    ]
    try:
        seed_number = data.get("seed_number")
        teams = data.get("teams", [])
        player_name = data.get("player_name")
        player_icon_url = data.get("player_icon_url")
        
        is_update = False  # 上書きフラグ
        
        player = db.query(models.Player).filter(
            models.Player.tournament_id == tournament_id,
            models.Player.seed_number == seed_number
        ).first()
        # 編成登録前の icon_url を記録（上書き防止のため）
        previous_icon_url = player.icon_url if player else None

        if not player:
            # Player が存在しない場合は新規作成
            # icon_url はフロントから送られた場合のみ設定（なければ None のまま）
            player = models.Player(
                tournament_id=tournament_id,
                seed_number=seed_number,
                name=player_name or f"Player {seed_number}",
                icon_url=player_icon_url or None,
            )
            db.add(player)
            db.commit()
            db.refresh(player)
            print(f"[save_teams] 新規プレイヤー登録: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")
        else:
            # 既存 Player 更新
            if player_name:
                player.name = player_name
            # icon_url は player_icon_url が明示的に送られた場合のみ更新する。
            # 顔画像先行登録で既に icon_url が設定済みの場合は上書きしない。
            if player_icon_url:
                player.icon_url = player_icon_url
            db.commit()
            print(f"[save_teams] 既存プレイヤー更新: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")
        cleanup_replaced_player_icon(
            db,
            player.id,
            previous_icon_url,
            player.icon_url,
        )

        # 重複キャラクターのバリデーション
        all_char_ids = []
        unresolved_slots = []
        if len(teams) != 5:
            raise HTTPException(status_code=400, detail="編成は5ラウンド分必要です")

        for team_index, team_data in enumerate(teams, start=1):
            chars = team_data.get("characters", [])
            team_number = team_data.get("team_number") or team_index
            for slot_index in range(1, 6):
                c = chars[slot_index - 1] if slot_index <= len(chars) else {}
                cid = c.get("id")
                try:
                    cid = int(cid) if cid else None
                except (ValueError, TypeError):
                    cid = None
                if cid is None:
                    unresolved_slots.append(f"R{team_number}・{slot_index}人目")
                if cid is not None and cid != 9999:
                    all_char_ids.append(cid)

        if unresolved_slots:
            raise HTTPException(
                status_code=400,
                detail="不明のキャラクターが残っています: " + "、".join(unresolved_slots),
            )
        
        if len(all_char_ids) != len(set(all_char_ids)):
            raise HTTPException(status_code=400, detail="同じキャラクターを複数の部隊に編成することはできません")

        # 既存の編成データを削除（関連する DeckTeam を先に消す必要がある）
        existing_sets = db.query(models.DeckSet).filter(models.DeckSet.player_id == player.id).all()
        if existing_sets:
            is_update = True
            deleted_count = len(existing_sets)
            for es in existing_sets:
                db.query(models.DeckTeam).filter(models.DeckTeam.deck_set_id == es.id).delete()
                db.delete(es)
            db.commit()
            print(f"[save_teams] 古い編成データを {deleted_count} 件削除しました（上書き登録）: player_id={player.id}")
        
        deck_set = models.DeckSet(player_id=player.id)
        db.add(deck_set)
        db.commit()
        db.refresh(deck_set)
        
        template_dir = "uploads/templates"
        os.makedirs(template_dir, exist_ok=True)
        templates_added = 0
        
        for team_data in teams:
            chars = team_data.get("characters", [])
            char_ids = []
            for c in chars:
                cid = c.get("id")
                if cid == "" or cid is None:
                    char_ids.append(None)
                else:
                    try:
                        char_ids.append(int(cid))
                    except (ValueError, TypeError):
                        char_ids.append(None)
            # Pad to 5
            char_ids = (char_ids + [None]*5)[:5]
            
            deck_team = models.DeckTeam(
                deck_set_id=deck_set.id,
                team_number=team_data.get("team_number"),
                char1_id=char_ids[0],
                char2_id=char_ids[1],
                char3_id=char_ids[2],
                char4_id=char_ids[3],
                char5_id=char_ids[4]
            )
            db.add(deck_team)
            
            # 解析時に不明だった画像を人が補正した場合だけ自動学習する。
            for char_info in chars:
                if char_info.get("add_to_templates") is not True:
                    continue
                c_id = char_info.get("id")
                image_url = char_info.get("image_url")
                if c_id and image_url and image_url.startswith("/api/"):
                    # URLからローカルパスへ変換
                    local_path = image_url.replace("/api/", "")
                    if os.path.exists(local_path):
                        import shutil, cv2 as _cv2
                        # このキャラの既存テンプレートを収集（旧形式 char_{id}.png も含む）
                        existing = sorted([
                            f for f in os.listdir(template_dir)
                            if f.startswith(f"char_{c_id}_") or f == f"char_{c_id}.png"
                        ])
                        # 重複チェック: 平均絶対差分で類似度を計算
                        new_img = _cv2.imread(local_path, _cv2.IMREAD_GRAYSCALE)
                        is_duplicate = False
                        if new_img is not None:
                            for ef in existing:
                                ex_path = os.path.join(template_dir, ef)
                                ex_img = _cv2.imread(ex_path, _cv2.IMREAD_GRAYSCALE)
                                if ex_img is None:
                                    continue
                                try:
                                    h, w = new_img.shape[:2]
                                    ex_resized = _cv2.resize(ex_img, (w, h))
                                    diff = _cv2.absdiff(new_img, ex_resized)
                                    similarity = 1.0 - (diff.mean() / 255.0)
                                    if similarity > 0.92:  # 92%以上一致なら重複
                                        is_duplicate = True
                                        break
                                except Exception:
                                    pass
                        if not is_duplicate:
                            next_num = len(existing) + 1
                            template_path = os.path.join(template_dir, f"char_{c_id}_{next_num:03d}.png")
                            shutil.copy(local_path, template_path)
                            templates_added += 1
                            print(f"[Template] 追加: {template_path}（累計 {next_num} 枚）")
                        else:
                            print(f"[Template] スキップ（重複）: char_{c_id}")
                        # DB上のフラグを更新
                        char_db = db.query(models.Character).filter(models.Character.id == c_id).first()
                        if char_db:
                            char_db.is_template_available = True
                            if not getattr(char_db, "template_filename", None):
                                char_db.template_filename = f"char_{c_id}_{next_num:03d}.png"

        
        db.commit()
        deleted_crops = delete_temporary_crop_urls(temporary_crop_urls)
        if deleted_crops:
            print(f"[Cleanup] Removed {deleted_crops} registered crop images")
        return {
            "ok": True,
            "is_update": is_update,
            "templates_added": templates_added,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in save_teams: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/player-icon")
async def upload_player_icon(
    image: UploadFile = File(...),
    tournament_id: int = Form(...),
    seed_number: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    """
    プレイヤー顔アイコンを永続保存先に保存し、players.icon_url をDBに保存する。

    Player が存在しない場合は自動作成する（顔画像先行登録ユースケースに対応）。
    保存先: uploads/player_icons/tournament_{tournament_id}/seed_{seed_number}.png

    同一大会・同一シードを同時アップロードした場合は後勝ち（上書き）。
    異なる大会間でパスが衝突することはない。
    """
    # バリデーション
    if tournament_id <= 0 or seed_number <= 0:
        raise HTTPException(status_code=422, detail="tournament_id と seed_number は正の整数である必要があります")

    # 権限チェック：admin または大会作成者のみ操作可能
    require_tournament_manager(tournament_id, db, current_user)

    # tournament_id + seed_number で Player を検索し、存在しなければ自動作成
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number,
    ).first()
    if not player:
        # 顔画像先行登録：Player を自動作成（名前はデフォルト、後から編成登録時に更新可能）
        player = models.Player(
            tournament_id=tournament_id,
            seed_number=seed_number,
            name=f"Player {seed_number}",
        )
        db.add(player)
        db.flush()  # player.id を確定させるため flush（commit 前）
        print(f"[PlayerIcon] Player 自動作成: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")

    # 永続保存先ディレクトリを作成
    icon_dir = PLAYER_ICONS_DIR / f"tournament_{tournament_id}"
    icon_dir.mkdir(parents=True, exist_ok=True)

    filename = f"seed_{seed_number}.png"
    file_path = icon_dir / filename
    icon_url = f"/api/uploads/player_icons/tournament_{tournament_id}/seed_{seed_number}.png"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # DB の players.icon_url を更新してコミット
        player.icon_url = icon_url
        db.commit()
        db.refresh(player)
    except Exception as e:
        db.rollback()
        # 保存途中のファイルがあれば削除
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
        print(f"[PlayerIcon] 保存失敗: {e}")
        raise HTTPException(status_code=500, detail="顔画像の保存中にエラーが発生しました")

    print(f"[PlayerIcon] 保存完了: {file_path} → {icon_url} (player_id={player.id})")
    return {"url": icon_url, "player_id": player.id}

@app.post("/api/analyze/deck")
async def analyze_deck(request: Request):
    # Starlette 1.x ではマルチパートの1パートあたりデフォルト1MBの制限がある。
    # PC/タブレットのスクリーンショットは1MBを超える場合があるため、
    # Request.form() を直接使用して max_part_size を 20MB に引き上げる。
    MAX_PART_SIZE = 20 * 1024 * 1024  # 20MB per file
    form = await request.form(max_files=20, max_fields=20, max_part_size=MAX_PART_SIZE)

    try:
        tournament_id = int(form["tournament_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=422, detail="tournament_id が不正です")
    try:
        seed_number = int(form["seed_number"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=422, detail="seed_number が不正です")

    images = form.getlist("images")
    if not images:
        raise HTTPException(status_code=422, detail="images が指定されていません")

    saved_paths = []
    try:
        for idx, image in enumerate(images):
            original_name = Path(image.filename or "deck.png").name
            file_location = (
                f"{UPLOAD_DIR}/tour_{tournament_id}_seed_{seed_number}"
                f"_img_{idx}_{original_name}"
            )
            saved_paths.append(file_location)
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)

        try:
            return process_images(saved_paths, tournament_id, seed_number)
        except Exception as e:
            import traceback
            print(f"[analyze_deck] process_images でエラーが発生しました: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in saved_paths:
            delete_upload_file(path)

@app.post("/api/analyze/match_result")
async def analyze_match_result(
    tournament_id: int = Form(...),
    attacker_seed: int = Form(...),
    defender_seed: int = Form(...),
    stage: str = Form("Groups"),
    image: UploadFile = File(...)
):
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"match_t{tournament_id}_a{attacker_seed}_d{defender_seed}.png")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
        
    try:
        from services.match_processor import extract_match_results
        result = extract_match_results(file_path)
        
        resp = {
            "tournament_id": tournament_id,
            "attacker_seed": attacker_seed,
            "defender_seed": defender_seed,
            "stage": stage,
            "rounds": result["rounds"],
            "winner": result["winner"]
        }
        return resp
    except Exception as e:
        print(f"Error extracting match results: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        delete_upload_file(file_path)

@app.get("/api/tournaments/{tournament_id}/bracket")
def get_tournament_bracket(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_tournament_viewer(tournament_id, db, current_user)
    # 全プレイヤーと試合結果を取得
    players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()
    player_by_seed = {p.seed_number: p for p in players}
    matches = db.query(models.Match).filter(models.Match.tournament_id == tournament_id).all()
    
    def get_winner(p1_id, p2_id):
        if not p1_id or not p2_id:
            return None
        for m in matches:
            if m.winner_id:
                if (m.attacker_id == p1_id and m.defender_id == p2_id) or \
                   (m.attacker_id == p2_id and m.defender_id == p1_id):
                    return m.winner_id
        return None

    groups = []
    champion_seeds = [None] * 8
    
    for g_idx in range(8):
        base_seed = g_idx * 8
        
        # Best 64 (各グループの1回戦)
        qf_winners = []
        group_players = []
        for i in range(4):
            s1 = base_seed + i*2 + 1
            s2 = base_seed + i*2 + 2
            p1 = player_by_seed.get(s1)
            p2 = player_by_seed.get(s2)
            p1_id = p1.id if p1 else None
            p2_id = p2.id if p2 else None
            
            group_players.append({
                "seed": s1, "id": p1_id, "name": p1.name if p1 else f"Player {s1}",
                "icon_url": p1.icon_url if p1 else None,
                "has_deck": len(p1.deck_sets) > 0 if p1 else False
            })
            group_players.append({
                "seed": s2, "id": p2_id, "name": p2.name if p2 else f"Player {s2}",
                "icon_url": p2.icon_url if p2 else None,
                "has_deck": len(p2.deck_sets) > 0 if p2 else False
            })
            
            w_id = get_winner(p1_id, p2_id)
            qf_winners.append(w_id)
            
        # Best 32 (各グループの準決勝)
        sf_winners = []
        for i in range(2):
            w1 = qf_winners[i*2]
            w2 = qf_winners[i*2 + 1]
            sf_winners.append(get_winner(w1, w2))
            
        # Best 16 (各グループの決勝)
        group_winner = get_winner(sf_winners[0], sf_winners[1])
        champion_seeds[g_idx] = group_winner
        
        groups.append({
            "group_id": g_idx + 1,
            "players": group_players,
            "qf_winners": qf_winners,
            "sf_winners": sf_winners,
            "winner": group_winner
        })
        
    # チャンピオン対抗戦
    champ_qf_winners = []
    for i in range(4):
        w1 = champion_seeds[i*2]
        w2 = champion_seeds[i*2 + 1]
        champ_qf_winners.append(get_winner(w1, w2))
        
    champ_sf_winners = []
    for i in range(2):
        w1 = champ_qf_winners[i*2]
        w2 = champ_qf_winners[i*2 + 1]
        champ_sf_winners.append(get_winner(w1, w2))
        
    champ_winner = get_winner(champ_sf_winners[0], champ_sf_winners[1])
    
    def get_p_info(pid, seed_num):
        if not pid: 
            return {"seed": seed_num, "id": None, "name": "未確定", "has_deck": False}
        p = next((p for p in players if p.id == pid), None)
        if not p:
            return {"seed": seed_num, "id": None, "name": "未確定", "has_deck": False}
        return {
            "seed": seed_num, 
            "id": p.id, 
            "name": p.name, 
            "original_seed": p.seed_number,
            "icon_url": p.icon_url,
            "has_deck": len(p.deck_sets) > 0
        }
        
    champ_players = [get_p_info(champion_seeds[i], i+1) for i in range(8)]
    
    return {
        "groups": groups,
        "champion_finals": {
            "players": champ_players,
            "qf_winners": champ_qf_winners,
            "sf_winners": champ_sf_winners,
            "winner": champ_winner
        }
    }

@app.post("/api/tournaments/{tournament_id}/matches")
async def save_match(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    require_tournament_manager(tournament_id, db, current_user)
    data = await request.json()
    attacker_seed = data.get("attacker_seed")
    defender_seed = data.get("defender_seed")
    rounds = data.get("rounds")
    winner = data.get("winner")
    
    attacker = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == attacker_seed
    ).first()
    
    defender = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == defender_seed
    ).first()
    
    if not attacker or not defender:
        raise HTTPException(status_code=400, detail="両方のプレイヤーが編成登録されている必要があります。")
        
    winner_player = attacker if winner == "left" else defender
    
    # 既存のマッチがあれば削除（攻守逆のケースも含む）
    existing_matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id,
        ((models.Match.attacker_id == attacker.id) & (models.Match.defender_id == defender.id)) |
        ((models.Match.attacker_id == defender.id) & (models.Match.defender_id == attacker.id))
    ).all()
    
    for em in existing_matches:
        db.query(models.RoundResult).filter(models.RoundResult.match_id == em.id).delete()
        db.delete(em)
    
    match = models.Match(
        tournament_id=tournament_id,
        stage=data.get("stage", "Groups"),
        attacker_id=attacker.id,
        defender_id=defender.id,
        winner_id=winner_player.id
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    
    for r in rounds:
        round_winner = attacker if r["left"] == "WIN" else defender
        rr = models.RoundResult(
            match_id=match.id,
            round_number=r["round"],
            winner_id=round_winner.id
        )
        db.add(rr)
        
    db.commit()
    return {"ok": True}



@app.post("/api/tournaments/{tournament_id}/snapshot/rebuild")
def rebuild_tournament_snapshot(
    tournament_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    """管理者が手動でスナップショットを再生成する"""
    if current_user.role not in ("admin", "contributor"):
        raise HTTPException(status_code=403, detail="管理者のみ実行できます")
    tournament = db.query(models.Tournament).filter(
        models.Tournament.id == tournament_id
    ).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="大会が見つかりません")
    background_tasks.add_task(recompute_snapshot, tournament_id, current_user.id)
    return {"ok": True, "message": f"tournament_id={tournament_id} のスナップショット再生成を開始しました"}

@app.get("/api/tournaments/{tournament_id}/dashboard/stats")
def get_dashboard_stats(
    tournament_id: int,
    seed: int = None,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    stats = _compute_dashboard_stats(tournament_id, db, current_user, seed)
    if "team_usage" in stats:
        stats["team_usage"] = stats["team_usage"][:50]
    return stats




# ===== スナップショット管理 =====

def save_snapshot(tournament_id: int, stats: dict, db: Session):
    """_compute_dashboard_stats の結果を tournament_snapshots テーブルに保存する"""
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if snap is None:
        snap = models.TournamentSnapshot(tournament_id=tournament_id)
        db.add(snap)
    snap.team_usage    = stats.get("team_usage", [])
    snap.char_stats    = stats.get("character_stats", [])
    snap.matchups      = stats.get("matchups", [])
    snap.total_players = stats.get("total_players")
    snap.total_matches = stats.get("total_matches")
    db.commit()

    print("[snapshot saved] tournament_id:", tournament_id)
    print("[snapshot saved] total_players:", snap.total_players)
    print("[snapshot saved] total_matches:", snap.total_matches)
    print("[snapshot saved] char_stats len:", len(snap.char_stats or []))
    print("[snapshot saved] team_usage len:", len(snap.team_usage or []))



def delete_snapshot(tournament_id: int):
    """BackgroundTasks から呼ばれる。自前でDBセッションを作成・破棄する。"""
    db = SessionLocal()
    try:
        snap = db.query(models.TournamentSnapshot).filter(models.TournamentSnapshot.tournament_id == tournament_id).first()
        if snap:
            db.delete(snap)
            db.commit()
    except Exception as e:
        print(f"[delete_snapshot] ERROR tournament_id={tournament_id}: {e}")
    finally:
        db.close()

def recompute_snapshot(tournament_id: int, user_id: int):
    """BackgroundTasks から呼ばれる。自前でDBセッションを作成・破棄する。"""
    db = SessionLocal()
    try:
        user = db.query(models.AppUser).filter(models.AppUser.id == user_id).first()
        stats = _compute_dashboard_stats(tournament_id, db, user)
        save_snapshot(tournament_id, stats, db)
    except Exception as e:
        print(f"[recompute_snapshot] ERROR tournament_id={tournament_id}: {e}")
    finally:
        db.close()

def _compute_dashboard_stats(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None = None,
    seed: int = None,
):
    require_tournament_viewer(tournament_id, db, current_user)
    query = db.query(models.Player).filter(models.Player.tournament_id == tournament_id)
    if seed:
        query = query.filter(models.Player.seed_number == seed)
    
    players = query.all()
    player_ids = [p.id for p in players]
    
    deck_sets = db.query(models.DeckSet).filter(models.DeckSet.player_id.in_(player_ids)).all()
    deck_set_ids = [ds.id for ds in deck_sets]
    ds_to_player = {ds.id: ds.player_id for ds in deck_sets}
    
    deck_teams = db.query(models.DeckTeam).filter(models.DeckTeam.deck_set_id.in_(deck_set_ids)).all()
    
    char_usage = {}
    char_position = {}  # {char_id: {1: count, 2: count, ..., 5: count}}
    char_team_position = {} # {char_id: {1: {"count":0, "wins":0, "total":0, "players":set()}, ..., 5: ...}}
    team_usage = {}
    
    for team in deck_teams:
        chars = [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]
        chars_valid = [c for c in chars if c is not None]
        
        for c_id in chars_valid:
            if c_id == 9999:
                continue
            char_usage[c_id] = char_usage.get(c_id, 0) + 1
            if c_id not in char_team_position:
                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
            t_pos = getattr(team, "team_number", 0)
            if 1 <= t_pos <= 5:
                char_team_position[c_id][t_pos]["count"] += 1
                pid = ds_to_player.get(team.deck_set_id)
                if pid:
                    char_team_position[c_id][t_pos]["players"].add(pid)
        
        # 配置順の集計（1-indexed）
        for pos_idx, c_id in enumerate(chars):
            if c_id is not None and c_id != 9999:
                if c_id not in char_position:
                    char_position[c_id] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                char_position[c_id][pos_idx + 1] += 1
            
        if len(chars_valid) == 5:
            sorted_chars = tuple(sorted(chars_valid))
            if sorted_chars not in team_usage:
                team_usage[sorted_chars] = {
                    "count": 0, 
                    "original_order": chars_valid,
                    "position_stats": {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                }
            team_usage[sorted_chars]["count"] += 1
            t_pos = getattr(team, "team_number", 0)
            if 1 <= t_pos <= 5:
                team_usage[sorted_chars]["position_stats"][t_pos]["count"] += 1
                pid = ds_to_player.get(team.deck_set_id)
                if pid:
                    team_usage[sorted_chars]["position_stats"][t_pos]["players"].add(pid)

    # 勝敗集計用のデータ
    matches = db.query(models.Match).filter(models.Match.tournament_id == tournament_id).all()
    char_match_stats = {} # {char_id: {"wins": 0, "total": 0}}
    team_match_stats = {} # {canonical_id: {"wins": 0, "total": 0}}
    char_position_match_stats = {} # {char_id: {pos: {"wins": 0, "total": 0}}}

    for match in matches:
        attacker_id = match.attacker_id
        defender_id = match.defender_id
        
        # プレイヤーの編成セットを取得
        attacker_ds = db.query(models.DeckSet).filter(models.DeckSet.player_id == attacker_id).first()
        defender_ds = db.query(models.DeckSet).filter(models.DeckSet.player_id == defender_id).first()
        
        if not attacker_ds or not defender_ds:
            continue
            
        a_teams = {t.team_number: t for t in attacker_ds.teams}
        d_teams = {t.team_number: t for t in defender_ds.teams}
        
        for rr in match.round_results:
            rn = rr.round_number
            winner_id = rr.winner_id
            
            a_team = a_teams.get(rn)
            d_team = d_teams.get(rn)
            
            if a_team and d_team:
                # キャラクターIDのリスト抽出
                a_chars = [c for c in [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id] if c is not None]
                d_chars = [c for c in [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id] if c is not None]
                
                is_a_win = winner_id == attacker_id
                is_d_win = winner_id == defender_id
                
                # キャラクター統計更新
                for c_id in a_chars:
                    if c_id == 9999: continue
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_a_win: char_match_stats[c_id]["wins"] += 1
                for c_id in d_chars:
                    if c_id == 9999: continue
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_d_win: char_match_stats[c_id]["wins"] += 1
                
                # ポジション別勝敗集計
                a_all = [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id]
                d_all = [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id]
                for pos_idx, c_id in enumerate(a_all):
                    if c_id is not None and c_id != 9999:
                        pos = pos_idx + 1
                        if c_id not in char_position_match_stats:
                            char_position_match_stats[c_id] = {p: {"wins": 0, "total": 0} for p in range(1, 6)}
                        char_position_match_stats[c_id][pos]["total"] += 1
                        if is_a_win: char_position_match_stats[c_id][pos]["wins"] += 1
                        
                        a_t_pos = getattr(a_team, "team_number", 0)
                        if 1 <= a_t_pos <= 5:
                            if c_id not in char_team_position:
                                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                            char_team_position[c_id][a_t_pos]["total"] += 1
                            if is_a_win: char_team_position[c_id][a_t_pos]["wins"] += 1

                for pos_idx, c_id in enumerate(d_all):
                    if c_id is not None and c_id != 9999:
                        pos = pos_idx + 1
                        if c_id not in char_position_match_stats:
                            char_position_match_stats[c_id] = {p: {"wins": 0, "total": 0} for p in range(1, 6)}
                        char_position_match_stats[c_id][pos]["total"] += 1
                        if is_d_win: char_position_match_stats[c_id][pos]["wins"] += 1

                        d_t_pos = getattr(d_team, "team_number", 0)
                        if 1 <= d_t_pos <= 5:
                            if c_id not in char_team_position:
                                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                            char_team_position[c_id][d_t_pos]["total"] += 1
                            if is_d_win: char_team_position[c_id][d_t_pos]["wins"] += 1
                    
                # 編成統計更新
                if len(a_chars) == 5:
                    a_canon = ",".join(map(str, sorted(a_chars)))
                    if a_canon not in team_match_stats: team_match_stats[a_canon] = {"wins": 0, "total": 0}
                    team_match_stats[a_canon]["total"] += 1
                    if is_a_win: team_match_stats[a_canon]["wins"] += 1
                    
                    a_tup = tuple(sorted(a_chars))
                    if a_tup in team_usage and getattr(a_team, "team_number", 0) and 1 <= a_team.team_number <= 5:
                        team_usage[a_tup]["position_stats"][a_team.team_number]["total"] += 1
                        if is_a_win: team_usage[a_tup]["position_stats"][a_team.team_number]["wins"] += 1

                if len(d_chars) == 5:
                    d_canon = ",".join(map(str, sorted(d_chars)))
                    if d_canon not in team_match_stats: team_match_stats[d_canon] = {"wins": 0, "total": 0}
                    team_match_stats[d_canon]["total"] += 1
                    if is_d_win: team_match_stats[d_canon]["wins"] += 1
                    
                    d_tup = tuple(sorted(d_chars))
                    if d_tup in team_usage and getattr(d_team, "team_number", 0) and 1 <= d_team.team_number <= 5:
                        team_usage[d_tup]["position_stats"][d_team.team_number]["total"] += 1
                        if is_d_win: team_usage[d_tup]["position_stats"][d_team.team_number]["wins"] += 1

    # ============================================================
    # 各プレイヤーの最終成績を計算する
    # ============================================================
    all_players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()
    all_matches = db.query(models.Match).filter(models.Match.tournament_id == tournament_id).all()
    player_by_id = {p.id: p for p in all_players}

    # player_id -> 成績スコア（小さいほど良い）と成績文字列


    def get_winner_between(pid1, pid2):
        """2人のプレイヤー間の試合勝者IDを返す"""
        for m in all_matches:
            if m.winner_id and (
                (m.attacker_id == pid1 and m.defender_id == pid2) or
                (m.attacker_id == pid2 and m.defender_id == pid1)
            ):
                return m.winner_id
        return None

    def calc_player_result(player_id):
        """player_id の最終成績文字列を返す"""
        # 1. グループ内ステージを追う（シード番号からグループを特定）
        p = player_by_id.get(player_id)
        if not p or p.seed_number is None:
            return "ベスト64"

        g_idx = (p.seed_number - 1) // 8
        base_seed = g_idx * 8

        group_all = [player_by_id.get(all_players_in_grp.id)
                     for all_players_in_grp in all_players
                     if all_players_in_grp.seed_number is not None
                     and (all_players_in_grp.seed_number - 1) // 8 == g_idx]

        # Best64 : グループの1回戦(4試合)
        qf_winners = []
        for i in range(4):
            s1 = base_seed + i * 2 + 1
            s2 = base_seed + i * 2 + 2
            p1 = next((x for x in all_players if x.seed_number == s1 and x.tournament_id == tournament_id), None)
            p2 = next((x for x in all_players if x.seed_number == s2 and x.tournament_id == tournament_id), None)
            w = get_winner_between(p1.id if p1 else None, p2.id if p2 else None)
            qf_winners.append(w)

        if player_id not in qf_winners:
            return "ベスト64"

        # Best32 : グループ準決勝
        sf_winners = []
        for i in range(2):
            w = get_winner_between(qf_winners[i * 2], qf_winners[i * 2 + 1])
            sf_winners.append(w)

        if player_id not in sf_winners:
            return "ベスト32"

        # Best16 : グループ決勝
        group_winner = get_winner_between(sf_winners[0], sf_winners[1])
        if player_id != group_winner:
            return "ベスト16"

        # Best8 : チャンピオン対抗戦（各グループ優勝者8名）
        # グループ優勝者を収集
        group_winners = []
        for gi in range(8):
            base = gi * 8
            qf_w = []
            for i in range(4):
                s1 = base + i * 2 + 1
                s2 = base + i * 2 + 2
                p1 = next((x for x in all_players if x.seed_number == s1 and x.tournament_id == tournament_id), None)
                p2 = next((x for x in all_players if x.seed_number == s2 and x.tournament_id == tournament_id), None)
                w = get_winner_between(p1.id if p1 else None, p2.id if p2 else None)
                qf_w.append(w)
            sf_w = []
            for i in range(2):
                w = get_winner_between(qf_w[i * 2], qf_w[i * 2 + 1])
                sf_w.append(w)
            gw = get_winner_between(sf_w[0], sf_w[1])
            group_winners.append(gw)

        champ_qf_winners = []
        for i in range(4):
            w = get_winner_between(group_winners[i * 2], group_winners[i * 2 + 1])
            champ_qf_winners.append(w)

        if player_id not in champ_qf_winners:
            return "ベスト8"

        champ_sf_winners = []
        for i in range(2):
            w = get_winner_between(champ_qf_winners[i * 2], champ_qf_winners[i * 2 + 1])
            champ_sf_winners.append(w)

        if player_id not in champ_sf_winners:
            return "ベスト4"

        champ_winner = get_winner_between(champ_sf_winners[0], champ_sf_winners[1])
        if player_id != champ_winner:
            return "準優勝"

        return "優勝"

    # キャラIDをプレイヤーにマッピング
    # {char_id: set(player_id)}
    char_to_players = {}
    for ds in db.query(models.DeckSet).filter(models.DeckSet.player_id.in_([p.id for p in all_players])).all():
        for team in ds.teams:
            for c_id in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]:
                if c_id is not None:
                    if c_id not in char_to_players:
                        char_to_players[c_id] = set()
                    char_to_players[c_id].add(ds.player_id)

    # 各プレイヤーの成績を一度だけ計算してキャッシュ
    player_result_cache = {}
    for pid in set(p for pids in char_to_players.values() for p in pids):
        player_result_cache[pid] = calc_player_result(pid)

    def get_best_result_for_char(c_id):
        """そのキャラを使ったプレイヤーの中で最も良い成績を返す"""
        user_ids = char_to_players.get(c_id, set())
        if not user_ids:
            return None
        best_score = 999
        best_result = "ベスト64"
        for pid in user_ids:
            result = player_result_cache.get(pid, "ベスト64")
            score = RESULT_SCORES.get(result, 64)
            if score < best_score:
                best_score = score
                best_result = result
        return best_result

    # ============================================================
    char_list = []
    for c_id, count in char_usage.items():
        char = db.query(models.Character).filter(models.Character.id == c_id).first()
        if char:
            m_stats = char_match_stats.get(c_id, {"wins": 0, "total": 0})
            win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else 0
            # 配置順統計
            pos_data = char_position.get(c_id, {1:0, 2:0, 3:0, 4:0, 5:0})
            pos_match = char_position_match_stats.get(c_id, {})
            position_stats = []
            for p in range(1, 6):
                p_count = pos_data.get(p, 0)
                p_ms = pos_match.get(p, {"wins": 0, "total": 0})
                p_wr = round(p_ms["wins"] / p_ms["total"] * 100, 1) if p_ms["total"] > 0 else None
                position_stats.append({
                    "position": p,
                    "count": p_count,
                    "pct": round(p_count / count * 100, 1) if count > 0 else 0,
                    "wins": p_ms["wins"],
                    "total": p_ms["total"],
                    "win_rate": p_wr
                })
            t_pos_data = char_team_position.get(c_id, {})
            team_position_stats = []
            for p in range(1, 6):
                p_ms = t_pos_data.get(p, {"count": 0, "wins": 0, "total": 0, "players": set()})
                p_count = p_ms["count"]
                p_wr = round(p_ms["wins"] / p_ms["total"] * 100, 1) if p_ms["total"] > 0 else None
                
                best_res = None
                if p_ms["players"]:
                    scores = []
                    for pid in p_ms["players"]:
                        res_str = player_result_cache.get(pid, "ベスト64")
                        scores.append((RESULT_SCORES.get(res_str, 999), res_str))
                    if scores:
                        best_res = min(scores, key=lambda x: x[0])[1]
                
                team_position_stats.append({
                    "position": p,
                    "count": p_count,
                    "pct": round(p_count / count * 100, 1) if count > 0 else 0,
                    "wins": p_ms["wins"],
                    "total": p_ms["total"],
                    "win_rate": p_wr,
                    "best_result": best_res
                })
                
            char_list.append({
                "id": char.id,
                "name": char.name,
                "rarity": char.rarity,
                "count": count,
                "win_count": m_stats["wins"],
                "total_matches": m_stats["total"],
                "win_rate": round(win_rate, 1),
                "best_result": get_best_result_for_char(c_id),
                "position_stats": position_stats,
                "team_position_stats": team_position_stats
            })
    char_list.sort(key=lambda x: x["count"], reverse=True)
    
    team_list = []
    for sorted_chars, data in team_usage.items():
        count = data["count"]
        original_order = data["original_order"]
        team_chars = []
        for c_id in original_order:
            char = db.query(models.Character).filter(models.Character.id == c_id).first()
            if char:
                team_chars.append({"id": char.id, "name": char.name, "rarity": char.rarity})
        
        canon_id = ",".join(map(str, sorted_chars))
        m_stats = team_match_stats.get(canon_id, {"wins": 0, "total": 0})
        win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else 0

        pos_stats_out = []
        for p in range(1, 6):
            ps = data["position_stats"][p]
            best_res = None
            if ps["players"]:
                scores = []
                for pid in ps["players"]:
                    res_str = player_result_cache.get(pid, "ベスト64")
                    scores.append((RESULT_SCORES.get(res_str, 999), res_str))
                if scores:
                    best_res = min(scores, key=lambda x: x[0])[1]
            pos_stats_out.append({
                "position": p,
                "count": ps["count"],
                "pct": round(ps["count"] / count * 100, 1) if count > 0 else 0,
                "wins": ps["wins"],
                "total": ps["total"],
                "win_rate": round(ps["wins"] / ps["total"] * 100, 1) if ps["total"] > 0 else None,
                "best_result": best_res
            })

        # この編成を使ったプレイヤーの最良成績を計算
        team_char_set = set(sorted_chars)
        team_player_ids = set()
        for ds in db.query(models.DeckSet).filter(models.DeckSet.player_id.in_([p.id for p in all_players])).all():
            for team in ds.teams:
                team_ids = set(c for c in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id] if c is not None)
                if team_ids == team_char_set:
                    team_player_ids.add(ds.player_id)
        
        best_team_score = 999
        best_team_result = "ベスト64"
        for pid in team_player_ids:
            result = player_result_cache.get(pid, "ベスト64")
            score = RESULT_SCORES.get(result, 64)
            if score < best_team_score:
                best_team_score = score
                best_team_result = result

        # この編成を採用したプレイヤー情報を収集
        adopted_players = []
        for pid in team_player_ids:
            player = db.query(models.Player).filter(models.Player.id == pid).first()
            if player:
                t = db.query(models.Tournament).filter(models.Tournament.id == player.tournament_id).first()
                adopted_players.append({
                    "player_name": player.name,
                    "tournament_name": t.name if t else "不明",
                    "tournament_id": player.tournament_id,
                    "result": player_result_cache.get(pid, "ベスト64")
                })
        # 成績順でソート（良い成績が先）
        adopted_players.sort(key=lambda x: RESULT_SCORES.get(x["result"], 64))

        team_list.append({
            "canonical_id": canon_id,
            "character_ids": original_order,
            "characters": team_chars,
            "count": count,
            "win_count": m_stats["wins"],
            "total_matches": m_stats["total"],
            "win_rate": round(win_rate, 1),
            "best_result": best_team_result if team_player_ids else None,
            "adopted_players": adopted_players,
            "position_stats": pos_stats_out
        })
    team_list.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "character_usage": char_list,
        "character_stats": char_list,
        "character_usage_by_result": _compute_character_usage_by_result([tournament_id], db),
        "team_usage": team_list,
        "total_players": len(player_ids),
        "total_matches": len(matches)
    }

@app.get("/api/tournaments/{tournament_id}/dashboard/matchups")
def get_dashboard_matchups(
    tournament_id: int,
    seed: int = None,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    query = db.query(models.Match).filter(models.Match.tournament_id == tournament_id)
    if seed:
        player = db.query(models.Player).filter(models.Player.tournament_id == tournament_id, models.Player.seed_number == seed).first()
        if player:
            query = query.filter(or_(models.Match.attacker_id == player.id, models.Match.defender_id == player.id))
        else:
            return {"matchups": []}

    matches = query.all()
    matchup_results = []
    
    for match in matches:
        attacker_ds = db.query(models.DeckSet).filter(models.DeckSet.player_id == match.attacker_id).first()
        defender_ds = db.query(models.DeckSet).filter(models.DeckSet.player_id == match.defender_id).first()
        
        if not attacker_ds or not defender_ds:
            continue
            
        attacker_teams = {t.team_number: t for t in attacker_ds.teams}
        defender_teams = {t.team_number: t for t in defender_ds.teams}
        
        for round_res in match.round_results:
            rn = round_res.round_number
            a_team = attacker_teams.get(rn)
            d_team = defender_teams.get(rn)
            
            if a_team and d_team:
                a_chars = [c for c in [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id] if c is not None]
                d_chars = [c for c in [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id] if c is not None]
                
                a_sorted = tuple(sorted(a_chars))
                d_sorted = tuple(sorted(d_chars))
                
                if len(a_chars) == 5 and len(d_chars) == 5:
                    winner_is_attacker = round_res.winner_id == match.attacker_id
                    
                    matchup_results.append({
                        "match_id": match.id,
                        "round_number": rn,
                        "stage": match.stage,
                        "attacker_team": list(a_chars),
                        "defender_team": list(d_chars),
                        "canonical_attacker": ",".join(map(str, a_sorted)),
                        "canonical_defender": ",".join(map(str, d_sorted)),
                        "winner_team": list(a_chars) if winner_is_attacker else list(d_chars),
                        "loser_team": list(d_chars) if winner_is_attacker else list(a_chars),
                        "winner_is_attacker": winner_is_attacker,
                        "tournament_name": match.tournament.name if match.tournament else "不明",
                        "tournament_id": match.tournament_id,
                        "attacker_name": match.attacker.name if match.attacker else "不明",
                        "defender_name": match.defender.name if match.defender else "不明"
                    })
                    
    return {"matchups": matchup_results}

@app.get("/api/tournaments/{tournament_id}/dashboard/best8-decks")
def get_best8_decks(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    """ベスト8進出者のプレイヤー名、成績、登録編成をまとめて取得する"""
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    bracket = get_tournament_bracket(tournament_id, db, current_user)
    best8_players = bracket["champion_finals"]["players"]
    champ_finals = bracket["champion_finals"]
    
    qf_winners = set(champ_finals["qf_winners"]) # ベスト4進出者
    sf_winners = set(champ_finals["sf_winners"]) # 決勝進出者
    winner_id = champ_finals["winner"]           # 優勝者
    
    results = []
    for p_info in best8_players:
        pid = p_info["id"]
        if pid:
            # 成績の判定
            result_label = "ベスト8"
            sort_score = 4
            if pid == winner_id:
                result_label = "優勝"
                sort_score = 1
            elif pid in sf_winners:
                result_label = "準優勝"
                sort_score = 2
            elif pid in qf_winners:
                result_label = "ベスト4"
                sort_score = 3
                
            # 既に定義済みの get_player_details を利用して編成を取得
            details = get_player_details(tournament_id, p_info["original_seed"], db)
            results.append({
                "player": p_info,
                "result": result_label,
                "sort_score": sort_score,
                "decks": details["decks"]
            })
        else:
            results.append({
                "player": p_info,
                "result": "ベスト8",
                "sort_score": 5,
                "decks": []
            })
            
    # 成績が良い順（sort_scoreの昇順）にソート
    results.sort(key=lambda x: x["sort_score"])
    
    return results


# ============================================================
# 大会横断検索 API
# ============================================================

from pydantic import BaseModel as PydanticBaseModel
def resolve_cross_tournament_ids(db, tournament_ids, play_server, championship_id):
    if not play_server or not championship_id:
        return tournament_ids if tournament_ids else []
    
    # 全ての有効な大会IDを取得
    valid_tournaments = db.query(models.Tournament.id).filter(
        models.Tournament.publication_status == "published",
        models.Tournament.play_server == play_server,
        models.Tournament.championship_id == championship_id
    ).all()
    valid_ids = {t[0] for t in valid_tournaments}
    
    if not tournament_ids:
        # 空の場合はスコープ内の全てを対象とする
        return list(valid_ids)
    
    # フィルタリング（スコープ外を除外）
    return [tid for tid in tournament_ids if tid in valid_ids]



def _merge_team_position_and_adopted(merged_teams, team, cid):
    if cid not in merged_teams:
        merged_teams[cid] = {
            **team,
            "count": 0,
            "win_count": 0,
            "total_matches": 0,
            "adopted_players": [],
            "position_stats": [
                {"position": p, "count": 0, "pct": 0.0, "wins": 0, "total": 0, "win_rate": None}
                for p in range(1, 6)
            ],
            "_seen_adopted": set()
        }
    target = merged_teams[cid]
    target["count"] += team.get("count", 0)
    target["win_count"] += team.get("win_count", 0)
    target["total_matches"] += team.get("total_matches", 0)
    
    cur_score = RESULT_SCORES.get(target.get("best_result", "不明"), 999)
    new_score = RESULT_SCORES.get(team.get("best_result", "不明"), 999)
    if new_score < cur_score:
        target["best_result"] = team.get("best_result")
        
    for p in (team.get("adopted_players") or []):
        if not isinstance(p, dict): continue
        pkey = (p.get("player_name"), p.get("tournament_id"), p.get("result"), p.get("seed"))
        if pkey not in target["_seen_adopted"]:
            target["_seen_adopted"].add(pkey)
            target["adopted_players"].append(p)
            
    pos_list = target["position_stats"]
    for ps in (team.get("position_stats") or []):
        if not isinstance(ps, dict): continue
        pos = ps.get("position")
        if isinstance(pos, int) and 1 <= pos <= 5:
            cur_ps = pos_list[pos - 1]
            cur_ps["count"] += ps.get("count", 0)
            cur_ps["wins"] += ps.get("wins", 0)
            cur_ps["total"] += ps.get("total", 0)

def _finalize_team_position_and_adopted(team):
    t_count = team.get("count", 0)
    for ps in team.get("position_stats", []):
        ps["pct"] = round(ps["count"] / t_count * 100, 1) if t_count > 0 else 0.0
        ps["win_rate"] = round(ps["wins"] / ps["total"] * 100, 1) if ps.get("total", 0) > 0 else None
    if "_seen_adopted" in team:
        del team["_seen_adopted"]
    if "adopted_players" in team and isinstance(team["adopted_players"], list):
        team["adopted_players"].sort(key=lambda x: RESULT_SCORES.get(x.get("result"), 64))


CHARACTER_USAGE_RESULT_FILTERS = (
    ("all", "全体", None),
    ("best16", "ベスト16以上", 16),
    ("best8", "ベスト8以上", 8),
    ("best4", "ベスト4以上", 4),
    ("runner_up", "準優勝以上", 2),
    ("champion", "優勝", 1),
)


def _compute_character_usage_by_result(tournament_ids: List[int], db: Session):
    """Aggregate unique character adoption per player, grouped by final result."""
    empty_result = {
        key: {"label": label, "denominator": 0, "characters": []}
        for key, label, _ in CHARACTER_USAGE_RESULT_FILTERS
    }
    if not tournament_ids:
        return empty_result

    players = db.query(models.Player).filter(
        models.Player.tournament_id.in_(tournament_ids)
    ).all()
    if not players:
        return empty_result

    player_ids = [player.id for player in players]
    matches = db.query(models.Match).filter(
        models.Match.tournament_id.in_(tournament_ids)
    ).all()
    deck_sets = db.query(models.DeckSet).filter(
        models.DeckSet.player_id.in_(player_ids)
    ).all()
    deck_set_ids = [deck_set.id for deck_set in deck_sets]
    deck_teams = db.query(models.DeckTeam).filter(
        models.DeckTeam.deck_set_id.in_(deck_set_ids)
    ).all() if deck_set_ids else []

    players_by_tournament = {}
    for player in players:
        players_by_tournament.setdefault(player.tournament_id, []).append(player)

    matches_by_tournament = {}
    for match in matches:
        matches_by_tournament.setdefault(match.tournament_id, []).append(match)

    result_score_by_player = {}
    for tournament_id, tournament_players in players_by_tournament.items():
        seed_to_player = {
            player.seed_number: player
            for player in tournament_players
            if player.seed_number is not None
        }
        winner_by_pair = {}
        for match in matches_by_tournament.get(tournament_id, []):
            if match.winner_id and match.attacker_id and match.defender_id:
                winner_by_pair[frozenset((match.attacker_id, match.defender_id))] = match.winner_id

        def winner_between(player_id_1, player_id_2):
            if not player_id_1 or not player_id_2:
                return None
            return winner_by_pair.get(frozenset((player_id_1, player_id_2)))

        group_rounds = []
        for group_index in range(8):
            base_seed = group_index * 8
            quarterfinal_winners = []
            for pair_index in range(4):
                player_1 = seed_to_player.get(base_seed + pair_index * 2 + 1)
                player_2 = seed_to_player.get(base_seed + pair_index * 2 + 2)
                quarterfinal_winners.append(winner_between(
                    player_1.id if player_1 else None,
                    player_2.id if player_2 else None,
                ))

            semifinal_winners = [
                winner_between(quarterfinal_winners[0], quarterfinal_winners[1]),
                winner_between(quarterfinal_winners[2], quarterfinal_winners[3]),
            ]
            group_winner = winner_between(semifinal_winners[0], semifinal_winners[1])
            group_rounds.append((quarterfinal_winners, semifinal_winners, group_winner))

        group_winners = [round_data[2] for round_data in group_rounds]
        best4_players = [
            winner_between(group_winners[0], group_winners[1]),
            winner_between(group_winners[2], group_winners[3]),
            winner_between(group_winners[4], group_winners[5]),
            winner_between(group_winners[6], group_winners[7]),
        ]
        finalists = [
            winner_between(best4_players[0], best4_players[1]),
            winner_between(best4_players[2], best4_players[3]),
        ]
        champion = winner_between(finalists[0], finalists[1])

        for player in tournament_players:
            score = 64
            if player.seed_number is not None:
                group_index = (player.seed_number - 1) // 8
                if 0 <= group_index < len(group_rounds):
                    quarterfinal_winners, semifinal_winners, group_winner = group_rounds[group_index]
                    if player.id in quarterfinal_winners:
                        score = 32
                    if player.id in semifinal_winners:
                        score = 16
                    if player.id == group_winner:
                        score = 8
                    if player.id in best4_players:
                        score = 4
                    if player.id in finalists:
                        score = 2
                    if player.id == champion:
                        score = 1
            result_score_by_player[player.id] = score

    deck_set_to_player = {deck_set.id: deck_set.player_id for deck_set in deck_sets}
    characters_by_player = {player_id: set() for player_id in player_ids}
    used_character_ids = set()
    for team in deck_teams:
        player_id = deck_set_to_player.get(team.deck_set_id)
        if not player_id:
            continue
        for character_id in (
            team.char1_id,
            team.char2_id,
            team.char3_id,
            team.char4_id,
            team.char5_id,
        ):
            if character_id is not None and character_id != EMPTY_SLOT_CHARACTER_ID:
                characters_by_player[player_id].add(character_id)
                used_character_ids.add(character_id)

    characters = db.query(models.Character).filter(
        models.Character.id.in_(used_character_ids)
    ).all() if used_character_ids else []
    character_by_id = {character.id: character for character in characters}

    result = {}
    all_player_ids = set(player_ids)
    for key, label, maximum_score in CHARACTER_USAGE_RESULT_FILTERS:
        eligible_player_ids = (
            all_player_ids
            if maximum_score is None
            else {
                player_id
                for player_id, score in result_score_by_player.items()
                if score <= maximum_score
            }
        )
        denominator = len(eligible_player_ids)
        adoption_counts = {}
        for player_id in eligible_player_ids:
            for character_id in characters_by_player.get(player_id, set()):
                adoption_counts[character_id] = adoption_counts.get(character_id, 0) + 1

        character_rows = []
        for character_id, count in adoption_counts.items():
            character = character_by_id.get(character_id)
            if not character:
                continue
            character_rows.append({
                "character_id": character_id,
                "id": character_id,
                "name": character.name,
                "count": count,
                "usage_rate": round(count / denominator * 100, 1) if denominator else 0.0,
            })
        character_rows.sort(key=lambda row: (-row["count"], row["character_id"]))
        result[key] = {
            "label": label,
            "denominator": denominator,
            "characters": character_rows,
        }

    return result


class CrossTournamentRequest(PydanticBaseModel):
    """大会横断検索リクエスト"""
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None


class CrossTournamentCharacterDetailRequest(PydanticBaseModel):
    character_id: int
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None


@app.post("/api/dashboard/cross-tournament/stats")
def get_cross_tournament_stats(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    if body.tournament_ids:
        target_ids = body.tournament_ids
    else:
        target_ids = resolve_cross_tournament_ids(
            db,
            body.tournament_ids,
            body.play_server,
            body.championship_id
        )

    print("[cross stats] body.tournament_ids:", body.tournament_ids)
    print("[cross stats] target_ids:", target_ids)

    snaps = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id.in_(target_ids)
    ).all() if target_ids else []

    if target_ids and len(snaps) == len(target_ids):
        print(f"[cross stats] using snapshots: {len(snaps)} / {len(target_ids)}")

        total_players = sum(s.total_players for s in snaps if s.total_players)
        total_matches = sum(s.total_matches for s in snaps if s.total_matches)
        
        merged_chars = {}
        merged_teams = {}
        
        for snap in snaps:
            print("[cross stats] snap total_players:", snap.total_players)
            print("[cross stats] snap total_matches:", snap.total_matches)
            print("[cross stats] snap char_stats len:", len(snap.char_stats or []))
            print("[cross stats] snap team_usage len:", len(snap.team_usage or []))
            # character_stats merging
            for char_stat in (snap.char_stats or []):
                cid = char_stat.get("id")
                if not cid: continue
                if cid not in merged_chars:
                    # Initialize with basic char info to preserve structure
                    merged_chars[cid] = {
                        "id": cid,
                        "name": char_stat.get("name"),
                        "rarity": char_stat.get("rarity"),
                        "count": 0,
                        "win_count": 0,
                        "total_matches": 0,
                        "best_result": char_stat.get("best_result", "不明"),
                        # We won't accurately merge nested position stats since they are complex, 
                        # but we can initialize them as empty if the frontend doesn't strictly need accurate position breakdown for cross-tournament top level.
                        # Wait, the prompt says "存在する数値項目を合算". So we will just sum the top level ones.
                        "position_stats": [],
                        "team_position_stats": [],
                        "_pos_map": {p: {"count": 0, "wins": 0, "total": 0} for p in range(1, 6)},
                        "_team_pos_map": {p: {"count": 0, "wins": 0, "total": 0, "best_result": None} for p in range(1, 6)}
                    }
                merged_chars[cid]["count"] += char_stat.get("count", 0)
                merged_chars[cid]["win_count"] += char_stat.get("win_count", 0)
                merged_chars[cid]["total_matches"] += char_stat.get("total_matches", 0)
                
                cur_score = RESULT_SCORES.get(merged_chars[cid]["best_result"], 999)
                new_score = RESULT_SCORES.get(char_stat.get("best_result", "不明"), 999)
                if new_score < cur_score:
                    merged_chars[cid]["best_result"] = char_stat.get("best_result")
                _merge_char_position_stats(merged_chars, char_stat, cid)
                    
            # team_usage merging
            for team in (snap.team_usage or []):
                cid = team.get("canonical_id")
                if not cid: continue
                _merge_team_position_and_adopted(merged_teams, team, cid)

        # Recalculate rates for chars
        char_list = []
        for char in merged_chars.values():
            t = char["total_matches"]
            w = char["win_count"]
            char["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            _finalize_char_position_stats(char)
            char_list.append(char)
        char_list.sort(key=lambda x: x["count"], reverse=True)

        # Recalculate rates for teams
        team_list = []
        for team in merged_teams.values():
            t = team["total_matches"]
            w = team["win_count"]
            team["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            _finalize_team_position_and_adopted(team)
            team_list.append(team)
        team_list.sort(key=lambda x: x["count"], reverse=True)

        stats = {
            "total_players": total_players,
            "total_matches": total_matches,
            "character_usage": char_list,
            "character_stats": char_list,
            "character_usage_by_result": _compute_character_usage_by_result(target_ids, db),
            "team_usage": team_list[:50],
            "matchups": [] # Usually cross matchups are fetched via their own endpoint
        }
        return stats
    else:
        print("[cross stats] fallback raw compute")
        stats = _compute_cross_tournament_stats(target_ids, db)
        if "team_usage" in stats:
            stats["team_usage"] = stats["team_usage"][:50]
        return stats


def _compute_cross_tournament_stats(tournament_ids_input: List[int], db: Session):
    """複数大会を横断したキャラ採用率・編成使用率・勝率を集計する"""
    tournament_ids = get_published_tournament_ids(tournament_ids_input, db)
    if not tournament_ids:
        raise HTTPException(status_code=400, detail="tournament_ids が必要です")

    # 対象大会の全プレイヤーを取得
    all_players = db.query(models.Player).filter(
        models.Player.tournament_id.in_(tournament_ids)
    ).all()
    player_ids = [p.id for p in all_players]

    deck_sets = db.query(models.DeckSet).filter(
        models.DeckSet.player_id.in_(player_ids)
    ).all()
    deck_set_ids = [ds.id for ds in deck_sets]
    ds_to_player = {ds.id: ds.player_id for ds in deck_sets}

    deck_teams = db.query(models.DeckTeam).filter(
        models.DeckTeam.deck_set_id.in_(deck_set_ids)
    ).all()

    char_usage = {}
    char_position = {}
    char_team_position = {}
    team_usage = {}

    for team in deck_teams:
        chars = [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]
        chars_valid = [c for c in chars if c is not None]

        for c_id in chars_valid:
            if c_id == EMPTY_SLOT_CHARACTER_ID:
                continue
            char_usage[c_id] = char_usage.get(c_id, 0) + 1
            if c_id not in char_team_position:
                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
            t_pos = getattr(team, "team_number", 0)
            if 1 <= t_pos <= 5:
                char_team_position[c_id][t_pos]["count"] += 1
                pid = ds_to_player.get(team.deck_set_id)
                if pid:
                    char_team_position[c_id][t_pos]["players"].add(pid)

        for pos_idx, c_id in enumerate(chars):
            if c_id is not None and c_id != EMPTY_SLOT_CHARACTER_ID:
                if c_id not in char_position:
                    char_position[c_id] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                char_position[c_id][pos_idx + 1] += 1

        if len(chars_valid) == 5:
            sorted_chars = tuple(sorted(chars_valid))
            if sorted_chars not in team_usage:
                team_usage[sorted_chars] = {
                    "count": 0,
                    "original_order": chars_valid,
                    "position_stats": {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                }
            team_usage[sorted_chars]["count"] += 1
            t_pos = getattr(team, "team_number", 0)
            if 1 <= t_pos <= 5:
                team_usage[sorted_chars]["position_stats"][t_pos]["count"] += 1
                pid = ds_to_player.get(team.deck_set_id)
                if pid:
                    team_usage[sorted_chars]["position_stats"][t_pos]["players"].add(pid)

    # 勝敗集計
    all_matches = db.query(models.Match).filter(
        models.Match.tournament_id.in_(tournament_ids)
    ).all()

    char_match_stats = {}
    team_match_stats = {}
    char_position_match_stats = {}

    for match in all_matches:
        attacker_ds = db.query(models.DeckSet).filter(
            models.DeckSet.player_id == match.attacker_id
        ).first()
        defender_ds = db.query(models.DeckSet).filter(
            models.DeckSet.player_id == match.defender_id
        ).first()

        if not attacker_ds or not defender_ds:
            continue

        a_teams = {t.team_number: t for t in attacker_ds.teams}
        d_teams = {t.team_number: t for t in defender_ds.teams}

        for rr in match.round_results:
            rn = rr.round_number
            winner_id = rr.winner_id
            a_team = a_teams.get(rn)
            d_team = d_teams.get(rn)

            if a_team and d_team:
                a_chars = [c for c in [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id] if c is not None]
                d_chars = [c for c in [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id] if c is not None]

                is_a_win = winner_id == match.attacker_id
                is_d_win = winner_id == match.defender_id

                for c_id in a_chars:
                    if c_id == EMPTY_SLOT_CHARACTER_ID:
                        continue
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_a_win: char_match_stats[c_id]["wins"] += 1
                for c_id in d_chars:
                    if c_id == EMPTY_SLOT_CHARACTER_ID:
                        continue
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_d_win: char_match_stats[c_id]["wins"] += 1

                # ポジション別勝敗
                a_all = [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id]
                d_all = [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id]
                for pos_idx, c_id in enumerate(a_all):
                    if c_id is not None and c_id != EMPTY_SLOT_CHARACTER_ID:
                        pos = pos_idx + 1
                        if c_id not in char_position_match_stats:
                            char_position_match_stats[c_id] = {p: {"wins": 0, "total": 0} for p in range(1, 6)}
                        char_position_match_stats[c_id][pos]["total"] += 1
                        if is_a_win: char_position_match_stats[c_id][pos]["wins"] += 1
                        
                        a_t_pos = getattr(a_team, "team_number", 0)
                        if 1 <= a_t_pos <= 5:
                            if c_id not in char_team_position:
                                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                            char_team_position[c_id][a_t_pos]["total"] += 1
                            if is_a_win: char_team_position[c_id][a_t_pos]["wins"] += 1

                for pos_idx, c_id in enumerate(d_all):
                    if c_id is not None and c_id != EMPTY_SLOT_CHARACTER_ID:
                        pos = pos_idx + 1
                        if c_id not in char_position_match_stats:
                            char_position_match_stats[c_id] = {p: {"wins": 0, "total": 0} for p in range(1, 6)}
                        char_position_match_stats[c_id][pos]["total"] += 1
                        if is_d_win: char_position_match_stats[c_id][pos]["wins"] += 1

                        d_t_pos = getattr(d_team, "team_number", 0)
                        if 1 <= d_t_pos <= 5:
                            if c_id not in char_team_position:
                                char_team_position[c_id] = {p: {"count": 0, "wins": 0, "total": 0, "players": set()} for p in range(1, 6)}
                            char_team_position[c_id][d_t_pos]["total"] += 1
                            if is_d_win: char_team_position[c_id][d_t_pos]["wins"] += 1

                if len(a_chars) == 5:
                    a_canon = ",".join(map(str, sorted(a_chars)))
                    if a_canon not in team_match_stats: team_match_stats[a_canon] = {"wins": 0, "total": 0}
                    team_match_stats[a_canon]["total"] += 1
                    if is_a_win: team_match_stats[a_canon]["wins"] += 1
                    
                    a_tup = tuple(sorted(a_chars))
                    if a_tup in team_usage and getattr(a_team, "team_number", 0) and 1 <= a_team.team_number <= 5:
                        team_usage[a_tup]["position_stats"][a_team.team_number]["total"] += 1
                        if is_a_win: team_usage[a_tup]["position_stats"][a_team.team_number]["wins"] += 1

                if len(d_chars) == 5:
                    d_canon = ",".join(map(str, sorted(d_chars)))
                    if d_canon not in team_match_stats: team_match_stats[d_canon] = {"wins": 0, "total": 0}
                    team_match_stats[d_canon]["total"] += 1
                    if is_d_win: team_match_stats[d_canon]["wins"] += 1
                    
                    d_tup = tuple(sorted(d_chars))
                    if d_tup in team_usage and getattr(d_team, "team_number", 0) and 1 <= d_team.team_number <= 5:
                        team_usage[d_tup]["position_stats"][d_team.team_number]["total"] += 1
                        if is_d_win: team_usage[d_tup]["position_stats"][d_team.team_number]["wins"] += 1

    # 各大会ごとの最終成績を計算するためのキャッシュ
    # {tournament_id: {player_id: result_string}}


    # 大会ごとにプレイヤー成績を計算
    per_tournament_results = {}
    for tid in tournament_ids:
        t_players = [p for p in all_players if p.tournament_id == tid]
        t_matches = [m for m in all_matches if m.tournament_id == tid]
        player_by_id_t = {p.id: p for p in t_players}

        def get_winner_between_t(pid1, pid2):
            for m in t_matches:
                if m.winner_id and (
                    (m.attacker_id == pid1 and m.defender_id == pid2) or
                    (m.attacker_id == pid2 and m.defender_id == pid1)
                ):
                    return m.winner_id
            return None

        def calc_result_t(player_id):
            p = player_by_id_t.get(player_id)
            if not p or p.seed_number is None:
                return "ベスト64"
            g_idx = (p.seed_number - 1) // 8
            base_seed = g_idx * 8
            qf_winners = []
            for i in range(4):
                s1 = base_seed + i * 2 + 1
                s2 = base_seed + i * 2 + 2
                p1 = next((x for x in t_players if x.seed_number == s1), None)
                p2 = next((x for x in t_players if x.seed_number == s2), None)
                w = get_winner_between_t(p1.id if p1 else None, p2.id if p2 else None)
                qf_winners.append(w)
            if player_id not in qf_winners:
                return "ベスト64"
            sf_winners = []
            for i in range(2):
                w = get_winner_between_t(qf_winners[i*2], qf_winners[i*2+1])
                sf_winners.append(w)
            if player_id not in sf_winners:
                return "ベスト32"
            group_winner = get_winner_between_t(sf_winners[0], sf_winners[1])
            if player_id != group_winner:
                return "ベスト16"
            # チャンピオン対抗戦
            group_winners = []
            for gi in range(8):
                base = gi * 8
                qf_w = []
                for i in range(4):
                    s1 = base + i * 2 + 1
                    s2 = base + i * 2 + 2
                    p1t = next((x for x in t_players if x.seed_number == s1), None)
                    p2t = next((x for x in t_players if x.seed_number == s2), None)
                    w = get_winner_between_t(p1t.id if p1t else None, p2t.id if p2t else None)
                    qf_w.append(w)
                sf_w = []
                for i in range(2):
                    w = get_winner_between_t(qf_w[i*2], qf_w[i*2+1])
                    sf_w.append(w)
                gw = get_winner_between_t(sf_w[0], sf_w[1])
                group_winners.append(gw)
            champ_qf_w = []
            for i in range(4):
                w = get_winner_between_t(group_winners[i*2], group_winners[i*2+1])
                champ_qf_w.append(w)
            if player_id not in champ_qf_w:
                return "ベスト8"
            champ_sf_w = []
            for i in range(2):
                w = get_winner_between_t(champ_qf_w[i*2], champ_qf_w[i*2+1])
                champ_sf_w.append(w)
            if player_id not in champ_sf_w:
                return "ベスト4"
            champ_winner = get_winner_between_t(champ_sf_w[0], champ_sf_w[1])
            if player_id != champ_winner:
                return "準優勝"
            return "優勝"

        t_result_cache = {}
        for p in t_players:
            t_result_cache[p.id] = calc_result_t(p.id)
        per_tournament_results[tid] = t_result_cache

    # キャラ→使用プレイヤーのマッピング
    char_to_players = {}
    for ds in deck_sets:
        for team in ds.teams:
            for c_id in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]:
                if c_id is not None and c_id != EMPTY_SLOT_CHARACTER_ID:
                    if c_id not in char_to_players:
                        char_to_players[c_id] = set()
                    char_to_players[c_id].add(ds.player_id)

    # 全大会横断での最良成績を返す
    player_by_id = {p.id: p for p in all_players}

    def get_best_result_cross(player_ids_set):
        best_score = 999
        best_result = "ベスト64"
        for pid in player_ids_set:
            p = player_by_id.get(pid)
            if not p:
                continue
            tid = p.tournament_id
            result = per_tournament_results.get(tid, {}).get(pid, "ベスト64")
            score = RESULT_SCORES.get(result, 64)
            if score < best_score:
                best_score = score
                best_result = result
        return best_result

    # キャラクターリスト構築
    char_list = []
    for c_id, count in char_usage.items():
        char = db.query(models.Character).filter(models.Character.id == c_id).first()
        if char:
            m_stats = char_match_stats.get(c_id, {"wins": 0, "total": 0})
            win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else 0
            pos_data = char_position.get(c_id, {1:0, 2:0, 3:0, 4:0, 5:0})
            pos_match = char_position_match_stats.get(c_id, {})
            position_stats = []
            for p in range(1, 6):
                p_count = pos_data.get(p, 0)
                p_ms = pos_match.get(p, {"wins": 0, "total": 0})
                p_wr = round(p_ms["wins"] / p_ms["total"] * 100, 1) if p_ms["total"] > 0 else None
                position_stats.append({
                    "position": p,
                    "count": p_count,
                    "pct": round(p_count / count * 100, 1) if count > 0 else 0,
                    "wins": p_ms["wins"],
                    "total": p_ms["total"],
                    "win_rate": p_wr
                })
            t_pos_data = char_team_position.get(c_id, {})
            team_position_stats = []
            for p in range(1, 6):
                p_ms = t_pos_data.get(p, {"count": 0, "wins": 0, "total": 0, "players": set()})
                p_count = p_ms["count"]
                p_wr = round(p_ms["wins"] / p_ms["total"] * 100, 1) if p_ms["total"] > 0 else None
                
                best_res_p = None
                if p_ms["players"]:
                    scores = []
                    for pid in p_ms["players"]:
                        p_obj = player_by_id.get(pid)
                        if p_obj:
                            res_str = per_tournament_results.get(p_obj.tournament_id, {}).get(pid, "ベスト64")
                            scores.append((RESULT_SCORES.get(res_str, 999), res_str))
                    if scores:
                        best_res_p = min(scores, key=lambda x: x[0])[1]
                
                team_position_stats.append({
                    "position": p,
                    "count": p_count,
                    "pct": round(p_count / count * 100, 1) if count > 0 else 0,
                    "wins": p_ms["wins"],
                    "total": p_ms["total"],
                    "win_rate": p_wr,
                    "best_result": best_res_p
                })

            user_ids = char_to_players.get(c_id, set())
            best_result = get_best_result_cross(user_ids) if user_ids else None

            char_list.append({
                "id": char.id,
                "name": char.name,
                "rarity": char.rarity,
                "count": count,
                "win_count": m_stats["wins"],
                "total_matches": m_stats["total"],
                "win_rate": round(win_rate, 1),
                "best_result": best_result,
                "position_stats": position_stats,
                "team_position_stats": team_position_stats
            })
    char_list.sort(key=lambda x: x["count"], reverse=True)

    # 編成リスト構築
    team_list = []
    for sorted_chars, data in team_usage.items():
        count = data["count"]
        original_order = data["original_order"]
        team_chars = []
        for c_id in original_order:
            char = db.query(models.Character).filter(models.Character.id == c_id).first()
            if char:
                team_chars.append({"id": char.id, "name": char.name, "rarity": char.rarity})

        canon_id = ",".join(map(str, sorted_chars))
        m_stats = team_match_stats.get(canon_id, {"wins": 0, "total": 0})
        win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else 0

        pos_stats_out = []
        for p in range(1, 6):
            ps = data["position_stats"][p]
            best_res = None
            if ps["players"]:
                scores = []
                for pid in ps["players"]:
                    p_obj = player_by_id.get(pid)
                    if p_obj:
                        res_str = per_tournament_results.get(p_obj.tournament_id, {}).get(pid, "ベスト64")
                        scores.append((RESULT_SCORES.get(res_str, 999), res_str))
                if scores:
                    best_res = min(scores, key=lambda x: x[0])[1]
            pos_stats_out.append({
                "position": p,
                "count": ps["count"],
                "pct": round(ps["count"] / count * 100, 1) if count > 0 else 0,
                "wins": ps["wins"],
                "total": ps["total"],
                "win_rate": round(ps["wins"] / ps["total"] * 100, 1) if ps["total"] > 0 else None,
                "best_result": best_res
            })

        team_char_set = set(sorted_chars)
        team_player_ids = set()
        for ds in deck_sets:
            for team in ds.teams:
                team_ids = set(c for c in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id] if c is not None)
                if team_ids == team_char_set:
                    team_player_ids.add(ds.player_id)

        best_team_result = get_best_result_cross(team_player_ids) if team_player_ids else None

        # この編成を採用したプレイヤー情報を収集
        adopted_players = []
        for pid in team_player_ids:
            player = db.query(models.Player).filter(models.Player.id == pid).first()
            if player:
                t = db.query(models.Tournament).filter(models.Tournament.id == player.tournament_id).first()
                # per_tournament_results[tournament_id][player_id] で成績を取得
                p_result = per_tournament_results.get(player.tournament_id, {}).get(pid, "ベスト64")
                adopted_players.append({
                    "player_name": player.name,
                    "tournament_name": t.name if t else "不明",
                    "tournament_id": player.tournament_id,
                    "result": p_result
                })
        adopted_players.sort(key=lambda x: RESULT_SCORES.get(x["result"], 64))

        team_list.append({
            "canonical_id": canon_id,
            "character_ids": original_order,
            "characters": team_chars,
            "count": count,
            "win_count": m_stats["wins"],
            "total_matches": m_stats["total"],
            "win_rate": round(win_rate, 1),
            "best_result": best_team_result,
            "adopted_players": adopted_players,
            "position_stats": pos_stats_out
        })
    team_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "character_usage": char_list,
        "character_stats": char_list,
        "character_usage_by_result": _compute_character_usage_by_result(tournament_ids, db),
        "team_usage": team_list,
        "total_players": len(player_ids),
        "total_matches": len(matches)
    }


@app.post("/api/dashboard/cross-tournament/matchups")
def get_cross_tournament_matchups(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    """複数大会を横断した対戦データを集計する"""
    tournament_ids = get_published_tournament_ids(body.tournament_ids, db)
    if not tournament_ids:
        raise HTTPException(status_code=400, detail="tournament_ids が必要です")

    matches = db.query(models.Match).filter(
        models.Match.tournament_id.in_(tournament_ids)
    ).all()

    matchup_results = []
    for match in matches:
        attacker_ds = db.query(models.DeckSet).filter(
            models.DeckSet.player_id == match.attacker_id
        ).first()
        defender_ds = db.query(models.DeckSet).filter(
            models.DeckSet.player_id == match.defender_id
        ).first()

        if not attacker_ds or not defender_ds:
            continue

        attacker_teams = {t.team_number: t for t in attacker_ds.teams}
        defender_teams = {t.team_number: t for t in defender_ds.teams}

        for round_res in match.round_results:
            rn = round_res.round_number
            a_team = attacker_teams.get(rn)
            d_team = defender_teams.get(rn)

            if a_team and d_team:
                a_chars = [c for c in [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id] if c is not None]
                d_chars = [c for c in [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id] if c is not None]

                a_sorted = tuple(sorted(a_chars))
                d_sorted = tuple(sorted(d_chars))

                if len(a_chars) == 5 and len(d_chars) == 5:
                    winner_is_attacker = round_res.winner_id == match.attacker_id
                    matchup_results.append({
                        "match_id": match.id,
                        "round_number": rn,
                        "stage": match.stage,
                        "attacker_team": list(a_chars),
                        "defender_team": list(d_chars),
                        "canonical_attacker": ",".join(map(str, a_sorted)),
                        "canonical_defender": ",".join(map(str, d_sorted)),
                        "winner_team": list(a_chars) if winner_is_attacker else list(d_chars),
                        "loser_team": list(d_chars) if winner_is_attacker else list(a_chars),
                        "winner_is_attacker": winner_is_attacker,
                        "tournament_name": match.tournament.name if match.tournament else "不明",
                        "tournament_id": match.tournament_id,
                        "attacker_name": match.attacker.name if match.attacker else "不明",
                        "defender_name": match.defender.name if match.defender else "不明"
                    })

    return {"matchups": matchup_results}



class CrossTournamentTeamsRequest(PydanticBaseModel):
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None
    seed: Optional[int] = None
    character_ids: Optional[List[int]] = None
    limit: Optional[int] = 10
    offset: Optional[int] = 0
    sort_by: Optional[str] = None
    min_matches: Optional[int] = None
    min_usage: Optional[int] = None
    min_win_rate: Optional[float] = None
    best_result: Optional[str] = None


@app.get("/api/tournaments/{tournament_id}/dashboard/teams")
def get_dashboard_teams(
    tournament_id: int,
    seed: Optional[int] = None,
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    character_ids: Optional[str] = None,
    sort_by: Optional[str] = None,
    min_matches: int = 0,
    min_usage: int = 0,
    min_win_rate: float = 0,
    best_result: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    # スナップショット優先（なければ既存集計にフォールバック）
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if snap is not None:
        teams = snap.team_usage or []
    else:
        stats = _compute_dashboard_stats(tournament_id, db, current_user, seed)
        teams = stats.get("team_usage", [])
    
    if character_ids:
        c_ids = [int(x) for x in character_ids.split(",") if x.isdigit()]
        if c_ids:
            filtered = []
            for t in teams:
                t_cids = t.get("character_ids") or [c["id"] for c in t.get("characters", []) if isinstance(c, dict) and "id" in c]
                if all(cid in t_cids for cid in c_ids):
                    filtered.append(t)
            teams = filtered

    if min_matches > 0:
        teams = [t for t in teams if t.get("total_matches", 0) >= min_matches]
    if min_usage > 0:
        teams = [t for t in teams if t.get("count", 0) >= min_usage]
    if min_win_rate > 0:
        teams = [t for t in teams if t.get("win_rate", 0) >= min_win_rate]
    if best_result:
        target_score = RESULT_SCORES.get(best_result, 999)
        teams = [t for t in teams if RESULT_SCORES.get(t.get("best_result", "不明"), 999) <= target_score]

    if sort_by == "win_rate":
        teams.sort(key=lambda x: x.get("win_rate", 0), reverse=True)
    elif sort_by in ("usage", "count"):
        teams.sort(key=lambda x: x.get("count", 0), reverse=True)
        
    return {
        "teams": teams[offset: offset + limit],
        "total": len(teams)
    }


@app.post("/api/dashboard/cross-tournament/teams")
def get_cross_dashboard_teams(
    req: CrossTournamentTeamsRequest,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    if req.tournament_ids:
        tournament_ids = req.tournament_ids
    else:
        tournament_ids = resolve_cross_tournament_ids(db, req.tournament_ids, req.play_server, req.championship_id)

    print("[cross teams] req.tournament_ids:", req.tournament_ids)
    print("[cross teams] target_ids:", tournament_ids)
    # スナップショット合成：指定大会の snapshot を読み込んで team_usage を統合
    snaps = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id.in_(tournament_ids)
    ).all() if tournament_ids else []

    if tournament_ids and len(snaps) == len(tournament_ids):

        merged: dict = {}
        for snap in snaps:
            for team in (snap.team_usage or []):
                cid = team.get("canonical_id")
                if not cid:
                    continue
                _merge_team_position_and_adopted(merged, team, cid)
        teams = []
        for team in merged.values():
            t = team["total_matches"]
            w = team["win_count"]
            team["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            _finalize_team_position_and_adopted(team)
            teams.append(team)
    else:
        # スナップショットがない場合は既存集計にフォールバック
        stats = _compute_cross_tournament_stats(tournament_ids, db)
        teams = stats.get("team_usage", [])
    
    if req.character_ids:
        c_ids = req.character_ids
        filtered = []
        for t in teams:
            t_cids = t.get("character_ids") or [c["id"] for c in t.get("characters", []) if isinstance(c, dict) and "id" in c]
            if all(cid in t_cids for cid in c_ids):
                filtered.append(t)
        teams = filtered

    if req.min_matches is not None and req.min_matches > 0:
        teams = [t for t in teams if t.get("total_matches", 0) >= req.min_matches]
    if req.min_usage is not None:
        teams = [t for t in teams if t.get("count", 0) >= req.min_usage]
    if req.min_win_rate is not None:
        teams = [t for t in teams if t.get("win_rate", 0) >= req.min_win_rate]
    if req.best_result:

        target_score = RESULT_SCORES.get(req.best_result, 999)
        teams = [t for t in teams if RESULT_SCORES.get(t.get("best_result", "不明"), 999) <= target_score]

    if req.sort_by == "win_rate":
        teams.sort(key=lambda x: x.get("win_rate", 0), reverse=True)
    elif req.sort_by in ("usage", "count"):
        teams.sort(key=lambda x: x.get("count", 0), reverse=True)
        
    limit = req.limit or 10
    offset = req.offset or 0
    return {
        "teams": teams[offset: offset + limit],
        "total": len(teams)
    }


@app.post("/api/dashboard/cross-tournament/character-detail")
def get_cross_tournament_character_detail(req: CrossTournamentCharacterDetailRequest, db: Session = Depends(get_db)):
    if req.tournament_ids:
        target_ids = req.tournament_ids
    else:
        target_ids = resolve_cross_tournament_ids(
            db,
            req.tournament_ids,
            req.play_server,
            req.championship_id
        )
    target_ids = get_published_tournament_ids(target_ids, db)
    if not target_ids:
        return {"character_usage": [], "team_usage": []}

    snaps = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id.in_(target_ids)
    ).all() if target_ids else []

    if target_ids and len(snaps) == len(target_ids):
        print(f"[cross char detail] using snapshots: {len(snaps)} / {len(target_ids)}")
        merged_chars = {}
        merged_teams = {}
        
        for snap in snaps:
            for char_stat in (snap.char_stats or []):
                cid = char_stat.get("id") or char_stat.get("character_id")
                try:
                    cid_int = int(cid) if cid is not None else None
                except (ValueError, TypeError):
                    cid_int = None
                try:
                    req_cid_int = int(req.character_id) if req.character_id is not None else None
                except (ValueError, TypeError):
                    req_cid_int = None
                if cid_int is None or cid_int != req_cid_int: continue
                if cid_int not in merged_chars:
                    merged_chars[cid_int] = {
                        "id": cid_int,
                        "character_id": cid_int,
                        "name": char_stat.get("name"),
                        "rarity": char_stat.get("rarity"),
                        "count": 0,
                        "win_count": 0,
                        "total_matches": 0,
                        "best_result": char_stat.get("best_result", "不明"),
                        "position_stats": [],
                        "team_position_stats": [],
                        "_pos_map": {p: {"count": 0, "wins": 0, "total": 0} for p in range(1, 6)},
                        "_team_pos_map": {p: {"count": 0, "wins": 0, "total": 0, "best_result": None} for p in range(1, 6)}
                    }
                merged_chars[cid_int]["count"] += char_stat.get("count", 0)
                merged_chars[cid_int]["win_count"] += char_stat.get("win_count", 0)
                merged_chars[cid_int]["total_matches"] += char_stat.get("total_matches", 0)
                
                cur_score = RESULT_SCORES.get(merged_chars[cid_int]["best_result"], 999)
                new_score = RESULT_SCORES.get(char_stat.get("best_result", "不明"), 999)
                if new_score < cur_score:
                    merged_chars[cid_int]["best_result"] = char_stat.get("best_result")
                _merge_char_position_stats(merged_chars, char_stat, cid_int)
                    
            for team in (snap.team_usage or []):
                t_cids = team.get("character_ids") or [c["id"] for c in team.get("characters", []) if isinstance(c, dict) and "id" in c]
                t_cids_int = [int(c) for c in t_cids if c is not None and str(c).isdigit()]
                if int(req.character_id) not in t_cids_int: continue
                cid = team.get("canonical_id")
                if not cid: continue
                _merge_team_position_and_adopted(merged_teams, team, cid)

        char_list = []
        for char in merged_chars.values():
            t = char["total_matches"]
            w = char["win_count"]
            char["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            char["id"] = int(char["id"])
            char["character_id"] = int(char["id"])
            _finalize_char_position_stats(char)
            char_list.append(char)
            
        if not char_list:
            char_model = db.query(models.Character).filter(models.Character.id == req.character_id).first()
            char_name = char_model.name if char_model else "不明"
            rarity = char_model.rarity if char_model else "SSR"
            char_list = [{
                "id": int(req.character_id),
                "character_id": int(req.character_id),
                "name": char_name,
                "rarity": rarity,
                "count": 0,
                "win_count": 0,
                "total_matches": 0,
                "win_rate": 0.0,
                "best_result": "不明",
                "position_stats": [],
                "team_position_stats": []
            }]
            
        team_list = []
        for team in merged_teams.values():
            t = team["total_matches"]
            w = team["win_count"]
            team["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            _finalize_team_position_and_adopted(team)
            team_list.append(team)
        team_list.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "character_usage": char_list,
            "team_usage": team_list
        }
    else:
        print("[cross char detail] fallback raw compute")
        stats = _compute_cross_tournament_stats(target_ids, db)
        char_stats = stats.get("character_stats", [])
        team_usage = stats.get("team_usage", [])
        
        char_item = next((x for x in char_stats if (int(x.get("id") or 0) == int(req.character_id) or int(x.get("character_id") or 0) == int(req.character_id))), None)
        if char_item:
            char_item["id"] = int(char_item.get("id") or char_item.get("character_id") or req.character_id)
            char_item["character_id"] = char_item["id"]
        else:
            char_model = db.query(models.Character).filter(models.Character.id == req.character_id).first()
            char_name = char_model.name if char_model else "不明"
            rarity = char_model.rarity if char_model else "SSR"
            char_item = {
                "id": int(req.character_id),
                "character_id": int(req.character_id),
                "name": char_name,
                "rarity": rarity,
                "count": 0,
                "win_count": 0,
                "total_matches": 0,
                "win_rate": 0.0,
                "best_result": "不明",
                "position_stats": [],
                "team_position_stats": []
            }
        related_teams = []
        for t in team_usage:
            t_cids = t.get("character_ids") or [c["id"] for c in t.get("characters", []) if isinstance(c, dict) and "id" in c]
            t_cids_int = [int(c) for c in t_cids if c is not None and str(c).isdigit()]
            if int(req.character_id) in t_cids_int:
                related_teams.append(t)
        
        return {
            "character_usage": [char_item] if char_item else [],
            "team_usage": related_teams
        }


@app.get("/api/tournaments/{tournament_id}/dashboard/character-winrates")
def get_dashboard_character_winrates(
    tournament_id: int,
    seed: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if snap is not None and snap.char_stats:
        char_stats = snap.char_stats
    else:
        stats = _compute_dashboard_stats(tournament_id, db, current_user, seed)
        char_stats = stats.get("character_stats", [])
    return {"character_winrates": char_stats, "character_stats": char_stats}


@app.get("/api/tournaments/{tournament_id}/dashboard/character/{character_id}")
def get_dashboard_character_detail(
    tournament_id: int,
    character_id: int,
    seed: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if snap is not None and snap.char_stats is not None and snap.team_usage is not None:
        char_stats = snap.char_stats
        team_usage = snap.team_usage
    else:
        stats = _compute_dashboard_stats(tournament_id, db, current_user, seed)
        char_stats = stats.get("character_usage", stats.get("character_stats", []))
        team_usage = stats.get("team_usage", [])

    char_item = next((x for x in char_stats if (int(x.get("id") or 0) == int(character_id) or int(x.get("character_id") or 0) == int(character_id))), None)
    if char_item:
        char_item["id"] = int(char_item.get("id") or char_item.get("character_id") or character_id)
        char_item["character_id"] = char_item["id"]
        if char_item.get("count", 0) > 0 and (not char_item.get("position_stats") or not char_item.get("team_position_stats")):
            comp_stats = _compute_dashboard_stats(tournament_id, db, current_user, seed)
            comp_chars = comp_stats.get("character_usage", comp_stats.get("character_stats", []))
            comp_item = next((x for x in comp_chars if (int(x.get("id") or 0) == int(character_id) or int(x.get("character_id") or 0) == int(character_id))), None)
            if comp_item:
                if not char_item.get("position_stats"):
                    char_item["position_stats"] = comp_item.get("position_stats", [])
                if not char_item.get("team_position_stats"):
                    char_item["team_position_stats"] = comp_item.get("team_position_stats", [])
    else:
        char_model = db.query(models.Character).filter(models.Character.id == character_id).first()
        char_name = char_model.name if char_model else "不明"
        rarity = char_model.rarity if char_model else "SSR"
        char_item = {
            "id": int(character_id),
            "character_id": int(character_id),
            "name": char_name,
            "rarity": rarity,
            "count": 0,
            "win_count": 0,
            "total_matches": 0,
            "win_rate": 0.0,
            "best_result": "不明",
            "position_stats": [],
            "team_position_stats": []
        }
    related_teams = []
    for t in team_usage:
        t_cids = t.get("character_ids") or [c["id"] for c in t.get("characters", []) if isinstance(c, dict) and "id" in c]
        t_cids_int = [int(c) for c in t_cids if c is not None and str(c).isdigit()]
        if int(character_id) in t_cids_int:
            related_teams.append(t)

    return {
        "character_usage": [char_item] if char_item else [],
        "team_usage": related_teams
    }


@app.get("/api/tournaments/{tournament_id}/dashboard/player-stats")
def get_dashboard_player_stats(
    tournament_id: int,
    seed: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    require_tournament_dashboard_viewer(tournament_id, db, current_user)
    if seed is not None:
        return get_player_details(tournament_id, seed, db, current_user)
    players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).order_by(models.Player.seed_number).all()
    return {"players": [schemas.Player.from_orm(p) for p in players]}
