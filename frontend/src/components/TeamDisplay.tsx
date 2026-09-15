"use client";

import { useEffect, useState } from "react";
import { getCharIconUrl } from "@/utils/charIcon";
import { useI18n } from "@/i18n/I18nProvider";

interface Character {
  id: number;
  name: string;
  is_template_available: boolean;
  template_filename?: string;
  icon_url?: string;
}

export default function TeamDisplay({
  charIds,
  allCharacters = [],
  collectionLevels,
  onCharacterClick,
}: {
  charIds: number[];
  allCharacters?: Character[];
  collectionLevels?: Array<string | null>;
  onCharacterClick?: (characterId: number) => void;
}) {
  const { t } = useI18n();
  const collectionLabel = (value: string | null | undefined) => {
    const labels: Record<string, string> = {
      none: t("common.none"),
      r_0_14: "R 0-14",
      r_15: "R 15",
      sr_0_14: "SR 0-14",
      sr_15: "SR 15",
      treasure_0_14: t("collection.treasure", { level: "0-14" }),
      treasure_15: t("collection.treasure", { level: "15" }),
      unknown: t("common.unavailable"),
    };
    return value ? labels[value] || t("common.unavailable") : t("common.unregistered");
  };

  const collectionBadgeUrl = (value: string | null | undefined) => {
    const badgeFiles: Record<string, string> = {
      none: "none.png",
      r_0_14: "r-0-14.png",
      r_15: "r-15.png",
      sr_0_14: "sr-0-14.png",
      sr_15: "sr-15.png",
      treasure_0_14: "treasure-0-14.png",
      treasure_15: "treasure-15.png",
      unknown: "unknown.png",
    };
    return `/collection-badges/${value ? badgeFiles[value] || "unknown.png" : "unregistered.png"}`;
  };

  const displayChars = charIds.map(cid => {
    return allCharacters.find(c => c.id === cid) || {
      id: cid,
      name: String(cid),
      is_template_available: cid !== 9999,
    };
  });
  return (
    <div className="flex space-x-1 sm:space-x-2">
      {displayChars.map((c: any, i: number) => {
        if (c.id === 9999) {
          return (
            <div key={i} className="flex flex-col items-center space-y-1 opacity-50">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-slate-800/50 ring-1 ring-white/5 overflow-hidden flex items-center justify-center">
                <div className="text-slate-600 text-xs">-</div>
              </div>
              <span className="text-[8px] sm:text-[9px] text-slate-500 w-9 sm:w-10 truncate text-center" title={t('character.emptySlot')}>{t('character.emptySlot')}</span>
            </div>
          );
        }
        return (
          <div
            key={i}
            className={`flex flex-col items-center space-y-1 group ${onCharacterClick ? "cursor-pointer" : ""}`}
            onClick={(event) => {
              if (!onCharacterClick) return;
              event.stopPropagation();
              onCharacterClick(c.id);
            }}
          >
            <div className="relative w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-slate-800 ring-1 ring-white/10 group-hover:ring-blue-500 overflow-hidden flex items-center justify-center transition-all">
              <CharacterIcon character={c} />
              {collectionLevels && (
                <img
                  src={collectionBadgeUrl(collectionLevels[i])}
                  alt={t('collection.label', { value: collectionLabel(collectionLevels[i]) })}
                  title={t('collection.label', { value: collectionLabel(collectionLevels[i]) })}
                  className="absolute left-0 top-1/2 z-10 h-4 w-4 -translate-y-1/2 drop-shadow-md"
                />
              )}
            </div>
            <span className="text-[8px] sm:text-[9px] text-slate-400 w-9 sm:w-10 truncate text-center" title={c?.name || t('common.unknown')}>{c?.name || t('common.unknown')}</span>
          </div>
        );
      })}
    </div>
  );
}

function CharacterIcon({ character }: { character: Character }) {
  const { t } = useI18n();
  const url = getCharIconUrl(character);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  if (!url || failed) {
    const fallback = character?.name || (character?.id ? `ID:${character.id}` : t('character.imageUnavailable'));
    return <span className="px-0.5 text-center text-[9px] font-bold leading-tight text-slate-400" title={fallback}>{fallback.slice(0, 6)}</span>;
  }
  return <img src={url} loading="lazy" decoding="async" alt={character?.name || `Character ${character.id}`} className="h-full w-full object-cover" onError={() => setFailed(true)} />;
}
