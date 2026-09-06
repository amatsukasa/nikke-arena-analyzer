import { prepareAnalysisImage } from "./deckImagePreparation";
import { PreparedMatchResultImage, selectMatchResultImage } from "./matchRegistration";

export async function prepareMatchResultImage(file: File): Promise<PreparedMatchResultImage> {
  const prepared = await prepareAnalysisImage(file, {
    maxOutputWidth: 1080,
    filenameSuffix: ".match-modal.png",
  });
  return selectMatchResultImage(file, prepared);
}
