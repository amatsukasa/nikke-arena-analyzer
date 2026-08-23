export type AdoptionEntry = {
  count?: number | null;
  player_count?: number | null;
  adoption_rate?: number | null;
};

export function adoptionDisplay(entry: AdoptionEntry, totalRegisteredPlayers: number) {
  const playerCount = Number(entry.player_count ?? 0);
  const backendRate = Number(entry.adoption_rate);
  const adoptionRate = Number.isFinite(backendRate)
    ? backendRate
    : totalRegisteredPlayers > 0
      ? playerCount / totalRegisteredPlayers * 100
      : 0;

  return {
    occurrenceCount: Number(entry.count ?? 0),
    playerCount,
    adoptionRate,
    totalRegisteredPlayers,
  };
}
