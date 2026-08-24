import { ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
}

export const deckRegistrationViewportClass = "mx-auto w-full min-w-0 max-w-7xl";

export default function DeckRegistrationViewport({ children, className = "" }: Props) {
  return (
    <div className={`${deckRegistrationViewportClass} ${className}`.trim()} data-deck-registration-viewport>
      {children}
    </div>
  );
}
