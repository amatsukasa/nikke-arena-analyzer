export function championPostSaveRefreshError(catalogUpdated: boolean, matchesRefreshed: boolean) {
  const failed = [
    !catalogUpdated ? "Character画像情報" : null,
    !matchesRefreshed ? "試合情報" : null,
  ].filter((label): label is string => label !== null);
  return failed.length
    ? `編成は保存されましたが、${failed.join("と")}を更新できませんでした。ページを再読み込みしてください。`
    : "";
}
