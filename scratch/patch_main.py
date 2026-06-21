import re

main_path = "c:/Users/youm3/.gemini/antigravity/brain/ec518f6a-c5b5-4935-a3bd-71616e26ed04/backend/main.py"

with open(main_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 認証機能とルートの定義ブロックの作成
auth_code = """
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
"""

# CORS設定の後にコードを挿入
cors_end = 'allow_headers=["*"],\n)'
insert_pos = content.find(cors_end)
if insert_pos != -1:
    split_pos = insert_pos + len(cors_end)
    content = content[:split_pos] + "\n" + auth_code + content[split_pos:]
    print("Authentication logic inserted successfully.")
else:
    print("CORS configuration not found, aborting.")
    exit(1)

# 2. 既存の登録・更新・削除系API関数の定義を正規表現で置換してDependsを付与
# (注意: 関数の最初の引数に Depends がある場合、2番目以降にDepends(get_current_active_user)を追加、
# または引数がない場合は新規に引数を追加する)

replacements = [
    # create_character
    (r"def create_character\(body:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def create_character(body: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
    
    # update_character
    (r"def update_character\(char_id:\s*int,\s*body:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def update_character(char_id: int, body: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # delete_character
    (r"def delete_character\(char_id:\s*int,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def delete_character(char_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # create_tournament
    (r"def create_tournament\(tournament:\s*schemas\.TournamentBase,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def create_tournament(tournament: schemas.TournamentBase, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # update_tournament
    (r"def update_tournament\(tournament_id:\s*int,\s*tournament:\s*schemas\.TournamentBase,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def update_tournament(tournament_id: int, tournament: schemas.TournamentBase, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # delete_tournament
    (r"def delete_tournament\(tournament_id:\s*int,\s*db:\s*Session\s*=\s*Depends\(get_db\)\):",
     "def delete_tournament(tournament_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # update_player_info
    (r"async def update_player_info\(\s*tournament_id:\s*int,\s*seed_number:\s*int,\s*data:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):",
     "async def update_player_info(tournament_id: int, seed_number: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # save_teams
    (r"async def save_teams\(\s*tournament_id:\s*int,\s*data:\s*dict,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):",
     "async def save_teams(tournament_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
     
    # analyze_deck
    (r"async def analyze_deck\(\s*tournament_id:\s*int\s*=\s*Form\(\.\.\.\\),\s*seed_number:\s*int\s*=\s*Form\(\.\.\.\\),\s*images:\s*List\[UploadFile\]\s*=\s*File\(\.\.\.\)\s*\):",
     "async def analyze_deck(tournament_id: int = Form(...), seed_number: int = Form(...), images: List[UploadFile] = File(...), current_user: models.User = Depends(get_current_active_user)):"),
     
    # analyze_match_result
    (r"async def analyze_match_result\(\s*tournament_id:\s*int\s*=\s*Form\(\.\.\.\\),\s*attacker_seed:\s*int\s*=\s*Form\(\.\.\.\\),\s*defender_seed:\s*int\s*=\s*Form\(\.\.\.\\),\s*stage:\s*str\s*=\s*Form\(\"Groups\"\),\s*image:\s*UploadFile\s*=\s*File\(\.\.\.\)\s*\):",
     "async def analyze_match_result(tournament_id: int = Form(...), attacker_seed: int = Form(...), defender_seed: int = Form(...), stage: str = Form(\"Groups\"), image: UploadFile = File(...), current_user: models.User = Depends(get_current_active_user)):"),
     
    # save_match
    (r"async def save_match\(\s*tournament_id:\s*int,\s*request:\s*Request,\s*db:\s*Session\s*=\s*Depends\(get_db\)\s*\):",
     "async def save_match(tournament_id: int, request: Request, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):"),
]

for pat, repl in replacements:
    content, count = re.subn(pat, repl, content)
    print(f"Replaced {pat} -> {count} times")

# Tournament作成時にcreated_byにユーザーIDをセットする処理を追加
create_tour_orig = """    db_tournament = models.Tournament(**tournament.model_dump())
    db.add(db_tournament)"""
create_tour_repl = """    db_tournament = models.Tournament(**tournament.model_dump(), created_by=current_user.id)
    db.add(db_tournament)"""

if create_tour_orig in content:
    content = content.replace(create_tour_orig, create_tour_repl)
    print("create_tournament updated to include created_by.")
else:
    print("Warning: create_tournament match not found for created_by replacement.")

with open(main_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch complete.")
