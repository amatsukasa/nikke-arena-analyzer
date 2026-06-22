import glob
from services.image_processor import process_images

files = glob.glob('/app/media__17812630286*.png')
files.sort()

# process_images processes a batch of images at once
try:
    res = process_images(files, 1, 1)
    teams = res['suggested_teams']
    for i, team in enumerate(teams):
        print(f"--- Round {i+1} ---")
        for j, char in enumerate(team):
            print(f"  Slot {j+1}: {char.get('predicted_character_id')} (Conf: {char.get('confidence', 'N/A')})")
except Exception as e:
    print(f"Error: {e}")
