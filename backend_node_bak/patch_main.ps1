$mainPath = "c:\Users\youm3\.gemini\antigravity\brain\ec518f6a-c5b5-4935-a3bd-71616e26ed04\backend\main.py"
$content = Get-Content -Raw -Path $mainPath -Encoding UTF8

$authCode = @"

from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from typing import Optional

# JWT認証・管理者制御の設定
JWT_SECRET = os.environ.get("JWT_SECRET", "super_secret_jwt_key_change_me_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24時間
REGISTRATION_INVITE_CODE = os.environ.get("REGISTRATION_INVITE_CODE", "INVITE2026")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

# 認証の依存関係
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="認証資格情報を検証できませんでした。",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
        
    if user.is_banned:
        raise HTTPException(status_code=403, detail="このアカウントは停止（BAN）されています。")
        
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    return current_user

async def get_current_admin_user(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="この操作を実行する権限がありません。")
    return current_user

# 認証APIルート
@app.post("/api/auth/register", response_model=schemas.UserResponse)
def register_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if user_in.invite_code != REGISTRATION_INVITE_CODE:
        raise HTTPException(status_code=400, detail="招待コードが正しくありません。")
    db_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="このメールアドレスは既に登録されています。")
    hashed_password = get_password_hash(user_in.password)
    new_user = models.User(
        email=user_in.email,
        hashed_password=hashed_password,
        role="user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/api/auth/login")
def login_for_access_token(user_in: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="メールアドレスまたはパスワードが正しくありません。")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="このアカウントは利用停止（BAN）されています。")
    if not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="メールアドレスまたはパスワードが正しくありません。")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@app.get("/api/auth/me")
def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

# 管理者APIルート
@app.get("/api/admin/users", response_model=List[schemas.UserResponse])
def get_users_list(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    return db.query(models.User).order_by(models.User.id.asc()).all()

@app.put("/api/admin/users/{user_id}/ban")
def ban_user(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="自分自身をアカウント停止することはできません。")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません。")
    user.is_banned = True
    db.commit()
    return {"message": "ユーザーをアカウント停止（BAN）しました。"}

@app.put("/api/admin/users/{user_id}/unban")
def unban_user(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません。")
    user.is_banned = False
    db.commit()
    return {"message": "ユーザーのアカウント停止を解除しました。"}

@app.put("/api/admin/users/{user_id}/role")
def update_user_role(user_id: int, body: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin_user)):
    role = body.get("role")
    if role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="無効なロールです。")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="自分自身の権限を変更することはできません。")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません。")
    user.role = role
    db.commit()
    return {"message": f"ユーザーの権限を {role} に変更しました。"}

# 起動時の初期シードデータ（管理者アカウントの自動作成）
@app.on_event("startup")
def create_initial_admin():
    db = next(get_db())
    # テーブルの自動生成
    Base.metadata.create_all(bind=engine)
    
    # 管理者がいるかチェック
    admin_exists = db.query(models.User).filter(models.User.role == "admin").first()
    if not admin_exists:
        hashed_password = get_password_hash("admin123")
        admin_user = models.User(
            email="admin@example.com",
            hashed_password=hashed_password,
            role="admin"
        )
        db.add(admin_user)
        db.commit()
        print("初期管理者アカウント (admin@example.com / admin123) を自動生成しました。")
"@

# CORS設定の直後に挿入
$corsTag = 'allow_headers=\["\*"\],\s*\)'
if ($content -match $corsTag) {
    $content = $content -replace $corsTag, "`$&`n$authCode"
    Write-Host "Auth code inserted successfully."
} else {
    Write-Error "CORS config not found."
    exit 1
}

# 関数の依存関係置換
$content = $content -replace 'def create_character\(body:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def create_character(body: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'def update_character\(char_id:\s*int,\s*body:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def update_character(char_id: int, body: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'def delete_character\(char_id:\s*int,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def delete_character(char_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'

$content = $content -replace 'def create_tournament\(tournament:\s*schemas\.TournamentBase,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def create_tournament(tournament: schemas.TournamentBase, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'def update_tournament\(tournament_id:\s*int,\s*tournament:\s*schemas\.TournamentBase,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def update_tournament(tournament_id: int, tournament: schemas.TournamentBase, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'def delete_tournament\(tournament_id:\s*int,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):', 'def delete_tournament(tournament_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'

$content = $content -replace 'async def update_player_info\(\s*tournament_id:\s*int,\s*seed_number:\s*int,\s*data:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):', 'async def update_player_info(tournament_id: int, seed_number: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'async def save_teams\(\s*tournament_id:\s*int,\s*data:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):', 'async def save_teams(tournament_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'

# 引数の複数行やバックスラッシュを含むものを置換
$content = $content -replace 'async def analyze_deck\(\s*tournament_id:\s*int\s*=\s*Form\(\.\.\.\\\),\s*seed_number:\s*int\s*=\s*Form\(\.\.\.\\\),\s*images:\s*List\[UploadFile\]\s*=\s*File\(\.\.\.\)\s*\):', 'async def analyze_deck(tournament_id: int = Form(...), seed_number: int = Form(...), images: List[UploadFile] = File(...), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'async def analyze_match_result\(\s*tournament_id:\s*int\s*=\s*Form\(\.\.\.\\\),\s*attacker_seed:\s*int\s*=\s*Form\(\.\.\.\\\),\s*defender_seed:\s*int\s*=\s*Form\(\.\.\.\\\),\s*stage:\s*str\s*=\s*Form\("Groups"\),\s*image:\s*UploadFile\s*=\s*File\(\.\.\.\)\s*\):', 'async def analyze_match_result(tournament_id: int = Form(...), attacker_seed: int = Form(...), defender_seed: int = Form(...), stage: str = Form("Groups"), image: UploadFile = File(...), current_user: models.User = Depends(get_current_active_user)):'
$content = $content -replace 'async def save_match\(\s*tournament_id:\s*int,\s*request:\s*Request,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):', 'async def save_match(tournament_id: int, request: Request, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):'

# Tournament作成時のcreated_by設定
$targetCreate = 'db_tournament = models\.Tournament\(\*\*tournament\.model_dump\(\)\)\s*db\.add\(db_tournament\)'
if ($content -match $targetCreate) {
    $content = $content -replace $targetCreate, 'db_tournament = models.Tournament(**tournament.model_dump(), created_by=current_user.id); db.add(db_tournament)'
    Write-Host "Tournament created_by patch applied."
}

[System.IO.File]::WriteAllText($mainPath, $content, [System.Text.Encoding]::UTF8)
Write-Host "Script completed."
