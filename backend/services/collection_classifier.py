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
COLLECTION_MATCH_MASK_PADDING = 4


def collection_match_mask(shape: tuple[int, ...]) -> np.ndarray:
    """Return a normalized validity mask which excludes the badge ROI.

    White pixels participate in Character matching.  The same proportional
    region is excluded for live crops and historical templates.
    """
    height, width = shape[:2]
    mask = np.full((height, width), 255, dtype=np.uint8)
    scale_x = width / NORMALIZED_SIZE
    scale_y = height / NORMALIZED_SIZE
    x1, y1, x2, y2 = COLLECTION_ROI
    padding = COLLECTION_MATCH_MASK_PADDING
    left = max(0, int(np.floor((x1 - padding) * scale_x)))
    top = max(0, int(np.floor((y1 - padding) * scale_y)))
    right = min(width, int(np.ceil((x2 + padding) * scale_x)))
    bottom = min(height, int(np.ceil((y2 + padding) * scale_y)))
    if left < right and top < bottom:
        mask[top:bottom, left:right] = 0
    return mask

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
# The unlevelled badge can render as only the filled centre jewel after the
# screenshot has passed through the browser crop/resize path.  Keep this as a
# separate, tightly bounded profile instead of relaxing the general shape
# limits, which would make character artwork eligible as a badge.
COMPACT_COMPONENT_X = (4, 13)
COMPACT_COMPONENT_Y = (25, 32)
COMPACT_COMPONENT_WIDTH = (13, 16)
COMPACT_COMPONENT_HEIGHT = (8, 9)
COMPACT_COMPONENT_AREA = (65.0, 100.0)
MIN_SHAPE_SCORE = 0.48
LEVEL_15_DARK_VALUE = 85
LEVEL_15_DARK_RATIO = 0.11
# The in-game badge is a pointy-top regular hexagon. At the normalized card
# scale its visible outer frame is about 28 px wide and 32 px high.
BADGE_HEXAGON_SIZE = (28, 32)
BADGE_INNER_HEXAGON_SIZE = (20, 24)
HEXAGON_PROBE_CENTER_X = (10, 19)
HEXAGON_PROBE_CENTER_Y = (33, 37)
HEXAGON_PROBE_MIN_COLOR_DENSITY = 0.60
HEXAGON_PROBE_MIN_CONTRAST_SCORE = 0.48
HEXAGON_PROBE_MIN_DENSITY_DELTA = 0.25


def _normalized_face(face: np.ndarray) -> np.ndarray:
    if face.shape[:2] == (NORMALIZED_SIZE, NORMALIZED_SIZE):
        return face
    return cv2.resize(face, (NORMALIZED_SIZE, NORMALIZED_SIZE))


def _bounded_score(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 1.0
    distance = low - value if value < low else value - high
    return max(0.0, 1.0 - distance / max(high - low, 1.0))


def _hexagon_points(
    center_x: float,
    center_y: float,
    width: int,
    height: int,
) -> np.ndarray:
    """Return the expected pointy-top badge hexagon in ROI coordinates."""
    half_width = width / 2.0
    half_height = height / 2.0
    quarter_height = height / 4.0
    return np.rint(
        np.array(
            [
                [center_x, center_y - half_height],
                [center_x + half_width, center_y - quarter_height],
                [center_x + half_width, center_y + quarter_height],
                [center_x, center_y + half_height],
                [center_x - half_width, center_y + quarter_height],
                [center_x - half_width, center_y - quarter_height],
            ],
            dtype=np.float32,
        )
    ).astype(np.int32)


def _badge_geometry(
    candidate: dict[str, Any],
    roi_shape: tuple[int, int],
) -> dict[str, Any]:
    """Infer the full badge hexagon from its colored frame or centre jewel."""
    x, y, width, height = candidate["bbox"]
    center_x = x + (width - 1) / 2.0
    center_y = y + (height - 1) / 2.0
    outer = _hexagon_points(center_x, center_y, *BADGE_HEXAGON_SIZE)
    inner = _hexagon_points(center_x, center_y, *BADGE_INNER_HEXAGON_SIZE)

    roi_height, roi_width = roi_shape
    outer[:, 0] = np.clip(outer[:, 0], 0, roi_width - 1)
    outer[:, 1] = np.clip(outer[:, 1], 0, roi_height - 1)
    inner[:, 0] = np.clip(inner[:, 0], 0, roi_width - 1)
    inner[:, 1] = np.clip(inner[:, 1], 0, roi_height - 1)

    contour = candidate["_contour"]
    contour_hexagon = _hexagon_points(
        center_x,
        center_y,
        max(width, 1),
        max(height, 1),
    ).reshape((-1, 1, 2))
    shape_distance = float(
        cv2.matchShapes(contour, contour_hexagon, cv2.CONTOURS_MATCH_I1, 0.0)
    )
    template_score = 1.0 / (1.0 + shape_distance * 4.0)
    # A compact component is the centre jewel, not the outer border. Its
    # position/size profile is therefore the reliable evidence for inferring
    # the surrounding hexagon.
    inferred = candidate["shape_profile"] == "compact"
    hexagon_score = (
        float(candidate["shape_score"]) * 0.70
        + (0.90 if inferred else template_score) * 0.30
    )
    return {
        "polygon": outer.tolist(),
        "inner_polygon": inner.tolist(),
        "center": [round(center_x, 2), round(center_y, 2)],
        "hexagon_score": round(min(1.0, hexagon_score), 4),
        "inferred_from_compact_jewel": inferred,
    }


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
        is_standard_component = (
            EXPECTED_COMPONENT_X[0] <= x <= EXPECTED_COMPONENT_X[1]
            and EXPECTED_COMPONENT_Y[0] <= y <= EXPECTED_COMPONENT_Y[1]
            and EXPECTED_COMPONENT_WIDTH[0] <= width <= EXPECTED_COMPONENT_WIDTH[1]
            and EXPECTED_COMPONENT_HEIGHT[0] <= height <= EXPECTED_COMPONENT_HEIGHT[1]
        )
        is_compact_component = (
            COMPACT_COMPONENT_X[0] <= x <= COMPACT_COMPONENT_X[1]
            and COMPACT_COMPONENT_Y[0] <= y <= COMPACT_COMPONENT_Y[1]
            and COMPACT_COMPONENT_WIDTH[0] <= width <= COMPACT_COMPONENT_WIDTH[1]
            and COMPACT_COMPONENT_HEIGHT[0] <= height <= COMPACT_COMPONENT_HEIGHT[1]
            and COMPACT_COMPONENT_AREA[0] <= area <= COMPACT_COMPONENT_AREA[1]
        )
        if not (is_standard_component or is_compact_component):
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
                "shape_profile": (
                    "compact" if is_compact_component else "standard"
                ),
                "_contour": contour,
            }
        )

    if not candidates:
        return None, mask
    return max(candidates, key=lambda item: (item["shape_score"], item["area"])), mask


