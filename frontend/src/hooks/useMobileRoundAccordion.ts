"use client";

import { useCallback, useRef, useState } from "react";

export function useMobileRoundAccordion(initialRound = 0) {
  const [expandedRound, setExpandedRound] = useState(initialRound);
  const roundToggleRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const toggleRound = useCallback((roundIndex: number) => {
    const willExpand = expandedRound !== roundIndex;
    setExpandedRound(willExpand ? roundIndex : -1);
    if (!willExpand || !window.matchMedia("(max-width: 639px)").matches) return;

    // Wait for the conditional round content to mount and finish layout before
    // calculating the same smooth-scroll target in both registration modes.
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        roundToggleRefs.current[roundIndex]?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    });
  }, [expandedRound]);

  return { expandedRound, setExpandedRound, roundToggleRefs, toggleRound };
}
