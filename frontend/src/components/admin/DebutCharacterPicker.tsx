"use client";

import { useState } from "react";
import { useCharacterCatalog } from "@/hooks/useCharacterCatalog";
import { useI18n } from "@/i18n/I18nProvider";

type Character = { id: number; name: string };

export default function DebutCharacterPicker({ selected, onChange }: { selected: number[]; onChange: (ids: number[]) => void }) {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [failed, setFailed] = useState(false);
  const { characters } = useCharacterCatalog<Character>(() => setFailed(true));
  const query = search.trim().toLocaleLowerCase();
  const shown = characters.filter(character => character.id !== 9999 && character.name.toLocaleLowerCase().includes(query));
  return (
    <fieldset className="space-y-2 rounded-lg border border-slate-700 p-3 text-sm">
      <legend className="px-1 font-semibold">{t("seasonSummary.debut")}</legend>
      <input type="search" value={search} onChange={event => setSearch(event.target.value)}
        aria-label={t("articles.searchCharacters")} placeholder={t("articles.searchCharacters")}
        className="min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3" />
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map(id => {
            const name = characters.find(character => character.id === id)?.name ?? String(id);
            return <button type="button" key={id} aria-label={t("articles.removeCharacter", { name })}
              className="rounded-lg border border-slate-700 px-3 py-2" onClick={() => onChange(selected.filter(value => value !== id))}>{name} ×</button>;
          })}
        </div>
      )}
      {failed && <p role="alert" className="text-rose-300">{t("articles.loadError")}</p>}
      <div className="grid max-h-36 gap-1 overflow-y-auto sm:grid-cols-2">
        {shown.map(character => (
          <label key={character.id} className="flex min-h-10 items-center gap-2 rounded px-1 hover:bg-white/5">
            <input type="checkbox" checked={selected.includes(character.id)}
              onChange={event => onChange(event.target.checked ? [...selected, character.id] : selected.filter(id => id !== character.id))} />
            {character.name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
