from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Request, Response
import auth as auth_module
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models, schemas
from typing import List
import shutil
import os

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
os.makedirs(UPLOAD_DIR, exist_ok=True)

from fastapi.staticfiles import StaticFiles
from services.image_processor import process_images
from fastapi.responses import FileResponse

app.mount("/api/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/api/char-icon/{char_id}.png")
def get_char_icon(char_id: int):
    """キャラクターの代表テンプレート画像を返す（旧形式・新形式両対応）"""
    template_dir = "uploads/templates"
    # 旧形式を優先
    old_path = os.path.join(template_dir, f"char_{char_id}.png")
    if os.path.exists(old_path):
        return FileResponse(old_path, media_type="image/png")
    # 新形式: 連番の最初のファイルを探す
    if os.path.exists(template_dir):
        candidates = sorted([
            f for f in os.listdir(template_dir)
            if f.startswith(f"char_{char_id}_") and f.endswith(".png")
        ])
        if candidates:
            return FileResponse(os.path.join(template_dir, candidates[0]), media_type="image/png")
    raise HTTPException(status_code=404, detail="Template not found")

@app.get("/")
def read_root():
    return {"message": "Welcome to NIKKE Arena Analysis API!"}


# ===== 初回起動時: 管理者アカウント自動作成 =====
from database import SessionLocal, Base
from scripts.init_db import init_db
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
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
            admin = models.AppUser(
                email=first_email,
                hashed_password=auth_module.hash_password(first_password),
                role="admin",
                provider_name="管理者",
                game_start_date=default_start_date
            )
            db.add(admin)
            db.commit()
            print(f"[Startup] 管理者アカウント作成: {first_email}")
        else:
            existing.hashed_password = auth_module.hash_password(first_password)
            existing.role = "admin"
            if not existing.provider_name:
                existing.provider_name = "管理者"
            if not existing.game_start_date:
                existing.game_start_date = default_start_date
            db.commit()
            print(f"[Startup] 管理者アカウントのパスワードおよびプロフィールを同期しました: {first_email}")
    finally:
        db.close()


# ===== 認証エンドポイント =====

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
    token = auth_module.create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie("auth_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"ok": True, "token": token, "user": {"id": user.id, "email": user.email, "role": user.role}}


@app.post("/api/auth/logout")
def user_logout(response: Response):
    """Cookie 削除"""
    response.delete_cookie("auth_token")
    response.delete_cookie("site_session")
    return {"ok": True}


@app.post("/api/auth/register")
def user_register(body: dict, db: Session = Depends(get_db)):
    """招待コード付きユーザー登録"""
    email       = body.get("email", "").strip().lower()
    password    = body.get("password", "")
    invite_code = body.get("inviteCode", "").strip() # 余分なスペースをトリミング
    provider_name = body.get("providerName", "").strip() or None
    game_start_date = body.get("gameStartDate", "") or None
    
    expected_code = auth_module.INVITE_CODE.strip() if auth_module.INVITE_CODE else ""
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="メールとパスワードは必須です")
    if expected_code and invite_code != expected_code:
        raise HTTPException(status_code=400, detail="招待コードが正しくありません")
    existing = db.query(models.AppUser).filter(models.AppUser.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="そのメールアドレスは既に登録されています")
    
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
    )
    db.add(user)
    db.commit()
    return {"ok": True, "message": "登録が完了しました"}


@app.get("/api/auth/me")
def get_me(current_user: models.AppUser = Depends(auth_module.get_current_user)):
    """現在ログイン中のユーザー情報"""
    return {
        "id": current_user.id, 
        "email": current_user.email, 
        "role": current_user.role,
        "provider_name": current_user.provider_name,
        "game_start_date": str(current_user.game_start_date) if current_user.game_start_date else None
    }


@app.get("/api/auth/users")
def list_users(
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db),
):
    """ユーザー一覧（管理者のみ）"""
    users = db.query(models.AppUser).order_by(models.AppUser.created_at).all()
    return [
        {"id": u.id, "email": u.email, "role": u.role, "is_banned": u.is_banned, "created_at": str(u.created_at)}
        for u in users
    ]


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

from sqlalchemy import case

@app.get("/api/characters", response_model=List[schemas.Character])
def get_characters(db: Session = Depends(get_db)):
    # SSR > SR > R 順、五十音順（名前順）
    rarity_order = case(
        (models.Character.rarity == 'SSR', 1),
        (models.Character.rarity == 'SR', 2),
        (models.Character.rarity == 'R', 3),
        else_=4
    )
    return db.query(models.Character).order_by(rarity_order, models.Character.name).all()

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

    chars = db.query(models.Character).order_by(models.Character.name).all()
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
            "image_url": f"/api/char-icon/{c.id}.png" if has_tpl else None,
        })
    return result

