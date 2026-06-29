"use client";

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Search, ChevronDown, X } from 'lucide-react';

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

export default function CharacterSearchSelect({
  value,
  onChange,
  characters,
  className = "",
  id,
  error = false,
}: CharacterSearchSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const mobileInputRef = useRef<HTMLInputElement>(null);
  const desktopInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (isOpen) {
      // Small delay to allow element to be rendered
      setTimeout(() => {
        if (window.innerWidth < 640 && mobileInputRef.current) {
          mobileInputRef.current.focus();
        } else if (desktopInputRef.current) {
          desktopInputRef.current.focus();
        }
      }, 50);
      
      // Prevent body scroll on mobile
      if (window.innerWidth < 640) {
        document.body.style.overflow = 'hidden';
      }
    } else {
      setSearchQuery("");
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    }
  }, [isOpen]);

  const selectedChar = characters.find(c => c.id === value);

  const { popularChars, otherChars, searchResults } = useMemo(() => {
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      // Partial match on name
      const results = characters.filter(c => c.name.toLowerCase().includes(q));
      return { popularChars: [], otherChars: [], searchResults: results };
    }

    const popular = characters
      .filter(c => (c.usage_count || 0) > 0 && c.id !== 9999) // exclude empty slot if any
      .sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))
      .slice(0, 30);
    
    // Exclude popular from others
    const popularIds = new Set(popular.map(c => c.id));
    const other = characters.filter(c => !popularIds.has(c.id));

    return { popularChars: popular, otherChars: other, searchResults: [] };
  }, [characters, searchQuery]);

  const baseButtonClasses = "relative w-full flex items-center justify-between text-left cursor-default sm:text-sm";
  const buttonStyle = error 
    ? 'bg-red-950/80 text-red-400 border-2 border-red-500 font-bold shadow-[0_0_10px_rgba(239,68,68,0.5)]'
    : 'bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700/80';

  const renderList = () => (
    <>
      <button
        type="button"
        className={`w-full text-left px-3 py-3 sm:py-2 text-base sm:text-sm rounded-sm mb-1 ${value === null ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-700'}`}
        onClick={() => {
          onChange(null);
          setIsOpen(false);
        }}
      >
        (不明)
      </button>
      
      {searchQuery ? (
        searchResults.length > 0 ? (
          searchResults.map(c => (
            <CharOption key={c.id} char={c} selected={value === c.id} onClick={() => { onChange(c.id); setIsOpen(false); }} />
          ))
        ) : (
          <div className="px-3 py-6 text-sm text-slate-500 text-center">見つかりませんでした</div>
        )
      ) : (
        <>
          {popularChars.length > 0 && (
            <div className="mb-2">
              <div className="px-3 py-2 sm:py-1 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-900/50 sm:bg-transparent sticky top-0 sm:static z-10 backdrop-blur-sm">よく使われるキャラ</div>
              {popularChars.map(c => (
                <CharOption key={c.id} char={c} selected={value === c.id} onClick={() => { onChange(c.id); setIsOpen(false); }} showUsage />
              ))}
            </div>
          )}
          
          <div>
            <div className="px-3 py-2 sm:py-1 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-900/50 sm:bg-transparent sticky top-0 sm:static z-10 backdrop-blur-sm">すべてのキャラ</div>
            {otherChars.map(c => (
              <CharOption key={c.id} char={c} selected={value === c.id} onClick={() => { onChange(c.id); setIsOpen(false); }} />
            ))}
          </div>
        </>
      )}
    </>
  );
    
  return (
    <div className="relative w-full" ref={dropdownRef}>
      <button
        type="button"
        id={id}
        onClick={() => setIsOpen(!isOpen)}
        className={`${baseButtonClasses} ${buttonStyle} ${className}`}
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

      {isOpen && (
        <>
          {/* Mobile Full Screen Modal */}
          <div className="fixed inset-0 z-[100] bg-slate-950 flex flex-col sm:hidden animate-in fade-in slide-in-from-bottom-4 duration-200">
            <div className="p-4 border-b border-slate-800 flex items-center gap-3 bg-slate-900">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-3.5 h-5 w-5 text-slate-400" />
                <input
                  ref={mobileInputRef}
                  type="text"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg py-3 pl-10 pr-4 text-base text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  placeholder="キャラ名で検索..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <button 
                type="button"
                className="p-2 -mr-2 text-slate-400 hover:text-white rounded-full bg-slate-800/50"
                onClick={() => setIsOpen(false)}
              >
                <X className="h-6 w-6" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 pb-8 bg-slate-950">
              {renderList()}
            </div>
          </div>
          
          {/* Desktop Dropdown */}
          <div className="hidden sm:flex absolute z-50 mt-1 w-full min-w-[260px] max-h-80 overflow-hidden rounded-md bg-slate-800 border border-slate-600 shadow-2xl flex-col left-0 lg:left-auto lg:-right-4 animate-in fade-in zoom-in-95 duration-100">
            <div className="p-2 border-b border-slate-700 bg-slate-800">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                <input
                  ref={desktopInputRef}
                  type="text"
                  className="w-full bg-slate-900 border border-slate-700 rounded-md py-2 pl-8 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  placeholder="キャラ名で検索..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>
            
            <div className="overflow-y-auto p-1 flex-1 custom-scrollbar">
              {renderList()}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function CharOption({ char, selected, onClick, showUsage = false }: { char: Character, selected: boolean, onClick: () => void, showUsage?: boolean }) {
  return (
    <button
      type="button"
      className={`w-full flex items-center justify-between px-3 py-3 sm:py-2 text-base sm:text-sm rounded-sm transition-colors ${selected ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-700'}`}
      onClick={onClick}
    >
      <div className="truncate pr-2 text-left">
        {char.id === 9999 ? '空枠' : `[${char.rarity}] ${char.name}`}
      </div>
      {showUsage && char.usage_count !== undefined && (
        <div className={`text-xs whitespace-nowrap ${selected ? 'text-indigo-200' : 'text-slate-500'}`}>
          ({char.usage_count}回)
        </div>
      )}
    </button>
  );
}
