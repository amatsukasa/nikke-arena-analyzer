"use client";

import TeamDisplay from "./TeamDisplay";

interface ViewerCharacter {
  id: number;
  name: string;
  is_template_available?: boolean;
  template_filename?: string;
  icon_url?: string;
  image_url?: string;
}

interface ViewerTeam {
  team_number: number;
  characters: Array<{ id: number | null; collection_level: string | null }>;
}

interface Props {
  playerName: string;
  playerDetail?: string;
  playerIconUrl?: string | null;
  teams: ViewerTeam[];
  characters: ViewerCharacter[];
  canEdit?: boolean;
  onEditTeams?: () => void;
  onEditPlayer?: () => void;
  notice?: string;
}

export default function DeckRegistrationViewer({
  playerName,
  playerDetail,
  playerIconUrl,
  teams,
  characters,
  canEdit = false,
  onEditTeams,
  onEditPlayer,
  notice,
}: Props) {
  const displayCharacters = characters.map(character => ({
    ...character,
    is_template_available: Boolean(
      character.is_template_available || character.image_url || character.icon_url || character.template_filename,
    ),
  }));

  return (
    <div className="space-y-5" data-registration-mode="view">
      <section className="rounded-xl bg-white/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <b className="text-lg text-white">{playerName}</b>
            {playerDetail && <p className="text-sm text-slate-400">{playerDetail}</p>}
            {notice && <p className="mt-1 text-xs font-bold text-amber-300">{notice}</p>}
          </div>
          {playerIconUrl && (
            <img
              src={playerIconUrl}
              alt={`${playerName}のPlayer画像`}
              className="h-16 w-16 rounded-full object-cover ring-2 ring-blue-500/50"
            />
          )}
        </div>
      </section>

      <section className="rounded-xl border border-white/10 bg-slate-950/50 p-4">
        <h3 className="mb-4 text-sm font-bold text-slate-300">登録済み編成</h3>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(teamNumber => {
            const team = teams.find(item => item.team_number === teamNumber);
            return (
              <div key={teamNumber} className="flex min-w-0 items-center gap-3 rounded-lg bg-slate-800/50 px-3 py-2 ring-1 ring-white/5">
                <span className="w-14 shrink-0 text-xs font-black text-slate-500">TEAM {teamNumber}</span>
                {team ? (
                  <div className="min-w-0 overflow-x-auto py-1">
                    <TeamDisplay
                      charIds={team.characters.map(character => character.id ?? 9999)}
                      allCharacters={displayCharacters}
                      collectionLevels={team.characters.map(character => character.collection_level)}
                    />
                  </div>
                ) : (
                  <span className="text-xs text-slate-600">未登録</span>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {canEdit && (onEditPlayer || onEditTeams) && (
        <div className={`grid gap-3 ${onEditPlayer && onEditTeams ? "sm:grid-cols-2" : ""}`}>
          {onEditPlayer && (
            <button onClick={onEditPlayer} className="rounded-xl bg-slate-800 py-3 font-bold text-slate-200">
              Player情報・画像を編集
            </button>
          )}
          {onEditTeams && (
            <button onClick={onEditTeams} className="rounded-xl bg-blue-600 py-3 font-bold text-white">
              編成を修正
            </button>
          )}
        </div>
      )}
    </div>
  );
}
