from services.match_processor import extract_match_results
import services.match_processor as mp

orig_fallback = mp._ocr_fallback
def mock_ocr(*args, **kwargs):
    print("FALLBACK CALLED")
    return orig_fallback(*args, **kwargs)
mp._ocr_fallback = mock_ocr

print(mp.extract_match_results("/app/uploads/match_t14_a13_d58.png"))
