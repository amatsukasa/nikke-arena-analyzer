"use client";

import { useEffect, useState } from "react";
import Link from "./LocalizedLink";
import PlayerIconEditor from "./PlayerIconEditor";
import { usePlayerIconCropSettings } from "../hooks/usePlayerIconCropSettings";
import DeckRegistrationEditor from "./DeckRegistrationEditor";
import DeckRegistrationViewer from "./DeckRegistrationViewer";
import { useCharacterCatalog } from "../hooks/useCharacterCatalog";
import { RegistrationTeam, normalizeAnalyzedRegistrationTeams } from "../lib/deckRegistration";
import { useI18n } from "@/i18n/I18nProvider";

type Phase = "initial" | "best8" | "final";
type Player = { id: number; name: string; seed_number: number | null; champion_slot: number | null; icon_url: string | null };
type Registration = { player_id: number; phase: Phase; eligible: boolean; qualification: string | null; revision_id: number | null; complete: boolean; teams: RegistrationTeam[] };
type Match = { key: string; remaining: number; slot: number; phase: Phase; result_phase: Phase; participants: (number | null)[]; upstream: string; registration_ids: (number | null)[]; revision_id: number | null; status: string; can_register: boolean; winner_id: number | null; rounds: number[]; teams: RegistrationTeam[][]; result_participants: number[]; result_teams: RegistrationTeam[][] };
type State = { format: "full_64" | "champion_8"; phases: Phase[]; players: Player[]; registrations: Registration[]; matches: Match[]; statistics: Record<Phase, { matches: number; registered_players: number; teams: { character_ids: number[]; adoptions: number; wins: number; played: number }[]; characters: { id: number; adoptions: number; wins: number; played: number }[] }> };
const blank = (): RegistrationTeam[] => Array.from({ length: 5 }, (_, i) => ({ team_number: i + 1, characters: Array.from({ length: 5 }, () => ({ id: null, collection_level: null })) }));

