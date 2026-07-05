"""Pixel-based collection badge detection.

The badge is rendered at a fixed position in the normalized 160x160 character
crop.  Detection deliberately happens in three stages: shape/presence, rarity
color, then the dark level-15 variant.  Character artwork color alone must
never be sufficient to report a collection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np


logger = logging.getLogger(__name__)

COLLECTION_VALUES = {
    "none",
    "r_0_14",
    "r_15",
    "sr_0_14",
    "sr_15",
    "treasure_0_14",
    "treasure_15",
    "unknown",
}

NORMALIZED_SIZE = 160
# x1, y1, x2, y2. This is intentionally much narrower than the old color ROI.
COLLECTION_ROI = (0, 45, 32, 105)

# OpenCV hue is 0..179. Saturation is required so white UI glyphs do not vote.
RARITY_HSV_RANGES = {
    "r": (80, 105),
    "sr": (125, 165),
    "treasure": (3, 25),
}

MIN_SATURATION = 100
MIN_COMPONENT_AREA = 60.0
EXPECTED_COMPONENT_X = (0, 10)
EXPECTED_COMPONENT_Y = (18, 34)
EXPECTED_COMPONENT_WIDTH = (12, 31)
EXPECTED_COMPONENT_HEIGHT = (10, 35)
MIN_SHAPE_SCORE = 0.48
LEVEL_15_DARK_VALUE = 85
LEVEL_15_DARK_RATIO = 0.16


def _normalized_face(face: np.ndarray) -> np.ndarray:
    if face.shape[:2] == (NORMALIZED_SIZE, NORMALIZED_SIZE):
        return face
    return cv2.resize(face, (NORMALIZED_SIZE, NORMALIZED_SIZE))


def _bounded_score(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 1.0
    distance = low - value if value < low else value - high
    return max(0.0, 1.0 - distance / max(high - low, 1.0))


def _candidate_for_rarity(
    hue: np.ndarray,
    saturation: np.ndarray,
    rarity: str,
) -> tuple[dict[str, Any] | None, np.ndarray]:
    hue_low, hue_high = RARITY_HSV_RANGES[rarity]
    mask = (
        (hue >= hue_low)
        & (hue <= hue_high)
        & (saturation >= MIN_SATURATION)
    ).astype(np.uint8) * 255

    # Only bridge tiny anti-aliasing gaps. A large close operation can turn
    # character artwork into a badge-like blob.
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((2, 2), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        if area < MIN_COMPONENT_AREA:
            continue
        if not (
            EXPECTED_COMPONENT_X[0] <= x <= EXPECTED_COMPONENT_X[1]
            and EXPECTED_COMPONENT_Y[0] <= y <= EXPECTED_COMPONENT_Y[1]
            and EXPECTED_COMPONENT_WIDTH[0] <= width <= EXPECTED_COMPONENT_WIDTH[1]
            and EXPECTED_COMPONENT_HEIGHT[0] <= height <= EXPECTED_COMPONENT_HEIGHT[1]
        ):
            continue

        hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
        solidity = area / hull_area if hull_area else 0.0
        fill_ratio = area / float(width * height)
        area_score = _bounded_score(area, 80.0, 340.0)
        solidity_score = _bounded_score(solidity, 0.55, 1.0)
        fill_score = _bounded_score(fill_ratio, 0.30, 0.85)
        position_score = (
            _bounded_score(x, *EXPECTED_COMPONENT_X)
            + _bounded_score(y, *EXPECTED_COMPONENT_Y)
        ) / 2.0
        shape_score = (
            area_score * 0.25
            + solidity_score * 0.25
            + fill_score * 0.20
            + position_score * 0.30
        )
        candidates.append(
            {
                "rarity": rarity,
                "area": round(area, 3),
                "bbox": [int(x), int(y), int(width), int(height)],
                "solidity": round(solidity, 4),
                "fill_ratio": round(fill_ratio, 4),
                "shape_score": round(shape_score, 4),
                "_contour": contour,
            }
        )

    if not candidates:
        return None, mask
    return max(candidates, key=lambda item: (item["shape_score"], item["area"])), mask


def _write_debug_images(
    debug_dir: str | Path,
    debug_prefix: str,
    normalized: np.ndarray,
    roi: np.ndarray,
    masks: dict[str, np.ndarray],
    candidate: dict[str, Any] | None,
) -> None:
    output_dir = Path(debug_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_dir / f"{debug_prefix}_normalized.png"), normalized)
    cv2.imwrite(str(output_dir / f"{debug_prefix}_roi.png"), roi)
    for rarity, mask in masks.items():
        cv2.imwrite(str(output_dir / f"{debug_prefix}_mask_{rarity}.png"), mask)

    annotated = roi.copy()
    if candidate is not None:
        x, y, width, height = candidate["bbox"]
        cv2.rectangle(
            annotated,
            (x, y),
            (x + width - 1, y + height - 1),
            (0, 255, 0),
            1,
        )
    cv2.imwrite(str(output_dir / f"{debug_prefix}_detected.png"), annotated)


def analyze_collection(
    face: np.ndarray,
    *,
    debug: bool = False,
    debug_dir: str | Path = ".local/collection-debug",
    debug_prefix: str = "collection",
) -> dict[str, Any]:
    """Return a structured, deterministic collection badge analysis."""
    if face is None or face.size == 0:
        return {
            "has_collection": False,
            "rarity": None,
            "level": None,
            "confidence": 0.0,
            "debug_info": {"reason": "empty_image"},
        }

    normalized = _normalized_face(face)
    x1, y1, x2, y2 = COLLECTION_ROI
    roi = normalized[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)

    candidates: list[dict[str, Any]] = []
    masks: dict[str, np.ndarray] = {}
    for rarity in RARITY_HSV_RANGES:
        candidate, mask = _candidate_for_rarity(hue, saturation, rarity)
        masks[rarity] = mask
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (item["shape_score"], item["area"]),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    if debug:
        _write_debug_images(
            debug_dir,
            debug_prefix,
            normalized,
            roi,
            masks,
            best,
        )

    public_candidates = [
        {key: value for key, value in candidate.items() if not key.startswith("_")}
        for candidate in candidates
    ]
    if best is None or best["shape_score"] < MIN_SHAPE_SCORE:
        best_nearby_score = best["shape_score"] if best else 0.0
        confidence = round(max(0.5, 1.0 - best_nearby_score), 3)
        debug_info = {
            "reason": "no_badge_shaped_component",
            "roi": list(COLLECTION_ROI),
            "candidates": public_candidates,
        }
        logger.debug("Collection absent: %s", debug_info)
        return {
            "has_collection": False,
            "rarity": None,
            "level": None,
            "confidence": confidence,
            "debug_info": debug_info,
        }

    rarity = str(best["rarity"])
    x, y, width, height = best["bbox"]
    # Ignore the anti-aliased outer rim and measure darkness only inside the
    # detected badge. The level-15 artwork has a stable dark interior.
    inset = 2 if width > 6 and height > 6 else 0
    level_patch = value[
        y + inset : y + height - inset,
        x + inset : x + width - inset,
    ]
    dark_ratio = (
        float(np.mean(level_patch < LEVEL_15_DARK_VALUE))
        if level_patch.size
        else 0.0
    )
    is_level_15 = dark_ratio >= LEVEL_15_DARK_RATIO
    level_band = "15" if is_level_15 else "0_14"
    level = 15 if is_level_15 else None

    second_score = candidates[1]["shape_score"] if len(candidates) > 1 else 0.0
    rarity_margin = max(0.0, float(best["shape_score"]) - float(second_score))
    shape_confidence = float(best["shape_score"])
    level_distance = abs(dark_ratio - LEVEL_15_DARK_RATIO)
    level_confidence = min(1.0, 0.65 + level_distance * 2.0)
    confidence = round(
        min(
            1.0,
            shape_confidence * 0.60
            + min(1.0, 0.7 + rarity_margin) * 0.25
            + level_confidence * 0.15,
        ),
        3,
    )

    debug_info = {
        "roi": list(COLLECTION_ROI),
        "selected_bbox": list(best["bbox"]),
        "shape_score": best["shape_score"],
        "rarity_margin": round(rarity_margin, 4),
        "dark_ratio": round(dark_ratio, 4),
        "level_band": level_band,
        "candidates": public_candidates,
    }
    logger.debug(
        "Collection detected rarity=%s level_band=%s confidence=%.3f details=%s",
        rarity,
        level_band,
        confidence,
        debug_info,
    )
    return {
        "has_collection": True,
        "rarity": rarity,
        "level": level,
        "confidence": confidence,
        "debug_info": debug_info,
    }


def classify_collection(face: np.ndarray) -> tuple[str, float]:
    """Compatibility wrapper for the existing API field."""
    analysis = analyze_collection(face)
    if not analysis["has_collection"]:
        return "none", float(analysis["confidence"])
    level_band = analysis["debug_info"]["level_band"]
    value = f"{analysis['rarity']}_{level_band}"
    if value not in COLLECTION_VALUES:
        return "unknown", 0.0
    return value, float(analysis["confidence"])


def mask_collection_icon(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    masked = image.copy()
    height, width = masked.shape[:2]
    x_end = max(1, round(width * 36 / NORMALIZED_SIZE))
    # Keep the established, slightly wider matcher mask for compatibility.
    y_start = max(0, round(height * 50 / NORMALIZED_SIZE))
    y_end = min(height, round(height * 110 / NORMALIZED_SIZE))
    masked[y_start:y_end, 0:x_end] = 127
    return masked
