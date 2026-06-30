"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { Search, ChevronDown, Check, X } from 'lucide-react';
import * as Popover from '@radix-ui/react-popover';
import * as Dialog from '@radix-ui/react-dialog';
import { Command } from 'cmdk';

interface Character {
  id: number;
  name: string;
  rarity: string;
  usage_count?: number;
  image_url?: string;
}

interface CharacterSearchSelectProps {
  value: number | null;
  onChange: (id: number | null) => void;
  characters: Character[];
  className?: string;
  id?: string;
  error?: boolean;
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = () => setMatches(media.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [query]);
  return matches;
}

const RECENT_CHARS_KEY = 'nikke_recent_chars';

export default function CharacterSearchSelect({
  value,
  onChange,
  characters,
  className = "",
  id,
  error = false,
}: CharacterSearchSelectProps) {
  const [open, setOpen] = useState(false);
  // Default to true for desktop first, will adjust on mount
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const [recentCharIds, setRecentCharIds] = useState<number[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_CHARS_KEY);
      if (stored) {
        setRecentCharIds(JSON.parse(stored));
      }
    } catch (e) {}
  }, []);

  const handleSelect = (charId: number | null) => {
    onChange(charId);
    setOpen(false);
    
    if (charId !== null && charId !== 9999) {
      setRecentCharIds(prev => {
        const newRecent = [charId, ...prev.filter(id => id !== charId)].slice(0, 5);
        try {
          localStorage.setItem(RECENT_CHARS_KEY, JSON.stringify(newRecent));
        } catch (e) {}
        return newRecent;
      });
    }
  };

  const selectedChar = characters.find(c => c.id === value);

  // Group characters
  const { recentChars, popularChars, otherChars } = useMemo(() => {
    const recent = recentCharIds.map(charId => characters.find(c => c.id === charId)).filter(Boolean) as Character[];
    
    const popular = characters
      .filter(c => (c.usage_count || 0) > 0 && c.id !== 9999 && !recentCharIds.includes(c.id))
      .sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))
      .slice(0, 10);
      
    const recentAndPopularIds = new Set([...recent.map(c => c.id), ...popular.map(c => c.id), 9999]);
    const other = characters.filter(c => !recentAndPopularIds.has(c.id));
    
    return { recentChars: recent, popularChars: popular, otherChars: other };
  }, [characters, recentCharIds]);

  const buttonStyle = error 
    ? 'bg-red-950/80 text-red-400 border-2 border-red-500 font-bold shadow-[0_0_10px_rgba(239,68,68,0.5)]'
    : 'bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700/80';

  const TriggerButton = React.forwardRef<HTMLButtonElement, any>((props, ref) => (
    <button
      ref={ref}
      type="button"
      id={id}
      className={`relative w-full flex items-center justify-between text-left cursor-pointer sm:text-sm h-11 sm:h-10 px-3 rounded-lg sm:rounded-md transition-colors ${buttonStyle} ${className}`}
      {...props}
    >
      <span className="block truncate pr-2">
        {selectedChar ? (
          selectedChar.id === 9999 ? '空枠' : `[${selectedChar.rarity}] ${selectedChar.name}`
        ) : (
          "(不明)"
        )}
      </span>
      <ChevronDown className="h-4 w-4 opacity-50 shrink-0" />
    </button>
  ));
  TriggerButton.displayName = "TriggerButton";

  const CommandListContent = ({ isMobile = false }: { isMobile?: boolean }) => (
    <Command className="flex h-full w-full flex-col overflow-hidden bg-slate-900 sm:bg-slate-800 text-slate-100 font-sans">
      <div className="flex flex-col border-b border-slate-700/50">
        {isMobile && (
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h2 className="text-sm font-bold text-slate-200">キャラクターを選択</h2>
            <button 
              onClick={() => setOpen(false)}
              className="p-2 -mr-2 text-slate-400 hover:text-white rounded-full bg-slate-800/50 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}
        <div className="flex items-center px-3 py-2 sm:py-1">
          <Search className="mr-2 h-5 w-5 sm:h-4 sm:w-4 shrink-0 text-slate-400" />
          <Command.Input
            className="flex h-10 w-full rounded-md bg-transparent py-3 text-base sm:text-sm outline-none placeholder:text-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="キャラ名で検索..."
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus={!isMobile} // Disable autofocus on mobile to prevent immediate keyboard pop
          />
        </div>
      </div>
      <Command.List className="flex-1 overflow-y-auto overflow-x-hidden p-1 sm:p-1 custom-scrollbar">
        <Command.Empty className="py-6 text-center text-sm text-slate-400">見つかりませんでした。</Command.Empty>
        
        <Command.Item
          key="unknown"
          value="不明 unknown null"
          onSelect={() => handleSelect(null)}
          className="relative flex cursor-pointer select-none items-center rounded-md sm:rounded-sm px-3 py-3 sm:py-2 text-base sm:text-sm outline-none aria-selected:bg-slate-700/80 aria-selected:text-white data-[selected=true]:bg-slate-700/80 data-[selected=true]:text-white data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 mb-1 min-h-[48px] sm:min-h-0"
        >
          <span className="flex-1">(不明)</span>
          {value === null && <Check className="h-5 w-5 sm:h-4 sm:w-4 text-indigo-400" />}
        </Command.Item>
        
        <Command.Item
          key="9999"
          value="空枠 empty 9999"
          onSelect={() => handleSelect(9999)}
          className="relative flex cursor-pointer select-none items-center rounded-md sm:rounded-sm px-3 py-3 sm:py-2 text-base sm:text-sm outline-none aria-selected:bg-slate-700/80 aria-selected:text-white data-[selected=true]:bg-slate-700/80 data-[selected=true]:text-white data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 mb-2 min-h-[48px] sm:min-h-0"
        >
          <span className="flex-1">空枠</span>
          {value === 9999 && <Check className="h-5 w-5 sm:h-4 sm:w-4 text-indigo-400" />}
        </Command.Item>

        {recentChars.length > 0 && (
          <Command.Group heading="最近使用したキャラ" className="text-slate-400 text-sm sm:text-xs mt-2 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 sm:[&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:font-semibold">
            {recentChars.map(c => (
              <CommandItem key={c.id} char={c} selected={value === c.id} onSelect={() => handleSelect(c.id)} />
            ))}
          </Command.Group>
        )}

        {popularChars.length > 0 && (
          <Command.Group heading="よく使われるキャラ" className="text-slate-400 text-sm sm:text-xs mt-2 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 sm:[&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:font-semibold">
            {popularChars.map(c => (
              <CommandItem key={c.id} char={c} selected={value === c.id} onSelect={() => handleSelect(c.id)} showUsage />
            ))}
          </Command.Group>
        )}

        <Command.Group heading="すべてのキャラ" className="text-slate-400 text-sm sm:text-xs mt-2 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 sm:[&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:font-semibold">
          {otherChars.map(c => (
            <CommandItem key={c.id} char={c} selected={value === c.id} onSelect={() => handleSelect(c.id)} />
          ))}
        </Command.Group>
      </Command.List>
    </Command>
  );

  if (isDesktop) {
    return (
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <TriggerButton />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            className="z-50 w-[var(--radix-popover-trigger-width)] min-w-[280px] h-[350px] rounded-md border border-slate-700 bg-slate-800 text-slate-100 shadow-xl outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2"
            align="start"
            sideOffset={4}
          >
            <CommandListContent />
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    );
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <TriggerButton />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-0 right-0 bottom-0 z-[100] h-[85dvh] max-h-[800px] w-full flex flex-col bg-slate-900 rounded-t-2xl shadow-2xl outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom duration-300">
          <CommandListContent isMobile={true} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function CommandItem({ char, selected, onSelect, showUsage = false }: { char: Character, selected: boolean, onSelect: () => void, showUsage?: boolean }) {
  const searchValue = `[${char.rarity}] ${char.name} ${char.name.toLowerCase()}`;
  
  return (
    <Command.Item
      value={searchValue}
      onSelect={onSelect}
      className="relative flex cursor-pointer select-none items-center justify-between rounded-md sm:rounded-sm px-3 py-3 sm:py-2 text-base sm:text-sm outline-none aria-selected:bg-slate-700/80 aria-selected:text-white data-[selected=true]:bg-slate-700/80 data-[selected=true]:text-white data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 min-h-[48px] sm:min-h-[36px] transition-colors"
    >
      <div className="flex items-center flex-1 truncate pr-2">
        <span className="truncate">{`[${char.rarity}] ${char.name}`}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {showUsage && char.usage_count !== undefined && (
          <span className="text-xs text-slate-500 font-mono">({char.usage_count}回)</span>
        )}
        {selected && <Check className="h-5 w-5 sm:h-4 sm:w-4 text-indigo-400" />}
      </div>
    </Command.Item>
  );
}
