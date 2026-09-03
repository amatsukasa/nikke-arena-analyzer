export interface PlayerIconCropSettings {
  crop: { x: number; y: number };
  zoom: number;
}

export const createInitialPlayerIconCropSettings = (): PlayerIconCropSettings => ({
  crop: { x: 0, y: 0 },
  zoom: 1,
});
