# Acceptance test data

The acceptance environment is separate from the normal development database and
the destructive automated-test database.

## Start and seed

```powershell
docker compose --profile acceptance up -d --build
docker compose --profile acceptance run --rm backend_acceptance python scripts/seed_acceptance_test.py
```

Open `http://localhost:3001`. The acceptance backend is exposed only at
`http://localhost:8001` and uses the dedicated `nikke_arena_acceptance` database.
The database (`5434`), backend (`8001`), and frontend (`3001`) ports bind only
to `127.0.0.1`; they are not exposed to the LAN.

The seed truncates only mapped tables in the allowlisted acceptance database
with `RESTART IDENTITY CASCADE`, so repeated runs reproduce the same row IDs.

## Dataset contract

- User: `acceptance-admin@example.test`
- Password: `acceptance-admin-password`
- Role/status: active administrator
- Play server: `JP`
- Provider game start date: `2022-11-04`
- Championship: `2026 Acceptance Championship`
- Tournament: `2026-09 Team Search Acceptance Tournament`
- Tournament date/season: `2026-09-17` / `2026-09 Acceptance`
- Tournament type: Champion Arena tournament with match data
- Registration scope: `full_64`
- Players: 8 complete players with seeds 1–8
- Decks: one deck set and five complete teams per player (40 teams total)
- Matches: four Best 64 matches, each with five round results
- Character source: `backend/testdata/characters_production.csv`, exported from the
  production Character master and retaining the original IDs
- Arena characters: IDs `19, 32, 33, 47, 52, 69, 103, 122, 145, 147, 162, 172`
- Non-arena comparison characters: every other Character in the CSV

Expected Team Search behavior:

- Arena priority shows used arena characters before used non-arena characters
  within each Burst group.
- Arena only hides every Character whose `is_arena_relevant` value is false.
- All characters ignores arena relevance while retaining the normal grouping.
- The top-page and tournament dashboard use the same shared selector and picker.

## Data quality rules

Normal acceptance fixtures must be creatable through the production workflow and
must include all required and effectively required fields. Deliberately incomplete
records belong in a separately named negative-test fixture and must never be mixed
into this dataset. Before changing application fallback behavior, verify whether a
reported state can be produced by the normal UI/API flow.

## Automated tests

Automated tests use only `TEST_DATABASE_URL`. Run them through the fail-closed
runner; it refuses missing, non-test, Railway-like, or application DB targets:

```powershell
docker compose exec -T backend python scripts/run_safe_tests.py discover -s tests -v
```
