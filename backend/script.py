from database import SessionLocal
from models import Player, DeckSet, DeckTeam
db=SessionLocal()
ds_ids=[d.id for d in db.query(DeckSet).join(Player).filter(Player.tournament_id==17).all()]
teams=db.query(DeckTeam).filter(DeckTeam.deck_set_id.in_(ds_ids)).all()
count=0
dupes=[]
player_dupes={}
for t in teams:
  chars=[t.char1_id,t.char2_id,t.char3_id,t.char4_id,t.char5_id]
  c=chars.count(34)
  count+=c
  if c>1: dupes.append(t.id)
  if c>0:
    player_dupes[t.deck_set_id] = player_dupes.get(t.deck_set_id, 0) + c
print(f'Total count: {count}')
print(f'Teams with multiple 34: {dupes}')
p_with_multiple = {k: v for k, v in player_dupes.items() if v > 1}
print(f'DeckSets with >1 34s: {p_with_multiple}')
