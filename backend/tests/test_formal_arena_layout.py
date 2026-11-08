import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.image_processor import (_find_round_tab_anchor, _find_character_card_centers,
    _extract_modal_roi, _aligned_character_centers, _character_crop_left, process_images)

class FormalArenaLayoutTests(unittest.TestCase):
    def test_both_layouts_and_all_rounds_at_multiple_resolutions(self):
        for tab_y, height in ((30, 559), (121, 648)):
            for active in range(5):
                for width in (720, 1080, 1440):
                    with self.subTest(tab_y=tab_y, active=active, width=width):
                        image = np.full((height,1080,3), 245, np.uint8)
                        for index in range(5):
                            left = 60 + index*194
                            cv2.rectangle(image, (left,tab_y), (left+179,tab_y+74),
                                          (235,175,20) if index == active else (150,150,150), -1)
                        # Tiny cyan decoration at the panel edge must not win.
                        image[0:3,1074:1080] = (235,175,20)
                        image = cv2.resize(cv2.resize(image,(width,round(height*width/1080))),(1080,height))
                        y,x,reliable = _find_round_tab_anchor(image)
                        self.assertTrue(reliable)
                        self.assertLessEqual(abs(y-tab_y),1)
                        self.assertLessEqual(abs(x-(149+194*active)),2)
                        fallback,shift = _aligned_character_centers(x,reliable)
                        centers,grid = _find_character_card_centers(image,shift,fallback)
                        self.assertTrue(grid)
                        for i,center in enumerate(centers):
                            left = _character_crop_left(center,i)
                            self.assertEqual(image[y+200:y+360,left:left+160].shape,(160,160,3))

    def test_invalid_layout_is_rejected_before_output_or_matching(self):
        for image in (None, np.full((648,1080,3),245,np.uint8)):
            with self.subTest(valid_image=image is not None), patch('services.image_processor.cv2.imread',return_value=image), patch('services.image_processor.os.makedirs') as output:
                with self.assertRaises(ValueError):
                    process_images(['invalid.png'],1,1,pre_cropped_flags=[True])
                output.assert_not_called()

    @unittest.skipUnless(os.environ.get('ARENA_LAYOUT_SAMPLES'), 'Set ARENA_LAYOUT_SAMPLES to the supplied sample directory')
    def test_real_pipeline_writes_five_faces_for_raw_and_pre_cropped_images(self):
        root = Path(os.environ['ARENA_LAYOUT_SAMPLES'])
        original_cwd = Path.cwd()
        for name in ('77625.png', 'IMG_4397.png'):
            source = cv2.imdecode(np.fromfile(root/name, dtype=np.uint8), cv2.IMREAD_COLOR)
            x,y,w,h = _extract_modal_roi(source)
            for pre_cropped in (False, True):
                with self.subTest(name=name, pre_cropped=pre_cropped), tempfile.TemporaryDirectory() as directory:
                    try:
                        os.chdir(directory)
                        image = source[y:y+h,x:x+w] if pre_cropped else source
                        self.assertTrue(cv2.imwrite('input.png', image))
                        with patch('services.template_matcher.get_templates', return_value={}):
                            result = process_images(['input.png'], 1, 1, pre_cropped_flags=[pre_cropped])
                        team = result['suggested_teams'][0]
                        self.assertEqual(len(team), 5)
                        for character in team:
                            self.assertIsNone(character['predicted_character_id'])
                            crop = cv2.imread(character['template_source_url'].removeprefix('/api/'))
                            self.assertEqual(crop.shape, (160,160,3))
                    finally:
                        os.chdir(original_cwd)

    @unittest.skipUnless(os.environ.get('ARENA_LAYOUT_SAMPLES'), 'Set ARENA_LAYOUT_SAMPLES to the supplied sample directory')
    def test_supplied_real_images_and_scaled_versions(self):
        root=Path(os.environ['ARENA_LAYOUT_SAMPLES'])
        for name, expected in [('77625.png',30),('IMG_4397.png',121)]:
            image=cv2.imdecode(np.fromfile(root/name,dtype=np.uint8),cv2.IMREAD_COLOR)
            self.assertIsNotNone(image)
            for scale in (0.75,1,1.5):
                resized=cv2.resize(image,None,fx=scale,fy=scale)
                x,y,w,h=_extract_modal_roi(resized)
                normalized=cv2.resize(resized[y:y+h,x:x+w],(1080,int(h*1080/w)))
                tab_y,tab_x,reliable=_find_round_tab_anchor(normalized)
                self.assertTrue(reliable)
                self.assertLessEqual(abs(tab_y-expected),4)
                fallback,shift=_aligned_character_centers(tab_x,reliable)
                centers,grid=_find_character_card_centers(normalized,shift,fallback)
                self.assertTrue(grid)
                for i,center in enumerate(centers):
                    left=_character_crop_left(center,i)
                    face=normalized[tab_y+200:tab_y+360,left:left+160]
                    self.assertEqual(face.shape,(160,160,3))

if __name__ == '__main__':
    unittest.main()
