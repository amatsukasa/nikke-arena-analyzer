"use client";
export const dynamic = 'force-dynamic';
import { useState, useEffect } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import CharacterDetailView from "../../../../../../components/CharacterDetailView";
import { useI18n } from "@/i18n/I18nProvider";

export default function SingleTournamentCharacterDetailPage() {
  const { t, href } = useI18n();
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tournamentId = Number(params.id);
  const charId = Number(params.charId);
  const tournamentsParam = searchParams?.get("tournaments");

  useEffect(() => {
    if (tournamentsParam) {
      router.replace(href(`/character/${charId}?tournaments=${tournamentsParam}`));
    }
  }, [tournamentsParam, charId, router]);

  const [tournament, setTournament] = useState<any>(null);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (tournamentsParam) return;
    if (!tournamentId || !charId || isNaN(tournamentId) || isNaN(charId)) {
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      setTournament(null);
      setStats(null);
      setError("");
      try {
        // Do not request individual dashboard data until the backend has
        // confirmed owner/admin access to this tournament.
        const tRes = await fetch(`/api/tournaments/${tournamentId}`);
        if (!tRes.ok) {
          setError(t('tournament.unavailable'));
          return;
        }
        const [cRes, sRes] = await Promise.all([
          fetch("/api/characters"),
          fetch(`/api/tournaments/${tournamentId}/dashboard/character/${charId}`)
        ]);

        const tData = await tRes.json();
        setTournament(tData);
        if (cRes.ok) {
          const cData = await cRes.json();
          setAllCharacters(Array.isArray(cData) ? cData : (cData.characters || []));
        }
        if (sRes.ok) {
          const sData = await sRes.json();
          setStats(sData);
        }
      } catch (err) {
        console.error("Failed to fetch character detail:", err);
        setError(t('tournament.unavailable'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [tournamentId, charId]);

  if (loading || tournamentsParam) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !tournament) {
    return <main className="mx-auto max-w-3xl p-6"><div role="alert" className="rounded-xl border border-red-800 bg-red-950/40 p-4 text-red-300">{error || t('tournament.unavailable')}</div></main>;
  }

  return (
    <CharacterDetailView
      mode="single"
      characterId={charId}
      tournamentId={tournamentId}
      stats={stats}
      allCharacters={allCharacters}
      title={t('character.singleDetailTitle', { tournament: tournament?.name || t('filter.tournamentFallback', { id: tournamentId }) })}
    />
  );
}
