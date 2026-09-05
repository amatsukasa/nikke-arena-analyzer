export interface RegistrationTeamCharacter {
  id: number | null;
  collection_level: string | null;
  source_image_index?: number | null;
  image_url?: string | null;
  preview_image_data_url?: string | null;
  original_predicted_id?: number | null;
  was_unrecognized?: boolean;
  add_to_templates?: boolean;
  template_source_url?: string | null;
  template_source_data_url?: string | null;
  matched_template_filename?: string | null;
  similarity?: number | null;
  match_method?: string | null;
  analysis_token?: string | null;
  round_number?: number | null;
  position?: number | null;
}

export interface RegistrationTeam {
  team_number: number;
  characters: RegistrationTeamCharacter[];
}

export function normalizeRegistrationCharacterId(value: unknown): number | null {
  if (typeof value === "number") return Number.isInteger(value) ? value : null;
  if (typeof value !== "string" || !/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

export function registrationCharacterImageUrl(
  character: RegistrationTeamCharacter,
  info?: { id: number; icon_url?: string | null; image_url?: string | null; is_template_available?: boolean; template_filename?: string | null },
) {
  if (character.preview_image_data_url) return character.preview_image_data_url;
  if (character.image_url) return character.image_url;
  if (!info) return "";
  if (info.icon_url) return info.icon_url;
  if (info.image_url) return info.image_url;
  if (info.is_template_available || info.template_filename) return `/api/char-icon/${info.id}.png`;
  return "";
}

export function hasCompleteRegistrationStructure(teams: RegistrationTeam[]) {
  return teams.length === 5
    && [...teams.map(team => team.team_number)].sort((a, b) => a - b).join(",") === "1,2,3,4,5"
    && teams.every(team => team.characters.length === 5 && team.characters.every(character => character.id != null));
}

export function validateRegistrationTeams(teams: RegistrationTeam[], knownCharacterIds: Set<number>) {
  const issues: string[] = [];
  if (teams.length !== 5) issues.push("部隊は5件ちょうど必要です。");
  const numbers = teams.map(team => team.team_number);
  if (numbers.length !== 5 || [...numbers].sort((a, b) => a - b).join(",") !== "1,2,3,4,5") {
    issues.push("部隊番号は1～5を1件ずつ指定してください。");
  }
  const seen = new Map<number, string>();
  teams.forEach(team => {
    if (team.characters.length !== 5) issues.push(`部隊${team.team_number}は5人必要です。`);
    team.characters.forEach((character, index) => {
      const label = `部隊${team.team_number}・${index + 1}人目`;
      if (character.id == null) issues.push(`${label}が未判定です。`);
      else if (character.id === 9999) return;
      else if (!knownCharacterIds.has(character.id)) issues.push(`${label}のキャラクターが存在しません。`);
      else if (seen.has(character.id)) issues.push(`${label}が${seen.get(character.id)}と重複しています。`);
      else seen.set(character.id, label);
    });
  });
  return issues;
}

export function normalizeSavedRegistrationTeams(data: any): RegistrationTeam[] {
  const source = Array.isArray(data?.teams) ? data.teams : Array.isArray(data?.decks) ? data.decks : [];
  return source.map((team: any) => ({
    team_number: Number(team.team_number),
    characters: (Array.isArray(team.character_ids) ? team.character_ids : []).map((id: unknown, index: number) => ({
      id: normalizeRegistrationCharacterId(id),
      collection_level: Array.isArray(team.collection_levels) ? team.collection_levels[index] ?? null : null,
    })),
  }));
}

export function normalizeAnalyzedRegistrationTeams(data: any): RegistrationTeam[] {
  const structured = Array.isArray(data?.teams);
  const source = structured ? data.teams : Array.isArray(data?.suggested_teams) ? data.suggested_teams : [];
  return source.map((team: any, teamIndex: number) => {
    const characters = structured && Array.isArray(team?.characters) ? team.characters : Array.isArray(team) ? team : [];
    return {
      team_number: Number(structured ? team.team_number : teamIndex + 1),
      characters: characters.map((character: any) => {
        const rawId = structured ? character.character_id : character.predicted_character_id;
        const id = normalizeRegistrationCharacterId(rawId);
        return {
          id,
          collection_level: id === 9999 ? null : character.collection_level ?? "unknown",
          source_image_index: character.source_image_index ?? (structured ? team.source_image_index : null) ?? null,
          image_url: character.image_url ?? null,
          preview_image_data_url: character.preview_image_data_url ?? null,
          original_predicted_id: id,
          was_unrecognized: structured ? Boolean(character.unresolved) : id == null,
          add_to_templates: false,
          template_source_url: character.template_source_url ?? null,
          template_source_data_url: character.template_source_data_url ?? null,
          matched_template_filename: character.matched_template_filename ?? null,
          similarity: typeof character.similarity === "number" ? character.similarity : (typeof character.confidence === "number" ? character.confidence : null),
          match_method: character.match_method ?? null,
          analysis_token: character.analysis_token ?? null,
          round_number: character.round_number ?? teamIndex + 1,
          position: character.position ?? null,
        };
      }),
    };
  });
}

export function registrationTeamsPayload(teams: RegistrationTeam[]) {
  return teams.map(team => ({ team_number: team.team_number, characters: team.characters.map((character, characterIndex) => ({
    id: character.id,
    collection_level: character.id === 9999 ? null : character.collection_level,
    image_url: character.image_url ?? null,
    original_predicted_id: character.original_predicted_id ?? null,
    was_unrecognized: Boolean(character.was_unrecognized),
    add_to_templates: Boolean(character.add_to_templates),
    // Keep the owned lossless crop reference even when no template is added.
    // champion_8 consumes both preview and lossless files after a successful
    // save; full_64 ignores it unless add_to_templates is true.
    template_source_url: character.template_source_url ?? null,
    template_source_data_url: character.add_to_templates ? character.template_source_data_url ?? null : null,
    matched_template_filename: character.matched_template_filename ?? null,
    similarity: character.similarity ?? null,
    match_method: character.match_method ?? null,
    analysis_token: character.analysis_token ?? null,
    round_number: character.round_number ?? team.team_number,
    position: character.position ?? characterIndex + 1,
  })) }));
}

export function registrationSaveConfirmation(
  playerLabel: string,
  positionLabel: string,
  teams: RegistrationTeam[],
  characterNames: Map<number, string>,
  overwrite: boolean,
) {
  const label = (id: number | null | undefined) => id == null ? "（不明）" : id === 9999 ? "空き枠" : characterNames.get(id) ?? `ID:${id}`;
  const corrected: string[] = [], changed: string[] = [], empty: string[] = [];
  teams.forEach((team, teamIndex) => team.characters.forEach((character, characterIndex) => {
    const position = `R${teamIndex + 1}・${characterIndex + 1}人目`;
    if (character.id === 9999) empty.push(position);
    if (!character.add_to_templates) return;
    if (character.was_unrecognized) corrected.push(`${position}：（不明）→ ${label(character.id)}`);
    else changed.push(`${position}：${label(character.original_predicted_id)} → ${label(character.id)}`);
  }));
  const lines = (values: string[]) => values.length ? values.map(value => `・${value}`).join("\n") : "・なし";
  const introduction = overwrite
    ? `${playerLabel}の保存済み編成を、この内容で上書きしますか？`
    : `${playerLabel}（${positionLabel}）をこの内容で登録しますか？`;
  const templateNotice = corrected.length || changed.length ? "\n\n補正した画像は、今後の解析テンプレートへ自動追加されます。" : "";
  return `${introduction}\n\n未判定から補正したキャラ：\n${lines(corrected)}\n\n推測結果から変更したキャラ：\n${lines(changed)}\n\n空き枠：\n${lines(empty)}${templateNotice}`;
}

export interface DeckRegistrationAdapter {
  analyze(prepared: { file: File; preCropped: boolean }[]): Promise<RegistrationTeam[]>;
  save(teams: RegistrationTeam[]): Promise<{ overwrite: boolean }>;
}