@app.delete("/api/characters/{char_id}")
def delete_character(
    char_id: int,
    _: models.AppUser = Depends(auth_module.require_admin),
    db: Session = Depends(get_db)
):
    """キャラクターをDBから完全削除（テンプレートも削除、管理者のみ）"""
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
    
    # championship_id から名前などの情報を引き継ぐ
    if tournament.championship_id:
        championship = db.query(models.Championship).filter(models.Championship.id == tournament.championship_id).first()
        if championship:
            data["name"] = championship.name
            # dateはChampionshipの作成日またはシステム日付にする
            data["date"] = championship.created_at.date() if championship.created_at else tournament.date

    db_tournament = models.Tournament(**data)
    db.add(db_tournament)
    db.commit()
    db.refresh(db_tournament)
    return db_tournament

@app.get("/api/tournaments", response_model=List[schemas.Tournament])
def get_tournaments(db: Session = Depends(get_db)):
    return db.query(models.Tournament).all()

@app.get("/api/tournaments/{tournament_id}", response_model=schemas.Tournament)
def get_tournament(tournament_id: int, db: Session = Depends(get_db)):
    db_tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not db_tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return db_tournament

@app.put("/api/tournaments/{tournament_id}", response_model=schemas.Tournament)
def update_tournament(
    tournament_id: int, 
    tournament: schemas.TournamentBase, 
    db: Session = Depends(get_db),
    current_user: models.AppUser = Depends(auth_module.get_current_user)
):
    db_tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not db_tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # championship_id が更新されたら名前などを再同期
    if tournament.championship_id:
        championship = db.query(models.Championship).filter(models.Championship.id == tournament.championship_id).first()
        if championship:
            db_tournament.name = championship.name
            db_tournament.championship_id = tournament.championship_id
            
    db_tournament.season = tournament.season
    # 提供者情報が紐付け変更されることは原則ないが、ログイン中ユーザー情報で常に上書き保護
    db_tournament.owner_name = current_user.provider_name or db_tournament.owner_name
    db.commit()
    db.refresh(db_tournament)
    return db_tournament

@app.delete("/api/tournaments/{tournament_id}")
def delete_tournament(tournament_id: int, db: Session = Depends(get_db)):
    db_tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not db_tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    db.delete(db_tournament)
    db.commit()
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
def create_championship(championship: schemas.ChampionshipCreate, db: Session = Depends(get_db)):
    db_championship = models.Championship(**championship.model_dump())
    db.add(db_championship)
    db.commit()
    db.refresh(db_championship)
    return db_championship

@app.put("/api/championships/{id}", response_model=schemas.ChampionshipResponse)
def update_championship(id: int, championship: schemas.ChampionshipCreate, db: Session = Depends(get_db)):
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    db_championship.name = championship.name
    db_championship.date = championship.date
    db_championship.start_date = championship.start_date
    db_championship.owner_name = championship.owner_name
    db.commit()
    db.refresh(db_championship)
    return db_championship

@app.delete("/api/championships/{id}")
def delete_championship(id: int, db: Session = Depends(get_db)):
    db_championship = db.query(models.Championship).filter(models.Championship.id == id).first()
    if not db_championship:
        raise HTTPException(status_code=404, detail="Championship not found")
    db.delete(db_championship)
    db.commit()
    return {"ok": True}

@app.get("/api/championships/{id}/matches", response_model=List[schemas.Tournament])
def get_championship_matches(id: int, db: Session = Depends(get_db)):
    return db.query(models.Tournament).filter(models.Tournament.championship_id == id).order_by(models.Tournament.created_at.desc()).all()

@app.get("/api/tournaments/{tournament_id}/players", response_model=List[schemas.Player])
def get_players(tournament_id: int, db: Session = Depends(get_db)):
    return db.query(models.Player).filter(models.Player.tournament_id == tournament_id).all()

@app.get("/api/tournaments/{tournament_id}/players/{seed_number}/details")
def get_player_details(tournament_id: int, seed_number: int, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number
    ).first()
    
    if not player:
        return {"player": None, "decks": []}
        
    deck_set = db.query(models.DeckSet).filter(models.DeckSet.player_id == player.id).first()
    if not deck_set:
        return {"player": {"id": player.id, "name": player.name, "seed_number": player.seed_number}, "decks": []}
        
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



@app.post("/api/tournaments/{tournament_id}/players/{seed_number}")
async def update_player_info(
    tournament_id: int,
    seed_number: int,
    data: dict,
    db: Session = Depends(get_db)
):
    player = db.query(models.Player).filter(
        models.Player.tournament_id == tournament_id,
        models.Player.seed_number == seed_number
    ).first()
    
    name = data.get("name")
    icon_url = data.get("icon_url")
    
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
    return player

