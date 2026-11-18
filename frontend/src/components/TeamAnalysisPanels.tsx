"use client";

import { useState } from "react";
import { Trophy } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { ArenaCharacterDisplayMode } from "@/lib/synergyCharacters";
import PaginatedTeamList from "./PaginatedTeamList";
import SynergyCharacterPicker, { ArenaCharacterDisplaySelect, SynergyPickerInstructions } from "./SynergyCharacterPicker";
import { TeamResultFilters, TeamSearchFilters, WIN_RATE_FILTER_CLASS } from "./TeamStatisticsMeaning";

type Scope = {
  tournamentId?: number;
  tournamentIds: number[];
  playServer?: string;
  championshipId?: number;
};

type PanelProps = {
  scope: Scope;
  formal: boolean;
  allCharacters: any[];
  selectedTeam: string;
  onTeamClick: (id: string, team?: any) => void;
};

export function useTeamWinRateFilters(defaultMinMatches: number) {
  const [teamMinMatches, setTeamMinMatches] = useState(defaultMinMatches);
  const [winRateStage, setWinRateStage] = useState("all");
  const [teamCompositionBestResult, setTeamCompositionBestResult] = useState("");
  const [teamMinWinRate, setTeamMinWinRate] = useState(0);
  return { teamMinMatches, setTeamMinMatches, winRateStage, setWinRateStage,
    teamCompositionBestResult, setTeamCompositionBestResult, teamMinWinRate, setTeamMinWinRate };
}

export function useTeamSearchFilters() {
  const [filterRarity, setFilterRarity] = useState("");
  const [filterManufacturer, setFilterManufacturer] = useState("");
  const [filterBurst, setFilterBurst] = useState("");
  const [filterElement, setFilterElement] = useState("");
  const [filterWeapon, setFilterWeapon] = useState("");
  const [arenaCharacterDisplay, setArenaCharacterDisplay] = useState<ArenaCharacterDisplayMode>("only");
  const [searchStage, setSearchStage] = useState("all");
  const [searchSort, setSearchSort] = useState<"count" | "win_rate" | "composition_best_result">("count");
  const [searchComposition, setSearchComposition] = useState("");
  const [searchWinRate, setSearchWinRate] = useState(0);
  return { filterRarity, setFilterRarity, filterManufacturer, setFilterManufacturer, filterBurst, setFilterBurst,
    filterElement, setFilterElement, filterWeapon, setFilterWeapon, arenaCharacterDisplay, setArenaCharacterDisplay,
    searchStage, setSearchStage, searchSort, setSearchSort, searchComposition, setSearchComposition, searchWinRate, setSearchWinRate };
}

export function TeamWinRatePanel({ scope, formal, allCharacters, selectedTeam, onTeamClick, filters }:
  PanelProps & { filters: ReturnType<typeof useTeamWinRateFilters> }) {
  const { t } = useI18n();
  const { teamMinMatches, setTeamMinMatches, winRateStage, setWinRateStage,
    teamCompositionBestResult, setTeamCompositionBestResult, teamMinWinRate, setTeamMinWinRate } = filters;
  return (
   <div className="space-y-12 animate-in fade-in zoom-in-95 duration-300">
    <section>
      <div className="mb-6 flex flex-col gap-4">
        <h2 className="text-xl font-bold text-white flex items-center space-x-2">
          <Trophy className="text-emerald-400" />
          <span>{t('stats.teamWinRateRanking')}</span>
        </h2>

        {/* 編成フィルタコントロール群 */}
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={teamMinMatches}
            onChange={(e) => setTeamMinMatches(Number(e.target.value))}
            className={WIN_RATE_FILTER_CLASS}
          >
            {[0, 1, 10, 30, 50].map((count) => <option key={count} value={count}>{t('filter.matchesAtLeast', { count })}</option>)}
          </select>

          <select
            value={teamMinWinRate}
            onChange={(e) => setTeamMinWinRate(Number(e.target.value))}
            className={WIN_RATE_FILTER_CLASS}
          >
            <option value={0}>{t('filter.winRateAny')}</option>
            {[50, 60, 70, 80].map((rate) => <option key={rate} value={rate}>{t('filter.winRateAtLeast', { rate })}</option>)}
          </select>

          <TeamResultFilters composition={teamCompositionBestResult} onCompositionChange={setTeamCompositionBestResult} stage={winRateStage} onStageChange={setWinRateStage} formal={formal}/>
        </div>
      </div>

      <div className="space-y-3">
        <PaginatedTeamList registrationPhase={formal ? winRateStage : "all"}
          {...scope}
          mode={scope.tournamentId === undefined ? "cross" : "single"}
          allCharacters={allCharacters}
          onTeamClick={onTeamClick}
          selectedTeam={selectedTeam}
          sortBy="win_rate"
          minMatches={teamMinMatches}

          minWinRate={teamMinWinRate}
          compositionBestResult={teamCompositionBestResult}
        />
      </div>
    </section>
  </div>
  );
}