def _hexagon_probe_candidate(
    mask: np.ndarray,
    rarity: str,
) -> dict[str, Any] | None:
    """Recover a badge whose color contour merged into character artwork."""
    colored = mask > 0
    best_probe: dict[str, Any] | None = None
    for center_y in range(HEXAGON_PROBE_CENTER_Y[0], HEXAGON_PROBE_CENTER_Y[1] + 1):
        for center_x in range(HEXAGON_PROBE_CENTER_X[0], HEXAGON_PROBE_CENTER_X[1] + 1):
            inner_mask = np.zeros(mask.shape, dtype=np.uint8)
            outer_mask = np.zeros(mask.shape, dtype=np.uint8)
            inner_polygon = _hexagon_points(center_x, center_y, 20, 24)
            outer_polygon = _hexagon_points(center_x, center_y, 30, 36)
            cv2.fillConvexPoly(inner_mask, inner_polygon, 255)
            cv2.fillConvexPoly(outer_mask, outer_polygon, 255)
            inner_pixels = inner_mask > 0
            ring_pixels = (outer_mask > 0) & ~inner_pixels
            color_density = float(np.mean(colored[inner_pixels]))
            ring_density = float(np.mean(colored[ring_pixels]))
            density_delta = color_density - ring_density
            contrast_score = color_density - ring_density * 0.40
            if (
                color_density < HEXAGON_PROBE_MIN_COLOR_DENSITY
                or contrast_score < HEXAGON_PROBE_MIN_CONTRAST_SCORE
                or density_delta < HEXAGON_PROBE_MIN_DENSITY_DELTA
            ):
                continue
            if best_probe is None or contrast_score > best_probe["contrast_score"]:
                contour = _hexagon_points(
                    center_x,
                    center_y,
                    *BADGE_HEXAGON_SIZE,
                ).reshape((-1, 1, 2))
                x, y, width, height = cv2.boundingRect(contour)
                best_probe = {
                    "rarity": rarity,
                    "area": round(float(cv2.contourArea(contour)), 3),
                    "bbox": [int(x), int(y), int(width), int(height)],
                    "solidity": 1.0,
                    "fill_ratio": round(
                        float(cv2.contourArea(contour)) / float(width * height),
                        4,
                    ),
                    "shape_score": round(min(1.0, 0.50 + contrast_score), 4),
                    "shape_profile": "hexagon_probe",
                    "color_density": round(color_density, 4),
                    "ring_density": round(ring_density, 4),
                    "density_delta": round(density_delta, 4),
                    "contrast_score": round(contrast_score, 4),
                    "_contour": contour,
                }
    return best_probe


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
        # Treasure-colored frames can touch orange character artwork and turn
        # into one oversized contour. Probe the expected hexagon directly in
        # that case, while retaining an inside-vs-ring contrast requirement.
        if candidate is None and rarity == "treasure":
            candidate = _hexagon_probe_candidate(mask, rarity)
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
    geometry = _badge_geometry(best, roi.shape[:2])
    inner_mask = np.zeros(value.shape, dtype=np.uint8)
    cv2.fillConvexPoly(
        inner_mask,
        np.asarray(geometry["inner_polygon"], dtype=np.int32),
        255,
    )
    level_patch = value[inner_mask > 0]
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
        "badge_geometry": geometry,
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
