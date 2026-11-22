from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Request, Response, Query, BackgroundTasks
import auth as auth_module
import article_routes
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import engine, Base, get_db, SessionLocal
import models, schemas
from services import article_image_cleanup, championship_settings, season_summary
from typing import List, Literal, Optional
from datetime import date as date_type, datetime, timedelta, timezone
import json
import hashlib
import base64
import secrets
import asyncio
import contextlib
import shutil
import os
import time
import re
from pathlib import Path
from starlette.exceptions import HTTPException as StarletteHTTPException
from services.template_management import (
    describe_template,
    list_template_paths,
    move_to_quarantine,
    next_template_name,
    parse_template_name,
    reassign_active_template,
    representative_template,
    restore_from_quarantine,
    rollback_move,
    safe_template_path,
    template_operation_lock,
    template_sha256,
)

app = FastAPI(
    title="NIKKE Arena Analysis API",
    description="API for extracting and analyzing NIKKE Arena data",
    version="1.0.0"
)

article_routes.register_article_routes(app)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"

CHAMPION_TEMPLATE_SOURCE_MAX_BYTES = 1024 * 1024
CHAMPION_TEMPLATE_SOURCE_TOTAL_MAX_BYTES = 10 * 1024 * 1024
CHAMPION_CROP_TTL_SECONDS = int(os.environ.get("CHAMPION_CROP_TTL_SECONDS", "21600"))
CHAMPION_CROP_NAME = re.compile(
    r"^crop_t(?P<tournament>\d+)_(?:p(?P<player>\d+)|s(?P<seed>\d+))_"
    r"(?P<token>[0-9a-f]{12})_r\d+_c\d+(?:_preview)?\.(?:png|webp)$"
)

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

DASHBOARD_CACHE_TTL_SECONDS = int(os.environ.get("DASHBOARD_CACHE_TTL_SECONDS", "60"))
_dashboard_cache: dict[tuple[int, str, tuple[tuple[str, str], ...]], dict] = {}


def _dashboard_cache_key(tournament_id: int, endpoint: str, params: dict | None = None):
    params = params or {}
    clean_params = tuple(
        sorted(
            (key, str(value))
            for key, value in params.items()
            if value is not None and key != "t"
        )
    )
    return (int(tournament_id), endpoint, clean_params)


def get_private_dashboard_cache(
    tournament: models.Tournament,
    endpoint: str,
    params: dict | None = None,
):
    if tournament.publication_status == "published":
        return None
    key = _dashboard_cache_key(tournament.id, endpoint, {**(params or {}), "title_settings": (tournament.deck_registration_phases, tournament.is_champion_arena, tournament.has_match_data)})
    cached = _dashboard_cache.get(key)
    now = time.monotonic()
    if cached and cached["expires_at"] > now:
        print(f"[dashboard-cache] hit tournament={tournament.id} endpoint={endpoint}")
        return cached["value"]
    if cached:
        _dashboard_cache.pop(key, None)
    print(f"[dashboard-cache] miss tournament={tournament.id} endpoint={endpoint}")
    return None


def set_private_dashboard_cache(
    tournament: models.Tournament,
    endpoint: str,
    value,
    params: dict | None = None,
):
    if tournament.publication_status != "published" and DASHBOARD_CACHE_TTL_SECONDS > 0:
        key = _dashboard_cache_key(tournament.id, endpoint, {**(params or {}), "title_settings": (tournament.deck_registration_phases, tournament.is_champion_arena, tournament.has_match_data)})
        _dashboard_cache[key] = {
            "value": value,
            "expires_at": time.monotonic() + DASHBOARD_CACHE_TTL_SECONDS,
        }
    return value


def invalidate_dashboard_cache(tournament_id: int):
    before = len(_dashboard_cache)
    for key in list(_dashboard_cache.keys()):
        if key[0] == int(tournament_id):
            _dashboard_cache.pop(key, None)
    removed = before - len(_dashboard_cache)
    if removed:
        print(f"[dashboard-cache] invalidate tournament={tournament_id} entries={removed}")


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

from services.image_processor import process_images, write_lossless_png
from services.analysis_execution import AnalysisBusyError, AnalysisReservation, reserve_analysis_slot, run_cpu_analysis, shutdown_analysis_executor


def require_analysis_capacity():
    try:
        reservation = reserve_analysis_slot()
    except AnalysisBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail="画像解析が混み合っています。数秒後にもう一度お試しください。",
            headers={"Retry-After": "5"},
        ) from exc
    try:
        yield reservation
    finally:
        # Once submitted, only the worker Future is allowed to release it.
        reservation.release_if_unsubmitted()


def request_analysis_reservation(value) -> AnalysisReservation | None:
    """Return FastAPI's resolved dependency; direct unit calls pass Depends."""
    return value if isinstance(value, AnalysisReservation) else None
from services.character_templates import find_character_template, get_character_template_inventory
from services.collection_classifier import COLLECTION_VALUES, collection_match_mask
from services.template_matcher import prepare_character_image, masked_absolute_similarity
from services.registration_email import (
    send_registration_approved,
    send_registration_request,
)
from services.champion_bracket import (
    CHAMPION_BRACKET,
    CHAMPION_BRACKET_BY_KEY,
    dependent_keys,
    get_bracket_definition,
    match_is_complete,
    participant_ids,
)
from services.champion_result import normalize_champion_result
from services import arena_phases
from services.champion_publication import validate_champion_publication
from copy import deepcopy
from services import composition_analytics, cross_analytics, team_statistics_display
from services.champion_snapshot import enrich_champion_snapshot_stats
from services.tournament_results import (
    RESULT_SCORES as TOURNAMENT_RESULT_SCORES,
    calculate_player_results,
    result_label,
)
from services.match_processor import extract_match_results
from services.upload_cleanup import (
    cleanup_stale_uploads,
    delete_temporary_crop_urls,
    delete_tournament_player_icons,
    delete_upload_file,
    path_from_upload_url,
    stale_age_hours_from_env,
    CROPPED_DIR,
    PLAYER_ICONS_DIR,
    _is_within,
)
from services.player_icons import (write_webp, icon_mutation_lock, InvalidIcon, IconTooLarge)
from fastapi.responses import FileResponse, RedirectResponse


def get_team_collection_levels(team: models.DeckTeam) -> list[str | None]:
    return [getattr(team, f"collection{slot}") for slot in range(1, 6)]


def automatic_player_name(seed_number: int) -> str:
    return f"Player {seed_number}"


def automatic_champion_player_name(champion_slot: int, seed_number: int | None) -> str:
    if seed_number is None:
        return f"champion_slot_{champion_slot}"
    return automatic_player_name(seed_number)


IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
NO_STORE_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