export function TeamSearchPanel({ scope, formal, allCharacters, selectedTeam, onTeamClick, filters,
  analysisKey, searchCandidates, includedCharacterIds, excludedCharacterIds, onSelectionChange }:
  PanelProps & {
    filters: ReturnType<typeof useTeamSearchFilters>;
    analysisKey: string | null;
    searchCandidates: { usage: { id: number; count: number }[]; state: "loading" | "ready" | "error" };
    includedCharacterIds: number[];
    excludedCharacterIds: number[];
    onSelectionChange: (included: number[], excluded: number[]) => void;
  }) {
  const { t } = useI18n();
  const { filterRarity, setFilterRarity, filterManufacturer, setFilterManufacturer, filterBurst, setFilterBurst,
    filterElement, setFilterElement, filterWeapon, setFilterWeapon, arenaCharacterDisplay, setArenaCharacterDisplay,
    searchStage, setSearchStage, searchSort, setSearchSort, searchComposition, setSearchComposition, searchWinRate, setSearchWinRate } = filters;
  const filteredCharacters = allCharacters.filter(c => {
    if (c.id === 9999) return false;
    if (filterRarity && c.rarity !== filterRarity) return false;
    if (filterManufacturer && c.manufacturer !== filterManufacturer) return false;
    if (filterElement && c.element !== filterElement) return false;
    if (filterWeapon && c.weapon !== filterWeapon) return false;
    if (filterBurst) {
      if (filterBurst === "1" && c.burst_phase !== "1" && c.burst_phase !== "A") return false;
      if (filterBurst === "2" && c.burst_phase !== "2" && c.burst_phase !== "A") return false;
      if (filterBurst === "3" && c.burst_phase !== "3" && c.burst_phase !== "A") return false;
    }
    return true;
  });

  return (
  <div className="space-y-8 animate-in fade-in zoom-in-95 duration-300">
    <div className="bg-emerald-500/10 p-6 rounded-2xl ring-1 ring-emerald-500/20">
      <SynergyPickerInstructions />

      <ArenaCharacterDisplaySelect
        value={arenaCharacterDisplay}
        onChange={setArenaCharacterDisplay}
      />

      {/* フィルターUI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterRarity} onChange={e => setFilterRarity(e.target.value)}>
          <option value="">{t('filter.rarity')} ({t('common.all')})</option>
          <option value="SSR">SSR</option>
          <option value="SR">SR</option>
          <option value="R">R</option>
        </select>
        <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterManufacturer} onChange={e => setFilterManufacturer(e.target.value)}>
          <option value="">{t('filter.manufacturer')} ({t('common.all')})</option>
          <option value="エリシオン">{t('manufacturer.elysion')}</option>
          <option value="ミシリス">{t('manufacturer.missilis')}</option>
          <option value="テトラ">{t('manufacturer.tetra')}</option>
          <option value="ピルグリム">{t('manufacturer.pilgrim')}</option>
          <option value="アブノーマル">{t('manufacturer.abnormal')}</option>
        </select>
        <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterBurst} onChange={e => setFilterBurst(e.target.value)}>
          <option value="">{t('filter.burst')} ({t('common.all')})</option>
          {[1, 2, 3].map((value) => <option key={value} value={value}>{t('filter.includesAlternate', { value })}</option>)}
        </select>
        <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterElement} onChange={e => setFilterElement(e.target.value)}>
          <option value="">{t('filter.element')} ({t('common.all')})</option>
          <option value="灼熱">{t('element.fire')}</option>
          <option value="水冷">{t('element.water')}</option>
          <option value="風圧">{t('element.wind')}</option>
          <option value="鉄甲">{t('element.iron')}</option>
          <option value="電撃">{t('element.electric')}</option>
        </select>
        <select className="bg-slate-900 border border-emerald-500/30 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" value={filterWeapon} onChange={e => setFilterWeapon(e.target.value)}>
          <option value="">{t('filter.weapon')} ({t('common.all')})</option>
          <option value="AR">{t('weapon.ar')}</option>
          <option value="SG">{t('weapon.sg')}</option>
          <option value="SMG">{t('weapon.smg')}</option>
          <option value="MG">{t('weapon.mg')}</option>
          <option value="SR">{t('weapon.sr')}</option>
          <option value="RL">{t('weapon.rl')}</option>
        </select>
      </div>

      <SynergyCharacterPicker
        key={`synergy-picker-${analysisKey}`}
        characters={filteredCharacters}
        characterUsage={searchCandidates.usage}
        usageState={!analysisKey || allCharacters.length === 0 ? "loading" : searchCandidates.state}
        includedIds={includedCharacterIds}
        excludedIds={excludedCharacterIds}
        displayMode={arenaCharacterDisplay}
        onChange={({ includedIds, excludedIds }) => onSelectionChange(includedIds, excludedIds)}
      />
      <div className="mt-4 flex items-center justify-between border-t border-emerald-500/20 pt-4">
        <span className="text-sm text-slate-400">{t('search.target')}: {includedCharacterIds.length}/5　{t('search.exclude')}: {excludedCharacterIds.length}</span>
        {(includedCharacterIds.length > 0 || excludedCharacterIds.length > 0) && (
          <button onClick={() => onSelectionChange([], [])} className="text-sm text-emerald-400 hover:text-emerald-300 font-bold">
            {t('common.clear')}
          </button>
        )}
      </div>
    </div>

    <div className="space-y-4">
      <h3 className="font-bold text-white mb-4">{t('search.results')}</h3>
      <TeamSearchFilters sort={searchSort} onSortChange={setSearchSort} stage={searchStage} onStageChange={setSearchStage} composition={searchComposition} onCompositionChange={setSearchComposition} winRate={searchWinRate} onWinRateChange={setSearchWinRate} formal={formal}/>
      {includedCharacterIds.length === 0 ? (
        <p className="text-slate-500 text-center py-12">{t('search.selectOne')}</p>
      ) : (
        <div className="space-y-3">
          <PaginatedTeamList registrationPhase={formal ? searchStage : "all"}
            key={`synergy-${analysisKey}-${includedCharacterIds.join(",")}-${excludedCharacterIds.join(",")}`}
            {...scope}
          mode={scope.tournamentId === undefined ? "cross" : "single"}
            allCharacters={allCharacters}
            characterIds={includedCharacterIds}
            excludedCharacterIds={excludedCharacterIds}
            onTeamClick={canonicalId => onTeamClick(canonicalId)}
            selectedTeam={selectedTeam}
            sortBy={searchSort}
            compositionBestResult={searchComposition}
            minWinRate={searchWinRate}
          />
        </div>
      )}
    </div>
  </div>
  );
}
