"""Local-only crop inspection; never loads templates or connects to a database."""
import argparse
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.image_processor import (_extract_modal_roi, _find_round_tab_anchor,
    _aligned_character_centers, _find_character_card_centers, _character_crop_left)

def inspect(path, output):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Invalid image')
    x, y, w, h = _extract_modal_roi(image)
    modal = cv2.resize(image[y:y+h, x:x+w], (1080, int(h*1080/w)))
    tab_y, tab_x, reliable = _find_round_tab_anchor(modal)
    if not reliable or tab_y + 360 > modal.shape[0]:
        raise ValueError('Unsupported ROUND layout')
    fallback, shift = _aligned_character_centers(tab_x, reliable)
    centers, grid = _find_character_card_centers(modal, shift, fallback)
    output.mkdir(parents=True, exist_ok=True)
    annotated = modal.copy()
    faces = []
    for index, center in enumerate(centers):
        left, top = _character_crop_left(center, index), tab_y + 200
        face = modal[top:top+160, left:left+160]
        faces.append(face)
        cv2.imencode('.png', face)[1].tofile(output / f'face-{index+1}.png')
        cv2.rectangle(annotated, (left, top), (left+160, top+160), (0,0,255), 2)
    cv2.imencode('.png', annotated)[1].tofile(output / 'overlay.png')
    cv2.imencode('.png', np.hstack(faces))[1].tofile(output / 'faces.png')
    print(f'{path.name}: size={image.shape[1]}x{image.shape[0]} roi={(x,y,w,h)} normalized={modal.shape[1]}x{modal.shape[0]} tab={(tab_x,tab_y)} centers={centers} grid={grid}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inspect(args.image, args.output)
