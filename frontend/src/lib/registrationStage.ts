/** Analytics/display stage; never use this value to rewrite persisted registrations. */
export function registrationStage(stored: string, format?: string): string | null {
  if (stored === "final") return "final";
  if (format === "champion_8") return stored === "initial" ? "championship" : null;
  if (format === "full_64") return stored === "initial" ? "league" : stored === "best8" ? "championship" : null;
  return null;
}
