export type RegistrationScope = "full_64" | "champion_8";

export interface TournamentSummary {
  id: number;
  name: string;
  date: string;
  start_date?: string | null;
  owner_name?: string | null;
  championship_id?: number | null;
  creator_email?: string | null;
  created_by?: number | null;
  created_at?: string;
  publication_status: "draft" | "published";
  published_at?: string | null;
  registration_scope: RegistrationScope;
  provider_game_start_date: string | null;
}

export const REGISTRATION_SCOPE_LABELS: Record<RegistrationScope, string> = {
  full_64: "通常登録（64人）",
  champion_8: "チャンピオン対抗戦のみ（8人）",
};

export const REGISTRATION_SCOPE_DESCRIPTIONS: Record<RegistrationScope, string> = {
  full_64: "64人分の進級戦とチャンピオン対抗戦を登録します。",
  champion_8: "グループ戦は登録せず、チャンピオン対抗戦へ進出した8人のみ登録します。",
};

export interface TournamentFormScopeState {
  registrationScope: RegistrationScope;
  providerGameStartDate: string;
  providerDateTouched: boolean;
  providerDateInitialized: boolean;
}

export function createTournamentFormScopeState(profileDate?: string | null): TournamentFormScopeState {
  return {
    registrationScope: "full_64",
    providerGameStartDate: profileDate || "",
    providerDateTouched: false,
    providerDateInitialized: profileDate !== undefined,
  };
}

export function editTournamentFormScopeState(tournament: Pick<TournamentSummary, "registration_scope" | "provider_game_start_date">): TournamentFormScopeState {
  return {
    registrationScope: tournament.registration_scope,
    providerGameStartDate: tournament.provider_game_start_date || "",
    providerDateTouched: true,
    providerDateInitialized: true,
  };
}

export function normalizeTournament(value: Partial<TournamentSummary> & Pick<TournamentSummary, "id" | "name" | "date" | "publication_status">): TournamentSummary {
  if (!Number.isInteger(value.id) || value.id <= 0) {
    throw new Error("大会レスポンスに有効なIDがありません。");
  }
  if (value.registration_scope !== undefined && value.registration_scope !== "full_64" && value.registration_scope !== "champion_8") {
    throw new Error("大会の登録範囲が不正です。");
  }
  return {
    ...value,
    registration_scope: value.registration_scope ?? "full_64",
    provider_game_start_date: value.provider_game_start_date ?? null,
  } as TournamentSummary;
}

export function isValidDateInput(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;
  for (const candidate of [record.detail, record.message]) {
    if (typeof candidate === "string" && candidate.trim()) return candidate;
    if (Array.isArray(candidate)) {
      const messages = candidate.flatMap(item => {
        if (typeof item === "string") return [item];
        if (item && typeof item === "object" && typeof (item as Record<string, unknown>).msg === "string") {
          return [(item as Record<string, string>).msg];
        }
        return [];
      });
      if (messages.length) return messages.join(" / ");
    }
  }
  return fallback;
}
