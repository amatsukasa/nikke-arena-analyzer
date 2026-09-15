"use client";
export const dynamic = 'force-dynamic';
import { useState, useEffect, Suspense } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import CharacterDetailView from "../../../components/CharacterDetailView";
import { useI18n } from "@/i18n/I18nProvider";

function CrossTournamentCharacterDetailContent() {
  const { t, href } = useI18n();
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const charId = Number(params.charId);

  const tournamentsParam = searchParams.get("tournaments");
  const tournamentIds = (tournamentsParam || "")
    .split(",")
    .map(s => Number(s.trim()))
    .filter(n => !isNaN(n) && n > 0);

  const [allCharacters, setAllCharacters] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!charId || isNaN(charId) || tournamentIds.length === 0) {
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      try {
        const [cRes, sRes] = await Promise.all([
          fetch("/api/characters"),
          fetch("/api/dashboard/cross-tournament/character-detail", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              character_id: charId,
              tournament_ids: tournamentIds,
            }),
          }),
        ]);

        if (cRes.ok) {
          const cData = await cRes.json();
          setAllCharacters(Array.isArray(cData) ? cData : (cData.characters || []));
        }
        if (sRes.ok) {
          const sData = await sRes.json();
          setStats(sData);
        }
      } catch (err) {
        console.error("Failed to fetch cross character detail:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [charId, tournamentsParam]);

  if (tournamentIds.length === 0) {
    return (
      <main className="p-6 md:p-12 max-w-4xl mx-auto text-center space-y-6 py-24">
        <p className="text-slate-400 text-lg font-bold">{t('character.noTournamentSelected')}</p>
        <p className="text-slate-500 text-sm">{t('character.invalidTournamentSelection')}</p>
        <div>
          <button
            type="button"
            onClick={() => router.push(href("/"))}
            className="inline-flex items-center space-x-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-colors shadow-lg cursor-pointer"
          >
            <ChevronLeft size={18} />
            <span>{t('character.backHome')}</span>
          </button>
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <CharacterDetailView
      mode="cross"
      characterId={charId}
      tournamentIds={tournamentIds}
      stats={stats}
      allCharacters={allCharacters}
      title={t('character.crossDetailTitle')}
    />
  );
}

export default function CrossTournamentCharacterDetailPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    }>
      <CrossTournamentCharacterDetailContent />
    </Suspense>
  );
}
