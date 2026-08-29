import { REGISTRATION_SCOPE_LABELS, RegistrationScope } from "../lib/tournaments";

export default function RegistrationScopeBadge({ scope }: { scope?: RegistrationScope }) {
  const normalized = scope === "champion_8" ? "champion_8" : "full_64";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${
      normalized === "champion_8"
        ? "bg-amber-500/10 text-amber-200 ring-amber-500/30"
        : "bg-blue-500/10 text-blue-200 ring-blue-500/30"
    }`}>
      {REGISTRATION_SCOPE_LABELS[normalized]}
    </span>
  );
}