export default function ArenaPhaseRegistration({ tournamentId, canEdit = false, published = false }: { tournamentId: number; canEdit?: boolean; published?: boolean }) {
  const { t } = useI18n();
  const [cropSettings, setCropSettings] = usePlayerIconCropSettings();
  const { characters } = useCharacterCatalog<any>();
  const [history, setHistory] = useState<{ registrations: { id: number; player_id: number; phase: Phase; teams: RegistrationTeam[] }[]; results: { id: number; key: string; phase: Phase; participants: number[]; winner_id: number; rounds: number[]; teams: RegistrationTeam[][] }[] } | null>(null);
  const [data, setData] = useState<State | null>(null);
  const [phase, setPhase] = useState<Phase>("initial");
  const [playerId, setPlayerId] = useState<number | null>(null);
  const [teams, setTeams] = useState<RegistrationTeam[]>([]);
  const [editing, setEditing] = useState(false);
  const [matchKey, setMatchKey] = useState("");
  const [rounds, setRounds] = useState<(number | null)[]>(Array(5).fill(null));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "analysis" | "teams" | "player">("");
  const [iconRevision, setIconRevision] = useState(0);
  const [position, setPosition] = useState(1);
  const [name, setName] = useState("");
  const writable = canEdit && !published;
  const base = `/api/tournaments/${tournamentId}/arena-phases`;
  async function responseState(response: Response) {
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : t("arenaPhases.error"));
    setData(result); setHistory(null);
    return result as State;
  }
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError("");
    fetch(base, { cache: "no-store", signal: controller.signal }).then(responseState).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [base]);
  const entry = data?.registrations.find(r => r.player_id === playerId && r.phase === phase);
  const player = data?.players.find(p => p.id === playerId);
  const match = data?.matches.find(m => m.key === matchKey);
  const label = (pid: number | null) => data?.players.find(p => p.id === pid)?.name || t("arenaPhases.pending");
  const phaseLabel = (value: Phase) => t(`arenaPhases.${value}`);
  function discard() { return !editing || window.confirm(t("arenaPhases.discard")); }
  async function mutate(path: string, body: unknown, method = "PUT") {
    return responseState(await fetch(base + path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
  }
  async function saveTeams() {
    if (!entry || !window.confirm(t("arenaPhases.confirmSave"))) return;
    setBusy("teams"); setError("");
    try { await mutate(`/players/${entry.player_id}/${phase}`, { qualification: entry.qualification, revision_id: entry.revision_id, teams }); setEditing(false); }
    catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); }
    finally { setBusy(""); }
  }
  async function analyze(files: { file: File; preCropped: boolean }[]) {
    if (!player || !data) return;
    setBusy("analysis"); setError("");
    try {
      const form = new FormData();
      files.forEach(item => { form.append("images", item.file); form.append("image_pre_cropped", String(item.preCropped)); });
      form.append("tournament_id", String(tournamentId)); form.append("seed_number", String(player.seed_number));
      const url = data.format === "champion_8" ? `/api/tournaments/${tournamentId}/players/by-id/${player.id}/analyze-deck` : "/api/analyze/deck";
      const response = await fetch(url, { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : t("arenaPhases.error"));
      setTeams(normalizeAnalyzedRegistrationTeams(result));
    } catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); }
    finally { setBusy(""); }
  }
  async function saveMatch() {
    if (!match || !window.confirm(t("arenaPhases.confirmResult"))) return;
    setBusy("teams"); setError("");
    try { await mutate(`/matches/${match.key}`, { upstream: match.upstream, registration_ids: match.registration_ids, revision_id: match.revision_id, rounds }); setMatchKey(""); }
    catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); }
    finally { setBusy(""); }
  }
  async function createPlayer() {
    setBusy("player"); setError("");
    try { const result = await mutate("/players", { position, name }, "POST"); setPlayerId(result.players.find(p => (result.format === "champion_8" ? p.champion_slot : p.seed_number) === position)?.id || null); setName(""); }
    catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); }
    finally { setBusy(""); }
  }
  async function uploadIcon(file: File) {
    if (!player || !data) return;
    setBusy("player"); setError("");
    try {
      const form = new FormData(); form.append("image", file); form.append("tournament_id", String(tournamentId)); form.append("seed_number", String(player.seed_number));
      const url = data.format === "champion_8" ? `/api/tournaments/${tournamentId}/players/by-id/${player.id}/icon` : "/api/upload/player-icon";
      const response = await fetch(url, { method: "POST", body: form });
      if (!response.ok) throw new Error(t("arenaPhases.error"));
      await responseState(await fetch(base, { cache: "no-store" })); setIconRevision(value => value + 1);
    } catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); }
    finally { setBusy(""); }
  }
  return <main className="mx-auto max-w-7xl space-y-6 p-4 text-slate-200">
    <Link href="/" className="text-blue-300">← {t("arenaPhases.back")}</Link>
    <h1 className="text-2xl font-bold">{t("arenaPhases.title")}</h1>
    <p>{t("arenaPhases.description")}</p>
    {published && canEdit && <p>{t("arenaPhases.published")}</p>}
    {error && <p role="alert" className="rounded bg-red-950 p-4 text-red-200">{error} <button onClick={() => { if (discard()) { setEditing(false); setMatchKey(""); void fetch(base, { cache: "no-store" }).then(responseState).catch(e => setError(e.message)); } }}>{t("arenaPhases.reload")}</button></p>}
    {!data ? <p>{t("arenaPhases.loading")}</p> : <>
      <p>{data.format === "champion_8" ? t("arenaPhases.mode8") : t("arenaPhases.mode64")}</p>
      <nav className="flex flex-wrap gap-3">{data.phases.map(p => <button key={p} disabled={Boolean(busy)} aria-pressed={phase === p} className={`rounded px-4 py-3 ${phase === p ? "bg-blue-700" : "bg-slate-800"}`} onClick={() => { if (discard()) { setPhase(p); setEditing(false); setMatchKey(""); setPlayerId(null); } }}>{phaseLabel(p)}</button>)}</nav>
      <section className="rounded-xl bg-slate-900 p-4">
        <h2 className="text-xl">{t("arenaPhases.registrations")}: {phaseLabel(phase)}</h2>
        <p>{t("arenaPhases.emptyNotice")}</p>
        <div className="my-3 flex flex-wrap gap-2">{data.registrations.filter(r => r.phase === phase && r.eligible).map(r => <button key={r.player_id} disabled={Boolean(busy)} className={`rounded border p-3 ${r.player_id === playerId ? "border-blue-400" : "border-slate-700"}`} onClick={() => { if (discard()) { setPlayerId(r.player_id); setEditing(false); setMatchKey(""); } }}>{label(r.player_id)} · {r.complete ? t("arenaPhases.complete") : t("arenaPhases.incomplete")}</button>)}</div>
        {player && entry && <>
          <DeckRegistrationViewer playerName={player.name} playerDetail={phaseLabel(phase)} playerIconUrl={player.icon_url ? `${player.icon_url}${player.icon_url.includes("?") ? "&" : "?"}v=${iconRevision}` : null} teams={entry.teams} characters={characters} />
          {writable && <div className="my-3 flex flex-wrap gap-3"><button disabled={Boolean(busy)} onClick={() => { setTeams(entry.teams.length ? structuredClone(entry.teams) : blank()); setEditing(true); }} className="rounded bg-blue-700 p-3">{t("arenaPhases.edit")}</button><PlayerIconEditor key={player.id} iconUrl={player.icon_url ? `${player.icon_url}${player.icon_url.includes("?") ? "&" : "?"}v=${iconRevision}` : null} disabled={Boolean(busy)} busy={busy === "player"} onUpload={uploadIcon} cropSettings={cropSettings} onCropSettingsChange={setCropSettings} /></div>}
          {editing && writable && <DeckRegistrationEditor key={`${playerId}:${phase}`} teams={teams} characters={characters} saved={entry.complete} saveLabel={t("arenaPhases.saveVersion")} disabled={Boolean(busy)} busy={busy} dirty onTeamsChange={setTeams} onAnalyze={analyze} onSave={saveTeams} onClose={() => setEditing(false)} />}
        </>}
        {phase === "initial" && writable && <details className="mt-4"><summary>{t("arenaPhases.addPlayer")}</summary><label>{t("arenaPhases.position")}<input type="number" min={1} max={data.format === "champion_8" ? 8 : 64} value={position} onChange={e => setPosition(Number(e.target.value))} className="m-2 w-20 rounded bg-slate-800 p-2" /></label><input aria-label={t("arenaPhases.name")} value={name} onChange={e => setName(e.target.value)} placeholder={t("arenaPhases.name")} className="rounded bg-slate-800 p-2" /><button disabled={Boolean(busy) || !name.trim()} onClick={() => void createPlayer()} className="m-2 rounded bg-blue-700 p-2">{t("arenaPhases.addPlayer")}</button></details>}
      </section>
      <section className="rounded-xl bg-slate-900 p-4"><h2 className="text-xl">{t("arenaPhases.matches")}: {phaseLabel(phase)}</h2><div className="my-3 grid gap-2 sm:grid-cols-2">{data.matches.filter(m => m.phase === phase).map(m => <button key={m.key} disabled={Boolean(busy)} onClick={() => { if (discard()) { setEditing(false); setMatchKey(m.key); setRounds(m.rounds.length === 5 && m.participants.every(p => m.result_participants.includes(p as number)) ? [...m.rounds] : Array(5).fill(null)); } }} className="rounded border border-slate-700 p-3 text-left">{m.remaining === 2 ? phaseLabel("final") : `Best ${m.remaining}`} #{m.slot}: {label(m.participants[0])} / {label(m.participants[1])} · {t(`arenaPhases.${m.status}`)}{m.winner_id ? ` · ${label(m.winner_id)}` : ""}</button>)}</div>
        {match && <div className="space-y-3"><p>{label(match.participants[0])} / {label(match.participants[1])}</p>{match.result_teams.map((savedTeams, i) => <DeckRegistrationViewer key={i} playerName={label(match.result_participants[i])} playerDetail={`${t("arenaPhases.usedDecks")} · ${phaseLabel(match.result_phase)}`} teams={savedTeams} characters={characters} />)}
          {writable && match.can_register && <><p>{t("arenaPhases.newResult")}</p>{match.teams.map((currentTeams, i) => <DeckRegistrationViewer key={i} playerName={label(match.participants[i])} playerDetail={phaseLabel(match.phase)} teams={currentTeams} characters={characters} />)}<div className="flex flex-wrap gap-3">{rounds.map((winner, i) => <label key={i}>R{i + 1}<select value={winner || ""} onChange={e => setRounds(old => old.map((p, index) => index === i ? Number(e.target.value) || null : p))} className="m-2 rounded bg-slate-800 p-2"><option value="">—</option>{match.participants.map(pid => <option key={pid} value={pid || ""}>{label(pid)}</option>)}</select></label>)}</div><button disabled={Boolean(busy) || rounds.some(r => !r)} onClick={() => void saveMatch()} className="rounded bg-emerald-800 p-3">{t("arenaPhases.saveResult")}</button></>}
        </div>}
      </section>
      <section className="rounded-xl bg-slate-900 p-4"><h2 className="text-xl">{t("arenaPhases.statistics")}: {phaseLabel(phase)}</h2><p>{t("arenaPhases.statsNotice")}</p><p>{t("arenaPhases.registrations")}: {data.statistics[phase].registered_players} · {t("arenaPhases.matches")}: {data.statistics[phase].matches}</p><div className="overflow-auto"><table className="w-full text-left"><thead><tr><th>{t("arenaPhases.character")}</th><th>{t("arenaPhases.adoption")}</th><th>{t("arenaPhases.winrate")}</th></tr></thead><tbody>{data.statistics[phase].characters.sort((a, b) => b.adoptions - a.adoptions).map(c => <tr key={c.id}><td>{characters.find(ch => Number(ch.id) === c.id)?.name || c.id}</td><td>{c.adoptions} / {data.statistics[phase].registered_players} ({data.statistics[phase].registered_players ? (100 * c.adoptions / data.statistics[phase].registered_players).toFixed(1) : 0}%)</td><td>{c.wins} / {c.played} ({c.played ? (100 * c.wins / c.played).toFixed(1) : "—"}%)</td></tr>)}</tbody></table></div>
        <h3 className="mt-5 text-lg">{t("arenaPhases.teams")}</h3><div className="overflow-auto"><table className="w-full text-left"><thead><tr><th>{t("arenaPhases.teams")}</th><th>{t("arenaPhases.adoption")}</th><th>{t("arenaPhases.winrate")}</th></tr></thead><tbody>{data.statistics[phase].teams.sort((a, b) => b.adoptions - a.adoptions).map(team => <tr key={team.character_ids.join(",")}><td>{team.character_ids.map(cid => characters.find(c => Number(c.id) === cid)?.name || cid).join(" / ")}</td><td>{team.adoptions} / {data.statistics[phase].registered_players} ({data.statistics[phase].registered_players ? (100 * team.adoptions / data.statistics[phase].registered_players).toFixed(1) : 0}%)</td><td>{team.wins} / {team.played} ({team.played ? (100 * team.wins / team.played).toFixed(1) : "—"}%)</td></tr>)}</tbody></table></div>
      </section>
      <section className="rounded-xl bg-slate-900 p-4"><button onClick={async () => { try { const response = await fetch(base + "/history", { cache: "no-store" }); if (!response.ok) throw new Error(t("arenaPhases.error")); setHistory(await response.json()); } catch (e) { setError(e instanceof Error ? e.message : t("arenaPhases.error")); } }}>{t("arenaPhases.history")}</button><p>{t("arenaPhases.historyNotice")}</p>{history && <>{history.registrations.filter(r => r.phase === phase).map(r => <details key={`deck:${r.id}`}><summary>#{r.id} · {label(r.player_id)} · {phaseLabel(r.phase)}</summary><DeckRegistrationViewer playerName={label(r.player_id)} teams={r.teams} characters={characters} /></details>)}{history.results.filter(r => r.phase === phase).map(r => <details key={`result:${r.id}`}><summary>#{r.id} · {r.key} · {label(r.participants[0])} / {label(r.participants[1])} · {label(r.winner_id)}</summary><p>{r.rounds.map(label).join(" / ")}</p>{r.teams.map((saved, i) => <DeckRegistrationViewer key={i} playerName={label(r.participants[i])} teams={saved} characters={characters} />)}</details>)}</>}</section>
    </>}
  </main>;
}
