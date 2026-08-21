import RegistrationScopeBadge from "./RegistrationScopeBadge";

interface Props {
  tournamentId: number;
  publicationStatus: "draft" | "published";
  providerGameStartDate: string | null;
  canEdit: boolean;
  error?: string;
}

export default function ChampionTournamentRegistrationShell({
  tournamentId,
  publicationStatus,
  providerGameStartDate,
  canEdit,
  error,
}: Props) {
  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-8" data-tournament-id={tournamentId}>
      <section className="rounded-2xl bg-slate-900/80 p-5 ring-1 ring-white/10 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <RegistrationScopeBadge scope="champion_8" />
            <h1 className="mt-3 text-2xl font-black text-slate-100 md:text-3xl">チャンピオン対抗戦 登録</h1>
          </div>
          <span className="text-sm text-slate-400">{publicationStatus === "published" ? "公開中" : "下書き"}</span>
        </div>
        <p className="mt-5 text-sm leading-7 text-slate-300">
          チャンピオン対抗戦へ進出した8人の登録状況とトーナメントを、この画面で管理します。
        </p>
        <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-xl bg-white/5 p-4"><dt className="text-slate-500">データ提供者のゲーム開始日</dt><dd className="mt-1 text-slate-200">{providerGameStartDate || "未設定"}</dd></div>
          <div className="rounded-xl bg-white/5 p-4"><dt className="text-slate-500">編集権限</dt><dd className="mt-1 text-slate-200">{canEdit ? "編集可能" : "閲覧のみ"}</dd></div>
        </dl>
        {error && <div role="alert" className="mt-5 rounded-xl border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</div>}
      </section>
    </main>
  );
}
