"""Pure conversion of legacy left/right match analysis into player IDs."""


def normalize_champion_result(raw_result: dict, attacker_id: int, defender_id: int) -> dict:
    raw_rounds = raw_result.get("rounds")
    issues: list[str] = []
    if not isinstance(raw_rounds, list):
        raw_rounds = []
        issues.append("解析結果にラウンド一覧がありません")
    if len(raw_rounds) != 5:
        issues.append(f"解析されたラウンド数が5件ではありません（{len(raw_rounds)}件）")

    by_number: dict[int, list[dict]] = {}
    for raw_round in raw_rounds:
        if not isinstance(raw_round, dict):
            issues.append("ラウンド結果の形式が不正です")
            continue
        number = raw_round.get("round", raw_round.get("round_number"))
        if not isinstance(number, int) or number not in range(1, 6):
            issues.append(f"不正なround_numberです: {number}")
            continue
        by_number.setdefault(number, []).append(raw_round)

    rounds = []
    for number in range(1, 6):
        candidates = by_number.get(number, [])
        side = None
        winner_id = None
        unresolved = True
        if len(candidates) != 1:
            issues.append(
                f"ラウンド{number}が欠落しています"
                if not candidates
                else f"ラウンド{number}が重複しています"
            )
        else:
            left = candidates[0].get("left")
            right = candidates[0].get("right")
            if left == "WIN" and right == "LOSE":
                side, winner_id, unresolved = "left", attacker_id, False
            elif left == "LOSE" and right == "WIN":
                side, winner_id, unresolved = "right", defender_id, False
            else:
                issues.append(
                    f"ラウンド{number}の左右判定が未確定または矛盾しています"
                )
        rounds.append({
            "round_number": number,
            "winner_id": winner_id,
            "side": side,
            "unresolved": unresolved,
        })

    complete = not issues and all(not result["unresolved"] for result in rounds)
    winner_id = None
    if complete:
        attacker_wins = sum(result["winner_id"] == attacker_id for result in rounds)
        calculated_side = "left" if attacker_wins >= 3 else "right"
        reported_side = raw_result.get("winner")
        if reported_side in {"left", "right"} and reported_side != calculated_side:
            issues.append("ラウンド多数結果と解析器の左右勝者が矛盾しています")
            complete = False
        else:
            winner_id = attacker_id if calculated_side == "left" else defender_id
    return {
        "winner_id": winner_id,
        "round_results": rounds,
        "complete": complete,
        "issues": issues,
    }
