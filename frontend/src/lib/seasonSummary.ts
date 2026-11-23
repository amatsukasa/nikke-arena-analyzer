export const serverLabels = {
  JP: "server.jp", GLOBAL: "server.global", KR: "server.kr", NA: "server.na", SEA: "server.sea",
} as const;

export type PlayServer = keyof typeof serverLabels;
export type SummaryStage = "legacy" | "league" | "championship" | "final";
export const summaryStageLabel = (stage: SummaryStage) => stage === "legacy" ? "seasonSummary.wholeEvent" : `arenaPhases.${stage}`;

export function isPlayServer(value: string | null): value is PlayServer {
  return value !== null && Object.hasOwn(serverLabels, value);
}

export type Scope = {
  championship_id: number;
  title: string;
  play_server: PlayServer;
  tournament_ids: number[];
  tournament_count: number;
  full_64: number;
  champion_8: number;
};

export type ReferenceScope = Pick<Scope, "play_server" | "tournament_count">;
type Result = { attack: number; defense: number; total: number };
export type Adoption = { count: number; population: number; rate: number | null };
export type RankedTeam = Adoption & {
  rank: number;
  canonical_id: string;
  character_ids: number[];
  earlier?: Partial<Record<SummaryStage, Adoption>>;
};
export type Ranking = { tournament_ids: number[]; population: number; teams: RankedTeam[] };
type NamedNikke = { id: number; name: string };
type Burst = "1" | "2" | "3";
export type WeaponMetric = "slots" | "commanders";
type Weapon = "SG" | "SR" | "AR" | "MG" | "RL" | "SMG";
type WeaponScope = { commanders: number; slots: number; unknown_slots: number };
export type StageAdoption = {
  weapons: WeaponScope & { weapons: ({ weapon: Weapon } & Record<WeaponMetric, Adoption>)[] };
  burst: { population: number; groups: Record<Burst, (NamedNikke & Adoption)[]> };
};
export type AdoptionChange = { current: Adoption; previous: Adoption; change_pt: number | null };
type TransitionScope = WeaponScope & { tournaments: number; public_tournaments: number;
  reason: "no_public_tournaments" | "no_complete_registrations" | null };
export type WeaponTransition = {
  current: TransitionScope;
  previous: TransitionScope;
  weapons: ({ weapon: Weapon } & Record<WeaponMetric, AdoptionChange>)[];
};
export type StageGrowth = {
  current_population: number;
  previous_population: number;
  previous_tournaments: number;
  characters: (NamedNikke & AdoptionChange)[];
  teams: ({ canonical_id: string; character_ids: number[] } & AdoptionChange)[];
};
type SeasonComparison =
  | { mode: "transition"; previous: NamedNikke; reason: null; transition: WeaponTransition }
  | { mode: "growth"; previous: NamedNikke; reason: null; growth: Partial<Record<SummaryStage, StageGrowth>> }
  | { mode: "unavailable"; previous: null; reason: "order_unknown" | "format_unknown" | "no_previous_season" | null };
export type BattleSide = "attack" | "defense";
export type SideLeaders = { minimum_rounds: number } & Record<BattleSide, {
  canonical_id: string; character_ids: number[]; wins: number; losses: number;
  rounds: number; win_rate: number; has_details: boolean;
}[]>;
export type DebutResults = Adoption & {
  wins: number; losses: number; rounds: number; win_rate: number | null;
  partners: (NamedNikke & { rate: number })[];
};
type DebutCharacter = NamedNikke & { sections: { all: DebutResults } & Partial<Record<SummaryStage, DebutResults>> };

export type SummaryStatistics = Scope & {
  rounds: Result;
  matches: Result;
  side_leaders: SideLeaders;
  initial_stage: SummaryStage;
  rankings: Partial<Record<SummaryStage, Ranking>>;
  adoption_stages: Partial<Record<SummaryStage, StageAdoption>>;
  season_comparison: SeasonComparison;
  debut: { stage: SummaryStage; tournament_ids: number[]; characters: DebutCharacter[];
    tournament_ids_by_stage: Partial<Record<SummaryStage, number[]>> } | null;
};

export function summaryEndpoint(championship: number, server: PlayServer, scopeOnly = false) {
  return `/api/season-summary/${championship}?play_server=${server}${scopeOnly ? "&scope_only=true" : ""}`;
}

export function compositionSummaryHref(
  scope: Scope, stage: SummaryStage | "all", ids: number[], composition: string, side?: BattleSide,
) {
  const params = new URLSearchParams({
    tab: "matchups", teamKey: composition, detail_phase: stage, tournaments: ids.join(","),
    summary_championship: String(scope.championship_id), summary_server: scope.play_server,
  });
  return `/?${params}${side ? `#detail-${side}` : ""}`;
}

export function characterSummaryHref(id: number, stage: SummaryStage, ids: number[]) {
  return `/character/${id}?tournaments=${ids.join(",")}&registration_phase=${stage}`;
}
