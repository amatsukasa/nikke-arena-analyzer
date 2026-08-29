import type { RegistrationScope } from "./tournaments";

type MatchStageDisplayInput = {
  registrationScope?: RegistrationScope | null;
  rawStage?: string | null;
  bracketStage?: string | null;
  bracketSlot?: number | null;
};

export const MATCH_STAGE_DISPLAY_ORDER = [
  "ベスト64",
  "ベスト32",
  "ベスト16",
  "ベスト8",
  "ベスト4",
  "FINAL",
] as const;

export function sortUniqueMatchStageDisplays(stages: Array<string | null | undefined>): string[] {
  const uniqueStages = Array.from(new Set(stages.map((stage) => stage || "不明")));
  return uniqueStages.sort((left, right) => {
    const leftIndex = MATCH_STAGE_DISPLAY_ORDER.indexOf(left as typeof MATCH_STAGE_DISPLAY_ORDER[number]);
    const rightIndex = MATCH_STAGE_DISPLAY_ORDER.indexOf(right as typeof MATCH_STAGE_DISPLAY_ORDER[number]);
    if (leftIndex !== -1 && rightIndex !== -1) return leftIndex - rightIndex;
    if (leftIndex !== -1) return -1;
    if (rightIndex !== -1) return 1;
    return left.localeCompare(right, "ja");
  });
}

export function formatMatchStageForDisplay({
  registrationScope,
  rawStage,
  bracketStage,
  bracketSlot,
}: MatchStageDisplayInput): string | null | undefined {
  const normalizedRawStage = rawStage?.trim();
  const compactRawStage = normalizedRawStage?.replace(/\s+/g, "").toLowerCase();
  const fullStage = compactRawStage?.match(/^best(64|32|16|8|4)$/);
  if (fullStage) return `ベスト${fullStage[1]}`;
  if (/^FINAL$/i.test(normalizedRawStage ?? "")) return "FINAL";

  if (registrationScope !== "champion_8") return rawStage;

  if (/^QF[1-4]$/i.test(normalizedRawStage ?? "")) return "ベスト8";
  if (/^SF[1-2]$/i.test(normalizedRawStage ?? "")) return "ベスト4";

  const normalizedBracketStage = bracketStage?.trim().toLowerCase();
  if (normalizedBracketStage === "quarterfinal" && bracketSlot != null && bracketSlot >= 1 && bracketSlot <= 4) {
    return "ベスト8";
  }
  if (normalizedBracketStage === "semifinal" && bracketSlot != null && bracketSlot >= 1 && bracketSlot <= 2) {
    return "ベスト4";
  }
  if (normalizedBracketStage === "final" && bracketSlot === 1) return "FINAL";

  return rawStage;
}
