export type TeamKey = (value: unknown) => string;

export type MatchupResult = "WIN" | "LOSE";

export function matchupSideResults(match: {
  winner_is_attacker?: boolean;
  isAttacker: boolean;
  isWin: boolean;
}): { attacker: MatchupResult; defender: MatchupResult } {
  const attackerWon = typeof match.winner_is_attacker === "boolean"
    ? match.winner_is_attacker
    : match.isAttacker === match.isWin;
  return attackerWon
    ? { attacker: "WIN", defender: "LOSE" }
    : { attacker: "LOSE", defender: "WIN" };
}

export function teamMatchupPerspective(matchups: any[], targetKey: string, teamKey: TeamKey) {
  const details: any[] = [];
  let totalWins = 0;
  let totalLosses = 0;
  let attackWins = 0;
  let attackLosses = 0;
  let defenseWins = 0;
  let defenseLosses = 0;

  for (const match of matchups) {
    const attackerMatches = teamKey(match.canonical_attacker || match.attacker_team) === targetKey;
    const defenderMatches = teamKey(match.canonical_defender || match.defender_team) === targetKey;
    const sides = [
      ...(attackerMatches ? [true] : []),
      ...(defenderMatches ? [false] : []),
    ];

    for (const isAttacker of sides) {
      const isWin = Boolean(match.winner_is_attacker) === isAttacker;
      if (isWin) totalWins += 1; else totalLosses += 1;
      if (isAttacker) {
        if (isWin) attackWins += 1; else attackLosses += 1;
      } else if (isWin) defenseWins += 1; else defenseLosses += 1;

      details.push({
        ...match,
        participationKey: `${match.match_id}:${match.round_number}:${isAttacker ? "attacker" : "defender"}`,
        playerId: isAttacker ? match.attacker_player_id : match.defender_player_id,
        teamId: isAttacker ? match.attacker_team_id : match.defender_team_id,
        teamNumber: isAttacker ? match.attacker_team_number : match.defender_team_number,
        opponent: isAttacker ? match.defender_team : match.attacker_team,
        opponentCanonical: isAttacker ? match.canonical_defender : match.canonical_attacker,
        attackerTeam: match.attacker_team,
        defenderTeam: match.defender_team,
        attackerCollections: match.attacker_collections,
        defenderCollections: match.defender_collections,
        canonicalAttacker: match.canonical_attacker,
        canonicalDefender: match.canonical_defender,
        isAttacker,
        isWin,
        stage: match.stage,
        tournamentName: match.tournament_name,
        attackerName: match.attacker_name,
        defenderName: match.defender_name,
      });
    }
  }

  return { details, totalWins, totalLosses, attackWins, attackLosses, defenseWins, defenseLosses };
}
