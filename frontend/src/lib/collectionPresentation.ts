export const COLLECTION_OPTIONS = [
  { value: "none", label: "コレクションなし" },
  { value: "r_0_14", label: "R 0～14" },
  { value: "r_15", label: "R 15" },
  { value: "sr_0_14", label: "SR 0～14" },
  { value: "sr_15", label: "SR 15" },
  { value: "treasure_0_14", label: "宝物 0～14" },
  { value: "treasure_15", label: "宝物 15" },
  { value: "unknown", label: "判定不能" },
] as const;

export function collectionSelectClass(value?: string | null) {
  switch (value) {
    case "r_0_14": return "border-blue-500 bg-white text-blue-700";
    case "r_15": return "border-blue-500 bg-black text-white";
    case "sr_0_14": return "border-purple-500 bg-white text-purple-700";
    case "sr_15": return "border-purple-500 bg-black text-white";
    case "treasure_0_14": return "border-orange-500 bg-white text-orange-700";
    case "treasure_15": return "border-orange-500 bg-black text-white";
    case "unknown": return "border-red-500 bg-red-50 text-red-700";
    case "none": return "border-slate-400 bg-white text-slate-700";
    default: return "border-slate-600 bg-slate-800 text-slate-300";
  }
}
