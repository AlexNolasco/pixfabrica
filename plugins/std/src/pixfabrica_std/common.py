from enum import StrEnum


class FitMode(StrEnum):
    CONTAIN = "contain"  # fit inside bounds, letterbox
    COVER = "cover"  # fill bounds, crop overflow
    FIT_WIDTH = "fit_width"  # match width, crop/letterbox height
    FIT_HEIGHT = "fit_height"  # match height, crop/letterbox width
    STRETCH = "stretch"  # ignore aspect ratio
