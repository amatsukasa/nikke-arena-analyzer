"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useCharacterCatalog<T>(onError?: () => void) {
  const [characters, setCharacters] = useState<T[]>([]);
  const generation = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const refreshCharacters = useCallback(async (): Promise<boolean> => {
    const current = ++generation.current;
    activeController.current?.abort();
    const controller = new AbortController();
    activeController.current = controller;
    try {
      const response = await fetch("/api/characters", {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Character catalog request failed");
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("Character catalog response is invalid");
      if (current !== generation.current) return false;
      setCharacters(data);
      return true;
    } catch (error) {
      if (controller.signal.aborted || current !== generation.current) return false;
      onErrorRef.current?.();
      return false;
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, []);

  useEffect(() => {
    void refreshCharacters();
    return () => {
      generation.current += 1;
      activeController.current?.abort();
      activeController.current = null;
    };
  }, [refreshCharacters]);

  return { characters, refreshCharacters };
}
