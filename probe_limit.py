"""Нативная карта маски региона ЛИМИТ ВРЕМЕНИ."""
import numpy as np
from qt.core.io import imread_u
from qt.ocr.preprocess import stretch
import cv2

img = imread_u("tests/fixtures/screen_01.png")
crop = img[70:90, 1810:1860]
st = stretch(crop)
hsv = cv2.cvtColor(st, cv2.COLOR_BGR2HSV)
m = cv2.inRange(hsv, np.array([80, 40, 40], np.uint8), np.array([115, 255, 255], np.uint8))
gray = cv2.cvtColor(st, cv2.COLOR_BGR2GRAY)
_, g = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
print("y\\x 1810..1859  COLOR-MASK")
for y in range(m.shape[0]):
    print("%2d " % (70 + y) + "".join("#" if v else "." for v in m[y]))
print("y\\x 1810..1859  GRAY-OTSU")
for y in range(g.shape[0]):
    print("%2d " % (70 + y) + "".join("#" if v else "." for v in g[y]))