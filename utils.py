# -*- coding: utf-8 -*-
import cv2
import colorsys
import numpy as np

from scipy import interpolate


# Checks the contour directionality based on the Part type.  Returns true if
# the contour should be flipped to ensure consistency and false otherwise.
# contour: list of numpy arrays in matrix coordinates.
def reverse_contour_directionality(contour, type_):
    # Flukes: left to right.
    if type_.lower() == 'fluke':
        start, end = contour[0][0], contour[-1][-1]
        return start[1] > end[1]  # Compare j-coordinates.
    # Dorsal fins: left to right.
    elif type_.lower() == 'dorsal':
        start, end = contour[0][0], contour[-1][-1]
        return start[1] > end[1]  # Compare j-coordinates.
    # Left and right ears: top to bottom.
    elif type_.lower() in ('left ear', 'right ear'):
        start, end = contour[0][0], contour[-1][-1]
        return start[0] < end[0]  # Compare i-coodinates.
    else:
        raise ValueError(
            'No consistent directionality defined for Part type:' '%s.' % (type_)
        )


# Applies resampling along the axis=0, treating all columns as
# independent functions of equidistant points.
def resample1d(input, length):
    interp = np.linspace(0, length, num=input.shape[0])
    f = interpolate.interp1d(interp, input, axis=0, kind='linear')

    return f(np.arange(length))


# Resamples a parametric curve f(t) = (x(t), y(t)), while assuming that
# initially the points are not necessarily equidistant.
def resample2d(input, length):
    dist = np.linalg.norm(np.diff(input, axis=0), axis=1)
    u = np.hstack((0.0, np.cumsum(dist)))
    t = np.linspace(0.0, u.max(), length)
    xn = np.interp(t, u, input[:, 0])
    yn = np.interp(t, u, input[:, 1])

    return np.vstack((xn, yn)).T


def random_colors(n):
    grc = 0.618033988749895
    h = np.random.random()
    colors = []
    for i in range(n):
        h += grc
        h %= 1
        r, g, b = colorsys.hsv_to_rgb(h, 0.99, 0.99)
        colors.append((255.0 * r, 255.0 * g, 255.0 * b))

    return colors


def points_to_mask(pts, radii, occluded, size):
    mask = np.zeros(size, dtype=np.uint8)
    for idx, (x, y) in enumerate(pts):
        r = radii[idx]
        if not occluded[idx]:
            cv2.circle(mask, (x, y), r, 255, -1)

    return mask


# Padding is expressed as a fraction of the width.
def crop_with_padding(image, x, y, w, h, pad):
    img_height, img_width = image.shape[0:2]
    if x >= 0 or y >= 0 or w >= 0 or h >= 0:
        x0 = int(max(0, x - int(pad * w)))
        x1 = int(min(img_width, x + w + int(pad * w)))
        y0 = int(max(0, y - int(pad * h)))
        y1 = int(min(img_height, y + h + int(pad * h)))
        crop = image[y0:y1, x0:x1]
    else:
        crop = image
        x0, y0, x1, y1 = 0, 0, image.shape[1], image.shape[0]

    return crop, (x0, y0, x1, y1)


# https://github.com/martinjevans/OpenCV-Rotate-and-Crop/blob/master/rotate_and_crop.py
def sub_image(image, center, theta, width, height, border_mode=cv2.BORDER_REPLICATE):
    """Extract a rectangle from the source image.

    image - source image
    center - (x,y) tuple for the centre point.
    theta - angle of rectangle.
    width, height - rectangle dimensions.
    """

    # if np.pi / 4. < theta <= np.pi / 2.:
    #    theta = theta - np.pi / 2.
    #    width, height = height, width

    # theta *= np.pi / 180  # convert to rad
    v_x = (np.cos(theta), np.sin(theta))
    v_y = (-np.sin(theta), np.cos(theta))
    s_x = center[0] - v_x[0] * (width / 2) - v_y[0] * (height / 2)
    s_y = center[1] - v_x[1] * (width / 2) - v_y[1] * (height / 2)
    mapping = np.array([[v_x[0], v_y[0], s_x], [v_x[1], v_y[1], s_y]])

    return cv2.warpAffine(
        image,
        mapping,
        (width, height),
        flags=cv2.WARP_INVERSE_MAP,
        borderMode=border_mode,
        borderValue=0.0,
    )
