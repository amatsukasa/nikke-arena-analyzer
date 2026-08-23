export interface PublicationIssue {
  code: string;
  message: string;
}
export interface PublicationReadiness {
  player_count: number;
  complete_player_count: number;
  incomplete_player_count: number;
  unresolved_slot_count: number;
  match_count: number;
  can_publish: boolean;
  warnings: string[];
  errors?: PublicationIssue[];
  counts?: {
    players: number;
    complete_players: number;
    teams: number;
    matches: number;
    round_results: number;
  };
}

export function publicationSummary(readiness: PublicationReadiness): string[] {
  const counts = readiness.counts;
  if (counts) {
    return [
      `登録Player: ${counts.players}人（編成完了 ${counts.complete_players}人）`,
      `登録部隊: ${counts.teams}部隊`,
      `登録試合: ${counts.matches}試合`,
      `登録ラウンド: ${counts.round_results}ラウンド`,
    ];
  }
  return [
    `登録プレイヤー: ${readiness.player_count}人`,
    `編成登録完了: ${readiness.complete_player_count}人`,
    `編成未完了: ${readiness.incomplete_player_count}人`,
    `未確定のキャラクター枠: ${readiness.unresolved_slot_count}件`,
    `対戦結果: ${readiness.match_count}件`,
  ];
}

export function publicationErrorLines(readiness: PublicationReadiness): string[] {
  return (readiness.errors ?? []).map(error => `・[${error.code}] ${error.message}`);
}
