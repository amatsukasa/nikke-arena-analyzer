from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date as date_type, datetime

class CharacterBase(BaseModel):
    name: str
    weapon: Optional[str] = None
    element: Optional[str] = None
    burst_phase: Optional[str] = None
    manufacturer: Optional[str] = None
    rarity: Optional[str] = None
    class_type: Optional[str] = None
    is_template_available: bool = False
    template_filename: Optional[str] = None
    icon_url: Optional[str] = None

class Character(CharacterBase):
    id: int
    created_at: datetime
    usage_count: Optional[int] = 0
    model_config = ConfigDict(from_attributes=True)

class ChampionshipBase(BaseModel):
    name: str
    date: Optional[date_type] = None
    start_date: Optional[date_type] = None
    owner_name: Optional[str] = None

class ChampionshipCreate(ChampionshipBase):
    pass

class ChampionshipResponse(ChampionshipBase):
    id: int
    created_at: datetime
    created_by: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class TournamentBase(BaseModel):
    name: str
    date: date_type
    season: Optional[str] = None
    owner_name: Optional[str] = None
    championship_id: Optional[int] = None

class Tournament(TournamentBase):
    id: int
    created_at: datetime
    created_by: Optional[int] = None
    creator_email: Optional[str] = None
    publication_status: str = "draft"
    published_at: Optional[datetime] = None
    published_by: Optional[int] = None
    play_server: Optional[str] = None
    provider_game_start_date: Optional[date_type] = None
    model_config = ConfigDict(from_attributes=True)

class PlayerBase(BaseModel):
    tournament_id: int
    name: str
    seed_number: Optional[int] = None

class Player(PlayerBase):
    id: int
    icon_url: Optional[str] = None  # プレイヤーアイコンURL
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DeckTeamBase(BaseModel):
    team_number: int
    char1_id: Optional[int] = None
    char2_id: Optional[int] = None
    char3_id: Optional[int] = None
    char4_id: Optional[int] = None
    char5_id: Optional[int] = None
    collection1: Optional[str] = None
    collection2: Optional[str] = None
    collection3: Optional[str] = None
    collection4: Optional[str] = None
    collection5: Optional[str] = None

class DeckTeam(DeckTeamBase):
    id: int
    deck_set_id: int
    model_config = ConfigDict(from_attributes=True)

class DeckSetBase(BaseModel):
    player_id: int
    image_path: Optional[str] = None

class DeckSet(DeckSetBase):
    id: int
    created_at: datetime
    teams: List[DeckTeam] = []
    model_config = ConfigDict(from_attributes=True)

class RoundResultBase(BaseModel):
    round_number: int
    winner_id: Optional[int] = None

class RoundResult(RoundResultBase):
    id: int
    match_id: int
    model_config = ConfigDict(from_attributes=True)

class MatchBase(BaseModel):
    tournament_id: int
    stage: str
    attacker_id: int
    defender_id: int
    winner_id: Optional[int] = None

class Match(MatchBase):
    id: int
    created_at: datetime
    round_results: List[RoundResult] = []
    model_config = ConfigDict(from_attributes=True)

# 認証・ユーザー管理用のスキーマ追加
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str
    invite_code: str
    provider_name: Optional[str] = None # 追加: 提供者名
    game_start_date: Optional[date_type] = None # 追加: 指揮官のゲーム開始日
    play_server: Optional[str] = None

class UserLogin(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    role: str
    is_banned: bool
    provider_name: Optional[str] = None # 追加
    game_start_date: Optional[date_type] = None # 追加
    play_server: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
