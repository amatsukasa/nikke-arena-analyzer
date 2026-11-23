"use client";
import { useEffect, useMemo, useState } from "react";
import {
  calculateChampionArenaStats,
  CHAMPION_ARENA_STORAGE_KEY,
  emptyUserData,
  LEGACY_ARENA_STORAGE_KEY,
  loadUserData,
  resolveArenaEntries,
  saveArenaResult,
  type ArenaResult,
  type ArenaResultEntry,
  type ArenaTournament,
  type UserDataV1,
} from "../../../lib/championArenaResults";
import { useI18n } from "@/i18n/I18nProvider";

const choices: ArenaResult[] = ["not_entered", "not_participated", "unknown", "league_loss", "best64", "best32", "best16", "best8", "best4", "runner_up", "champion"];
const resultKeys: Record<ArenaResult, string> = {
  not_entered: "championArena.result.notEntered",
  not_participated: "championArena.result.notParticipated",
  unknown: "championArena.result.unknown",
  league_loss: "championArena.result.leagueLoss",
  best64: "championArena.result.best64",
  best32: "championArena.result.best32",
  best16: "championArena.result.best16",
  best8: "championArena.result.best8",
  best4: "championArena.result.best4",
  runner_up: "championArena.result.runnerUp",
  champion: "championArena.result.champion",
};

export default function ChampionArenaResultsPage() {
  const { t } = useI18n();
  const [tournaments,setTournaments]=useState<ArenaTournament[]>([]);
  const [data,setData]=useState<UserDataV1|null>(null);
  const [oldData, setOldData] = useState(emptyUserData);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [loading,setLoading]=useState(true);
  useEffect(() => {
    const refresh = () => {
      setData(loadUserData(window.localStorage));
      setOldData(loadUserData(window.localStorage, LEGACY_ARENA_STORAGE_KEY));
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === CHAMPION_ARENA_STORAGE_KEY || event.key === LEGACY_ARENA_STORAGE_KEY || event.key === null) refresh();
    };
    refresh();
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/champion-arena/tournaments", { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error();
        const events = await response.json();
        if (!Array.isArray(events)) throw new Error();
        setTournaments(events);
      })
      .catch(() => { if (!controller.signal.aborted) setLoadError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  const entries = useMemo(() => resolveArenaEntries(tournaments, data ?? emptyUserData(), oldData), [tournaments, data, oldData]);
  const stats = calculateChampionArenaStats(entries);
  function update(entry: ArenaResultEntry, result: ArenaResult) {
    try {
      setData(saveArenaResult(window.localStorage, entry, result));
      setSaveError(false);
    } catch {
      setSaveError(true);
    }
  }
  return <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100"><div className="mx-auto max-w-4xl space-y-6">
    <header><h1 className="text-3xl font-black">{t("championArena.title")}</h1><p className="mt-2 text-sm text-slate-400">{t("championArena.description")}</p></header>
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <Stat label={t("championArena.appearanceCount")} value={t("championArena.appearanceCountValue",{count:stats.appearanceCount})}/><Stat label={t("championArena.bestResult")} value={stats.bestResult?t(resultKeys[stats.bestResult]):"－"}/>
      <Stat label={t("championArena.latestResult")} value={stats.latest?t("championArena.latestResultValue",{tournament:stats.latest.tournament.title,result:t(resultKeys[stats.latest.result])}):"－"}/>
      <Stat label={t("championArena.knownResults")} value={t("championArena.knownResultsValue",{known:stats.knownCount,total:stats.appearanceCount})}/><Stat label={t("championArena.unknownCount")} value={String(stats.unknownCount)}/>
    </section>
    {(loadError || saveError) && <p role="alert" className="rounded border border-red-700 p-3 text-red-300">{t(loadError ? "championArena.loadError" : "championArena.saveError")}</p>}
    {loading&&<p className="text-slate-400">{t("common.loading")}</p>}
    {!loading&&!loadError&&tournaments.length===0&&<p className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-slate-400">{t("championArena.noTournaments")}</p>}
    <section className="space-y-3">{entries.map(entry => {
      const { tournament, result, conflicts } = entry;
      const descriptionId = conflicts.length ? `result-conflict-${tournament.id}` : undefined;
      return <label key={tournament.id} className="block rounded-xl border border-slate-800 bg-slate-900 p-4">
        <span className="mb-2 block font-bold">{tournament.title}</span>
        {tournament.source === "legacy_tournament" && <span className="mb-2 block text-xs text-amber-300">{t("championArena.legacyMaster", { id: tournament.tournament_id ?? "—" })}</span>}
        {descriptionId && <span id={descriptionId} className="mb-2 block text-xs text-amber-300">
          {t("championArena.conflict", { results: conflicts.map(value => t(resultKeys[value])).join(" / ") })}
        </span>}
        <select
          aria-label={t("championArena.resultAria", { tournament: tournament.title })}
          aria-describedby={descriptionId}
          value={descriptionId ? "" : result}
          disabled={!data}
          onChange={event => update(entry, event.target.value as ArenaResult)}
          className="w-full rounded border border-slate-700 bg-slate-950 p-3"
        >
          {descriptionId && <option value="" disabled>{t("championArena.chooseConflict")}</option>}
          {choices.map(value => <option key={value} value={value}>{t(resultKeys[value])}</option>)}
        </select>
      </label>;
    })}</section>
  </div></main>;
}
function Stat({label,value}:{label:string;value:string}){return <div className="rounded-xl border border-slate-800 bg-slate-900 p-4"><div className="text-xs text-slate-400">{label}</div><div className="mt-1 font-bold">{value}</div></div>}