def _private_upload_tournament_id(asset_path: str, db: Session) -> int | None:
    """Return the owning tournament for a private upload URL, if it is known."""
    ownership = re.fullmatch(r"player_icons/tournament_(\d+)/(?:seed|player)_\d+\.(?:png|webp)", asset_path)
    normalized_url = f"/api/uploads/{asset_path}"
    player = db.query(models.Player).filter(
        models.Player.icon_url == normalized_url
    ).first()
    if player is not None:
        if ownership and int(ownership.group(1)) != player.tournament_id:
            return None
        return player.tournament_id

    # Older full_64 registrations could persist a cache-buster in icon_url.
    # The HTTP request correctly omits its query string from asset_path, so look
    # up only the exact URL followed by a query boundary.  Escaping LIKE keeps
    # underscores and percent signs in the requested path literal.
    escaped_url = (
        normalized_url
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    legacy_player = db.query(models.Player).filter(
        models.Player.icon_url.like(f"{escaped_url}?%", escape="\\")
    ).first()
    if (
        legacy_player is not None
            and legacy_player.icon_url.partition("?")[0] == normalized_url
    ):
        if ownership and int(ownership.group(1)) != legacy_player.tournament_id:
            return None
        return legacy_player.tournament_id

    crop_match = CHAMPION_CROP_NAME.fullmatch(Path(asset_path).name)
    if crop_match is not None and asset_path.startswith("cropped/"):
        return int(crop_match.group("tournament"))
    return None


@app.get("/api/uploads/{asset_path:path}")
def get_upload(
    asset_path: str,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    """Serve public Character templates and owner/admin-only tournament uploads."""
    requested = Path(asset_path)
    upload_root = Path(UPLOAD_DIR).resolve()
    full_path = (upload_root / requested).resolve()
    canonical_asset = None
    if re.fullmatch(r"player_icons/tournament_\d+/(?:seed|player)_\d+\.png", asset_path):
        candidate = asset_path[:-4] + ".webp"
        if _private_upload_tournament_id(candidate, db) is not None:
            canonical_asset = candidate
            full_path = (upload_root / candidate).resolve()
    if (
        not asset_path
        or requested.is_absolute()
        or ".." in requested.parts
        or not _is_within(full_path, upload_root)
        or not full_path.is_file()
    ):
        raise HTTPException(
            status_code=404,
            detail="File not found",
            headers={"Cache-Control": NO_STORE_CACHE_CONTROL},
        )

    # Character templates are the only upload assets used by the public
    # cross-tournament analysis. Tournament-owned uploads remain private.
    is_template = asset_path.startswith("templates/")
    if not is_template:
        tournament_id = _private_upload_tournament_id(canonical_asset or asset_path, db)
        if tournament_id is None:
            raise HTTPException(
                status_code=404,
                detail="File not found",
                headers={"Cache-Control": NO_STORE_CACHE_CONTROL},
            )
        require_tournament_viewer(tournament_id, db, current_user)

    if canonical_asset:
        return RedirectResponse(f"/api/uploads/{canonical_asset}", status_code=307,
                                headers={"Cache-Control": NO_STORE_CACHE_CONTROL})
    return FileResponse(
        full_path,
        media_type={".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(full_path.suffix.lower()),
        headers={
            "Cache-Control": (
                IMMUTABLE_CACHE_CONTROL if is_template else NO_STORE_CACHE_CONTROL
            )
        },
    )


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
    
    # Filesystem active generations are authoritative. This GET is read-only.
    template_path = find_character_template(UPLOAD_DIR, char_id)
    if template_path:
        return FileResponse(
            template_path,
            media_type="image/png",
            headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
        )
    
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


    if os.environ.get("ARTICLE_IMAGE_CLEANUP_ENABLED", "1") != "0":
        with SessionLocal() as db:
            try:
                article_image_cleanup.collect_unused(db)
            except Exception as error:
                print(f"[Cleanup] Scheduled article image cleanup failed: {error}")


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
    # Admission is closed before shutdown waits for the one shared worker.
    # Waiting in a helper thread keeps the event loop responsive while it drains.
    await asyncio.to_thread(shutdown_analysis_executor)


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
    # All five Character slots are flattened before aggregation so usage counts
    # require one query while preserving one count per occupied slot.
    character_slots = union_all(*(
        select(getattr(models.DeckTeam, f"char{i}_id").label("character_id"))
        for i in range(1, 6)
    )).subquery()
    usage_counts = dict(
        db.query(character_slots.c.character_id, func.count())
        .filter(character_slots.c.character_id.is_not(None))
        .group_by(character_slots.c.character_id)
        .all()
    )

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
    # The filesystem is authoritative for display availability.  DB metadata can
    # lag behind files restored from a persistent uploads volume; discovering the
    # files here avoids both missing saved-deck icons and speculative per-icon 404s.
    template_inventory = get_character_template_inventory(UPLOAD_DIR)
    res = []
    for character in characters:
        template_path = template_inventory.get(character.id)
        tpl_filename = template_path.name if template_path else None
        is_avail = template_path is not None
        if is_avail:
            icon_url = f"/api/char-icon/{character.id}.png?v={template_path.stem}"
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
    if "is_arena_relevant" in body and not isinstance(body["is_arena_relevant"], bool):
        raise HTTPException(status_code=422, detail="is_arena_relevant must be a boolean")
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
        is_arena_relevant=body.get("is_arena_relevant", False),
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
    if "is_arena_relevant" in body:
        if not isinstance(body["is_arena_relevant"], bool):
            raise HTTPException(status_code=422, detail="is_arena_relevant must be a boolean")
        char.is_arena_relevant = body["is_arena_relevant"]
    db.commit()
    db.refresh(char)
    return {"ok": True, "character": {"id": char.id, "name": char.name}}

@app.get("/api/admin/templates")
def get_templates_list(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """AI学習に使用しているテンプレート画像の一覧を返す"""
    template_dir = str(Path(UPLOAD_DIR) / "templates")
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
    """Legacy destructive endpoint intentionally disabled; use per-file quarantine."""
    raise HTTPException(status_code=409, detail="テンプレートは管理画面から個別に無効化してください")


def _template_roots() -> tuple[Path, Path, Path]:
    upload_root = Path(UPLOAD_DIR)
    return upload_root, upload_root / "templates", upload_root / "template_quarantine"


def _invalidate_template_matcher_cache() -> None:
    from services.template_matcher import invalidate_template_cache
    invalidate_template_cache()


def _refresh_character_template_metadata(db: Session, character_ids: set[int]) -> None:
    _, active_root, _ = _template_roots()
    for character_id in character_ids:
        character = db.get(models.Character, character_id)
        if character is None:
            continue
        representative = representative_template(active_root, character_id)
        character.is_template_available = representative is not None
        character.template_filename = representative.name if representative else None


def _template_audit(
    db: Session, actor_id: int, action: str, *, source_character_id=None,
    target_character_id=None, source_filename=None, target_filename=None,
    digest=None, review_id=None, success=True,
):
    db.add(models.CharacterTemplateAudit(
        actor_id=actor_id,
        action=action,
        source_character_id=source_character_id,
        target_character_id=target_character_id,
        source_filename=source_filename,
        target_filename=target_filename,
        sha256=digest,
        review_id=review_id,
        success=success,
    ))


def _record_failed_template_audit(db: Session, actor_id: int, action: str, **values) -> None:
    """Best-effort failure audit; never hides the original operation error."""
    try:
        db.rollback()
        _template_audit(db, actor_id, action, success=False, **values)
        db.commit()
    except Exception as audit_error:
        db.rollback()
        print(f"[template-management] failed to persist failure audit action={action}: {audit_error}")


@app.get("/api/admin/character-templates")
def list_character_templates(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
    state: Literal["active", "quarantine"] = "active",
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    query: str = Query("", max_length=100),
    character_id: int | None = Query(None, ge=1),
):
    _, active_root, quarantine_root = _template_roots()
    exact_character_id = character_id if isinstance(character_id, int) else None
    selected_paths = list_template_paths(active_root if state == "active" else quarantine_root)
    if exact_character_id is not None:
        selected_paths = [
            path for path in selected_paths
            if parse_template_name(path.name).character_id == exact_character_id
        ]
    character_ids = {
        parse_template_name(path.name).character_id for path in selected_paths
    }
    characters = {
        row.id: row for row in db.query(models.Character).filter(models.Character.id.in_(character_ids or {-1})).all()
    }
    pending_query = db.query(
        models.CharacterTemplateReview.predicted_character_id,
        func.count(models.CharacterTemplateReview.id),
    ).filter(models.CharacterTemplateReview.status == "pending")
    if exact_character_id is not None:
        pending_query = pending_query.filter(
            models.CharacterTemplateReview.predicted_character_id == exact_character_id
        )
    pending_counts = dict(pending_query.group_by(
        models.CharacterTemplateReview.predicted_character_id
    ).all())
    active_representatives = {}
    for path in selected_paths if state == "active" else []:
        parsed = parse_template_name(path.name)
        current = active_representatives.get(parsed.character_id)
        if current is None or parsed.generation > parse_template_name(current.name).generation:
            active_representatives[parsed.character_id] = path
    normalized_query = query.strip().casefold()
    entries = [
        path for path in selected_paths
        if not normalized_query or normalized_query in (
            f"{parse_template_name(path.name).character_id} "
            f"{characters.get(parse_template_name(path.name).character_id).name if characters.get(parse_template_name(path.name).character_id) else ''}"
        ).casefold()
    ]
    total = len(entries)
    page_paths = entries[offset:offset + limit]
    page_character_ids = sorted({parse_template_name(path.name).character_id for path in page_paths})
    return {
        "characters": [
            {
                "character_id": character_id,
                "character_name": characters.get(character_id).name if characters.get(character_id) else f"ID:{character_id}",
                "active": [describe_template(path, active=True, representative=path == active_representatives.get(character_id)) for path in page_paths if state == "active" and parse_template_name(path.name).character_id == character_id],
                "quarantined": [describe_template(path, active=False, representative=False) for path in page_paths if state == "quarantine" and parse_template_name(path.name).character_id == character_id],
                "pending_count": pending_counts.get(character_id, 0),
                "representative_url": (
                    f"/api/admin/character-templates/assets/active/{active_representatives[character_id].name}"
                    if active_representatives.get(character_id) else None
                ),
            }
            for character_id in page_character_ids
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/admin/character-template-reviews")
def list_character_template_reviews(
    status: str = "pending",
    offset: int = Query(0, ge=0),
    limit: int = Query(15, ge=1, le=100),
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    if status not in {"pending", "kept", "reassigned", "disabled"}:
        raise HTTPException(status_code=422, detail="Invalid review status")
    query = db.query(models.CharacterTemplateReview).filter(
        models.CharacterTemplateReview.status == status
    )
    total = query.count()
    reviews = query.order_by(models.CharacterTemplateReview.created_at.desc(), models.CharacterTemplateReview.id.desc()).offset(offset).limit(limit).all()
    return {"reviews": [{
        "id": review.id,
        "status": review.status,
        "predicted_character_id": review.predicted_character_id,
        "corrected_character_id": review.corrected_character_id,
        "matched_template_filename": review.matched_template_filename,
        "corrected_template_filename": review.corrected_template_filename,
        "similarity": review.similarity,
        "tournament_id": review.tournament_id,
        "player_id": review.player_id,
        "seed_number": review.seed_number,
        "champion_slot": review.champion_slot,
        "round_number": review.round_number,
        "position": review.position,
        "created_at": review.created_at,
    } for review in reviews], "total": total, "offset": offset, "limit": limit}


@app.get("/api/admin/character-templates/assets/{state}/{filename}")
def get_admin_template_asset(
    state: Literal["active", "quarantine"], filename: str,
    _: models.AppUser = Depends(auth_module.require_admin),
):
    _, active_root, quarantine_root = _template_roots()
    try:
        path = safe_template_path(active_root if state == "active" else quarantine_root, filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Template not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": NO_STORE_CACHE_CONTROL})


@app.post("/api/admin/character-templates/{character_id}/{filename}/disable")
def disable_character_template(
    character_id: int, filename: str, body: dict | None = None,
    admin: models.AppUser = Depends(auth_module.require_admin), db: Session = Depends(get_db),
):
    upload_root, _, _ = _template_roots()
    moved = None
    with template_operation_lock(upload_root):
        try:
            digest = template_sha256(safe_template_path(upload_root / "templates", filename, character_id))
            original, destination = move_to_quarantine(upload_root, character_id, filename)
            moved = (destination, original)
            _refresh_character_template_metadata(db, {character_id})
            _template_audit(db, admin.id, "disable", source_character_id=character_id, source_filename=filename, target_filename=destination.name, digest=digest)
            db.commit()
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            _record_failed_template_audit(db, admin.id, "disable", source_character_id=character_id, source_filename=filename)
            raise HTTPException(status_code=404, detail="Template not found or unavailable") from exc
        except Exception:
            db.rollback()
            if moved:
                rollback_move(*moved)
            raise
    _invalidate_template_matcher_cache()
    return {"ok": True, "filename": destination.name}


@app.post("/api/admin/character-templates/{character_id}/{filename}/restore")
def restore_character_template(
    character_id: int, filename: str,
    admin: models.AppUser = Depends(auth_module.require_admin), db: Session = Depends(get_db),
):
    upload_root, _, _ = _template_roots()
    moved = None
    with template_operation_lock(upload_root):
        try:
            digest = template_sha256(safe_template_path(upload_root / "template_quarantine", filename, character_id))
            original, destination = restore_from_quarantine(upload_root, character_id, filename)
            moved = (destination, original)
            _refresh_character_template_metadata(db, {character_id})
            _template_audit(db, admin.id, "restore", source_character_id=character_id, source_filename=filename, target_filename=destination.name, digest=digest)
            db.commit()
        except (ValueError, FileNotFoundError) as exc:
            _record_failed_template_audit(db, admin.id, "restore", source_character_id=character_id, source_filename=filename)
            raise HTTPException(status_code=404, detail="Quarantined template not found") from exc
        except Exception:
            db.rollback()
            if moved:
                rollback_move(*moved)
            raise
    _invalidate_template_matcher_cache()
    return {"ok": True, "filename": destination.name}


@app.post("/api/admin/character-templates/{character_id}/{filename}/reassign")
def reassign_character_template(
    character_id: int, filename: str, body: dict,
    admin: models.AppUser = Depends(auth_module.require_admin), db: Session = Depends(get_db),
):
    try:
        target_character_id = int(body.get("target_character_id"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="target_character_id is required") from exc
    if target_character_id == character_id or db.get(models.Character, target_character_id) is None:
        raise HTTPException(status_code=422, detail="A different existing target Character is required")
    upload_root, active_root, _ = _template_roots()
    moved = None
    with template_operation_lock(upload_root):
        try:
            source = safe_template_path(active_root, filename, character_id)
            digest = template_sha256(source)
            original, destination, duplicate = reassign_active_template(
                upload_root, character_id, target_character_id, filename
            )
            moved = (destination, original)
            representative = representative_template(active_root, target_character_id)
            target_filename = representative.name if duplicate and representative else destination.name
            _refresh_character_template_metadata(db, {character_id, target_character_id})
            _template_audit(db, admin.id, "reassign", source_character_id=character_id, target_character_id=target_character_id, source_filename=filename, target_filename=target_filename, digest=digest)
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            if moved:
                rollback_move(*moved)
            _record_failed_template_audit(db, admin.id, "reassign", source_character_id=character_id, target_character_id=target_character_id, source_filename=filename)
            raise HTTPException(status_code=409, detail="Template state changed; reload and retry") from exc
        except Exception:
            db.rollback()
            if moved:
                rollback_move(*moved)
            raise
    _invalidate_template_matcher_cache()
    return {"ok": True, "filename": target_filename, "duplicate": duplicate}


@app.delete("/api/admin/character-templates/{character_id}/{filename}")
def permanently_delete_character_template(
    character_id: int, filename: str, confirm: str = Query(...),
    admin: models.AppUser = Depends(auth_module.require_admin), db: Session = Depends(get_db),
):
    if confirm != "DELETE":
        raise HTTPException(status_code=422, detail="Permanent deletion requires confirm=DELETE")
    upload_root, _, quarantine_root = _template_roots()
    with template_operation_lock(upload_root):
        tombstone = None
        original = None
        try:
            path = safe_template_path(quarantine_root, filename, character_id)
            if not path.is_file():
                raise FileNotFoundError(filename)
            digest = template_sha256(path)
            original = path
            tombstone = quarantine_root / f".{filename}.{secrets.token_hex(8)}.deleting"
            os.replace(path, tombstone)
            _template_audit(db, admin.id, "permanent_delete", source_character_id=character_id, source_filename=filename, digest=digest)
            db.commit()
        except (ValueError, FileNotFoundError) as exc:
            _record_failed_template_audit(db, admin.id, "permanent_delete", source_character_id=character_id, source_filename=filename)
            raise HTTPException(status_code=404, detail="Quarantined template not found") from exc
        except Exception:
            db.rollback()
            if tombstone and original and tombstone.exists():
                os.replace(tombstone, original)
            raise
        try:
            tombstone.unlink()
        except OSError as exc:
            print(f"[template-management] tombstone cleanup failed file={filename}: {exc}")
    _invalidate_template_matcher_cache()
    return {"ok": True}


@app.post("/api/admin/character-template-reviews/{review_id}/resolve")
def resolve_character_template_review(
    review_id: int, body: dict,
    admin: models.AppUser = Depends(auth_module.require_admin), db: Session = Depends(get_db),
):
    action = body.get("action")
    if action not in {"keep", "reassign", "disable"}:
        raise HTTPException(status_code=422, detail="Invalid review action")
    review = db.query(models.CharacterTemplateReview).filter(
        models.CharacterTemplateReview.id == review_id
    ).with_for_update().first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.status != "pending":
        raise HTTPException(status_code=409, detail="Review is already resolved")
    upload_root, active_root, _ = _template_roots()
    moved = None
    with template_operation_lock(upload_root):
        try:
            source_path = safe_template_path(active_root, review.matched_template_filename, review.predicted_character_id)
            digest = template_sha256(source_path)
            target_character_id = None
            target_filename = None
            if action == "keep":
                review.status = "kept"
            elif action == "disable":
                original, destination = move_to_quarantine(upload_root, review.predicted_character_id, review.matched_template_filename)
                moved = (destination, original)
                target_filename = destination.name
                review.status = "disabled"
            else:
                target_character_id = int(body.get("target_character_id") or review.corrected_character_id)
                if db.get(models.Character, target_character_id) is None:
                    raise HTTPException(status_code=422, detail="Target Character not found")
                original, destination, duplicate = reassign_active_template(
                    upload_root, review.predicted_character_id, target_character_id, review.matched_template_filename
                )
                moved = (destination, original)
                target_filename = (representative_template(active_root, target_character_id) if duplicate else destination).name
                review.status = "reassigned"
            review.resolved_by = admin.id
            review.resolved_at = datetime.now(timezone.utc)
            affected_ids = {review.predicted_character_id}
            if target_character_id is not None:
                affected_ids.add(target_character_id)
            _refresh_character_template_metadata(db, affected_ids)
            _template_audit(db, admin.id, action, source_character_id=review.predicted_character_id, target_character_id=target_character_id, source_filename=review.matched_template_filename, target_filename=target_filename, digest=digest, review_id=review.id)
            db.commit()
        except HTTPException:
            if moved:
                rollback_move(*moved)
            _record_failed_template_audit(db, admin.id, action, source_character_id=review.predicted_character_id, source_filename=review.matched_template_filename, review_id=review.id)
            raise
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            if moved:
                rollback_move(*moved)
            _record_failed_template_audit(db, admin.id, action, source_character_id=review.predicted_character_id, source_filename=review.matched_template_filename, review_id=review.id)
            raise HTTPException(status_code=409, detail="Template state changed; reload and retry") from exc
        except Exception:
            db.rollback()
            if moved:
                rollback_move(*moved)
            raise
    _invalidate_template_matcher_cache()
    return {"ok": True, "status": review.status, "target_filename": target_filename}

@app.get("/api/admin/all-characters")
def get_all_characters_admin(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    query: str = Query("", max_length=100),
    rarity: str = Query("", max_length=20),
    class_type: str = Query("", max_length=20),
):
    """Return one filtered admin page; scan template filenames once per request."""
    template_dir = Path(UPLOAD_DIR) / "templates"
    chars_query = db.query(models.Character).filter(models.Character.id != EMPTY_SLOT_CHARACTER_ID)
    normalized_query = query.strip()
    if normalized_query:
        chars_query = chars_query.filter(models.Character.name.ilike(f"%{normalized_query}%"))
    if rarity:
        chars_query = chars_query.filter(models.Character.rarity == rarity)
    if class_type:
        chars_query = chars_query.filter(models.Character.class_type == class_type)
    total = chars_query.count()
    chars = chars_query.order_by(models.Character.name, models.Character.id).offset(offset).limit(limit).all()
    page_character_ids = {character.id for character in chars}
    template_counts: dict[int, int] = {}
    representatives: dict[int, Path] = {}
    for template_path in list_template_paths(template_dir):
        parsed = parse_template_name(template_path.name)
        if parsed.character_id not in page_character_ids:
            continue
        template_counts[parsed.character_id] = template_counts.get(parsed.character_id, 0) + 1
        current = representatives.get(parsed.character_id)
        if current is None or parsed.generation > parse_template_name(current.name).generation:
            representatives[parsed.character_id] = template_path
    result = []
    for c in chars:
        template_path = representatives.get(c.id)
        has_tpl = template_path is not None
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
            "is_arena_relevant": c.is_arena_relevant,
            "has_template": has_tpl,
            "template_count": tpl_count,
            "image_url": (
                f"/api/char-icon/{c.id}.png?v={template_path.stem}"
                if template_path else None
            ),
        })
    return {
        "characters": result,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_next": offset + len(result) < total,
        "page": offset // limit + 1,
    }

@app.delete("/api/characters/{char_id}")
def delete_character(
    char_id: int,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db)
):
    """Character deletion never bypasses recoverable template management."""
    if char_id == EMPTY_SLOT_CHARACTER_ID:
        raise HTTPException(status_code=400, detail="空枠は削除できません")
    char = db.query(models.Character).filter(models.Character.id == char_id).first()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    upload_root, active_root, quarantine_root = _template_roots()
    related_files = [
        path for path in list_template_paths(active_root) + list_template_paths(quarantine_root)
        if parse_template_name(path.name).character_id == char_id
    ]
    if related_files:
        raise HTTPException(status_code=409, detail="テンプレートを無効化し、隔離済み画像を完全削除してからCharacterを削除してください")
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
        _, active_root, quarantine_root = _template_roots()
        if any(
            parse_template_name(path.name).character_id == from_id
            for path in list_template_paths(active_root) + list_template_paths(quarantine_root)
        ):
            db.rollback()
            raise HTTPException(status_code=409, detail="統合元テンプレートを管理画面で整理してからCharacterを統合してください")
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

TOURNAMENT_ADMIN_FIELDS = frozenset({
    "game_start_date", "display_order", "is_champion_arena", "has_match_data", "deck_registration_phases",
})


def apply_tournament_admin_settings(tournament, changes, db):
    if {"deck_registration_phases", "is_champion_arena", "has_match_data"} & changes.keys():
        raise HTTPException(403, "Manage arena settings on the championship title")
    for field in {"game_start_date", "display_order"} & changes.keys():
        setattr(tournament, field, changes[field])


@app.post("/api/tournaments", response_model=schemas.Tournament)
def create_tournament(
    tournament: schemas.TournamentBase, 
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user)
):
    if current_user.role != "admin" and TOURNAMENT_ADMIN_FIELDS & tournament.model_fields_set:
        raise HTTPException(403, "Tournament settings are administrator-only")
    title_fields = {"deck_registration_phases", "is_champion_arena", "has_match_data"}
    if title_fields & tournament.model_fields_set:
        raise HTTPException(403, "Manage arena settings on the championship title")
    # Only the Championship is editable; legacy compatibility columns use old defaults.
    data = tournament.model_dump(exclude=title_fields)

    # 省略時だけプロフィール値を初期値にする。明示的な null は維持する。
    if "provider_game_start_date" not in tournament.model_fields_set:
        data["provider_game_start_date"] = current_user.game_start_date
    
    # ログインユーザーから提供者名を取得
    data["owner_name"] = current_user.provider_name or "不明な提供者"
    
    # 作成者を記録
    data["created_by"] = current_user.id
    data["publication_status"] = "draft"
    data["published_at"] = None
    data["published_by"] = None
    
    # championship_id から名前などの情報を引き継ぐ
    if tournament.championship_id:
        championship = db.query(models.Championship).filter_by(id=tournament.championship_id).populate_existing().with_for_update().first()
        if championship is None:
            raise HTTPException(404, "Championship not found")
        championship_settings.require_resolved(championship, championship_settings.children(db, championship.id))
        data["name"] = championship.name
        data["date"] = championship.date or tournament.date
    # Legacy callers without a title retain the old defaults; the UI requires a title.

    db_tournament = models.Tournament(**data)
    try:
        db.add(db_tournament)
        db.commit()
        db.refresh(db_tournament)
    except Exception:
        db.rollback()
        raise
    return db_tournament

def require_tournament_manager(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
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
    # Individual dashboards are private even when their tournament contributes
    # to public cross-tournament analysis.
    return require_tournament_viewer(tournament_id, db, current_user)


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
            models.Tournament.has_match_data.is_(True),
        ).all()
    }
    return [
        tournament_id
        for tournament_id in tournament_ids
        if tournament_id in published_ids
    ]


def get_publication_readiness(tournament: models.Tournament, db: Session):
    if tournament.deck_registration_phases:
        return arena_phases.publication_readiness(tournament, db)
    if tournament.registration_scope == "champion_8":
        return validate_champion_publication(tournament, db)
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


def get_dashboard_summary_data(tournament: models.Tournament, db: Session):
    players = db.query(models.Player).filter(
        models.Player.tournament_id == tournament.id
    ).order_by(models.Player.seed_number).all()
    player_ids = [player.id for player in players]
    matches_count = len(arena_phases.effective_matches(db, [tournament.id]))
    deck_sets = arena_phases.initial_deck_sets(db, player_ids) if player_ids else []
    deck_sets_by_player: dict[int, list[models.DeckSet]] = {}
    for deck_set in deck_sets:
        deck_sets_by_player.setdefault(deck_set.player_id, []).append(deck_set)

    deck_set_ids = [deck_set.id for deck_set in deck_sets]
    deck_teams = [team for deck in deck_sets for team in deck.teams] if deck_set_ids else []
    deck_teams_by_set: dict[int, list[models.DeckTeam]] = {}
    for team in deck_teams:
        deck_teams_by_set.setdefault(team.deck_set_id, []).append(team)

    missing_seed_numbers = (
        [
            seed
            for seed in range(1, 65)
            if not any(player.seed_number == seed for player in players)
        ]
        if tournament.registration_scope == "full_64"
        else []
    )
    players_without_decks = []
    players_with_incomplete_decks = []
    representative_team_count = 0

    for player in players:
        player_deck_sets = deck_sets_by_player.get(player.id, [])
        if not player_deck_sets:
            players_without_decks.append({
                "id": player.id,
                "seed_number": player.seed_number,
                "name": player.name,
            })
            continue
        latest_deck_set = sorted(
            player_deck_sets,
            key=lambda deck_set: (deck_set.created_at, deck_set.id),
            reverse=True,
        )[0]
        teams = deck_teams_by_set.get(latest_deck_set.id, [])
        representative_team_count += len(teams)
        incomplete_team_numbers = []
        teams_by_number = {team.team_number: team for team in teams}
        for team_number in range(1, 6):
            team = teams_by_number.get(team_number)
            if not team:
                incomplete_team_numbers.append(team_number)
                continue
            char_ids = [
                team.char1_id,
                team.char2_id,
                team.char3_id,
                team.char4_id,
                team.char5_id,
            ]
            if any(character_id is None for character_id in char_ids):
                incomplete_team_numbers.append(team_number)
        if incomplete_team_numbers:
            players_with_incomplete_decks.append({
                "id": player.id,
                "seed_number": player.seed_number,
                "name": player.name,
                "incomplete_team_numbers": incomplete_team_numbers,
            })

    return {
        "tournament_id": tournament.id,
        "publication_status": tournament.publication_status,
        "is_published": tournament.publication_status == "published",
        "is_in_public_analysis": tournament.publication_status == "published",
        "registered_player_count": len(players),
        "expected_player_count": 8 if tournament.registration_scope == "champion_8" else 64,
        "registered_match_count": matches_count,
        "expected_match_count": 7 if tournament.registration_scope == "champion_8" else 63,
        "registered_team_count": representative_team_count,
        "registered_representative_team_count": representative_team_count,
        "expected_team_count": 40 if tournament.registration_scope == "champion_8" else 320,
        "missing_seed_numbers": missing_seed_numbers,
        "players_without_decks": players_without_decks,
        "players_with_incomplete_decks": players_with_incomplete_decks,
        "readiness": get_publication_readiness(tournament, db),
    }


@app.get("/api/tournaments/{tournament_id}/dashboard/summary")
def get_dashboard_summary(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    return get_dashboard_summary_data(tournament, db)

def _champion_arena_master_payload(tournament: models.Tournament) -> dict:
    return {
        "id": tournament.id,
        "title": tournament.name,
        "game_start_date": tournament.game_start_date,
        "display_order": tournament.display_order,
        "is_champion_arena": tournament.is_champion_arena,
        "has_match_data": tournament.has_match_data,
        "deck_registration_phases": bool(tournament.deck_registration_phases),
    }


@app.get("/api/champion-arena/tournaments", response_model=List[schemas.ArenaResultEvent])
def get_champion_arena_tournaments(db: Session = Depends(get_db)):
    # One title per event; preserve unresolved legacy visibility using only the FK.
    legacy_visible = db.query(models.Tournament.id).filter(
        models.Tournament.championship_id == models.Championship.id,
        models.Tournament.legacy_is_champion_arena.is_(True),
    ).exists()
    titles = db.query(models.Championship).filter(or_(
        models.Championship.is_champion_arena.is_(True),
        models.Championship.is_champion_arena.is_(None) & legacy_visible,
    )).order_by(models.Championship.date.desc().nullslast(), models.Championship.id.desc()).all()
    events = [{"id": f"championship:{title.id}", "championship_id": title.id,
               "source": "championship", "title": title.name, "event_date": title.date,
               "display_order": title.display_order} for title in titles]
    # Retain unlinked legacy targets without guessing associations from names/IDs.
    linked_title = db.query(models.Championship.id).filter(models.Championship.id == models.Tournament.championship_id).exists()
    legacy = db.query(models.Tournament.id, models.Tournament.name, models.Tournament.game_start_date, models.Tournament.display_order).filter(~linked_title, models.Tournament.legacy_is_champion_arena.is_(True)).all()
    events.extend({"id": f"legacy-tournament:{row.id}", "tournament_id": row.id,
                   "championship_id": None, "source": "legacy_tournament", "title": row.name,
                   "event_date": row.game_start_date, "display_order": row.display_order} for row in legacy)
    events.sort(key=lambda row: (row["display_order"] if row["display_order"] is not None else float("-inf"), row["event_date"] or date_type.min, row.get("tournament_id") or row.get("championship_id") or 0, row["id"]), reverse=True)
    return events


@app.get("/api/admin/champion-arena-tournaments", response_model=List[schemas.ChampionArenaTournament])
def get_admin_champion_arena_tournaments(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    # Administrators must also be able to configure tournaments whose flag is off.
    tournaments = db.query(models.Tournament).order_by(models.Tournament.display_order.desc().nullslast(), models.Tournament.id.desc()).all()
    return [_champion_arena_master_payload(tournament) for tournament in tournaments]


@app.post("/api/admin/champion-arena-tournaments", response_model=schemas.ChampionArenaTournament)
def create_champion_arena_tournament(
    body: schemas.ChampionArenaTournamentBase,
    admin: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    raise HTTPException(409, "Create a championship title, then register tournament data under that title")


@app.put("/api/admin/champion-arena-tournaments/{tournament_id}", response_model=schemas.ChampionArenaTournament)
def update_champion_arena_tournament(
    tournament_id: int,
    body: schemas.ChampionArenaTournamentBase,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    tournament = db.get(models.Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    changes = body.model_dump(exclude_unset=True)
    apply_tournament_admin_settings(tournament, changes, db)
    tournament.name = body.title.strip()
    if "game_start_date" in changes:
        tournament.game_start_date = body.game_start_date
        tournament.date = body.game_start_date or tournament.date
    db.commit()
    db.refresh(tournament)
    invalidate_dashboard_cache(tournament_id)
    return _champion_arena_master_payload(tournament)


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
        query = query.filter(
            models.Tournament.publication_status == "published",
            models.Tournament.has_match_data.is_(True),
        )
    tournaments = query.order_by(
        models.Tournament.created_at.desc(),
        models.Tournament.id.desc(),
    ).all()
    
    result = []
    for t in tournaments:
        t_schema = schemas.Tournament.model_validate(t)
        if mine or current_user is not None and current_user.role == "admin":
            if t.creator:
                t_schema.creator_email = t.creator.email
        else:
            # The public selector is intentionally a minimal analysis input,
            # not an individual tournament detail API.
            t_schema = t_schema.model_copy(update={
                "owner_name": None,
                "created_by": None,
                "creator_email": None,
            })
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
    tournament: schemas.TournamentUpdate,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user)
):
    db_tournament = require_tournament_manager(tournament_id, db, current_user)
    changes = tournament.model_dump(exclude_unset=True)
    restricted = TOURNAMENT_ADMIN_FIELDS | {"date", "season", "owner_name"}
    if current_user.role != "admin" and restricted & changes.keys():
        raise HTTPException(403, "Tournament settings are administrator-only")
    observed_title_id = db_tournament.championship_id
    target_title_id = changes.get("championship_id", observed_title_id)
    titles = {}
    title_ids = {value for value in (db_tournament.championship_id, target_title_id) if value is not None}
    if title_ids:
        titles = {row.id: row for row in db.query(models.Championship).filter(models.Championship.id.in_(title_ids)).order_by(models.Championship.id).populate_existing().with_for_update().all()}
    db_tournament = db.query(models.Tournament).filter_by(id=tournament_id).populate_existing().with_for_update(of=models.Tournament).first()
    if db_tournament is None:
        db.rollback()
        raise HTTPException(404, "Tournament not found")
    if db_tournament.championship_id != observed_title_id:
        db.rollback()
        raise HTTPException(409, "Tournament title changed while acquiring locks; reload before saving")
    if current_user.role != "admin" and db_tournament.created_by != current_user.id:
        db.rollback()
        raise HTTPException(403, "Tournament manager required")

    # registration_scope は作成時に固定する。Pydantic の既定値を
    # 「クライアントが明示した値」と誤認しないよう fields_set を使う。
    if (
        "registration_scope" in tournament.model_fields_set
        and tournament.registration_scope != db_tournament.registration_scope
    ):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="registration_scope cannot be changed after tournament creation",
        )

    try:
        # Only explicitly supplied provider fields are updated. Do not re-sync dates.
        if "name" in changes:
            db_tournament.name = tournament.name
        if "championship_id" in changes:
            title = titles.get(tournament.championship_id)
            if title is None:
                raise HTTPException(409, "Choose an existing championship title")
            if tournament.championship_id != db_tournament.championship_id:
                linked_tournaments = championship_settings.children(db, title.id)
                championship_settings.require_resolved(title, linked_tournaments)
                # Reassignment must not bypass title history protection.
                target = championship_settings.describe(title, linked_tournaments)
                championship_settings.ensure_history_visible(db, [db_tournament], {key: target[key] for key in championship_settings.FIELDS})
            db_tournament.name = title.name
            db_tournament.championship_id = tournament.championship_id
            db_tournament.championship = title
        if "provider_game_start_date" in changes:
            db_tournament.provider_game_start_date = tournament.provider_game_start_date
        if current_user.role == "admin":
            for field in ("date", "season", "owner_name"):
                if field in changes:
                    setattr(db_tournament, field, changes[field])
            apply_tournament_admin_settings(db_tournament, changes, db)

        db.commit()
        db.refresh(db_tournament)
    except Exception:
        db.rollback()
        raise
    invalidate_dashboard_cache(tournament_id)
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
    if tournament.registration_scope == "champion_8":
        tournament = require_locked_champion_tournament_manager(
            tournament_id, db, current_user
        )
    publish = body.get("published") is True
    readiness = get_publication_readiness(tournament, db)

    if publish and not readiness["can_publish"]:
        if tournament.registration_scope == "champion_8":
            raise HTTPException(status_code=409, detail=readiness)
        raise HTTPException(
            status_code=400,
            detail="未完成の編成データがあるため公開できません",
        )

    # ステータスが変わった場合のみ処理
    if tournament.registration_scope == "champion_8":
        status_changed = (tournament.publication_status == "published") != publish
        try:
            if publish:
                stats = _compute_dashboard_stats(tournament_id, db, current_user)
                if not tournament.deck_registration_phases:
                    stats = enrich_champion_snapshot_stats(stats, tournament_id, db)
                apply_snapshot(tournament_id, stats, db)
                tournament.publication_status = "published"
                tournament.published_at = datetime.now(timezone.utc)
                tournament.published_by = current_user.id
            else:
                tournament.publication_status = "draft"
                tournament.published_at = None
                tournament.published_by = None
                db.query(models.TournamentSnapshot).filter(
                    models.TournamentSnapshot.tournament_id == tournament_id
                ).delete(synchronize_session=False)
            db.commit()
            db.refresh(tournament)
        except Exception:
            db.rollback()
            raise
        if status_changed:
            invalidate_dashboard_cache_safely(tournament_id)
        return {
            "ok": True,
            "publication_status": tournament.publication_status,
            "published_at": tournament.published_at,
            "published_by": tournament.published_by,
            "readiness": readiness,
        }

    status_changed = (tournament.publication_status == "published") != publish

    tournament.publication_status = "published" if publish else "draft"
    tournament.published_at = datetime.now(timezone.utc) if publish else None
    tournament.published_by = current_user.id if publish else None
    db.commit()
    db.refresh(tournament)
    
    if status_changed:
        invalidate_dashboard_cache(tournament_id)
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
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    with icon_mutation_lock(PLAYER_ICONS_DIR):
        db_tournament = require_tournament_manager(tournament_id, db, current_user)
        if db.query(models.ArenaDeckRegistration.id).filter_by(tournament_id=tournament_id).first() or db.query(models.ArenaMatchRevision.id).filter_by(tournament_id=tournament_id).first():
            raise HTTPException(409, "Phase history exists; export and review a separate deletion plan first")
        invalidate_dashboard_cache(tournament_id)
        db.delete(db_tournament)
        db.commit()
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

def championship_admin_payload(title, tournaments):
    return {**schemas.ChampionshipResponse.model_validate(title).model_dump(),
            **championship_settings.describe(title, tournaments),
            "debut_character_ids": title.debut_character_ids or []}


def validated_debut_characters(db, ids):
    if not ids:
        return []
    known = set(db.scalars(select(models.Character.id).where(models.Character.id.in_(ids))))
    if known != set(ids) or EMPTY_SLOT_CHARACTER_ID in known:
        raise HTTPException(422, "Unknown debut character")
    return list(dict.fromkeys(ids))


@app.get("/api/admin/championships", response_model=List[schemas.ChampionshipAdminResponse])
def get_admin_championships(db: Session = Depends(get_db), admin: models.AppUser = Depends(auth_module.require_admin)):
    titles = db.query(models.Championship).order_by(models.Championship.date.desc(), models.Championship.id.desc()).all()
    grouped = {}
    for row in db.query(models.Tournament).order_by(models.Tournament.id).all():
        grouped.setdefault(row.championship_id, []).append(row)
    return [championship_admin_payload(title, grouped.get(title.id, [])) for title in titles]


@app.post("/api/championships", response_model=schemas.ChampionshipAdminResponse)
def create_championship(
    championship: schemas.ChampionshipCreate,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.require_admin),
):
    data = championship.model_dump(exclude=championship_settings.FIELDS | {"settings_revision", "apply_to_existing"})
    data.update({key: getattr(championship, key) if key in championship.model_fields_set else value for key, value in championship_settings.DEFAULTS.items()})
    data["created_by"] = current_user.id
    data["debut_character_ids"] = validated_debut_characters(db, championship.debut_character_ids)
    db_championship = models.Championship(**data)
    db.add(db_championship)
    db.commit()
    db.refresh(db_championship)
    return championship_admin_payload(db_championship, [])

@app.put("/api/championships/{id}", response_model=schemas.ChampionshipAdminResponse)
def update_championship(
    id: int,
    championship: schemas.ChampionshipCreate,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.require_admin),
):
    title = db.query(models.Championship).filter_by(id=id).populate_existing().with_for_update().first()
    if title is None:
        raise HTTPException(404, "Championship not found")
    tournaments = championship_settings.children(db, id, lock=True)
    try:
        affected = championship_settings.save(db, title, championship, tournaments)
        previous_date = title.date
        changes = championship.model_dump(exclude_unset=True)
        if "debut_character_ids" in changes:
            if championship.settings_revision is not None and not (championship_settings.FIELDS & championship.model_fields_set):
                if championship.settings_revision != championship_settings.describe(title, tournaments)["settings_revision"]:
                    raise HTTPException(409, "Title or linked tournaments changed; reload before saving")
            title.debut_character_ids = validated_debut_characters(db, changes["debut_character_ids"])
        for field in ("name", "date", "start_date", "owner_name", "display_order"):
            if field in changes:
                setattr(title, field, changes[field])
        if "date" in changes and championship.date is not None and championship.date != previous_date:
            for row in tournaments:
                if row.date != championship.date:
                    row.date = championship.date
                    affected.append(row.id)
        db.commit()
        db.refresh(title)
    except Exception:
        db.rollback()
        raise
    for tournament_id in set(affected):
        invalidate_dashboard_cache(tournament_id)
    return championship_admin_payload(title, tournaments)

@app.delete("/api/championships/{id}")
def delete_championship(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.require_admin),
):
    """大会シリーズ削除（管理者限定）"""
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    if db.query(models.Tournament.id).filter_by(championship_id=id).first():
        raise HTTPException(409, "This title has linked tournaments; deleting it would lose settings and result identity")
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
    tournaments = query.order_by(models.Tournament.created_at.desc()).all()
    result = []
    for tournament in tournaments:
        item = schemas.Tournament.model_validate(tournament)
        can_view_owner_metadata = bool(
            current_user
            and (current_user.role == "admin" or tournament.created_by == current_user.id)
        )
        if can_view_owner_metadata and tournament.creator:
            item.creator_email = tournament.creator.email
        elif not can_view_owner_metadata:
            item = item.model_copy(update={
                "owner_name": None,
                "created_by": None,
                "creator_email": None,
            })
        result.append(item)
    return result


def require_champion_tournament_viewer(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    tournament = require_tournament_viewer(tournament_id, db, current_user)
    if tournament.registration_scope != "champion_8":
        raise HTTPException(
            status_code=409,
            detail="Champion slot API is available only for champion_8 tournaments",
        )
    return tournament


def require_champion_tournament_manager(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    tournament = require_tournament_manager(tournament_id, db, current_user)
    if tournament.registration_scope != "champion_8":
        raise HTTPException(
            status_code=409,
            detail="Champion slot API is available only for champion_8 tournaments",
        )
    return tournament


def require_locked_champion_tournament_manager(
    tournament_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> models.Tournament:
    """Lock Tournament first, then recheck authorization, scope and status."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    tournament = (
        db.query(models.Tournament)
        .filter(models.Tournament.id == tournament_id)
        .populate_existing()
        .with_for_update(of=models.Tournament)
        .first()
    )
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if current_user.role != "admin" and tournament.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this tournament")
    if tournament.registration_scope != "champion_8":
        raise HTTPException(status_code=409, detail="Champion API is available only for champion_8 tournaments")
    return tournament


def require_unpublished_champion_edit(tournament: models.Tournament) -> None:
    if tournament.publication_status == "published":
        raise HTTPException(
            status_code=409,
            detail="Unpublish this tournament before editing it, then validate and publish it again.",
        )


def validate_champion_slot(champion_slot: int) -> None:
    if not 1 <= champion_slot <= 8:
        raise HTTPException(status_code=422, detail="champion slot must be between 1 and 8")


def champion_seed_range(champion_slot: int) -> tuple[int, int]:
    validate_champion_slot(champion_slot)
    return (champion_slot - 1) * 8 + 1, champion_slot * 8


def validate_champion_seed(champion_slot: int, seed_number: int | None) -> None:
    if seed_number is None:
        return
    minimum, maximum = champion_seed_range(champion_slot)
    if not minimum <= seed_number <= maximum:
        raise HTTPException(
            status_code=422,
            detail=f"seed_number for champion slot {champion_slot} must be null or between {minimum} and {maximum}",
        )


def require_champion_player_manager(
    tournament_id: int,
    player_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> tuple[models.Tournament, models.Player]:
    tournament = require_champion_tournament_manager(tournament_id, db, current_user)
    player = db.query(models.Player).filter(
        models.Player.id == player_id,
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return tournament, player


def require_locked_champion_player_manager(
    tournament_id: int,
    player_id: int,
    db: Session,
    current_user: models.AppUser | None,
) -> tuple[models.Tournament, models.Player]:
    tournament = require_locked_champion_tournament_manager(
        tournament_id, db, current_user
    )
    require_unpublished_champion_edit(tournament)
    player = db.query(models.Player).filter(
        models.Player.id == player_id,
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return tournament, player


def champion_teams_response(player: models.Player, deck_set: models.DeckSet | None):
    if deck_set is None:
        return {
            "player_id": player.id,
            "tournament_id": player.tournament_id,
            "champion_slot": player.champion_slot,
            "deck_set_id": None,
            "status": "not_saved",
            "teams": [],
        }
    teams = sorted(deck_set.teams, key=lambda team: team.team_number)
    response_teams = []
    complete = len(teams) == 5
    for team in teams:
        character_ids = [getattr(team, f"char{slot}_id") for slot in range(1, 6)]
        complete = complete and team.team_number in range(1, 6) and all(
            character_id is not None for character_id in character_ids
        )
        response_teams.append({
            "team_number": team.team_number,
            "character_ids": character_ids,
            "collection_levels": get_team_collection_levels(team),
        })
    return {
        "player_id": player.id,
        "tournament_id": player.tournament_id,
        "champion_slot": player.champion_slot,
        "deck_set_id": deck_set.id,
        "status": "complete" if complete else "incomplete",
        "teams": response_teams,
    }


def validate_champion_teams_payload(data: schemas.ChampionTeamsUpsert) -> list[tuple[int, list[int], list[str | None], list[schemas.ChampionTeamCharacterInput]]]:
    if len(data.teams) != 5:
        raise HTTPException(status_code=422, detail="Exactly five teams are required")
    team_numbers = [team.team_number for team in data.teams]
    if sorted(team_numbers) != [1, 2, 3, 4, 5]:
        raise HTTPException(status_code=422, detail="team_number must contain each value from 1 to 5 exactly once")
    normalized = []
    all_character_ids = []
    for team in data.teams:
        if len(team.characters) != 5:
            raise HTTPException(status_code=422, detail="Each team must contain exactly five characters")
        character_ids = [character.id for character in team.characters]
        if any(character_id <= 0 for character_id in character_ids):
            raise HTTPException(status_code=422, detail="All character slots must contain a resolved character or the empty-slot marker")
        real_character_ids = [character_id for character_id in character_ids if character_id != EMPTY_SLOT_CHARACTER_ID]
        if len(set(real_character_ids)) != len(real_character_ids):
            raise HTTPException(status_code=422, detail="Characters must not be duplicated within a team")
        all_character_ids.extend(real_character_ids)
        normalized.append((
            team.team_number,
            character_ids,
            [
                None if character.id == EMPTY_SLOT_CHARACTER_ID
                else character.collection_level if character.collection_level in COLLECTION_VALUES else None
                for character in team.characters
            ],
            team.characters,
        ))
    if len(set(all_character_ids)) != len(all_character_ids):
        raise HTTPException(status_code=422, detail="Characters must not be duplicated across teams")
    return sorted(normalized, key=lambda item: item[0])


def decode_champion_template_source(data_url: str):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=422, detail="Template source must be a PNG data URL")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Template source is not valid base64") from exc
    if not raw or len(raw) > CHAMPION_TEMPLATE_SOURCE_MAX_BYTES:
        raise HTTPException(status_code=422, detail="Template source exceeds the size limit")
    import cv2 as _cv2
    import numpy as _np
    image = _cv2.imdecode(_np.frombuffer(raw, dtype=_np.uint8), _cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Template source is not a decodable image")
    height, width = image.shape[:2]
    if width > CHAMPION_ICON_MAX_WIDTH or height > CHAMPION_ICON_MAX_HEIGHT or width * height > CHAMPION_ICON_MAX_PIXELS:
        raise HTTPException(status_code=422, detail="Template source dimensions exceed the limit")
    return image, len(raw)


def validate_owned_champion_crop_url(
    url: str,
    tournament_id: int,
    player_id: int,
    *,
    require_lossless: bool = False,
    seed_number: int | None = None,
) -> Path:
    source_path = path_from_upload_url(url)
    match = CHAMPION_CROP_NAME.fullmatch(source_path.name) if source_path else None
    if (
        source_path is None
        or not _is_within(source_path, CROPPED_DIR)
        or match is None
        or int(match.group("tournament")) != tournament_id
        or (match.group("player") != str(player_id) if seed_number is None else match.group("seed") != str(seed_number))
        or (require_lossless and source_path.suffix.lower() != ".png")
        or not source_path.is_file()
    ):
        raise HTTPException(status_code=422, detail="The analysis crop does not belong to this tournament and Player")
    age = time.time() - source_path.stat().st_mtime
    if age < 0 or age > CHAMPION_CROP_TTL_SECONDS:
        raise HTTPException(status_code=422, detail="The analysis crop has expired")
    return source_path


def load_champion_template_source(
    character: schemas.ChampionTeamCharacterInput,
    tournament_id: int,
    player_id: int,
    *, seed_number: int | None = None,
):
    """Load only a live crop issued for the current tournament and Player."""
    if character.template_source_url:
        source_path = validate_owned_champion_crop_url(
            character.template_source_url,
            tournament_id,
            player_id,
            require_lossless=True,
            seed_number=seed_number,
        )
        source_size = source_path.stat().st_size
        if not 0 < source_size <= CHAMPION_TEMPLATE_SOURCE_MAX_BYTES:
            raise HTTPException(status_code=422, detail="Template source exceeds the size limit")
        import cv2 as _cv2
        source_image = _cv2.imread(str(source_path), _cv2.IMREAD_COLOR)
        if source_image is None:
            raise HTTPException(status_code=422, detail="Template source is not a decodable image")
        height, width = source_image.shape[:2]
        if width > CHAMPION_ICON_MAX_WIDTH or height > CHAMPION_ICON_MAX_HEIGHT or width * height > CHAMPION_ICON_MAX_PIXELS:
            raise HTTPException(status_code=422, detail="Template source dimensions exceed the limit")
        return source_image, source_size
    if character.template_source_data_url:
        raise HTTPException(status_code=422, detail="Inline template sources are no longer accepted; analyze the image again")
    raise HTTPException(status_code=422, detail="A corrected Character requires its source crop")


def install_champion_character_template(character_id: int, source_image, db: Session):
    """Install one corrected crop using the shared naming/dedup rules."""
    import cv2 as _cv2

    template_dir = Path(UPLOAD_DIR) / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    # Keep enumeration, duplicate detection, generation allocation, and the
    # write in one lock so concurrent workers cannot choose the same filename.
    with template_operation_lock(Path(UPLOAD_DIR)):
        existing = sorted(
            path for path in list_template_paths(template_dir)
            if parse_template_name(path.name).character_id == character_id
        )
        prepared_source = prepare_character_image(source_image)
        for path in existing:
            existing_image = _cv2.imread(str(path))
            if existing_image is None:
                continue
            try:
                prepared_existing = prepare_character_image(existing_image)
                height, width = prepared_source.shape[:2]
                resized = _cv2.resize(prepared_existing, (width, height))
                similarity = masked_absolute_similarity(
                    prepared_source, resized, collection_match_mask(prepared_source.shape)
                )
                if similarity > 0.92:
                    character = db.get(models.Character, character_id)
                    character.is_template_available = True
                    representative = representative_template(template_dir, character_id)
                    character.template_filename = representative.name if representative else path.name
                    return None
            except Exception:
                continue
        destination = template_dir / next_template_name(template_dir, character_id)
        if not write_lossless_png(str(destination), source_image):
            raise OSError(f"Failed to save template: {destination}")
        character = db.get(models.Character, character_id)
        character.is_template_available = True
        character.template_filename = destination.name
        return destination


def add_template_correction_review(
    db: Session,
    *,
    payload,
    corrected_template_filename: str | None,
    tournament: models.Tournament,
    player: models.Player,
    actor: models.AppUser,
) -> None:
    """Record a fresh, uniquely attributable A→B correction without moving A."""
    value = (lambda key: getattr(payload, key, None)) if not isinstance(payload, dict) else payload.get
    try:
        predicted_id = int(value("original_predicted_id"))
        corrected_id = int(value("id"))
        round_number = int(value("round_number"))
        position = int(value("position"))
    except (TypeError, ValueError):
        return
    matched_filename = value("matched_template_filename")
    analysis_token = value("analysis_token")
    match_method = value("match_method")
    if (
        predicted_id == corrected_id
        or not matched_filename
        or not analysis_token
        or match_method != "masked_ccoeff_normed"
        or not corrected_template_filename
        or not (1 <= round_number <= 5 and 1 <= position <= 5)
    ):
        return
    try:
        parsed = parse_template_name(matched_filename)
        matched_path = safe_template_path(Path(UPLOAD_DIR) / "templates", matched_filename, predicted_id)
    except ValueError:
        return
    if parsed.character_id != predicted_id or not matched_path.is_file():
        return
    source_url = value("template_source_url") or value("image_url")
    source_path = path_from_upload_url(source_url) if source_url else None
    source_match = CHAMPION_CROP_NAME.fullmatch(source_path.name) if source_path else None
    if source_match is None or source_match.group("token") != analysis_token:
        return
    if int(source_match.group("tournament")) != tournament.id:
        return
    if source_match.group("player") and int(source_match.group("player")) != player.id:
        return
    if source_match.group("seed") and int(source_match.group("seed")) != player.seed_number:
        return
    exists = db.query(models.CharacterTemplateReview.id).filter(
        models.CharacterTemplateReview.analysis_token == analysis_token,
        models.CharacterTemplateReview.round_number == round_number,
        models.CharacterTemplateReview.position == position,
        models.CharacterTemplateReview.matched_template_filename == matched_filename,
    ).first()
    if exists:
        return
    db.add(models.CharacterTemplateReview(
        predicted_character_id=predicted_id,
        corrected_character_id=corrected_id,
        matched_template_filename=matched_filename,
        corrected_template_filename=corrected_template_filename,
        similarity=value("similarity"),
        tournament_id=tournament.id,
        player_id=player.id,
        seed_number=player.seed_number,
        champion_slot=player.champion_slot,
        round_number=round_number,
        position=position,
        analysis_token=analysis_token,
        match_method=match_method,
        created_by=actor.id,
    ))


@app.get(
    "/api/tournaments/{tournament_id}/champion-slots",
    response_model=schemas.ChampionSlotsResponse,
)
def get_champion_slots(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    tournament = require_champion_tournament_viewer(tournament_id, db, current_user)
    players = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).order_by(models.Player.champion_slot).all()
    player_by_slot = {player.champion_slot: player for player in players}
    return {
        "tournament_id": tournament.id,
        "registration_scope": tournament.registration_scope,
        "slots": [
            {
                "champion_slot": champion_slot,
                "player": player_by_slot.get(champion_slot),
            }
            for champion_slot in range(1, 9)
        ],
    }


@app.put(
    "/api/tournaments/{tournament_id}/champion-slots/{champion_slot}",
    response_model=schemas.ChampionPlayerResponse,
)
def upsert_champion_slot(
    tournament_id: int,
    champion_slot: int,
    body: schemas.ChampionSlotUpsert,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    phase_tournament = require_legacy_registration_path(tournament_id, db, current_user)
    validate_champion_slot(champion_slot)
    validate_champion_seed(champion_slot, body.seed_number)
    tournament = require_locked_champion_tournament_manager(tournament_id, db, current_user)
    require_unpublished_champion_edit(tournament)

    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot == champion_slot,
    ).first()

    if body.seed_number is not None:
        duplicate_query = db.query(models.Player).filter(
            models.Player.tournament_id == tournament_id,
            models.Player.seed_number == body.seed_number,
        )
        if player is not None:
            duplicate_query = duplicate_query.filter(models.Player.id != player.id)
        if duplicate_query.first():
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="seed_number is already registered in this tournament",
            )

    generated_name = automatic_champion_player_name(champion_slot, body.seed_number)
    if player is None:
        player = models.Player(
            tournament_id=tournament_id,
            champion_slot=champion_slot,
            seed_number=body.seed_number,
            name=generated_name,
        )
        db.add(player)
    else:
        if tournament.deck_registration_phases and player.seed_number != body.seed_number and (
            db.query(models.ArenaDeckRegistration.id).filter_by(player_id=player.id).first() or
            db.query(models.Match.id).filter(models.Match.tournament_id==tournament_id).first() or
            db.query(models.ArenaMatchRevision.id).filter_by(tournament_id=tournament_id).first()
        ):
            raise HTTPException(409, "Registered seed identity is protected once phase history exists")
        player.seed_number = body.seed_number
        player.name = generated_name

    try:
        db.commit()
        db.refresh(player)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="champion slot or seed_number conflicts with another player",
        ) from exc
    except Exception:
        db.rollback()
        raise

    # DB commit後に無効化する。失敗しても確定済みDB更新と正常レスポンスを維持する。
    try:
        invalidate_dashboard_cache(tournament_id)
    except Exception as exc:
        print(
            f"[dashboard-cache] invalidate failed tournament={tournament_id}: {exc}"
        )
    return player


@app.get(
    "/api/tournaments/{tournament_id}/players/by-id/{player_id}",
    response_model=schemas.ChampionPlayerResponse,
)
def get_champion_player_by_id(
    tournament_id: int,
    player_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_champion_tournament_viewer(tournament_id, db, current_user)
    player = db.query(models.Player).filter(
        models.Player.id == player_id,
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


CHAMPION_DECK_MAX_IMAGES = 5
CHAMPION_DECK_MAX_IMAGE_BYTES = 20 * 1024 * 1024
CHAMPION_DECK_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CHAMPION_ICON_MAX_BYTES = 10 * 1024 * 1024
CHAMPION_ICON_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CHAMPION_ICON_MAX_WIDTH = 10_000
CHAMPION_ICON_MAX_HEIGHT = 10_000
CHAMPION_ICON_MAX_PIXELS = 25_000_000
CHAMPION_RESULT_MAX_BYTES = 20 * 1024 * 1024


def champion_player_icon_location(tournament_id: int, player_id: int) -> tuple[Path, str]:
    icon_dir = (PLAYER_ICONS_DIR / f"tournament_{tournament_id}").resolve()
    if not _is_within(icon_dir, PLAYER_ICONS_DIR):
        raise HTTPException(status_code=500, detail="Unsafe player icon path")
    path = (icon_dir / f"player_{player_id}.webp").resolve()
    if not _is_within(path, icon_dir):
        raise HTTPException(status_code=500, detail="Unsafe player icon path")
    return path, f"/api/uploads/player_icons/tournament_{tournament_id}/player_{player_id}.webp"


def champion_icon_temporary_paths(final_path: Path, token: str) -> tuple[Path, Path, Path]:
    return (
        final_path.parent / f".{final_path.name}.{token}.upload",
        final_path.parent / f".{final_path.name}.{token}.webp",
        final_path.parent / f".{final_path.name}.{token}.backup",
    )


def invalidate_dashboard_cache_safely(tournament_id: int) -> None:
    try:
        invalidate_dashboard_cache(tournament_id)
    except Exception as exc:
        print(f"[dashboard-cache] invalidate failed tournament={tournament_id}: {exc}")


async def save_player_icon(image, player, final_path, icon_url, db):
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    if image.content_type not in CHAMPION_ICON_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image MIME type")
    data = await image.read(CHAMPION_ICON_MAX_BYTES + 1)
    if len(data) > CHAMPION_ICON_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB")
    token = secrets.token_hex(8)
    upload_path, normalized_path, backup_path = champion_icon_temporary_paths(final_path, token)
    # Finish all awaits before acquiring the process/file lock.
    with icon_mutation_lock(PLAYER_ICONS_DIR):
        db.flush()
        db.query(models.Player).filter(models.Player.id == player.id).populate_existing().with_for_update().one()
        final_path.parent.mkdir(parents=True, exist_ok=True)
        recovery_path = final_path.parent / f".{final_path.name}.{token}.recovery.json"
        previous_url = player.icon_url
        replaced_existing = False
        installed = False
        commit_attempted = False
        committed = False
        try:
            try:
                write_webp(normalized_path, data)
            except IconTooLarge as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            except InvalidIcon as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            recovery = dict(player_id=player.id, old_url=previous_url, new_url=icon_url,
                            old_sha256=hashlib.sha256(final_path.read_bytes()).hexdigest() if final_path.exists() else None,
                            new_sha256=hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
                            target=final_path.name, backup=backup_path.name)
            with recovery_path.open("x", encoding="utf-8") as output:
                json.dump(recovery, output); output.flush(); os.fsync(output.fileno())
            if final_path.exists():
                os.replace(final_path, backup_path)
                replaced_existing = True
            os.replace(normalized_path, final_path)
            installed = True
            player.icon_url = icon_url
            db.flush()
            commit_attempted = True
            db.commit()
            committed = True
        except Exception:
            db.rollback()
            restore_files = not commit_attempted
            if commit_attempted and previous_url != icon_url:
                try:
                    with db.get_bind().connect() as connection:
                        current_url = connection.execute(
                            select(models.Player.icon_url).where(models.Player.id == player.id)
                        ).scalar_one_or_none()
                    restore_files = current_url != icon_url
                except Exception:
                    # A lost commit acknowledgement must never leave a committed
                    # WebP URL without its file. Preserve both files for recovery.
                    restore_files = False
                    print("[player-icon] commit outcome unknown; retained recovery files")
            if restore_files:
                if installed:
                    final_path.unlink(missing_ok=True)
                if replaced_existing and backup_path.exists():
                    os.replace(backup_path, final_path)
                recovery_path.unlink(missing_ok=True)
            raise
        finally:
            for temporary_path in (upload_path, normalized_path):
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    print("[player-icon] temporary cleanup failed")
            if committed:
                try:
                    backup_path.unlink(missing_ok=True)
                    recovery_path.unlink(missing_ok=True)
                except OSError:
                    print("[player-icon] backup cleanup failed")
    # Old PNGs are deliberately retained for separately approved cleanup.


@app.put(
    "/api/tournaments/{tournament_id}/players/by-id/{player_id}/icon",
    response_model=schemas.ChampionPlayerIconResponse,
)
async def upload_champion_player_icon(
    tournament_id: int,
    player_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    _, player = require_champion_player_manager(
        tournament_id, player_id, db, current_user
    )
    final_path, icon_url = champion_player_icon_location(tournament_id, player.id)
    await save_player_icon(image, player, final_path, icon_url, db)
    invalidate_dashboard_cache_safely(tournament_id)
    return {
        "player_id": player.id,
        "tournament_id": tournament_id,
        "champion_slot": player.champion_slot,
        "icon_url": player.icon_url,
    }


@app.delete(
    "/api/tournaments/{tournament_id}/players/by-id/{player_id}/icon",
    response_model=schemas.ChampionPlayerIconResponse,
)
def delete_champion_player_icon(
    tournament_id: int,
    player_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    _, player = require_champion_player_manager(
        tournament_id, player_id, db, current_user
    )
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    final_path, _ = champion_player_icon_location(tournament_id, player.id)
    with icon_mutation_lock(PLAYER_ICONS_DIR):
        db.query(models.Player).filter(models.Player.id == player.id).populate_existing().with_for_update().one()
        moved = []
        try:
            for path in (final_path, final_path.with_suffix(".png")):
                if path.exists():
                    backup = path.parent / f".{path.name}.{secrets.token_hex(8)}.delete"
                    os.replace(path, backup)
                    moved.append((path, backup))
            player.icon_url = None
            db.commit()
        except Exception:
            db.rollback()
            for original, backup in reversed(moved):
                os.replace(backup, original)
            raise
        for _, backup in moved:
            try:
                backup.unlink()
            except OSError:
                print("[player-icon] cleanup failed")
    invalidate_dashboard_cache_safely(tournament_id)
    return {
        "player_id": player.id,
        "tournament_id": tournament_id,
        "champion_slot": player.champion_slot,
        "icon_url": None,
    }


@app.post("/api/tournaments/{tournament_id}/players/by-id/{player_id}/analyze-deck")
async def analyze_champion_deck(
    tournament_id: int,
    player_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
    _analysis_capacity: AnalysisReservation = Depends(require_analysis_capacity),
):
    # Authorization and ownership checks deliberately precede multipart parsing/decoding.
    _, player = require_champion_player_manager(
        tournament_id, player_id, db, current_user
    )
    form = await request.form(
        max_files=CHAMPION_DECK_MAX_IMAGES,
        max_fields=CHAMPION_DECK_MAX_IMAGES,
        max_part_size=CHAMPION_DECK_MAX_IMAGE_BYTES,
    )
    images = form.getlist("images")
    if not 1 <= len(images) <= CHAMPION_DECK_MAX_IMAGES:
        raise HTTPException(status_code=422, detail="Provide between one and five images")
    pre_cropped_flags = [
        str(value).strip().lower() in {"1", "true", "yes", "on"}
        for value in form.getlist("image_pre_cropped")
    ]
    saved_paths: list[str] = []
    analysis_output_paths: list[str] = []
    keep_analysis_outputs = False
    try:
        for index, image in enumerate(images):
            if getattr(image, "content_type", None) not in CHAMPION_DECK_IMAGE_TYPES:
                raise HTTPException(status_code=422, detail="Unsupported image MIME type")
            suffix = Path(image.filename or "deck.png").suffix.lower() or ".png"
            file_path = os.path.join(
                UPLOAD_DIR,
                f"champion_t{tournament_id}_p{player.id}_{secrets.token_hex(6)}_{index}{suffix}",
            )
            saved_paths.append(file_path)
            total = 0
            with open(file_path, "wb") as output:
                while chunk := await image.read(1024 * 1024):
                    total += len(chunk)
                    if total > CHAMPION_DECK_MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail="Image exceeds 20 MB")
                    output.write(chunk)
            if total == 0:
                raise HTTPException(status_code=422, detail="Empty image files are not allowed")
        try:
            result = await run_cpu_analysis(
                process_images,
                saved_paths,
                tournament_id,
                player.id,
                pre_cropped_flags=pre_cropped_flags,
                include_source_metadata=True,
                created_output_paths=analysis_output_paths,
                crop_owner_player_id=player.id,
                reservation=request_analysis_reservation(_analysis_capacity),
            )
        except AnalysisBusyError as exc:
            raise HTTPException(
                status_code=429,
                detail="画像解析が混み合っています。数秒後にもう一度お試しください。",
                headers={"Retry-After": "5"},
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            print(f"[champion-deck] analysis failed tournament={tournament_id} player={player.id}: {exc}")
            raise HTTPException(status_code=500, detail="Deck analysis failed") from exc
        # The legacy analyzer uses its third argument only for result/file labels.
        result["suggested_player_name"] = player.name
        result["suggested_seed"] = player.seed_number
        result["teams"] = [
            {
                "team_number": team_number,
                "source_image_index": next(
                    (
                        character.get("source_image_index")
                        for character in characters
                        if character.get("source_image_index") is not None
                    ),
                    None,
                ),
                "characters": [
                    {
                        **character,
                        "character_id": character.get("predicted_character_id"),
                        "unresolved": character.get("predicted_character_id") is None,
                    }
                    for character in characters
                ],
            }
            for team_number, characters in enumerate(
                result.get("suggested_teams", []), start=1
            )
        ]
        # The structured response retains the same temporary crop URLs as the
        # existing full_64 flow. They remain available while the user reviews
        # and corrects the result, and are deleted only after a successful save.
        for characters in result.get("suggested_teams", []):
            for character in characters:
                character.pop("image_url", None)
                character.pop("template_source_url", None)
        keep_analysis_outputs = True
        return result
    finally:
        cleanup_paths = saved_paths + ([] if keep_analysis_outputs else analysis_output_paths)
        for path in cleanup_paths:
            delete_upload_file(path)


def prepare_registration_assets(normalized, tournament_id, player_id, *, seed_number=None):
    temporary_crop_urls = [
        url
        for _, _, _, characters in normalized
        for character in characters
        for url in (character.image_url, character.template_source_url)
        if url
    ]
    owned_crop_paths = {
        validate_owned_champion_crop_url(url, tournament_id, player_id, seed_number=seed_number)
        for url in temporary_crop_urls
    }
    template_sources = []
    total_template_bytes = 0
    for _, _, _, characters in normalized:
        for character in characters:
            if not character.add_to_templates:
                continue
            if character.id == EMPTY_SLOT_CHARACTER_ID:
                raise HTTPException(status_code=422, detail="The empty slot cannot be added as a Character template")
            if not (
                character.was_unrecognized
                or character.original_predicted_id != character.id
            ):
                raise HTTPException(status_code=422, detail="Templates may only be added for manually corrected analysis results")
            source_image, source_bytes = load_champion_template_source(
                character, tournament_id, player_id, seed_number=seed_number
            )
            total_template_bytes += source_bytes
            if total_template_bytes > CHAMPION_TEMPLATE_SOURCE_TOTAL_MAX_BYTES:
                raise HTTPException(status_code=422, detail="Corrected template sources exceed the total size limit")
            template_sources.append((character, source_image))

    return owned_crop_paths, template_sources


def install_registration_templates(template_sources, tournament, player, actor, db, created_paths):
    for character_payload, source_image in template_sources:
        created_path = install_champion_character_template(character_payload.id, source_image, db)
        if created_path is not None:
            created_paths.append(created_path)
        corrected_path = representative_template(Path(UPLOAD_DIR) / "templates", character_payload.id)
        add_template_correction_review(db, payload=character_payload,
            corrected_template_filename=corrected_path.name if corrected_path else None,
            tournament=tournament, player=player, actor=actor)


def remove_registration_assets(paths, reason):
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[registration-assets] {reason} failed file={path.name}: {exc}")


def finish_registration_assets(created_paths, crop_paths):
    if created_paths:
        _invalidate_template_matcher_cache()
    remove_registration_assets(crop_paths, "committed crop cleanup")


def save_phase_registration_with_assets(tournament, player, phase, payload, db, actor):
    # Resolve eligibility/version conflicts before creating any template files.
    # Registration, template metadata and correction review share one DB commit.
    created_paths = []
    try:
        arena_phases.save_registration(tournament, player.id, phase, payload, db, commit=False)
        from pydantic import ValidationError
        try:
            parsed = schemas.ChampionTeamsUpsert(teams=payload["teams"])
        except ValidationError as exc:
            raise HTTPException(422, "Invalid registration character metadata") from exc
        normalized = validate_champion_teams_payload(parsed)
        crop_paths, sources = prepare_registration_assets(normalized, tournament.id, player.id,
            seed_number=player.seed_number if tournament.registration_scope == "full_64" else None)
        install_registration_templates(sources, tournament, player, actor, db, created_paths)
        db.commit()
    except Exception:
        db.rollback()
        remove_registration_assets(created_paths, "rollback")
        raise
    finish_registration_assets(created_paths, crop_paths)
    return arena_phases.state(tournament, db)


@app.put(
    "/api/tournaments/{tournament_id}/players/by-id/{player_id}/teams",
    response_model=schemas.ChampionTeamsResponse,
)
def save_champion_teams(
    tournament_id: int,
    player_id: int,
    data: schemas.ChampionTeamsUpsert,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    phase_tournament = require_legacy_registration_path(tournament_id, db, current_user)
    tournament, player = require_locked_champion_player_manager(
        tournament_id, player_id, db, current_user
    )
    normalized = validate_champion_teams_payload(data)
    owned_crop_paths, template_sources = prepare_registration_assets(normalized, tournament_id, player_id)
    character_ids = {
        character_id
        for _, ids, _, _ in normalized
        for character_id in ids
        if character_id != EMPTY_SLOT_CHARACTER_ID
    }
    existing_character_ids = {
        row[0]
        for row in db.query(models.Character.id).filter(
            models.Character.id.in_(character_ids)
        ).all()
    }
    missing = sorted(character_ids - existing_character_ids)
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown character IDs: {missing}")

    phase_initial = tournament.deck_registration_phases
    existing_sets = [] if phase_initial else db.query(models.DeckSet).filter(models.DeckSet.player_id == player.id).order_by(models.DeckSet.id).all()
    deck_set = None if phase_initial else existing_sets[0] if existing_sets else models.DeckSet(player_id=player.id)
    if not phase_initial and not existing_sets:
        db.add(deck_set)
    created_template_paths: list[Path] = []
    committed = False
    response_data = None
    try:
        if phase_initial:
            db.add(models.ArenaDeckRegistration(tournament_id=tournament_id,player_id=player.id,phase="initial",qualification="initial",teams=[
                {"team_number":number,"characters":[{"id":cid,"collection_level":level} for cid,level in zip(ids,collections)]}
                for number,ids,collections,_ in normalized]))
        else:
            for extra_set in existing_sets[1:]:
                db.delete(extra_set)
            for old_team in list(deck_set.teams):
                db.delete(old_team)
            db.flush()
            for team_number, ids, collections, _ in normalized:
                db.add(models.DeckTeam(
                    deck_set=deck_set,
                    team_number=team_number,
                    char1_id=ids[0], char2_id=ids[1], char3_id=ids[2],
                    char4_id=ids[3], char5_id=ids[4],
                    collection1=collections[0], collection2=collections[1],
                    collection3=collections[2], collection4=collections[3],
                    collection5=collections[4],
                ))
        install_registration_templates(template_sources, tournament, player, current_user, db, created_template_paths)
        db.flush()
        db.commit()
        committed = True
        response_data = champion_teams_response(player, arena_phases.initial_deck_sets(db,[player.id])[0] if phase_initial else deck_set)
    except IntegrityError as exc:
        db.rollback()
        for path in created_template_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                print(f"[champion-template] rollback cleanup failed file={path.name}: {cleanup_error}")
        raise HTTPException(status_code=409, detail="Deck data conflicts with existing data") from exc
    except Exception:
        if not committed:
            db.rollback()
        for path in ([] if committed else created_template_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                print(f"[champion-template] rollback cleanup failed file={path.name}: {cleanup_error}")
        raise
    finish_registration_assets(created_template_paths, owned_crop_paths)
    try:
        invalidate_dashboard_cache(tournament_id)
    except Exception as exc:
        print(f"[dashboard-cache] invalidate failed tournament={tournament_id}: {exc}")
    return response_data


@app.get(
    "/api/tournaments/{tournament_id}/players/by-id/{player_id}/teams",
    response_model=schemas.ChampionTeamsResponse,
)
def get_champion_teams(
    tournament_id: int,
    player_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    require_champion_tournament_viewer(tournament_id, db, current_user)
    player = db.query(models.Player).filter(
        models.Player.id == player_id,
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if db.query(models.Tournament).filter_by(id=tournament_id).one().deck_registration_phases:
        decks = arena_phases.initial_deck_sets(db, [player.id])
        return champion_teams_response(player, decks[0] if decks else None)
    deck_set = db.query(models.DeckSet).filter(
        models.DeckSet.player_id == player.id
    ).order_by(models.DeckSet.id).first()
    return champion_teams_response(player, deck_set)


def champion_player_has_complete_deck(player_id: int, db: Session) -> bool:
    deck_sets = db.query(models.DeckSet).filter(
        models.DeckSet.player_id == player_id
    ).all()
    if len(deck_sets) != 1:
        return False
    teams = list(deck_sets[0].teams)
    if sorted(team.team_number for team in teams) != [1, 2, 3, 4, 5]:
        return False
    character_ids = []
    for team in teams:
        ids = [getattr(team, f"char{slot}_id") for slot in range(1, 6)]
        if any(character_id is None for character_id in ids):
            return False
        character_ids.extend(
            character_id for character_id in ids
            if character_id != EMPTY_SLOT_CHARACTER_ID
        )
    return len(set(character_ids)) == len(character_ids)


def champion_match_is_complete(
    match: models.Match | None,
    expected_participants: tuple[int | None, int | None] | None = None,
) -> bool:
    return match_is_complete(match, expected_participants)


def champion_bracket_context(tournament_id: int, db: Session):
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).one()
    if tournament.deck_registration_phases:
        players, nodes, _, _ = arena_phases.context(tournament, db)
        matches = arena_phases.effective_matches(db, [tournament_id])
        stage = {8:"quarterfinal",4:"semifinal",2:"final"}
        return ({p.id:p for p in players}, {p.champion_slot:p.id for p in players},
            {(m.bracket_stage,m.bracket_slot):m for m in matches},
            {(stage[n["remaining"]],n["slot"]):n["winner_id"] for n in nodes.values() if n["winner_id"]},
            {(stage[n["remaining"]],n["slot"]):tuple(n["participants"]) for n in nodes.values()})
    players = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.champion_slot.isnot(None),
    ).all()
    players_by_id = {player.id: player for player in players}
    player_ids_by_slot = {player.champion_slot: player.id for player in players}
    stored_matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id,
        models.Match.bracket_stage.isnot(None),
    ).all()
    matches_by_key = {
        (match.bracket_stage, match.bracket_slot): match for match in stored_matches
    }
    winners: dict[tuple[str, int], int] = {}
    expected_by_key = {}
    for definition in CHAMPION_BRACKET:
        expected = participant_ids(definition, player_ids_by_slot, winners)
        expected_by_key[definition.key] = expected
        match = matches_by_key.get(definition.key)
        if champion_match_is_complete(match, expected):
            winners[definition.key] = match.winner_id
    return players_by_id, player_ids_by_slot, matches_by_key, winners, expected_by_key


def champion_bracket_match_data(
    definition,
    players_by_id,
    matches_by_key,
    expected_by_key,
    db: Session,
):
    expected = expected_by_key[definition.key]
    attacker = players_by_id.get(expected[0])
    defender = players_by_id.get(expected[1])
    match = matches_by_key.get(definition.key)
    complete = champion_match_is_complete(match, expected)
    participants_ready = (
        attacker is not None
        and defender is not None
        and attacker.id != defender.id
        and champion_player_has_complete_deck(attacker.id, db)
        and champion_player_has_complete_deck(defender.id, db)
    )
    status = "complete" if complete else ("ready" if participants_ready else "locked")
    winner = players_by_id.get(match.winner_id) if complete else None
    return {
        "bracket_stage": definition.key[0],
        "bracket_slot": definition.key[1],
        "name": definition.name,
        "status": status,
        "attacker": attacker,
        "defender": defender,
        "match_id": match.id if match else None,
        "winner": winner,
        "round_results": [
            {"round_number": result.round_number, "winner_id": result.winner_id}
            for result in sorted(match.round_results, key=lambda item: item.round_number)
        ] if match else [],
        "upstream": [CHAMPION_BRACKET_BY_KEY[key].name for key in definition.upstream],
    }


@app.get(
    "/api/tournaments/{tournament_id}/champion-bracket",
    response_model=schemas.ChampionBracketResponse,
)
def get_champion_bracket(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
):
    tournament = require_champion_tournament_viewer(tournament_id, db, current_user)
    if tournament.deck_registration_phases:
        players, nodes, _, _ = arena_phases.context(tournament, db)
        by_id = {p.id: p for p in players}
        return {"tournament_id": tournament_id, "matches": [{
            "bracket_stage": {8: "quarterfinal", 4: "semifinal", 2: "final"}[node["remaining"]],
            "bracket_slot": node["slot"], "name": "Final" if node["remaining"] == 2 else f"{ 'QF' if node['remaining'] == 8 else 'SF'}{node['slot']}",
            "status": node["status"], "attacker": by_id.get(node["participants"][0]), "defender": by_id.get(node["participants"][1]),
            "match_id": -node["revision_id"] if node["revision_id"] else node["legacy_match_id"], "winner": by_id.get(node["winner_id"]),
            "round_results": [{"round_number": i+1, "winner_id": pid} for i, pid in enumerate(node["rounds"])], "upstream": node["sources"], "phase_context": node
        } for node in nodes.values()]}
    players_by_id, _, matches_by_key, _, expected_by_key = champion_bracket_context(
        tournament_id, db
    )
    return {
        "tournament_id": tournament_id,
        "matches": [
            champion_bracket_match_data(
                definition, players_by_id, matches_by_key, expected_by_key, db
            )
            for definition in CHAMPION_BRACKET
        ],
    }


def validate_champion_match_result(
    data: schemas.ChampionMatchUpsert,
    participants: tuple[int, int],
) -> None:
    if len(data.round_results) != 5:
        raise HTTPException(status_code=422, detail="Exactly five round results are required")
    round_numbers = [result.round_number for result in data.round_results]
    if sorted(round_numbers) != [1, 2, 3, 4, 5]:
        raise HTTPException(status_code=422, detail="round_number must contain each value from 1 to 5 exactly once")
    if data.winner_id not in participants:
        raise HTTPException(status_code=422, detail="Match winner must be a participant")
    if any(result.winner_id not in participants for result in data.round_results):
        raise HTTPException(status_code=422, detail="Round winner must be a participant")
    attacker_wins = sum(result.winner_id == participants[0] for result in data.round_results)
    calculated_winner = participants[0] if attacker_wins >= 3 else participants[1]
    if data.winner_id != calculated_winner:
        raise HTTPException(status_code=422, detail="Match winner does not match the five-round majority")


def delete_champion_match_branch(key, matches_by_key, db: Session) -> None:
    for dependent in dependent_keys(key):
        delete_champion_match_branch(dependent, matches_by_key, db)
    match = matches_by_key.pop(key, None)
    if match is not None:
        db.delete(match)


def reconcile_champion_dependents(key, tournament_id: int, matches_by_key, db: Session) -> None:
    _, _, current_matches, _, expected_by_key = champion_bracket_context(tournament_id, db)
    matches_by_key.update(current_matches)
    for dependent in dependent_keys(key):
        dependent_match = matches_by_key.get(dependent)
        if dependent_match is None:
            for descendant in dependent_keys(dependent):
                delete_champion_match_branch(descendant, matches_by_key, db)
            continue
        if not champion_match_is_complete(dependent_match, expected_by_key[dependent]):
            delete_champion_match_branch(dependent, matches_by_key, db)
        else:
            reconcile_champion_dependents(dependent, tournament_id, matches_by_key, db)


@app.put(
    "/api/tournaments/{tournament_id}/matches/{bracket_stage}/{bracket_slot}",
    response_model=schemas.ChampionBracketMatchResponse,
)
def save_champion_match(
    tournament_id: int,
    bracket_stage: str,
    bracket_slot: int,
    data: schemas.ChampionMatchUpsert,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    phase_tournament = require_legacy_registration_path(tournament_id, db, current_user)
    if phase_tournament.deck_registration_phases:
        if phase_tournament.registration_scope != "champion_8":
            raise HTTPException(409, "Use the result/registration API for this tournament format")
        require_unpublished_champion_edit(phase_tournament)
        remaining = {"quarterfinal": 8, "semifinal": 4, "final": 2}.get(bracket_stage)
        if remaining is None:
            raise HTTPException(422, "Invalid bracket stage")
        _, nodes, _, _ = arena_phases.context(phase_tournament, db)
        node = nodes.get(f"{remaining}:{bracket_slot}")
        if node is None:
            raise HTTPException(422, "Invalid bracket slot")
        validate_champion_match_result(data, tuple(node["participants"]))
        payload = result_revision_payload(node, [r.winner_id for r in sorted(data.round_results, key=lambda r: r.round_number)], data.phase_context)
        arena_phases.save_result(phase_tournament, node["key"], payload, db)
        invalidate_dashboard_cache_safely(tournament_id)
        return next(m for m in get_champion_bracket(tournament_id, db, current_user)["matches"] if m["bracket_stage"] == bracket_stage and m["bracket_slot"] == bracket_slot)
    tournament = require_locked_champion_tournament_manager(tournament_id, db, current_user)
    require_unpublished_champion_edit(tournament)
    definition = get_bracket_definition(bracket_stage, bracket_slot)
    if definition is None:
        raise HTTPException(status_code=422, detail="Invalid champion bracket slot")
    players_by_id, _, matches_by_key, _, expected_by_key = champion_bracket_context(
        tournament_id, db
    )
    expected = expected_by_key[definition.key]
    if expected[0] is None or expected[1] is None:
        raise HTTPException(status_code=409, detail="Upstream participants are not complete")
    participants = (expected[0], expected[1])
    if participants[0] == participants[1]:
        raise HTTPException(status_code=409, detail="Attacker and defender must differ")
    if any(player_id not in players_by_id for player_id in participants):
        raise HTTPException(status_code=409, detail="Participant does not belong to tournament")
    if not all(champion_player_has_complete_deck(player_id, db) for player_id in participants):
        raise HTTPException(status_code=409, detail="Both participants must have complete decks")
    validate_champion_match_result(data, participants)

    match = matches_by_key.get(definition.key)
    old_winner_id = match.winner_id if match and champion_match_is_complete(match, expected) else None
    if match is None:
        match = models.Match(
            tournament_id=tournament_id,
            stage=definition.name,
            bracket_stage=definition.key[0],
            bracket_slot=definition.key[1],
            attacker_id=participants[0],
            defender_id=participants[1],
        )
        db.add(match)
        matches_by_key[definition.key] = match
    else:
        match.stage = definition.name
        match.attacker_id = participants[0]
        match.defender_id = participants[1]
    match.winner_id = data.winner_id
    match.round_results.clear()
    for result in sorted(data.round_results, key=lambda item: item.round_number):
        match.round_results.append(models.RoundResult(
            round_number=result.round_number,
            winner_id=result.winner_id,
        ))
    try:
        db.flush()
        if old_winner_id != data.winner_id:
            for dependent in dependent_keys(definition.key):
                delete_champion_match_branch(dependent, matches_by_key, db)
        else:
            reconcile_champion_dependents(definition.key, tournament_id, matches_by_key, db)
        db.commit()
        db.refresh(match)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Champion match conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise
    invalidate_dashboard_cache_safely(tournament_id)
    players_by_id, _, matches_by_key, _, expected_by_key = champion_bracket_context(
        tournament_id, db
    )
    return champion_bracket_match_data(
        definition, players_by_id, matches_by_key, expected_by_key, db
    )


@app.post(
    "/api/tournaments/{tournament_id}/matches/{bracket_stage}/{bracket_slot}/analyze",
    response_model=schemas.ChampionMatchAnalysisResponse,
)
async def analyze_champion_match_result(
    tournament_id: int,
    bracket_stage: str,
    bracket_slot: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
    _analysis_capacity: AnalysisReservation = Depends(require_analysis_capacity),
):
    # Authorization, scope, fixed participants and deck readiness must precede
    # multipart parsing and all image/OCR work.
    require_champion_tournament_manager(tournament_id, db, current_user)
    definition = get_bracket_definition(bracket_stage, bracket_slot)
    if definition is None:
        raise HTTPException(status_code=422, detail="Invalid champion bracket slot")
    players_by_id, _, _, _, expected_by_key = champion_bracket_context(
        tournament_id, db
    )
    expected = expected_by_key[definition.key]
    if expected[0] is None or expected[1] is None:
        raise HTTPException(status_code=409, detail="Upstream participants are not complete")
    attacker = players_by_id.get(expected[0])
    defender = players_by_id.get(expected[1])
    if attacker is None or defender is None or attacker.id == defender.id:
        raise HTTPException(status_code=409, detail="Fixed match participants are invalid")
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).one()
    if tournament.deck_registration_phases:
        _, nodes, _, _ = arena_phases.context(tournament, db)
        remaining = {"quarterfinal":8,"semifinal":4,"final":2}[bracket_stage]
        node = nodes[f"{remaining}:{bracket_slot}"]
        if not node["can_register"]:
            raise HTTPException(409, "Both participants need complete registrations for this phase")
    else:
        if not (
            champion_player_has_complete_deck(attacker.id, db)
            and champion_player_has_complete_deck(defender.id, db)
        ):
            raise HTTPException(status_code=409, detail="Both participants must have complete decks")
    try:
        # Parse once, then enforce the exact multipart contract below. Limits
        # remain finite for resource safety; parser-limit errors are normalized
        # to this endpoint's 422 input-error contract.
        form = await request.form(
            max_files=20,
            max_fields=20,
            max_part_size=CHAMPION_RESULT_MAX_BYTES,
        )
    except StarletteHTTPException as exc:
        if exc.status_code == 400:
            raise HTTPException(status_code=422, detail="Invalid multipart form data") from exc
        raise
    if hasattr(form, "multi_items"):
        unexpected = {key for key, _ in form.multi_items()} - {"image"}
        if unexpected:
            raise HTTPException(status_code=422, detail="Unexpected multipart fields")
    images = form.getlist("image")
    if len(images) != 1:
        raise HTTPException(status_code=422, detail="Exactly one result image is required")
    image = images[0]
    if getattr(image, "content_type", None) not in CHAMPION_ICON_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image MIME type")

    temporary_path = os.path.join(
        UPLOAD_DIR,
        f"champion_result_t{tournament_id}_{secrets.token_hex(8)}.upload",
    )
    try:
        total = 0
        with open(temporary_path, "wb") as output:
            while chunk := await image.read(1024 * 1024):
                total += len(chunk)
                if total > CHAMPION_RESULT_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Image exceeds 20 MB")
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=422, detail="Empty image files are not allowed")

        import cv2
        decoded = cv2.imread(temporary_path, cv2.IMREAD_UNCHANGED)
        if decoded is None or decoded.size == 0:
            raise HTTPException(status_code=422, detail="File is not a decodable image")
        height, width = decoded.shape[:2]
        if (
            width > CHAMPION_ICON_MAX_WIDTH
            or height > CHAMPION_ICON_MAX_HEIGHT
            or width * height > CHAMPION_ICON_MAX_PIXELS
        ):
            raise HTTPException(status_code=413, detail="Decoded image dimensions exceed the allowed limit")
        try:
            raw_result = await run_cpu_analysis(
                extract_match_results,
                temporary_path,
                reservation=request_analysis_reservation(_analysis_capacity),
            )
        except AnalysisBusyError as exc:
            raise HTTPException(
                status_code=429,
                detail="画像解析が混み合っています。数秒後にもう一度お試しください。",
                headers={"Retry-After": "5"},
            ) from exc
        except Exception as exc:
            print(
                f"[champion-result] analysis failed tournament={tournament_id} "
                f"stage={bracket_stage} slot={bracket_slot}: {exc}"
            )
            raise HTTPException(status_code=500, detail="Match result analysis failed") from exc
        converted = normalize_champion_result(raw_result, attacker.id, defender.id)
        return {
            "tournament_id": tournament_id,
            "bracket_stage": definition.key[0],
            "bracket_slot": definition.key[1],
            "attacker": attacker,
            "defender": defender,
            **converted,
        }
    finally:
        delete_upload_file(temporary_path)

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
    return _get_player_details_data(tournament_id, seed_number, db)


def _get_player_details_data(tournament_id: int, seed_number: int, db: Session, registration_phase="initial"):
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number
    ).first()

    return _get_player_details_by_player(tournament_id, player, db, registration_phase)


def _get_player_details_by_player(tournament_id: int, player: models.Player | None, db: Session, registration_phase="initial", *, registration_sets=None, resolved_matches=None):
    if registration_phase == "legacy":
        registration_phase = "initial"
    if not player:
        return {"player": None, "decks": []}
        
    initial_sets = arena_phases.phase_deck_sets(db, [player.id], registration_phase) if registration_sets is None else registration_sets
    deck_set = initial_sets[0] if initial_sets else None
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
    matches = [m for m in (arena_phases.effective_matches(db, [tournament_id]) if resolved_matches is None else resolved_matches) if m.tournament_id == tournament_id and m.winner_id is not None and player.id in (m.attacker_id, m.defender_id) and arena_phases.matches_analysis_phase(db, m, registration_phase)]

    # Pre-calculate win/loss per team number
    team_stats = {1: {"wins": 0, "losses": 0}, 2: {"wins": 0, "losses": 0}, 3: {"wins": 0, "losses": 0}, 4: {"wins": 0, "losses": 0}, 5: {"wins": 0, "losses": 0}}
    
    current_teams = {team.team_number: team for team in deck_set.teams}
    def composition(team):
        return tuple(sorted(getattr(team, f"char{i}_id") for i in range(1, 6) if getattr(team, f"char{i}_id") is not None))
    for m in matches:
        used_set = arena_phases.deck_for_match(m, player.id, db)
        used_teams = {team.team_number: team for team in used_set.teams} if used_set else {}
        for r in m.round_results:
            current = current_teams.get(r.round_number)
            used = used_teams.get(r.round_number)
            if current is None or used is None or composition(current) != composition(used):
                continue
            if r.winner_id == player.id:
                team_stats[r.round_number]["wins"] += 1
            else:
                team_stats[r.round_number]["losses"] += 1
                
    decks = []
    for team in deck_set.teams:
        raw_char_ids = [
            team.char1_id,
            team.char2_id,
            team.char3_id,
            team.char4_id,
            team.char5_id,
        ]
        populated_slots = [
            (character_id, collection_level)
            for character_id, collection_level in zip(
                raw_char_ids,
                get_team_collection_levels(team),
            )
            if character_id
        ]
        char_ids = [character_id for character_id, _ in populated_slots]
        collection_levels = [
            collection_level for _, collection_level in populated_slots
        ]
        stats = team_stats.get(team.team_number, {"wins": 0, "losses": 0})
        total = stats["wins"] + stats["losses"]
        win_rate = round((stats["wins"] / total * 100)) if total > 0 else None
        
        canon_id = ",".join(map(str, sorted(char_ids)))
        
        decks.append({
            "team_number": team.team_number,
            "character_ids": char_ids,
            "collection_levels": collection_levels,
            "canonical_id": canon_id,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "total_matches": total,
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



def validated_player_icon_reference(url, tournament_id, db):
    if not url:
        return None
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    normalized = url.partition("?")[0]
    match = re.fullmatch(r"/api/uploads/player_icons/tournament_(\d+)/(?:seed|player)_\d+\.(png|webp)", normalized)
    if match:
        if int(match.group(1)) != tournament_id:
            raise HTTPException(status_code=422, detail="Icon belongs to another tournament")
        candidate = normalized[:-4] + ".webp" if match.group(2) == "png" else normalized
        chosen = candidate if _private_upload_tournament_id(candidate.removeprefix("/api/uploads/"), db) == tournament_id else normalized
        path = (PLAYER_ICONS_DIR / chosen.removeprefix("/api/uploads/player_icons/")).resolve()
        if not _is_within(path, PLAYER_ICONS_DIR.resolve()) or not path.is_file():
            raise HTTPException(status_code=422, detail="Player icon file does not exist")
        return chosen
    if normalized.startswith("/api/uploads/cropped/") and _private_upload_tournament_id(normalized.removeprefix("/api/uploads/"), db) == tournament_id:
        return normalized
    raise HTTPException(status_code=422, detail="Invalid player icon reference")


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
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    with icon_mutation_lock(PLAYER_ICONS_DIR):
        tournament = require_tournament_manager(tournament_id, db, current_user)
        player = db.query(models.Player).filter(
            models.Player.tournament_id == tournament_id,
            models.Player.seed_number == seed_number
        ).first()
    
        icon_url = validated_player_icon_reference(data.get("icon_url"), tournament_id, db)
        previous_icon_url = player.icon_url if player else None
        player_name = automatic_player_name(seed_number)
    
        if not player:
            player = models.Player(
                tournament_id=tournament_id,
                seed_number=seed_number,
                name=player_name,
                icon_url=icon_url
            )
            db.add(player)
        else:
            player.name = player_name
            if icon_url: player.icon_url = icon_url
    
        db.commit()
        db.refresh(player)
        cleanup_replaced_player_icon(db, player.id, previous_icon_url, player.icon_url)
        invalidate_dashboard_cache(tournament_id)
        return player


@app.post("/api/tournaments/{tournament_id}/teams")
async def save_teams(
    tournament_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    phase_tournament = require_legacy_registration_path(tournament_id, db, current_user)
    if phase_tournament.deck_registration_phases:
        if phase_tournament.registration_scope != "full_64":
            raise HTTPException(409, "Use the result/registration API for this tournament format")
        require_unpublished_champion_edit(phase_tournament)
        seed = data.get("seed_number") if isinstance(data, dict) else None
        if type(seed) is not int or seed not in range(1, 65):
            raise HTTPException(422, "seed_number must be between 1 and 64")
        player = db.query(models.Player).filter_by(tournament_id=tournament_id, seed_number=seed).first()
        is_update = player is not None and bool(arena_phases.initial_deck_sets(db, [player.id]))
        if player is None:
            player = models.Player(tournament_id=tournament_id, seed_number=seed, name=automatic_player_name(seed))
            db.add(player)
            db.flush()
        save_initial_arena_registration(phase_tournament, player, data.get("teams"), db, current_user)
        invalidate_dashboard_cache_safely(tournament_id)
        return {"ok": True, "is_update": is_update, "history_preserved": True}
    if os.environ.get("PLAYER_ICON_WRITES_PAUSED") == "1":
        raise HTTPException(status_code=503, detail="Player icon maintenance in progress")
    tournament = require_tournament_manager(tournament_id, db, current_user)
    temporary_crop_urls = [
        character.get(url_field)
        for team in data.get("teams", [])
        for character in team.get("characters", [])
        for url_field in ("image_url", "template_source_url")
    ]
    try:
        seed_number = data.get("seed_number")
        teams = data.get("teams", [])
        player_icon_url = data.get("player_icon_url")
        
        is_update = False  # 上書きフラグ
        
        with icon_mutation_lock(PLAYER_ICONS_DIR):
            player_icon_url = validated_player_icon_reference(player_icon_url, tournament_id, db)
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
                    name=automatic_player_name(seed_number),
                    icon_url=player_icon_url or None,
                )
                db.add(player)
                db.commit()
                db.refresh(player)
                print(f"[save_teams] 新規プレイヤー登録: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")
            else:
                # 既存 Player 更新
                player.name = automatic_player_name(seed_number)
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
            collection_levels = []
            for character_id, character in zip(char_ids, chars):
                raw_collection = character.get("collection_level")
                if character_id == 9999:
                    collection_levels.append(None)
                elif raw_collection in COLLECTION_VALUES:
                    collection_levels.append(raw_collection)
                else:
                    collection_levels.append(None)
            collection_levels = (collection_levels + [None] * 5)[:5]
            
            deck_team = models.DeckTeam(
                deck_set_id=deck_set.id,
                team_number=team_data.get("team_number"),
                char1_id=char_ids[0],
                char2_id=char_ids[1],
                char3_id=char_ids[2],
                char4_id=char_ids[3],
                char5_id=char_ids[4],
                collection1=collection_levels[0],
                collection2=collection_levels[1],
                collection3=collection_levels[2],
                collection4=collection_levels[3],
                collection5=collection_levels[4],
            )
            db.add(deck_team)
            
            # 解析時に不明だった画像を人が補正した場合だけ自動学習する。
            for char_info in chars:
                if char_info.get("add_to_templates") is not True:
                    continue
                c_id = char_info.get("id")
                image_url = (
                    char_info.get("template_source_url")
                    or char_info.get("image_url")
                )
                if c_id and image_url and image_url.startswith("/api/"):
                    local_path = path_from_upload_url(image_url)
                    if local_path and local_path.exists():
                        import cv2 as _cv2
                        template_source = _cv2.imread(str(local_path))
                        if template_source is None:
                            raise OSError(f"Failed to decode template source: {local_path}")
                        created_path = install_champion_character_template(int(c_id), template_source, db)
                        representative = representative_template(Path(template_dir), int(c_id))
                        saved_template_filename = representative.name if representative else None
                        if created_path is not None:
                            templates_added += 1
                            print(f"[Template] 追加: {created_path}")
                        else:
                            print(f"[Template] スキップ（重複）: char_{c_id}")
                        add_template_correction_review(
                            db,
                            payload=char_info,
                            corrected_template_filename=saved_template_filename,
                            tournament=tournament,
                            player=player,
                            actor=current_user,
                        )

        
        db.commit()
        if templates_added:
            _invalidate_template_matcher_cache()
        deleted_crops = delete_temporary_crop_urls(temporary_crop_urls)
        if deleted_crops:
            print(f"[Cleanup] Removed {deleted_crops} registered crop images")
        invalidate_dashboard_cache(tournament_id)
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
            name=automatic_player_name(seed_number),
        )
        db.add(player)
        # Flush inside the shared icon lock to keep filesystem/DB lock order consistent.

    else:
        player.name = automatic_player_name(seed_number)

    icon_dir = (PLAYER_ICONS_DIR / f"tournament_{tournament_id}").resolve()
    if not _is_within(icon_dir, PLAYER_ICONS_DIR):
        raise HTTPException(status_code=422, detail="Unsafe icon path")
    file_path = icon_dir / f"seed_{seed_number}.webp"
    icon_url = f"/api/uploads/player_icons/tournament_{tournament_id}/seed_{seed_number}.webp"
    await save_player_icon(image, player, file_path, icon_url, db)
    invalidate_dashboard_cache_safely(tournament_id)
    return {"url": icon_url, "player_id": player.id}


@app.post("/api/analyze/deck")
async def analyze_deck(
    request: Request,
    _analysis_capacity: AnalysisReservation = Depends(require_analysis_capacity),
):
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
    pre_cropped_flags = [
        str(value).strip().lower() in {"1", "true", "yes", "on"}
        for value in form.getlist("image_pre_cropped")
    ]
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
            return await run_cpu_analysis(
                process_images,
                saved_paths,
                tournament_id,
                seed_number,
                pre_cropped_flags=pre_cropped_flags,
                reservation=request_analysis_reservation(_analysis_capacity),
            )
        except AnalysisBusyError as e:
            raise HTTPException(
                status_code=429,
                detail="画像解析が混み合っています。数秒後にもう一度お試しください。",
                headers={"Retry-After": "5"},
            ) from e
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
    image: UploadFile = File(...),
    _analysis_capacity: AnalysisReservation = Depends(require_analysis_capacity),
):
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"match_t{tournament_id}_a{attacker_seed}_d{defender_seed}.png")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
        
    try:
        from services.match_processor import extract_match_results
        result = await run_cpu_analysis(
            extract_match_results,
            file_path,
            reservation=request_analysis_reservation(_analysis_capacity),
        )
        
        resp = {
            "tournament_id": tournament_id,
            "attacker_seed": attacker_seed,
            "defender_seed": defender_seed,
            "stage": stage,
            "rounds": result["rounds"],
            "winner": result["winner"]
        }
        return resp
    except AnalysisBusyError as e:
        raise HTTPException(
            status_code=429,
            detail="画像解析が混み合っています。数秒後にもう一度お試しください。",
            headers={"Retry-After": "5"},
        ) from e
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
    tournament = require_tournament_viewer(tournament_id, db, current_user)
    cached = get_private_dashboard_cache(tournament, "bracket")
    if cached is not None:
        return cached
    # 全プレイヤーと試合結果を取得
    players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()
    player_by_seed = {p.seed_number: p for p in players}
    matches = arena_phases.effective_matches(db, [tournament_id])
    
    def get_winner(p1_id, p2_id):
        if not p1_id or not p2_id:
            return None
        for m in matches:
            if m.winner_id:
                if (m.attacker_id == p1_id and m.defender_id == p2_id) or \
                   (m.attacker_id == p2_id and m.defender_id == p1_id):
                    return m.winner_id
        return None

    initial_sets = arena_phases.initial_deck_sets(db, [p.id for p in players])
    complete_ids = {ds.player_id for ds in initial_sets if len(ds.teams) == 5 and all(all(getattr(t, f"char{i}_id") is not None for i in range(1, 6)) for t in ds.teams)}
    if not tournament.deck_registration_phases:
        complete_ids = {p.id for p in players if p.deck_sets}
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
                "has_deck": p1.id in complete_ids if p1 else False
            })
            group_players.append({
                "seed": s2, "id": p2_id, "name": p2.name if p2 else f"Player {s2}",
                "icon_url": p2.icon_url if p2 else None,
                "has_deck": p2.id in complete_ids if p2 else False
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
            "has_deck": p.id in complete_ids
        }
        
    champ_players = [get_p_info(champion_seeds[i], i+1) for i in range(8)]
    
    return set_private_dashboard_cache(tournament, "bracket", {
        "groups": groups,
        "phase_matches": arena_phases.state(tournament, db)["matches"] if tournament.deck_registration_phases else [],
        "champion_finals": {
            "players": champ_players,
            "qf_winners": champ_qf_winners,
            "sf_winners": champ_sf_winners,
            "winner": champ_winner
        }
    })

@app.post("/api/tournaments/{tournament_id}/matches")
async def save_match(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user),
):
    phase_tournament = require_legacy_registration_path(tournament_id, db, current_user)
    if phase_tournament.deck_registration_phases:
        if phase_tournament.registration_scope != "full_64":
            raise HTTPException(409, "Use the result/registration API for this tournament format")
        require_unpublished_champion_edit(phase_tournament)
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(422, "JSON object required")
        attacker = db.query(models.Player).filter_by(tournament_id=tournament_id, seed_number=data.get("attacker_seed")).first()
        defender = db.query(models.Player).filter_by(tournament_id=tournament_id, seed_number=data.get("defender_seed")).first()
        if not attacker or not defender or attacker.id == defender.id:
            raise HTTPException(422, "Invalid participants")
        _, nodes, _, _ = arena_phases.context(phase_tournament, db)
        node = next((n for n in nodes.values() if set(n["participants"]) == {attacker.id, defender.id}), None)
        if node is None:
            raise HTTPException(409, "Participants are not qualified for this match")
        rounds = data.get("rounds", [])
        if not isinstance(rounds, list) or len(rounds) != 5 or any(not isinstance(r, dict) for r in rounds) or sorted(r.get("round", 0) for r in rounds) != [1,2,3,4,5]:
            raise HTTPException(422, "Exactly five numbered rounds are required")
        if any((r.get("left"), r.get("right")) not in {("WIN", "LOSE"), ("LOSE", "WIN")} for r in rounds):
            raise HTTPException(422, "Round winners are unresolved")
        winners = [attacker.id if r["left"] == "WIN" else defender.id for r in sorted(rounds, key=lambda r: r["round"])]
        payload = result_revision_payload(node, winners, data.get("phase_context"))
        arena_phases.save_result(phase_tournament, node["key"], payload, db)
        invalidate_dashboard_cache_safely(tournament_id)
        return {"ok": True, "history_preserved": True}
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
    invalidate_dashboard_cache(tournament_id)
    return {"ok": True}



@app.post("/api/tournaments/{tournament_id}/snapshot/rebuild")
def rebuild_tournament_snapshot(
    tournament_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.require_admin),
):
    """管理者が手動でスナップショットを再生成する"""
    tournament = db.query(models.Tournament).filter(
        models.Tournament.id == tournament_id
    ).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="大会が見つかりません")
    invalidate_dashboard_cache(tournament_id)
    background_tasks.add_task(recompute_snapshot, tournament_id, current_user.id)
    return {"ok": True, "message": f"tournament_id={tournament_id} のスナップショット再生成を開始しました"}

@app.get("/api/tournaments/{tournament_id}/dashboard/stats")
def get_dashboard_stats(
    tournament_id: int,
    seed: int = None,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
    registration_phase: str = "initial",
    trends_result: Optional[str] = None,
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    if trends_result is not None:
        return _trends_stats([tournament_id], db, registration_phase, trends_result)
    if registration_phase == "all" and tournament.deck_registration_phases:
        all_params = {"registration_phase": "all", "seed": seed}
        cached = get_private_dashboard_cache(tournament, "stats", all_params)
        if cached is not None:
            return cached
        stages = [phase for phase in arena_phases.ANALYSIS_STAGES if arena_phases.analysis_applicable(tournament, phase)]
        with arena_phases.analysis_scope(db, [tournament_id]):
            by_phase = {phase: _composition_stage_stats(tournament_id, db, current_user, seed, phase) for phase in stages}
        teams = [row for values in by_phase.values() for row in values.get("team_usage", [])]
        teams.sort(key=lambda row: row.get("count", 0), reverse=True)
        return set_private_dashboard_cache(tournament, "stats", {"registration_phase": "all", "by_phase": by_phase, "team_usage": teams,
                "character_usage_by_result": {}, "character_usage": [], "character_stats": []}, all_params)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    params = {"seed": seed, "registration_phase": registration_phase}
    cached = get_private_dashboard_cache(tournament, "stats", params)
    if cached is not None:
        return cached
    stats = _compute_dashboard_stats(tournament_id, db, current_user, seed, registration_phase)
    if "team_usage" in stats:
        stats["team_usage"] = stats["team_usage"][:50]
    return set_private_dashboard_cache(tournament, "stats", stats, params)




# ===== スナップショット管理 =====

def apply_snapshot(tournament_id: int, stats: dict, db: Session):
    """Apply snapshot values without committing the current Session."""
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if snap is None:
        snap = models.TournamentSnapshot(tournament_id=tournament_id)
        db.add(snap)
    snap.team_usage = stats.get("team_usage", [])
    snap.char_stats = stats.get("character_stats", [])
    snap.matchups = stats.get("matchups", [])
    snap.total_players = stats.get("total_players")
    snap.total_matches = stats.get("total_matches")
    return snap


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
    registration_phase: str = "initial",
):
    tournament = require_tournament_viewer(tournament_id, db, current_user)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    display_phase = (arena_phases.normalized_stage(tournament, arena_phases.stored_analysis_phase(tournament, registration_phase))
        if tournament.deck_registration_phases else "legacy")
    registration_phase = arena_phases.stored_analysis_phase(tournament, registration_phase)
    all_players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()
    players = [p for p in all_players if not seed or p.seed_number == seed]
    all_phase_decks = arena_phases.phase_deck_sets(db, [p.id for p in all_players], registration_phase)
    if registration_phase != "initial":
        # Denominator includes qualified but not-yet-registered participants.
        _, _, qualifications, _ = arena_phases.context(tournament, db)
        players = [p for p in players if (p.id, registration_phase) in qualifications]
    player_ids = [p.id for p in players]
    selected_players = set(player_ids)
    deck_sets = [deck for deck in all_phase_decks if deck.player_id in selected_players]
    all_matches = arena_phases.effective_matches(db, [tournament_id])
    character_ids = {getattr(team, f"char{i}_id") for deck in all_phase_decks for team in deck.teams for i in range(1, 6)} - {None}
    character_by_id = {c.id: c for c in db.query(models.Character).filter(models.Character.id.in_(character_ids)).all()}
    team_players = {}
    for deck in all_phase_decks:
        for team in deck.teams:
            key = frozenset(getattr(team, f"char{i}_id") for i in range(1, 6) if getattr(team, f"char{i}_id") is not None)
            team_players.setdefault(key, set()).add(deck.player_id)
    deck_set_ids = [ds.id for ds in deck_sets]
    ds_to_player = {ds.id: ds.player_id for ds in deck_sets}
    
    deck_teams = [team for deck in deck_sets for team in deck.teams]
    
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
    matches = all_matches
    char_match_stats = {} # {char_id: {"wins": 0, "total": 0}}
    team_match_stats = {} # {canonical_id: {"wins": 0, "total": 0}}
    char_position_match_stats = {} # {char_id: {pos: {"wins": 0, "total": 0}}}

    for match in matches:
        if not arena_phases.matches_analysis_phase(db, match, registration_phase):
            continue
        attacker_id = match.attacker_id
        defender_id = match.defender_id
        
        # プレイヤーの編成セットを取得
        attacker_ds = arena_phases.deck_for_match(match, attacker_id, db)
        defender_ds = arena_phases.deck_for_match(match, defender_id, db)
        
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
    player_by_id = {p.id: p for p in all_players}

    # キャラIDをプレイヤーにマッピング
    # {char_id: set(player_id)}
    char_to_players = {}
    for ds in all_phase_decks:
        for team in ds.teams:
            for c_id in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]:
                if c_id is not None:
                    if c_id not in char_to_players:
                        char_to_players[c_id] = set()
                    char_to_players[c_id].add(ds.player_id)

    player_result_cache = {
        player_id: result_label(code)
        for player_id, code in calculate_player_results(
            tournament,
            all_players,
            all_matches,
        ).items()
    }

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
        char = character_by_id.get(c_id)
        if char:
            m_stats = char_match_stats.get(c_id, {"wins": 0, "total": 0})
            win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else None
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
                    "best_result": best_res,
                    "commander_results": team_statistics_display.finish_counts(p_ms["players"], player_result_cache)
                })
                
            user_ids = char_to_players.get(c_id, set())
            char_list.append({
                "id": char.id,
                "name": char.name,
                "rarity": char.rarity,
                "count": count,
                "player_count": len(user_ids),
                "adoption_rate": round(len(user_ids) / len(player_ids) * 100, 1) if player_ids else 0.0,
                "win_count": m_stats["wins"],
                "total_matches": m_stats["total"],
                "win_rate": round(win_rate, 1) if win_rate is not None else None,
                "best_result": get_best_result_for_char(c_id),
                "commander_results": team_statistics_display.finish_counts(user_ids, player_result_cache),
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
            char = character_by_id.get(c_id)
            if char:
                team_chars.append({"id": char.id, "name": char.name, "rarity": char.rarity})
        
        canon_id = ",".join(map(str, sorted_chars))
        m_stats = team_match_stats.get(canon_id, {"wins": 0, "total": 0})
        win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else None

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
        team_player_ids = team_players.get(frozenset(sorted_chars), set())

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
            player = player_by_id.get(pid)
            if player:
                t = tournament
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
            "player_count": len(team_player_ids),
            "adoption_rate": round(len(team_player_ids) / len(player_ids) * 100, 1) if player_ids else 0.0,
            "win_count": m_stats["wins"],
            "total_matches": m_stats["total"],
            "win_rate": round(win_rate, 1) if win_rate is not None else None,
            "best_result": best_team_result if team_player_ids else None,
            "adopted_players": adopted_players,
            "position_stats": pos_stats_out
        })
    team_statistics_display.annotate(team_list, team_statistics_display.metadata(
        deck_sets, all_matches, player_result_cache, display_phase, {tournament_id: tournament}, all_players), display_phase)
    team_list.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "registration_phase": display_phase,
        "character_usage": char_list,
        "character_stats": char_list,
        "character_usage_by_result": _compute_character_usage_by_result([tournament_id], db, registration_phase, prepared_scope={"players": all_players, "decks": all_phase_decks, "matches": all_matches, "tournaments": {tournament_id: tournament}, "characters": character_by_id, "eligible_player_ids": {pid for pid, phase in qualifications if phase == registration_phase} if registration_phase != "initial" else set(player_ids)}),
        "team_usage": team_list,
        "total_players": len(player_ids),
        "total_matches": sum(arena_phases.matches_analysis_phase(db, m, registration_phase) for m in matches)
    }

@app.get("/api/tournaments/{tournament_id}/dashboard/matchups")
def get_dashboard_matchups(
    tournament_id: int,
    seed: int = None,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
    registration_phase: str = "initial",
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    if registration_phase == "all" and tournament.deck_registration_phases:
        all_params = {"registration_phase": "all", "seed": seed}
        cached = get_private_dashboard_cache(tournament, "matchups", all_params)
        if cached is not None:
            return cached
        stages = [phase for phase in arena_phases.ANALYSIS_STAGES if arena_phases.analysis_applicable(tournament, phase)]
        with arena_phases.analysis_scope(db, [tournament_id]):
            rows = [{**row, "registration_phase": phase} for phase in stages
                    for row in get_dashboard_matchups(tournament_id, seed, db, current_user, phase)["matchups"]]
        return set_private_dashboard_cache(tournament, "matchups", {"registration_phase": "all", "matchups": rows}, all_params)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    if registration_phase == "legacy":
        registration_phase = "initial"
    params = {"seed": seed, "registration_phase": registration_phase}
    cached = get_private_dashboard_cache(tournament, "matchups", params)
    if cached is not None:
        return cached
    query = db.query(models.Match).filter(models.Match.tournament_id == tournament_id)
    if seed:
        player = db.query(models.Player).filter(models.Player.tournament_id == tournament_id, models.Player.seed_number == seed).first()
        if player:
            query = query.filter(or_(models.Match.attacker_id == player.id, models.Match.defender_id == player.id))
        else:
            return {"matchups": []}

    matches = arena_phases.effective_matches(db, [tournament_id])
    if seed:
        matches = [m for m in matches if player.id in (m.attacker_id, m.defender_id)]
    matchup_results = []
    
    for match in matches:
        if not arena_phases.matches_analysis_phase(db, match, registration_phase):
            continue
        attacker_ds = arena_phases.deck_for_match(match, match.attacker_id, db)
        defender_ds = arena_phases.deck_for_match(match, match.defender_id, db)
        
        if not attacker_ds or not defender_ds:
            continue
            
        attacker_teams = {t.team_number: t for t in attacker_ds.teams}
        defender_teams = {t.team_number: t for t in defender_ds.teams}
        
        for round_res in match.round_results:
            rn = round_res.round_number
            a_team = attacker_teams.get(rn)
            d_team = defender_teams.get(rn)
            
            if a_team and d_team:
                a_slots = [
                    (character_id, collection_level)
                    for character_id, collection_level in zip(
                        [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id],
                        get_team_collection_levels(a_team),
                    )
                    if character_id is not None
                ]
                d_slots = [
                    (character_id, collection_level)
                    for character_id, collection_level in zip(
                        [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id],
                        get_team_collection_levels(d_team),
                    )
                    if character_id is not None
                ]
                a_chars = [character_id for character_id, _ in a_slots]
                d_chars = [character_id for character_id, _ in d_slots]
                a_collections = [collection_level for _, collection_level in a_slots]
                d_collections = [collection_level for _, collection_level in d_slots]
                
                a_sorted = tuple(sorted(a_chars))
                d_sorted = tuple(sorted(d_chars))
                
                if len(a_chars) == 5 and len(d_chars) == 5:
                    winner_is_attacker = round_res.winner_id == match.attacker_id
                    
                    matchup_results.append({
                        "match_id": match.id,
                        "round_number": rn,
                        "attacker_player_id": match.attacker_id,
                        "defender_player_id": match.defender_id,
                        "winner_player_id": round_res.winner_id,
                        "attacker_team_id": attacker_teams[rn].id,
                        "defender_team_id": defender_teams[rn].id,
                        "attacker_team_number": rn,
                        "defender_team_number": rn,
                        "stage": match.stage,
                        "attacker_team": list(a_chars),
                        "defender_team": list(d_chars),
                        "attacker_collections": a_collections,
                        "defender_collections": d_collections,
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
                    
    return set_private_dashboard_cache(tournament, "matchups", {"matchups": matchup_results}, params)

@app.get("/api/tournaments/{tournament_id}/dashboard/best8-decks")
def get_best8_decks(
    tournament_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional),
    registration_phase: str = "initial",
):
    """ベスト8進出者のプレイヤー名、成績、登録編成をまとめて取得する"""
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    if registration_phase == "all" and tournament.deck_registration_phases:
        all_params = {"registration_phase": "all"}
        cached = get_private_dashboard_cache(tournament, "best8-decks", all_params)
        if cached is not None:
            return cached
        stages = [phase for phase in arena_phases.ANALYSIS_STAGES if arena_phases.analysis_applicable(tournament, phase)]
        with arena_phases.analysis_scope(db, [tournament_id]):
            rows = [row for phase in stages for row in get_best8_decks(tournament_id, db, current_user, phase)]
        return set_private_dashboard_cache(tournament, "best8-decks", rows, all_params)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    cached = get_private_dashboard_cache(tournament, "best8-decks", {"registration_phase":registration_phase})
    if cached is not None:
        return cached
    all_players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()
    all_matches = arena_phases.effective_matches(db, [tournament_id])
    if tournament.deck_registration_phases:
        _, _, qualifications, registration = arena_phases.context(tournament, db)
        stored_phase = arena_phases.stored_analysis_phase(tournament, registration_phase)
        result_codes = calculate_player_results(tournament, all_players, all_matches)
        results = []
        for player in all_players:
            if (player.id, stored_phase) not in qualifications:
                continue
            if registration_phase == "league" and (player.id, "best8") not in qualifications:
                continue
            teams, _ = registration(player.id, stored_phase)
            if not teams:
                continue
            details = _get_player_details_by_player(tournament_id, player, db, registration_phase,
                registration_sets=[arena_phases.projected_deck(player.id, teams, -player.id)], resolved_matches=all_matches)
            if not details["decks"]:
                continue
            code = result_codes.get(player.id, "best8" if tournament.registration_scope == "champion_8" else "best64")
            results.append({"player": {"id": player.id, "seed": player.seed_number, "original_seed": player.seed_number,
                "champion_slot": player.champion_slot, "name": player.name, "icon_url": player.icon_url, "has_deck": True},
                "result": result_label(code), "sort_score": TOURNAMENT_RESULT_SCORES[code],
                "registration_phase": registration_phase, "decks": details["decks"]})
        results.sort(key=lambda item: (item["sort_score"], item["player"]["original_seed"] or 0))
        return set_private_dashboard_cache(tournament, "best8-decks", results, {"registration_phase": registration_phase})
    if tournament.registration_scope == "champion_8":
        result_codes = calculate_player_results(tournament, all_players, all_matches)
        results = []
        for player in sorted(all_players, key=lambda item: item.champion_slot or 999):
            result_code = result_codes.get(player.id, "best8")
            details = _get_player_details_by_player(tournament_id, player, db, registration_phase)
            results.append({
                "player": {
                    "id": player.id,
                    "seed": player.seed_number,
                    "original_seed": player.seed_number,
                    "champion_slot": player.champion_slot,
                    "name": player.name,
                    "icon_url": player.icon_url,
                    "has_deck": bool(details["decks"]),
                },
                "result": result_label(result_code),
                "sort_score": TOURNAMENT_RESULT_SCORES[result_code],
                "registration_phase": registration_phase,
                "decks": details["decks"],
            })
        results.sort(key=lambda item: (item["sort_score"], item["player"]["champion_slot"]))
        return set_private_dashboard_cache(tournament, "best8-decks", results, {"registration_phase":registration_phase})

    bracket = get_tournament_bracket(tournament_id, db, current_user)
    best8_players = bracket["champion_finals"]["players"]
    champ_finals = bracket["champion_finals"]
    
    qf_winners = set(champ_finals["qf_winners"]) # ベスト4進出者
    sf_winners = set(champ_finals["sf_winners"]) # 決勝進出者
    winner_id = champ_finals["winner"]           # 優勝者
    result_codes = calculate_player_results(
        tournament,
        all_players,
        all_matches,
    )
    
    results = []
    for p_info in best8_players:
        pid = p_info["id"]
        if pid:
            # 成績の判定
            result_code = result_codes.get(pid, "best8")
            result_label_value = result_label(result_code)
            sort_score = TOURNAMENT_RESULT_SCORES[result_code]
                
            # 認証済みの内部処理としてプレイヤー詳細データを取得
            details = _get_player_details_data(tournament_id, p_info["original_seed"], db, registration_phase)
            results.append({
                "player": p_info,
                "result": result_label_value,
                "sort_score": sort_score,
                "registration_phase": registration_phase,
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
    
    return set_private_dashboard_cache(tournament, "best8-decks", results, {"registration_phase":registration_phase})


# ============================================================
# 大会横断検索 API
# ============================================================

from pydantic import BaseModel as PydanticBaseModel, field_validator
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
            "player_count": 0,
            "win_count": 0,
            "total_matches": 0,
            "adopted_players": [],
            "position_stats": [
                {"position": p, "count": 0, "pct": 0.0, "wins": 0, "total": 0, "win_rate": None, "best_result": None}
                for p in range(1, 6)
            ],
            "_seen_adopted": set()
        }
    target = merged_teams[cid]
    target["count"] += team.get("count", 0)
    target["player_count"] += team.get("player_count", 0)
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
            current_score = RESULT_SCORES.get(cur_ps.get("best_result", "不明"), 999)
            new_result = ps.get("best_result")
            if new_result and RESULT_SCORES.get(new_result, 999) < current_score:
                cur_ps["best_result"] = new_result

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


def _compute_character_usage_by_result(tournament_ids: List[int], db: Session, registration_phase="initial", *, prepared_scope=None):
    """最終成績の条件ごとに、各選手が採用したキャラクターを集計する。"""
    empty_result = {
        key: {"label": label, "denominator": 0, "characters": []}
        for key, label, _ in CHARACTER_USAGE_RESULT_FILTERS
    }
    if not tournament_ids:
        return empty_result

    scope = db.info.get("arena_analysis_scope")
    if prepared_scope is None and scope is not None:
        scoped_players = [p for p in scope["players"] if p.tournament_id in tournament_ids]
        prepared_scope = {"players": scoped_players,
            "matches": arena_phases.effective_matches(db, tournament_ids),
            "decks": arena_phases.phase_deck_sets(db, [p.id for p in scoped_players], registration_phase),
            "tournaments": {tid: scope["tournaments"][tid] for tid in tournament_ids},
            "characters": {c.id: c for c in db.query(models.Character).all()}}
    players = prepared_scope["players"] if prepared_scope is not None else db.query(models.Player).filter(
        models.Player.tournament_id.in_(tournament_ids)
    ).all()
    if not players:
        return empty_result

    player_ids = [player.id for player in players]
    matches = prepared_scope["matches"] if prepared_scope is not None else arena_phases.effective_matches(db, tournament_ids)
    deck_sets = prepared_scope["decks"] if prepared_scope is not None else arena_phases.phase_deck_sets(db, player_ids, registration_phase)
    deck_set_ids = [deck_set.id for deck_set in deck_sets]
    deck_teams = (
        [team for deck in deck_sets for team in deck.teams]
        if deck_set_ids
        else []
    )

    players_by_tournament = {}
    for player in players:
        players_by_tournament.setdefault(player.tournament_id, []).append(player)
    matches_by_tournament = {}
    for match in matches:
        matches_by_tournament.setdefault(match.tournament_id, []).append(match)

    tournaments_by_id = prepared_scope["tournaments"] if prepared_scope is not None else {
        tournament.id: tournament
        for tournament in db.query(models.Tournament).filter(
            models.Tournament.id.in_(list(players_by_tournament))
        ).all()
    }
    result_score_by_player = {}
    for tournament_id, tournament_players in players_by_tournament.items():
        codes = calculate_player_results(
            tournaments_by_id[tournament_id],
            tournament_players,
            matches_by_tournament.get(tournament_id, []),
        )
        result_score_by_player.update({
            player_id: TOURNAMENT_RESULT_SCORES[code]
            for player_id, code in codes.items()
        })

    deck_set_to_player = {
        deck_set.id: deck_set.player_id for deck_set in deck_sets
    }
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
            if (
                character_id is not None
                and character_id != EMPTY_SLOT_CHARACTER_ID
            ):
                characters_by_player[player_id].add(character_id)
                used_character_ids.add(character_id)

    characters = list(prepared_scope["characters"].values()) if prepared_scope is not None else (
        db.query(models.Character).filter(
            models.Character.id.in_(used_character_ids)
        ).all()
        if used_character_ids
        else []
    )
    character_by_id = {
        character.id: character for character in characters
    }

    result = {}
    all_player_ids = set(player_ids)
    if registration_phase != "initial":
        qualified_ids = prepared_scope.get("eligible_player_ids") if prepared_scope is not None else None
        if qualified_ids is None:
            qualified_ids = set()
            for tournament in tournaments_by_id.values():
                _, _, qualifications, _ = arena_phases.context(tournament, db)
                qualified_ids.update(pid for pid, phase in qualifications if phase == registration_phase)
        all_player_ids.intersection_update(qualified_ids)
    for key, label, maximum_score in CHARACTER_USAGE_RESULT_FILTERS:
        eligible_player_ids = (
            all_player_ids
            if maximum_score is None
            else {
                player_id
                for player_id, score in result_score_by_player.items()
                if player_id in all_player_ids and score <= maximum_score
            }
        )
        denominator = len(eligible_player_ids)
        adoption_counts = {}
        for player_id in eligible_player_ids:
            for character_id in characters_by_player.get(player_id, set()):
                adoption_counts[character_id] = (
                    adoption_counts.get(character_id, 0) + 1
                )

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
                "usage_rate": (
                    round(count / denominator * 100, 1)
                    if denominator
                    else 0.0
                ),
            })
        character_rows.sort(
            key=lambda row: (-row["count"], row["character_id"])
        )
        result[key] = {
            "label": label,
            "denominator": denominator,
            "characters": character_rows,
        }
    return result


class CrossAnalysisPhaseRequest(PydanticBaseModel):
    @field_validator("registration_phase", mode="before", check_fields=False)
    @classmethod
    def normalize_stage_filter(cls, value):
        return arena_phases.canonical_analysis_stage(value)


class CrossTournamentRequest(CrossAnalysisPhaseRequest):
    trends_result: Optional[str] = None
    """大会横断検索リクエスト"""
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None
    registration_scope: Literal["all", "full_64", "champion_8"] = "all"
    registration_phase: Literal["legacy", "initial", "best8", "league", "championship", "final", "all"] = "championship"


class CrossTournamentCharacterDetailRequest(CrossAnalysisPhaseRequest):
    character_id: int
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None
    registration_scope: Literal["all", "full_64", "champion_8"] = "all"
    registration_phase: Literal["legacy", "initial", "best8", "league", "championship", "final", "all"] = "championship"


def filter_cross_tournament_ids(db: Session, tournament_ids, registration_scope="all", registration_phase=None):
    query = db.query(models.Tournament).filter(
        models.Tournament.publication_status == "published",
        models.Tournament.has_match_data.is_(True),
    )
    if tournament_ids:
        query = query.filter(models.Tournament.id.in_(tournament_ids))
    if registration_scope != "all":
        query = query.filter(models.Tournament.registration_scope == registration_scope)
    if registration_phase == "legacy":
        query = query.filter(or_(models.Tournament.deck_registration_phases.is_(False), models.Tournament.deck_registration_phases.is_(None)))
    elif registration_phase in (*arena_phases.PHASES, *arena_phases.ANALYSIS_STAGES):
        query = query.filter(models.Tournament.deck_registration_phases.is_(True))
    allowed = {tournament.id for tournament in query.all()}
    if tournament_ids:
        return [tournament_id for tournament_id in tournament_ids if tournament_id in allowed]
    return sorted(allowed)


def cross_registration_breakdown(tournament_ids, db: Session, registration_phase="initial"):
    if not tournament_ids:
        return {
            "total_tournaments": 0, "full_64_tournaments": 0, "champion_8_tournaments": 0,
            "total_registered_players": 0, "full_64_registered_players": 0,
            "champion_8_registered_players": 0, "total_teams": 0,
            "total_matches": 0, "total_round_results": 0,
        }
    scope = db.info.get("arena_analysis_scope")
    tournaments = ([t for t in scope["tournaments"].values() if t.id in tournament_ids] if scope is not None else
        db.query(models.Tournament).filter(models.Tournament.id.in_(tournament_ids)).all())
    players = ([p for p in scope["players"] if p.tournament_id in tournament_ids] if scope is not None else
        db.query(models.Player).filter(models.Player.tournament_id.in_(tournament_ids)).all())
    if registration_phase != "initial":
        qualifications = set()
        for tournament in tournaments:
            qualifications.update(arena_phases.analysis_qualified_ids(tournament, db, registration_phase,
                [p.id for p in players if p.tournament_id == tournament.id]))
        players = [p for p in players if p.id in qualifications]
    player_ids = [player.id for player in players]
    initial_sets = arena_phases.phase_deck_sets(db, player_ids, registration_phase)
    matches = [m for m in arena_phases.effective_matches(db, tournament_ids) if arena_phases.matches_analysis_phase(db, m, registration_phase)]
    match_ids = [match.id for match in matches]
    scope_by_tournament = {tournament.id: tournament.registration_scope for tournament in tournaments}
    return {
        "total_tournaments": len(tournaments),
        "full_64_tournaments": sum(t.registration_scope == "full_64" for t in tournaments),
        "champion_8_tournaments": sum(t.registration_scope == "champion_8" for t in tournaments),
        "total_registered_players": len(players),
        "full_64_registered_players": sum(scope_by_tournament[p.tournament_id] == "full_64" for p in players),
        "champion_8_registered_players": sum(scope_by_tournament[p.tournament_id] == "champion_8" for p in players),
        "total_teams": sum(len(deck.teams) for deck in initial_sets),
        "total_matches": len(matches),
        "total_round_results": sum(len(match.round_results) for match in matches),
    }


def empty_cross_tournament_stats(db: Session):
    return {
        "total_players": 0, "total_matches": 0, "character_usage": [],
        "character_stats": [], "character_usage_by_result": _compute_character_usage_by_result([], db),
        "team_usage": [], "matchups": [],
        "registration_breakdown": cross_registration_breakdown([], db),
    }


def cross_snapshot_has_distinct_counts(snapshot, db: Session, registered_players=None):
    """Accept only structurally complete v2-style aggregation JSON.

    Legacy/corrupt JSON falls back as a whole tournament.  Empty arrays are
    valid only when the tournament genuinely has no registered players.
    """
    char_stats = snapshot.char_stats
    team_usage = snapshot.team_usage
    if not isinstance(char_stats, list) or not isinstance(team_usage, list):
        return False
    if registered_players is None:
        registered_players = db.query(models.Player.id).filter(
            models.Player.tournament_id == snapshot.tournament_id
        ).count()
    if registered_players == 0:
        return not char_stats and not team_usage
    if not char_stats or not team_usage:
        return False
    return all(
        isinstance(item, dict) and isinstance(item.get("player_count"), int)
        and item["player_count"] >= 0
        for item in char_stats + team_usage
    )


@app.post("/api/dashboard/cross-tournament/stats")
def get_cross_tournament_stats(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    ids = _cross_target_ids(body, db)
    if body.trends_result is not None:
        return _trends_stats(ids, db, body.registration_phase, body.trends_result)
    if body.registration_phase == "all":
        with contextlib.ExitStack() as shared_scope:
            return {"registration_phase": "all", "by_phase": {
                phase: _cross_aggregate(ids, db, phase, shared_scope=shared_scope)
                for phase in ("legacy", *arena_phases.ANALYSIS_STAGES)}}
    stats = _cross_aggregate(ids, db, body.registration_phase)
    # Preserve the response limit, but keep the full list in the shared cache.
    stats["team_usage"] = stats.get("team_usage", [])[:50]
    return stats


def _trends_stats(ids, db, phase, finish, *, shared_matches=None):
    """One population for both adoption rankings; no per-composition queries."""
    thresholds = {"all": None, "best16": 16, "best8": 8, "best4": 4, "runner_up": 2, "champion": 1}
    if finish not in thresholds or phase not in ("legacy", "league", "championship", "final"):
        raise HTTPException(422, "Invalid Trends filter")
    def compute():
        with arena_phases.analysis_scope(db, ids) as scope:
            tournaments = {tid:t for tid,t in scope["tournaments"].items() if arena_phases.analysis_applicable(t, phase)}
            players = [p for p in scope["players"] if p.tournament_id in tournaments]
            matches = (arena_phases.effective_matches(db, list(tournaments)) if shared_matches is None
                       else [match for match in shared_matches if match.tournament_id in tournaments])
            results = {}
            for tid,tournament in tournaments.items():
                codes = calculate_player_results(tournament, [p for p in players if p.tournament_id==tid], [m for m in matches if m.tournament_id==tid])
                results.update({pid:result_label(code) for pid,code in codes.items()})
            decks = arena_phases.phase_deck_sets(db, [p.id for p in players], phase)
            maximum = thresholds[finish] if phase=="legacy" else None
            decks = [d for d in decks if len(d.teams)==5 and (maximum is None or RESULT_SCORES.get(results.get(d.player_id),999)<=maximum)]
            eligible = {d.player_id for d in decks}
            denominator = len(eligible)
            characters = {c.id:c for c in db.query(models.Character).all()}
            character_users, team_users, occurrences, rows = {}, {}, {}, {}
            for deck in decks:
                for team in deck.teams:
                    key = team_statistics_display.canonical(team)
                    if not key: continue
                    ids_in_team = [getattr(team,f"char{i}_id") for i in range(1,6)]
                    for cid in set(ids_in_team)-{EMPTY_SLOT_CHARACTER_ID}:
                        if cid in characters: character_users.setdefault(cid,set()).add(deck.player_id)
                    team_users.setdefault(key,set()).add(deck.player_id)
                    occurrences[key] = occurrences.get(key,0)+1
                    rows.setdefault(key,{"canonical_id":key,"character_ids":ids_in_team,"characters":[{"id":cid,"name":characters[cid].name} for cid in ids_in_team if cid in characters],"win_count":0,"total_matches":0})
            for match in matches:
                if not arena_phases.matches_analysis_phase(db,match,phase): continue
                for pid in (match.attacker_id,match.defender_id):
                    if pid not in eligible: continue
                    used = arena_phases.deck_for_match(match,pid,db)
                    teams = {team.team_number:team for team in used.teams} if used else {}
                    for result in match.round_results:
                        if result.winner_id not in (match.attacker_id,match.defender_id): continue
                        team = teams.get(result.round_number)
                        key = team_statistics_display.canonical(team) if team else None
                        if key not in rows or pid not in team_users[key]: continue
                        rows[key]["total_matches"] += 1
                        rows[key]["win_count"] += int(result.winner_id==pid)
            teams = list(rows.values())
            for row in teams:
                key=row["canonical_id"];count=len(team_users[key]);total=row["total_matches"]
                row.update(count=occurrences[key],player_count=count,adoption_rate=round(count/denominator*100,1) if denominator else 0,win_rate=round(row["win_count"]/total*100,1) if total else None)
            team_statistics_display.annotate(teams,team_statistics_display.metadata(decks,matches,results,phase,tournaments,players),phase)
            teams.sort(key=lambda row:(-row["player_count"],-row["count"],row["canonical_id"]))
            chars=[{"id":cid,"name":characters[cid].name,"count":len(users),"usage_rate":round(len(users)/denominator*100,1) if denominator else 0} for cid,users in character_users.items()]
            chars.sort(key=lambda row:(-row["count"],row["id"]))
            return {"registration_phase":phase,"total_players":denominator,"team_usage":teams,"character_usage_by_result":{"all":{"denominator":denominator,"characters":chars}}}
    return cross_analytics.cached(db,ids,phase,"trends-population-v1:"+finish,compute)


@app.get("/api/season-summary/{championship_id}")
def get_season_summary(
    championship_id: int, play_server: season_summary.PlayServer,
    response: Response, scope_only: bool = False, db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    title, rows, scope = season_summary.public_scope(db, championship_id, play_server)
    if scope_only:
        return scope
    return season_summary.statistics(db, title, rows, scope, _trends_stats, _cross_aggregate)


def _cross_target_ids(body, db):
    ids = body.tournament_ids or resolve_cross_tournament_ids(
        db, body.tournament_ids, body.play_server, body.championship_id)
    if not ids:
        return []
    return sorted(set(filter_cross_tournament_ids(db, ids, body.registration_scope, body.registration_phase)))


def _team_display_metadata(ids, db, phase):
    def compute():
        with arena_phases.analysis_scope(db, ids) as scope:
            matches = arena_phases.effective_matches(db, ids)
            players = [p for p in scope["players"] if p.tournament_id in ids]
            decks = arena_phases.phase_deck_sets(db, [p.id for p in players], phase)
            results = {}
            for tid in ids:
                codes = calculate_player_results(scope["tournaments"][tid],
                    [p for p in players if p.tournament_id == tid],
                    [m for m in matches if m.tournament_id == tid])
                results.update({pid: result_label(code) for pid, code in codes.items()})
            return team_statistics_display.metadata(decks, matches, results, phase, {tid: scope["tournaments"][tid] for tid in ids}, players)
    return cross_analytics.cached(db, ids, phase, "team-display-v3-semantic-stage", compute)


def _cross_aggregate(ids, db, phase, *, shared_scope=None):
    phase = arena_phases.canonical_analysis_stage(phase)
    if phase == "all":
        def compute_all():
            with arena_phases.analysis_scope(db, ids):
                sections = {stage: _cross_aggregate(ids, db, stage) for stage in ("legacy", *arena_phases.ANALYSIS_STAGES)}
            return {"registration_phase": "all", "by_phase": sections,
                "team_usage": [row for value in sections.values() for row in value.get("team_usage", [])]}
        return cross_analytics.cached(db, ids, phase, "aggregate-all-v1-semantic-stage", compute_all)

    if not ids:
        return {**empty_cross_tournament_stats(db), "registration_phase": phase}
    def compute():
        if shared_scope is not None and db.info.get("arena_analysis_scope") is None:
            shared_scope.enter_context(arena_phases.analysis_scope(db, ids))
        with arena_phases.analysis_scope(db, ids) as scope:
            applicable = [t.id for t in scope["tournaments"].values()
                if arena_phases.analysis_applicable(t, phase)]
            if not applicable:
                return {**empty_cross_tournament_stats(db), "registration_phase": phase}
            if phase == "legacy":
                value = _cross_snapshot_stats(CrossTournamentRequest(tournament_ids=applicable), db)
                team_statistics_display.annotate(value.get("team_usage", []),
                    _team_display_metadata(applicable, db, phase), phase)
                value["registration_phase"] = phase
                return value
            return _compute_cross_tournament_stats(applicable, db, phase)
    return cross_analytics.cached(db, ids, phase, "aggregate-v4-semantic-stage", compute)


def _cross_snapshot_stats(body: CrossTournamentRequest, db: Session):
    if body.tournament_ids:
        target_ids = body.tournament_ids
    else:
        target_ids = resolve_cross_tournament_ids(
            db,
            body.tournament_ids,
            body.play_server,
            body.championship_id
        )
    target_ids = filter_cross_tournament_ids(
        db, target_ids, body.registration_scope
    )

    print("[cross stats] body.tournament_ids:", body.tournament_ids)
    print("[cross stats] target_ids:", target_ids)

    if not target_ids:
        return empty_cross_tournament_stats(db)

    snaps = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id.in_(target_ids)
    ).all() if target_ids else []

    player_counts = dict(db.query(
        models.Player.tournament_id, func.count(models.Player.id)
    ).filter(
        models.Player.tournament_id.in_(target_ids)
    ).group_by(models.Player.tournament_id).all()) if target_ids else {}

    arena_ids = {t.id for t in db.query(models.Tournament).filter(models.Tournament.id.in_(target_ids), models.Tournament.deck_registration_phases.is_(True)).all()}
    usable_snaps = [
        snapshot for snapshot in snaps
        if snapshot.tournament_id not in arena_ids and cross_snapshot_has_distinct_counts(
            snapshot, db, player_counts.get(snapshot.tournament_id, 0)
        )
    ]
    snapshot_ids = {snapshot.tournament_id for snapshot in usable_snaps}
    raw_ids = [tournament_id for tournament_id in target_ids if tournament_id not in snapshot_ids]
    if usable_snaps:
        print(f"[cross stats] using snapshots: {len(usable_snaps)} / {len(target_ids)}")
        raw_stats = _compute_cross_tournament_stats(raw_ids, db) if raw_ids else None

        total_players = sum(s.total_players for s in usable_snaps if s.total_players)
        total_matches = sum(s.total_matches for s in usable_snaps if s.total_matches)
        if raw_stats:
            total_players += raw_stats.get("total_players", 0)
            total_matches += raw_stats.get("total_matches", 0)
        
        merged_chars = {}
        merged_teams = {}
        
        for snap in usable_snaps:
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
                        "player_count": 0,
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
                merged_chars[cid]["player_count"] += char_stat["player_count"]
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

        # Old/missing snapshots are replaced at the tournament boundary by one
        # raw aggregate.  Usable snapshot tournament IDs are excluded from this
        # query, preventing both source-level and field-level double counting.
        if raw_stats:
            for char_stat in raw_stats.get("character_stats", []):
                cid = char_stat.get("id")
                if not cid:
                    continue
                if cid not in merged_chars:
                    merged_chars[cid] = {
                        "id": cid, "name": char_stat.get("name"),
                        "rarity": char_stat.get("rarity"), "count": 0,
                        "player_count": 0, "win_count": 0, "total_matches": 0,
                        "best_result": char_stat.get("best_result", "不明"),
                        "position_stats": [], "team_position_stats": [],
                        "_pos_map": {p: {"count": 0, "wins": 0, "total": 0} for p in range(1, 6)},
                        "_team_pos_map": {p: {"count": 0, "wins": 0, "total": 0, "best_result": None} for p in range(1, 6)},
                    }
                merged_chars[cid]["count"] += char_stat.get("count", 0)
                merged_chars[cid]["player_count"] += char_stat.get("player_count", 0)
                merged_chars[cid]["win_count"] += char_stat.get("win_count", 0)
                merged_chars[cid]["total_matches"] += char_stat.get("total_matches", 0)
                current_score = RESULT_SCORES.get(merged_chars[cid]["best_result"], 999)
                new_score = RESULT_SCORES.get(char_stat.get("best_result", "不明"), 999)
                if new_score < current_score:
                    merged_chars[cid]["best_result"] = char_stat.get("best_result")
                _merge_char_position_stats(merged_chars, char_stat, cid)
            for team in raw_stats.get("team_usage", []):
                canonical_id = team.get("canonical_id")
                if canonical_id:
                    _merge_team_position_and_adopted(merged_teams, team, canonical_id)

        # Recalculate rates for chars
        char_list = []
        for char in merged_chars.values():
            t = char["total_matches"]
            w = char["win_count"]
            char["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            char["adoption_rate"] = round(char["player_count"] / total_players * 100, 1) if total_players else 0.0
            _finalize_char_position_stats(char)
            char_list.append(char)
        char_list.sort(key=lambda x: x["count"], reverse=True)

        # Recalculate rates for teams
        team_list = []
        for team in merged_teams.values():
            t = team["total_matches"]
            w = team["win_count"]
            team["win_rate"] = round(w / t * 100, 1) if t > 0 else 0.0
            team["adoption_rate"] = round(team.get("player_count", 0) / total_players * 100, 1) if total_players else 0.0
            _finalize_team_position_and_adopted(team)
            team_list.append(team)
        team_list.sort(key=lambda x: x["count"], reverse=True)

        stats = {
            "total_players": total_players,
            "total_matches": total_matches,
            "registration_phase": "initial",
            "character_usage": char_list,
            "character_stats": char_list,
            "character_usage_by_result": _compute_character_usage_by_result(target_ids, db),
            "team_usage": team_list,
            "matchups": [] # Usually cross matchups are fetched via their own endpoint
        }
        stats["registration_breakdown"] = cross_registration_breakdown(target_ids, db)
        return stats
    else:
        print("[cross stats] fallback raw compute")
        stats = _compute_cross_tournament_stats(target_ids, db)
        return stats


def _compute_cross_tournament_stats(tournament_ids_input: List[int], db: Session, registration_phase="initial"):
    """複数大会を横断したキャラ採用率・編成使用率・勝率を集計する"""
    display_phase = registration_phase
    if registration_phase == "legacy":
        registration_phase = "initial"
    tournament_ids = get_published_tournament_ids(tournament_ids_input, db)
    if not tournament_ids:
        return {**empty_cross_tournament_stats(db), "registration_phase": display_phase}

    scope = db.info.get("arena_analysis_scope")
    tournaments_by_id = ({tid: scope["tournaments"][tid] for tid in tournament_ids} if scope is not None else {
        t.id: t for t in db.query(models.Tournament).filter(models.Tournament.id.in_(tournament_ids)).all()})
    scope_players = ([p for p in scope["players"] if p.tournament_id in tournament_ids] if scope is not None else
        db.query(models.Player).filter(models.Player.tournament_id.in_(tournament_ids)).all())
    all_players = scope_players
    if registration_phase != "initial":
        qualified = set()
        for tournament in tournaments_by_id.values():
            qualified.update(arena_phases.analysis_qualified_ids(tournament, db, registration_phase,
                [p.id for p in scope_players if p.tournament_id == tournament.id]))
        all_players = [p for p in scope_players if p.id in qualified]
    player_ids = [p.id for p in all_players]
    deck_sets = arena_phases.phase_deck_sets(db, player_ids, registration_phase)
    deck_set_ids = [ds.id for ds in deck_sets]
    ds_to_player = {ds.id: ds.player_id for ds in deck_sets}

    deck_teams = [team for deck in deck_sets for team in deck.teams]
    deck_sets_by_player = {deck_set.player_id: deck_set for deck_set in deck_sets}
    teams_by_deck_set = {}
    for team in deck_teams:
        teams_by_deck_set.setdefault(team.deck_set_id, []).append(team)

    char_usage = {}
    char_position = {}
    char_team_position = {}
    team_usage = {}
    team_players = {}

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
            player_id = ds_to_player.get(team.deck_set_id)
            if player_id:
                team_players.setdefault(sorted_chars, set()).add(player_id)
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
    all_matches = arena_phases.effective_matches(db, tournament_ids)
    match_ids = [match.id for match in all_matches]
    round_results = [r for match in all_matches for r in match.round_results]
    rounds_by_match = {}
    for round_result in round_results:
        rounds_by_match.setdefault(round_result.match_id, []).append(round_result)

    char_match_stats = {}
    team_match_stats = {}
    char_position_match_stats = {}

    for match in all_matches:
        if not arena_phases.matches_analysis_phase(db, match, registration_phase):
            continue
        attacker_ds = match.arena_decks.get(match.attacker_id) if hasattr(match, "arena_decks") else deck_sets_by_player.get(match.attacker_id)
        defender_ds = match.arena_decks.get(match.defender_id) if hasattr(match, "arena_decks") else deck_sets_by_player.get(match.defender_id)

        if not attacker_ds or not defender_ds:
            continue

        a_teams = {t.team_number: t for t in attacker_ds.teams}
        d_teams = {t.team_number: t for t in defender_ds.teams}

        for rr in rounds_by_match.get(match.id, []):
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

    per_tournament_results = {}
    for tournament_id in tournament_ids:
        codes = calculate_player_results(
            tournaments_by_id[tournament_id],
            [player for player in scope_players if player.tournament_id == tournament_id],
            [match for match in all_matches if match.tournament_id == tournament_id],
        )
        per_tournament_results[tournament_id] = {
            player_id: result_label(code) for player_id, code in codes.items()
        }

    # キャラ→使用プレイヤーのマッピング
    char_to_players = {}
    for team in deck_teams:
        player_id = ds_to_player.get(team.deck_set_id)
        for c_id in [team.char1_id, team.char2_id, team.char3_id, team.char4_id, team.char5_id]:
            if player_id and c_id is not None and c_id != EMPTY_SLOT_CHARACTER_ID:
                char_to_players.setdefault(c_id, set()).add(player_id)

    commander_result_by_player = {pid: result for results in per_tournament_results.values() for pid, result in results.items()}
    character_ids = set(char_usage)
    characters_by_id = {
        character.id: character
        for character in db.query(models.Character).filter(
            models.Character.id.in_(character_ids)
        ).all()
    } if character_ids else {}

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
        char = characters_by_id.get(c_id)
        if char:
            m_stats = char_match_stats.get(c_id, {"wins": 0, "total": 0})
            win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else (0 if registration_phase == "initial" else None)
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
                    "best_result": best_res_p,
                    "commander_results": team_statistics_display.finish_counts(p_ms["players"], commander_result_by_player)
                })

            user_ids = char_to_players.get(c_id, set())
            best_result = get_best_result_cross(user_ids) if user_ids else None

            char_list.append({
                "id": char.id,
                "name": char.name,
                "rarity": char.rarity,
                "count": count,
                "player_count": len(user_ids),
                "adoption_rate": round(len(user_ids) / len(player_ids) * 100, 1) if player_ids else 0.0,
                "win_count": m_stats["wins"],
                "total_matches": m_stats["total"],
                "win_rate": round(win_rate, 1) if win_rate is not None else None,
                "best_result": best_result,
                "commander_results": team_statistics_display.finish_counts(user_ids, commander_result_by_player),
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
            char = characters_by_id.get(c_id)
            if char:
                team_chars.append({"id": char.id, "name": char.name, "rarity": char.rarity})

        canon_id = ",".join(map(str, sorted_chars))
        m_stats = team_match_stats.get(canon_id, {"wins": 0, "total": 0})
        win_rate = (m_stats["wins"] / m_stats["total"] * 100) if m_stats["total"] > 0 else (0 if registration_phase == "initial" else None)

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

        team_player_ids = team_players.get(sorted_chars, set())

        best_team_result = get_best_result_cross(team_player_ids) if team_player_ids else None

        # この編成を採用したプレイヤー情報を収集
        adopted_players = []
        for pid in team_player_ids:
            player = player_by_id.get(pid)
            if player:
                t = tournaments_by_id.get(player.tournament_id)
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
            "player_count": len(team_player_ids),
            "adoption_rate": round(len(team_player_ids) / len(player_ids) * 100, 1) if player_ids else 0.0,
            "win_count": m_stats["wins"],
            "total_matches": m_stats["total"],
            "win_rate": round(win_rate, 1) if win_rate is not None else None,
            "best_result": best_team_result,
            "adopted_players": adopted_players,
            "position_stats": pos_stats_out
        })
    team_statistics_display.annotate(team_list, team_statistics_display.metadata(
        deck_sets, all_matches, {pid: result for results in per_tournament_results.values() for pid, result in results.items()}, display_phase, tournaments_by_id, scope_players), display_phase)
    team_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "registration_phase": display_phase,
        "character_usage": char_list,
        "character_stats": char_list,
        "character_usage_by_result": _compute_character_usage_by_result(tournament_ids, db, registration_phase,
            prepared_scope={"players": scope_players, "matches": all_matches, "decks": deck_sets,
                "tournaments": tournaments_by_id, "characters": characters_by_id, "eligible_player_ids": qualified if registration_phase != "initial" else set(player_ids)}),
        "team_usage": team_list,
        "total_players": len(player_ids),
        "total_matches": sum(arena_phases.matches_analysis_phase(db, m, registration_phase) for m in all_matches),
        "registration_breakdown": cross_registration_breakdown(tournament_ids, db, registration_phase),
    }


@app.post("/api/dashboard/cross-tournament/matchups")
def get_cross_tournament_matchups(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    ids = _cross_target_ids(body, db)
    if body.registration_phase == "all":
        return {"registration_phase": "all", "by_phase": {phase: get_cross_tournament_matchups(
            body.model_copy(update={"registration_phase": phase}), db) for phase in ("legacy", *arena_phases.ANALYSIS_STAGES)}}
    def compute():
        with arena_phases.analysis_scope(db, ids):
            return _cross_matchups(CrossTournamentRequest(tournament_ids=ids,
                registration_phase=body.registration_phase), db)
    return cross_analytics.cached(db, ids, body.registration_phase, "matchups-v1", compute)


def _cross_matchups(body: CrossTournamentRequest, db: Session):
    """複数大会を横断した対戦データを集計する"""
    tournament_ids = filter_cross_tournament_ids(
        db, body.tournament_ids, body.registration_scope
    )
    if not tournament_ids:
        return {"matchups": []}
    if not tournament_ids:
        raise HTTPException(status_code=400, detail="tournament_ids が必要です")

    matches = arena_phases.effective_matches(db, tournament_ids)

    matchup_results = []
    for match in matches:
        if not arena_phases.matches_analysis_phase(db, match, body.registration_phase):
            continue
        attacker_ds = arena_phases.deck_for_match(match, match.attacker_id, db)
        defender_ds = arena_phases.deck_for_match(match, match.defender_id, db)

        if not attacker_ds or not defender_ds:
            continue

        attacker_teams = {t.team_number: t for t in attacker_ds.teams}
        defender_teams = {t.team_number: t for t in defender_ds.teams}

        for round_res in match.round_results:
            rn = round_res.round_number
            a_team = attacker_teams.get(rn)
            d_team = defender_teams.get(rn)

            if a_team and d_team:
                a_slots = [
                    (character_id, collection_level)
                    for character_id, collection_level in zip(
                        [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id],
                        get_team_collection_levels(a_team),
                    )
                    if character_id is not None
                ]
                d_slots = [
                    (character_id, collection_level)
                    for character_id, collection_level in zip(
                        [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id],
                        get_team_collection_levels(d_team),
                    )
                    if character_id is not None
                ]
                a_chars = [character_id for character_id, _ in a_slots]
                d_chars = [character_id for character_id, _ in d_slots]
                a_collections = [collection_level for _, collection_level in a_slots]
                d_collections = [collection_level for _, collection_level in d_slots]

                a_sorted = tuple(sorted(a_chars))
                d_sorted = tuple(sorted(d_chars))

                if len(a_chars) == 5 and len(d_chars) == 5:
                    winner_is_attacker = round_res.winner_id == match.attacker_id
                    matchup_results.append({
                        "match_id": match.id,
                        "round_number": rn,
                        "attacker_player_id": match.attacker_id,
                        "defender_player_id": match.defender_id,
                        "winner_player_id": round_res.winner_id,
                        "attacker_team_id": attacker_teams[rn].id,
                        "defender_team_id": defender_teams[rn].id,
                        "attacker_team_number": rn,
                        "defender_team_number": rn,
                        "stage": match.stage,
                        "attacker_team": list(a_chars),
                        "defender_team": list(d_chars),
                        "attacker_collections": a_collections,
                        "defender_collections": d_collections,
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



class CrossTournamentTeamsRequest(CrossAnalysisPhaseRequest):
    tournament_ids: List[int] = []
    play_server: Optional[str] = None
    championship_id: Optional[int] = None
    registration_scope: Literal["all", "full_64", "champion_8"] = "all"
    seed: Optional[int] = None
    character_ids: Optional[List[int]] = None
    excluded_character_ids: Optional[List[int]] = None
    limit: Optional[int] = 10
    offset: Optional[int] = 0
    sort_by: Optional[str] = None
    sort_order: Literal["asc", "desc"] = "desc"
    provider_game_start_date: Optional[date_type] = None
    detail_team: Optional[str] = None
    character_usage: bool = False
    min_matches: Optional[int] = None
    min_usage: Optional[int] = None
    min_win_rate: Optional[float] = None
    best_result: Optional[str] = None
    composition_best_result: Optional[str] = None
    commander_best_result: Optional[str] = None
    registration_phase: Literal["legacy", "initial", "best8", "league", "championship", "final", "all"] = "championship"


def _filter_teams_by_character_conditions(
    teams: List[dict],
    included_character_ids: Optional[List[int]] = None,
    excluded_character_ids: Optional[List[int]] = None,
) -> List[dict]:
    included = {int(character_id) for character_id in (included_character_ids or []) if int(character_id) != EMPTY_SLOT_CHARACTER_ID}
    excluded = {int(character_id) for character_id in (excluded_character_ids or []) if int(character_id) != EMPTY_SLOT_CHARACTER_ID}
    if not included and not excluded:
        return teams

    filtered = []
    for team in teams:
        raw_character_ids = team.get("character_ids") or [
            character["id"]
            for character in team.get("characters", [])
            if isinstance(character, dict) and "id" in character
        ]
        team_character_ids = {int(character_id) for character_id in raw_character_ids}
        if included.issubset(team_character_ids) and team_character_ids.isdisjoint(excluded):
            filtered.append(team)
    return filtered


def _composition_stage_stats(tournament_id, db, current_user, seed, stage):
    def compute():
        with arena_phases.analysis_scope(db, [tournament_id]):
            return _compute_dashboard_stats(tournament_id, db, current_user, seed, stage)
    return cross_analytics.cached(db, [tournament_id], stage,
        f"private-composition-stage-v1:{seed}", compute)


def _composition_tournament_ids(db, request):
    query = db.query(models.Tournament.id).filter(
        models.Tournament.publication_status == "published", models.Tournament.has_match_data.is_(True))
    if request.tournament_ids:
        query = query.filter(models.Tournament.id.in_(request.tournament_ids))
    elif not (request.play_server and request.championship_id):
        return []
    if request.play_server:
        query = query.filter(models.Tournament.creator.has(models.AppUser.play_server == request.play_server))
    if request.championship_id:
        query = query.filter(models.Tournament.championship_id == request.championship_id)
    if request.provider_game_start_date:
        query = query.filter(models.Tournament.provider_game_start_date == request.provider_game_start_date)
    if request.registration_scope != "all":
        query = query.filter(models.Tournament.registration_scope == request.registration_scope)
    return [tid for (tid,) in query.order_by(models.Tournament.id)]


def _select_composition_cards(teams, included, excluded, min_matches, min_usage, min_win_rate,
                              best_result, commander_result, sort_by, sort_order, offset, limit):
    matches = _filter_teams_by_character_conditions(teams, included, excluded)
    matches = [team for team in matches if team["total_matches"] >= (min_matches or 0)
               and team["count"] >= (min_usage or 0)
               and (team["win_rate"] or 0) >= (min_win_rate or 0)]
    matches = team_statistics_display.filter_highest(matches, best_result, commander_result)
    matches.sort(key=lambda team: (-team["count"], team["canonical_id"]))
    reverse = sort_order == "desc"
    if sort_by == "win_rate":
        matches.sort(key=lambda team: team["win_rate"] if team["win_rate"] is not None else -1, reverse=reverse)
    elif sort_by == "composition_best_result":
        matches.sort(key=lambda team: team_statistics_display.RESULT_ORDER.get(team["composition_best_result"], 999),
                     reverse=not reverse)
    elif sort_by in ("usage", "count") and not reverse:
        matches.sort(key=lambda team: team["count"])
    return {"teams": matches[offset:offset + limit], "total": len(matches)}


@app.get("/api/tournaments/{tournament_id}/dashboard/teams")
def get_dashboard_teams(
    tournament_id: int,
    seed: Optional[int] = None,
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    character_ids: Optional[str] = None,
    excluded_character_ids: Optional[str] = None,
    sort_by: Optional[str] = None,
    min_matches: int = 0,
    min_usage: int = 0,
    min_win_rate: float = 0,
    best_result: Optional[str] = None,
    composition_best_result: Optional[str] = None,
    commander_best_result: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
    registration_phase: str = "initial",
    sort_order: Literal["asc", "desc"] = "desc",
    detail_team: Optional[str] = None,
    character_usage: bool = False,
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    phase = (arena_phases.normalized_stage(tournament, "initial") if registration_phase == "initial"
             else arena_phases.canonical_analysis_stage(registration_phase))
    if phase not in ("all", *composition_analytics.STAGES):
        arena_phases.validate_analysis_phase(tournament, phase)
    data = composition_analytics.load(db, [tournament_id], seed)
    if character_usage:
        return {"character_usage": data["character_usage"]}
    teams = data["teams"].get(phase, [])
    if detail_team is not None:
        return composition_analytics.details(data, teams, phase, detail_team)
    included_ids = [int(value) for value in character_ids.split(",") if value.isdigit()] if character_ids else []
    excluded_ids = [int(value) for value in excluded_character_ids.split(",") if value.isdigit()] if excluded_character_ids else []
    return _select_composition_cards(teams, included_ids, excluded_ids, min_matches, min_usage,
        min_win_rate, composition_best_result, commander_best_result or best_result,
        sort_by, sort_order, offset, limit)


@app.post("/api/dashboard/cross-tournament/teams")
def get_cross_dashboard_teams(
    req: CrossTournamentTeamsRequest,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
):
    ids = _composition_tournament_ids(db, req)
    data = composition_analytics.load(db, ids, req.seed)
    if req.character_usage:
        return {"character_usage": data["character_usage"]}
    phase = req.registration_phase
    teams = data["teams"].get(phase, [])
    if req.detail_team is not None:
        return composition_analytics.details(data, teams, phase, req.detail_team)
    return _select_composition_cards(teams, req.character_ids, req.excluded_character_ids,
        req.min_matches, req.min_usage, req.min_win_rate, req.composition_best_result,
        req.commander_best_result or req.best_result, req.sort_by, req.sort_order,
        req.offset or 0, req.limit or 10)


@app.post("/api/dashboard/cross-tournament/character-detail")
def get_cross_tournament_character_detail(req: CrossTournamentCharacterDetailRequest, db: Session = Depends(get_db)):
    target_ids = _cross_target_ids(req, db)
    if not target_ids:
        return {"character_usage": [], "team_usage": []}
    stats = _cross_aggregate(target_ids, db, req.registration_phase)
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
    registration_phase: str = "initial",
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    params = {"seed": seed, "registration_phase": registration_phase}
    cached = get_private_dashboard_cache(tournament, "character-winrates", params)
    if cached is not None:
        return cached
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if db.query(models.Tournament).filter_by(id=tournament_id).one().deck_registration_phases:
        snap = None
    if snap is not None and snap.char_stats:
        char_stats = snap.char_stats
    else:
        stats = _compute_dashboard_stats(tournament_id, db, current_user, seed, registration_phase)
        char_stats = stats.get("character_stats", [])
    return set_private_dashboard_cache(
        tournament,
        "character-winrates",
        {"character_winrates": char_stats, "character_stats": char_stats},
        params,
    )


@app.get("/api/tournaments/{tournament_id}/dashboard/character/{character_id}")
def get_dashboard_character_detail(
    tournament_id: int,
    character_id: int,
    seed: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.AppUser] = Depends(auth_module.get_current_user_optional),
    registration_phase: str = "initial",
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    snap = db.query(models.TournamentSnapshot).filter(
        models.TournamentSnapshot.tournament_id == tournament_id
    ).first()
    if db.query(models.Tournament).filter_by(id=tournament_id).one().deck_registration_phases:
        snap = None
    if snap is not None and snap.char_stats is not None and snap.team_usage is not None:
        char_stats = snap.char_stats
        team_usage = team_statistics_display.annotate(deepcopy(snap.team_usage or []),
            _team_display_metadata([tournament_id], db, registration_phase), registration_phase)
    else:
        stats = _compute_dashboard_stats(tournament_id, db, current_user, seed, registration_phase)
        char_stats = stats.get("character_usage", stats.get("character_stats", []))
        team_usage = stats.get("team_usage", [])

    char_item = next((x for x in char_stats if (int(x.get("id") or 0) == int(character_id) or int(x.get("character_id") or 0) == int(character_id))), None)
    if char_item:
        char_item["id"] = int(char_item.get("id") or char_item.get("character_id") or character_id)
        char_item["character_id"] = char_item["id"]
        if char_item.get("count", 0) > 0 and (not char_item.get("position_stats") or not char_item.get("team_position_stats")):
            comp_stats = _compute_dashboard_stats(tournament_id, db, current_user, seed, registration_phase)
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
            "win_rate": None,
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
    registration_phase: str = "initial",
):
    tournament = require_tournament_dashboard_viewer(tournament_id, db, current_user)
    if registration_phase == "all" and seed is not None:
        params = {"seed": seed, "registration_phase": "all"}
        cached = get_private_dashboard_cache(tournament, "player-stats", params)
        if cached is not None:
            return cached
        stages = [phase for phase in arena_phases.ANALYSIS_STAGES if arena_phases.analysis_applicable(tournament, phase)] if tournament.deck_registration_phases else ["legacy"]
        with arena_phases.analysis_scope(db, [tournament_id]) as scope:
            players = [player for player in scope["players"] if player.tournament_id == tournament_id]
            player = next((player for player in players if player.seed_number == seed), None)
            matches = arena_phases.effective_matches(db, [tournament_id])
            result_code = calculate_player_results(tournament, players, matches).get(player.id) if player else None
            sets = []
            details = {"player": None, "decks": []}
            for phase in stages:
                details = _get_player_details_by_player(tournament_id, player, db, phase, resolved_matches=matches)
                if details["decks"]:
                    sets.append({"registration_phase": phase, "decks": details["decks"]})
        value = {"player": details["player"], "result_code": result_code,
                 "result": result_label(result_code), "registration_sets": sets,
                 "decks": [deck for item in sets for deck in item["decks"]]}
        return set_private_dashboard_cache(tournament, "player-stats", value, params)
    registration_phase = (arena_phases.canonical_analysis_stage(registration_phase)
        if tournament.deck_registration_phases else "legacy" if registration_phase in ("initial", "all") else registration_phase)
    arena_phases.validate_analysis_phase(tournament, registration_phase)
    params = {"seed": seed, "registration_phase": registration_phase}
    cached = get_private_dashboard_cache(tournament, "player-stats", params)
    if cached is not None:
        return cached
    if seed is not None:
        value = _get_player_details_data(tournament_id, seed, db, registration_phase)
        return set_private_dashboard_cache(tournament, "player-stats", value, params)
    players = db.query(models.Player).filter(models.Player.tournament_id == tournament_id).order_by(models.Player.seed_number).all()
    result_codes = calculate_player_results(
        tournament,
        players,
        arena_phases.effective_matches(db, [tournament_id]),
    )
    for player in players:
        player.result_code = result_codes[player.id]
        player.result = result_label(result_codes[player.id])
    value = {"players": [{"id": p.id, "tournament_id": p.tournament_id, "seed_number": p.seed_number, "champion_slot": p.champion_slot, "name": p.name, "icon_url": p.icon_url, "created_at": p.created_at, "result_code": p.result_code, "result": p.result} for p in players]}
    return set_private_dashboard_cache(tournament, "player-stats", value, params)


# Official-arena phase APIs deliberately leave legacy result/deck rows untouched.


def arena_access(tournament_id, db, current_user, write=False):
    tournament = (require_tournament_manager if write else require_tournament_viewer)(tournament_id, db, current_user)
    if not arena_phases.supported(tournament):
        raise HTTPException(409, "Phase registrations require an official champion arena")
    if write:
        tournament = db.query(models.Tournament).filter_by(id=tournament_id).populate_existing().with_for_update(of=models.Tournament).one()
        # Recheck after acquiring the common tournament lock.
        if current_user.role != "admin" and tournament.created_by != current_user.id:
            raise HTTPException(403, "Tournament manager required")
        if not arena_phases.supported(tournament):
            raise HTTPException(409, "Tournament format changed")
        require_unpublished_champion_edit(tournament)
    return tournament


@app.get("/api/tournaments/{tournament_id}/arena-phases")
def get_arena_phases(tournament_id: int, db: Session = Depends(get_db), current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional)):
    return arena_phases.state(arena_access(tournament_id, db, current_user), db)


@app.put("/api/tournaments/{tournament_id}/arena-phases/players/{player_id}/{phase}")
async def put_arena_registration(tournament_id: int, player_id: int, phase: str, request: Request, db: Session = Depends(get_db), current_user: models.AppUser = Depends(auth_module.get_current_user)):
    tournament = arena_access(tournament_id, db, current_user, True)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(422, "JSON object required")
    player = db.query(models.Player).filter_by(id=player_id, tournament_id=tournament.id).first()
    if player is None:
        raise HTTPException(404, "Player not found")
    response = save_phase_registration_with_assets(tournament, player, phase, payload, db, current_user)
    invalidate_dashboard_cache_safely(tournament_id)
    return response


@app.put("/api/tournaments/{tournament_id}/arena-phases/matches/{match_key}")
async def put_arena_result(tournament_id: int, match_key: str, request: Request, db: Session = Depends(get_db), current_user: models.AppUser = Depends(auth_module.get_current_user)):
    tournament = arena_access(tournament_id, db, current_user, True)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(422, "JSON object required")
    response = arena_phases.save_result(tournament, match_key, payload, db)
    invalidate_dashboard_cache_safely(tournament_id)
    return response


@app.post("/api/tournaments/{tournament_id}/arena-phases/players")
async def create_arena_player(tournament_id: int, request: Request, db: Session = Depends(get_db), current_user: models.AppUser = Depends(auth_module.get_current_user)):
    tournament = arena_access(tournament_id, db, current_user, True)
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(422, "JSON object required")
    position = data.get("position")
    maximum = 8 if tournament.registration_scope == "champion_8" else 64
    if type(position) is not int or position not in range(1, maximum + 1):
        raise HTTPException(422, "Invalid position")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise HTTPException(422, "A player name of 1 to 100 characters is required")
    column = models.Player.champion_slot if maximum == 8 else models.Player.seed_number
    if db.query(models.Player).filter(models.Player.tournament_id == tournament_id, column == position).first():
        raise HTTPException(409, "Position is already registered; existing player identities cannot be replaced")
    db.add(models.Player(tournament_id=tournament_id, name=name.strip(), champion_slot=position if maximum == 8 else None, seed_number=position if maximum == 64 else None))
    db.commit()
    invalidate_dashboard_cache_safely(tournament_id)
    return arena_phases.state(tournament, db)


@app.get("/api/tournaments/{tournament_id}/arena-phases/history")
def get_arena_history(tournament_id: int, db: Session = Depends(get_db), current_user: models.AppUser | None = Depends(auth_module.get_current_user_optional)):
    return arena_phases.history(arena_access(tournament_id, db, current_user), db)


def require_legacy_registration_path(tournament_id, db, current_user):
    require_tournament_manager(tournament_id, db, current_user)
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).populate_existing().with_for_update(of=models.Tournament).one()
    return tournament



def save_initial_arena_registration(tournament, player, teams, db, actor):
    _, _, _, registration = arena_phases.context(tournament, db)
    _, revision_id = registration(player.id, "initial")
    return save_phase_registration_with_assets(tournament, player, "initial", {"qualification": "initial", "revision_id": revision_id, "teams": teams}, db, actor)


def result_revision_payload(node, rounds, expected):
    if not isinstance(expected, dict):
        raise HTTPException(409, "Reload the bracket before saving a phase-aware match")
    return {"rounds": rounds, "upstream": expected.get("upstream"), "registration_ids": expected.get("registration_ids"), "revision_id": expected.get("revision_id")}


@app.get("/api/tournaments/{tournament_id}/private-player-names")
def get_private_player_names(tournament_id: int, response: Response, db: Session = Depends(get_db), current_user: models.AppUser = Depends(auth_module.get_current_user)):
    require_tournament_manager(tournament_id, db, current_user)
    response.headers["Cache-Control"] = "private, no-store"
    players = db.query(models.Player).filter_by(tournament_id=tournament_id).all()
    return {"players": [{"id": p.id, "seed_number": p.seed_number, "champion_slot": p.champion_slot, "private_name": p.private_name} for p in players]}


@app.put("/api/tournaments/{tournament_id}/private-player-names")
async def update_private_player_name(tournament_id: int, request: Request, response: Response, db: Session = Depends(get_db), current_user: models.AppUser = Depends(auth_module.get_current_user)):
    tournament = require_legacy_registration_path(tournament_id, db, current_user)
    data = await request.json()
    if not isinstance(data, dict) or set(data) - {"player_id", "seed_number", "private_name"}:
        raise HTTPException(422, "Invalid private name request")
    name = data.get("private_name")
    if name is not None and not isinstance(name, str):
        raise HTTPException(422, "Private name must be text or null")
    name = name.strip() or None if isinstance(name, str) else None
    if name and (len(name) > 50 or any(ord(ch) < 32 for ch in name)):
        raise HTTPException(422, "Private name must be at most 50 characters without control characters")
    query = db.query(models.Player).filter_by(tournament_id=tournament_id)
    if "player_id" in data:
        if type(data["player_id"]) is not int:
            raise HTTPException(422, "Invalid Player")
        player = query.filter_by(id=data["player_id"]).first()
        if player is None:
            raise HTTPException(404, "Player not found")
    else:
        seed = data.get("seed_number")
        if tournament.registration_scope != "full_64" or type(seed) is not int or not 1 <= seed <= 64:
            raise HTTPException(422, "Invalid seed")
        player = query.filter_by(seed_number=seed).first()
        if player is None:
            raise HTTPException(404, "Player not found")
    player.private_name = name
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"id": player.id, "seed_number": player.seed_number, "champion_slot": player.champion_slot, "private_name": player.private_name}
