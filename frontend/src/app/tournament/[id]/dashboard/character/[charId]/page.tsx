"use client";
export const dynamic = 'force-dynamic';
import { useState, useEffect } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import CharacterDetailView from "../../../../../../components/CharacterDetailView";

export default function SingleTournamentCharacterDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tournamentId = Number(params.id);
  const charId = Number(params.charId);
  const tournamentsParam = searchParams?.get("tournaments");

  useEffect(() => {
    if (tournamentsParam) {
      router.replace(`/character/${charId}?tournaments=${tournamentsParam}`);
    }
  }, [tournamentsParam, charId, router]);

  const [tournament, setTournament] = useState<any>(null);
  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (tournamentsParam) return;
    if (!tournamentId || !charId || isNaN(tournamentId) || isNaN(charId)) {
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      try {
        const [tRes, cRes, sRes] = await Promise.all([
          fetch(`/api/tournaments/${tournamentId}`),
          fetch("/api/characters"),
          fetch(`/api/tournaments/${tournamentId}/dashboard/character/${charId}`)
        ]);

        if (tRes.ok) {
          const tData = await tRes.json();
          setTournament(tData);
        }
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

  return (
    <CharacterDetailView
      mode="single"
      characterId={charId}
      tournamentId={tournamentId}
      stats={stats}
      allCharacters={allCharacters}
      title={`${tournament?.name || `大会 ${tournamentId}`} — キャラクター詳細`}
    />
  );
}