@app.post("/api/tournaments/{tournament_id}/teams")
async def save_teams(
    tournament_id: int,
    data: dict,
    db: Session = Depends(get_db)
):
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
        
        if not player:
            player = models.Player(
                tournament_id=tournament_id,
                seed_number=seed_number,
                name=player_name or f"Player {seed_number}",
                icon_url=player_icon_url
            )
            db.add(player)
            db.commit()
            db.refresh(player)
            print(f"[save_teams] 新規プレイヤー登録: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")
        else:
            if player_name: player.name = player_name
            if player_icon_url: player.icon_url = player_icon_url
            db.commit()
            print(f"[save_teams] 既存プレイヤー更新: tournament={tournament_id}, seed={seed_number}, player_id={player.id}")

        # 重複キャラクターのバリデーション
        all_char_ids = []
        for team_data in teams:
            chars = team_data.get("characters", [])
            for c in chars:
                cid = c.get("id")
                try:
                    cid = int(cid) if cid else None
                except (ValueError, TypeError):
                    cid = None
                if cid is not None and cid != 9999:
                    all_char_ids.append(cid)
        
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
            
            # 自己学習パイプライン: 確定した画像をテンプレートとして追加保存（上書きしない）
            for char_info in chars:
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
                            print(f"[Template] 追加: {template_path}（累計 {next_num} 枚）")
                        else:
                            print(f"[Template] スキップ（重複）: char_{c_id}")
                        # DB上のフラグを更新
                        char_db = db.query(models.Character).filter(models.Character.id == c_id).first()
                        if char_db and not char_db.is_template_available:
                            char_db.is_template_available = True

        
        db.commit()
        return {"ok": True, "is_update": is_update}
    except Exception as e:
        import traceback
        print(f"Error in save_teams: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/player-icon")
async def upload_player_icon(
    image: UploadFile = File(...)
):
    # プレイヤーアイコンを保存
    filename = f"player_icon_{os.urandom(4).hex()}_{image.filename}"
    file_path = os.path.join("uploads/cropped", filename)
    os.makedirs("uploads/cropped", exist_ok=True)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
        
    return {"url": f"/api/uploads/cropped/{filename}"}

@app.post("/api/analyze/deck")
async def analyze_deck(
    tournament_id: int = Form(...),
    seed_number: int = Form(...),
    images: List[UploadFile] = File(...)
):
    saved_paths = []
    for idx, image in enumerate(images):
        file_location = f"{UPLOAD_DIR}/tour_{tournament_id}_seed_{seed_number}_img_{idx}_{image.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        saved_paths.append(file_location)
    
    # 画像処理サービスの呼び出し（ラウンドソートとキャラ切り抜き）
    result = process_images(saved_paths, tournament_id, seed_number)

    # ストレージ節約: 処理済みのスクショ原本を即削除
    for p in saved_paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            print(f"[Cleanup] 削除失敗: {p} - {e}")

    return result

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
        # ストレージ節約: 処理済みのスクショ原本を即削除
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as _e:
            print(f"[Cleanup] match画像削除失敗: {_e}")
        return resp
    except Exception as e:
        print(f"Error extracting match results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tournaments/{tournament_id}/bracket")
def get_tournament_bracket(tournament_id: int, db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
):
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

@app.get("/api/tournaments/{tournament_id}/dashboard/stats")
def get_dashboard_stats(tournament_id: int, seed: int = None, db: Session = Depends(get_db)):
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
    RESULT_SCORES = {
        "優勝": 1, "準優勝": 2, "ベスト4": 4,
        "ベスト8": 8, "ベスト16": 16, "ベスト32": 32, "ベスト64": 64
    }

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
        "team_usage": team_list
    }

@app.get("/api/tournaments/{tournament_id}/dashboard/matchups")
def get_dashboard_matchups(tournament_id: int, seed: int = None, db: Session = Depends(get_db)):
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
def get_best8_decks(tournament_id: int, db: Session = Depends(get_db)):
    """ベスト8進出者のプレイヤー名、成績、登録編成をまとめて取得する"""
    bracket = get_tournament_bracket(tournament_id, db)
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

class CrossTournamentRequest(PydanticBaseModel):
    """大会横断検索リクエスト"""
    tournament_ids: List[int]


@app.post("/api/dashboard/cross-tournament/stats")
def get_cross_tournament_stats(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    """複数大会を横断したキャラ採用率・編成使用率・勝率を集計する"""
    tournament_ids = body.tournament_ids
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
            if c_id is not None:
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
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_a_win: char_match_stats[c_id]["wins"] += 1
                for c_id in d_chars:
                    if c_id not in char_match_stats: char_match_stats[c_id] = {"wins": 0, "total": 0}
                    char_match_stats[c_id]["total"] += 1
                    if is_d_win: char_match_stats[c_id]["wins"] += 1

                # ポジション別勝敗
                a_all = [a_team.char1_id, a_team.char2_id, a_team.char3_id, a_team.char4_id, a_team.char5_id]
                d_all = [d_team.char1_id, d_team.char2_id, d_team.char3_id, d_team.char4_id, d_team.char5_id]
                for pos_idx, c_id in enumerate(a_all):
                    if c_id is not None:
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
                    if c_id is not None:
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
    RESULT_SCORES = {
        "優勝": 1, "準優勝": 2, "ベスト4": 4,
        "ベスト8": 8, "ベスト16": 16, "ベスト32": 32, "ベスト64": 64
    }

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
                if c_id is not None:
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
        "team_usage": team_list
    }


@app.post("/api/dashboard/cross-tournament/matchups")
def get_cross_tournament_matchups(body: CrossTournamentRequest, db: Session = Depends(get_db)):
    """複数大会を横断した対戦データを集計する"""
    tournament_ids = body.tournament_ids
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
