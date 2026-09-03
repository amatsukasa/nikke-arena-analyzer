"use client";

import { useState } from "react";
import {
  createInitialPlayerIconCropSettings,
  PlayerIconCropSettings,
} from "../lib/playerIconCrop";

/** Keeps crop preferences for the lifetime of one tournament registration page. */
export function usePlayerIconCropSettings() {
  return useState<PlayerIconCropSettings>(createInitialPlayerIconCropSettings);
}
