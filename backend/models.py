from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # "admin" or "user"
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="contributor") # "admin" or "contributor"
    is_banned = Column(Boolean, default=False)
    provider_name = Column(String, nullable=True) # 追加: 提供者名
    game_start_date = Column(Date, nullable=True) # 追加: 指揮官のゲーム開始日
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    championships = relationship("Championship", back_populates="creator")
    tournaments = relationship("Tournament", back_populates="creator")

class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    weapon = Column(String, nullable=True)
    element = Column(String, nullable=True)
    burst_phase = Column(String, nullable=True) # "1", "2", "3", "A"
    manufacturer = Column(String, nullable=True)
    rarity = Column(String)  # SSR, SR, R
    class_type = Column(String, nullable=True) # "火力型", "支援型", "防御型"
    is_template_available = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Championship(Base):
    __tablename__ = "championships"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=True) # 開催順管理とするため nullable に変更
    start_date = Column(Date, nullable=True)
    owner_name = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("app_users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("AppUser", back_populates="championships")
    tournaments = relationship("Tournament", back_populates="championship")

class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    season = Column(String, nullable=True) # e.g. "β30", "β31"
    owner_name = Column(String, nullable=True) # データ提供者
    championship_id = Column(Integer, ForeignKey("championships.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 追加: 登録ユーザーの関連付け
    created_by = Column(Integer, ForeignKey("app_users.id"), nullable=True)
    
    creator = relationship("AppUser", back_populates="tournaments")
    championship = relationship("Championship", back_populates="tournaments")
    players = relationship("Player", back_populates="tournament")
    matches = relationship("Match", back_populates="tournament")

class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint('tournament_id', 'seed_number', name='uq_player_tournament_seed'),
    )
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"))
    seed_number = Column(Integer, nullable=True) # 1 to 64
    name = Column(String, nullable=False)
    icon_url = Column(String, nullable=True) # 追加: プレイヤーアイコンのURL
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tournament = relationship("Tournament", back_populates="players")
    deck_sets = relationship("DeckSet", back_populates="player")

class DeckSet(Base):
    __tablename__ = "deck_sets"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    player = relationship("Player", back_populates="deck_sets")
    teams = relationship("DeckTeam", back_populates="deck_set", cascade="all, delete-orphan")

class DeckTeam(Base):
    __tablename__ = "deck_teams"
    id = Column(Integer, primary_key=True, index=True)
    deck_set_id = Column(Integer, ForeignKey("deck_sets.id"))
    team_number = Column(Integer, nullable=False) # 1 to 5
    
    char1_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    char2_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    char3_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    char4_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    char5_id = Column(Integer, ForeignKey("characters.id"), nullable=True)

    deck_set = relationship("DeckSet", back_populates="teams")

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"))
    stage = Column(String, nullable=False) # "Best 64", "Final" etc.
    attacker_id = Column(Integer, ForeignKey("players.id"))
    defender_id = Column(Integer, ForeignKey("players.id"))
    winner_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tournament = relationship("Tournament", back_populates="matches")
    attacker = relationship("Player", foreign_keys=[attacker_id])
    defender = relationship("Player", foreign_keys=[defender_id])
    winner = relationship("Player", foreign_keys=[winner_id])
    round_results = relationship("RoundResult", back_populates="match", cascade="all, delete-orphan")

class RoundResult(Base):
    __tablename__ = "round_results"
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    round_number = Column(Integer, nullable=False) # 1 to 5
    winner_id = Column(Integer, ForeignKey("players.id"), nullable=True)

    match = relationship("Match", back_populates="round_results")
    winner = relationship("Player", foreign_keys=[winner_id])
