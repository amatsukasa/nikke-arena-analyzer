import cv2, numpy as np
img=cv2.imread('/app/uploads/match_t14_a1_d2.png')
orig_h, orig_w = img.shape[:2]
target_w = 1080
target_h = int(orig_h * target_w / orig_w)
img = cv2.resize(img, (target_w, target_h))
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
lower_cyan = np.array([70, 60, 100])
upper_cyan = np.array([110, 255, 255])
lower_red1 = np.array([0, 60, 100])
upper_red1 = np.array([15, 255, 255])
lower_red2 = np.array([165, 60, 100])
upper_red2 = np.array([180, 255, 255])
cyan_mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
red_mask = cv2.bitwise_or(cv2.inRange(hsv, lower_red1, upper_red1), cv2.inRange(hsv, lower_red2, upper_red2))

kernel = np.ones((5,5), np.uint8)
cyan_mask = cv2.morphologyEx(cyan_mask, cv2.MORPH_CLOSE, kernel)
red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

def get_b(m,c):
    n,l,s,cent = cv2.connectedComponentsWithStats(m)
    res=[]
    for i in range(1,n):
        if s[i,cv2.CC_STAT_AREA]>50:
            res.append({'x':cent[i][0],'y':cent[i][1],'type':c, 'area': s[i,cv2.CC_STAT_AREA]})
    return res

blobs = get_b(cyan_mask,'WIN')+get_b(red_mask,'LOSE')
blobs.sort(key=lambda x:x['y'])
print('BLOBS:')
for b in blobs:
    print(b)
