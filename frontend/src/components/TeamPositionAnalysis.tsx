"use client";

import { ChevronDown } from "lucide-react";
import { localizedTournamentResult, tournamentResultClass, tournamentResultLabel } from "@/lib/tournamentResult";
import { useI18n } from "@/i18n/I18nProvider";

type Props = {
  positionStats: any[];
  open: boolean;
  onToggle: () => void;
};

export default function TeamPositionAnalysis({ positionStats, open, onToggle }: Props) {
  const { t } = useI18n();
  if (!Array.isArray(positionStats) || positionStats.length === 0) return null;
  return (
    <section className="space-y-3">
      <button type="button" onClick={onToggle} className="flex w-full items-center justify-between rounded-lg p-2 font-bold text-white transition-colors hover:bg-white/5">
        <span className="flex items-center gap-2"><span aria-hidden="true">📊</span>{t('team.positionTitle')}</span>
        <ChevronDown className={`h-5 w-5 text-slate-400 transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && (
        <div className="overflow-hidden rounded-xl bg-slate-800/50 ring-1 ring-white/10">
          <div className="hidden grid-cols-4 border-b border-white/10 bg-slate-900/50 text-center text-sm font-bold text-slate-400 sm:grid">
            <div className="p-3">{t('team.position')}</div><div className="p-3">{t('stats.usageCount')}</div><div className="p-3">{t('stats.winRate')}</div><div className="p-3">{t('stats.finalResult')}</div>
          </div>
          <div className="divide-y divide-white/5">
            {[1, 2, 3, 4, 5].map((position) => {
              const stat = positionStats.find((item: any) => item.position === position) ?? { count: 0, pct: 0, wins: 0, total: 0, win_rate: null, best_result: null };
              const result = tournamentResultLabel(stat.best_result);
              return (
                <div key={position} className="grid grid-cols-2 gap-3 p-3 text-center sm:grid-cols-4 sm:items-center">
                  <div className="text-lg font-black text-white">{t('team.positionValue', { position })}</div>
                  <div><strong className="text-lg text-white">{stat.count}</strong><span className="ml-0.5 text-xs text-slate-500">{t('team.people')}</span><div className="text-xs text-slate-400">({stat.pct}%)</div></div>
                  <div>{stat.win_rate !== null ? <><strong className={`text-lg ${stat.win_rate >= 50 ? "text-emerald-400" : "text-amber-400"}`}>{stat.win_rate}%</strong><div className="text-[10px] text-slate-500">{stat.wins}W {stat.total - stat.wins}L</div></> : <span className="text-xs text-slate-600">{t('stats.noMatches')}</span>}</div>
                  <div>{result ? <span className={`inline-block rounded-full px-3 py-1 text-xs font-bold ring-1 ${tournamentResultClass(result)}`}>{localizedTournamentResult(stat.best_result, t)}</span> : <span className="text-xs text-slate-500">{t('common.noData')}</span>}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
