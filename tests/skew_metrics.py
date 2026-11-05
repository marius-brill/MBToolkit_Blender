"""Dependency-free footprint comparisons for the disposable skew experiments."""
import hashlib
import math
import struct


def image_digest(pixels):
    """Compare decoded samples, not PNG metadata or rounded footprint statistics."""
    return hashlib.sha256(struct.pack('<' + 'f' * len(pixels), *pixels)).hexdigest()


def normal_detail(pixels, width, indices, threshold=.12):
    return {index for index in indices
            if (pixels[index * 4] - .5) ** 2 +
            (pixels[index * 4 + 1] - .5) ** 2 > threshold ** 2}


def compare_masks(actual, expected, width):
    """Missing detail and shape errors are distinct from displacement.

    This measures thresholded normal-detail coverage, NOT all high-surface hits.
    Empty actual masks remain measurable failures, rather than disappearing.
    """
    actual, expected = set(actual), set(expected)
    overlap = len(actual & expected)
    union = len(actual | expected)

    def centroid(mask):
        return [sum((index % width, index // width)[axis] + .5 for index in mask) / len(mask)
                for axis in (0, 1)] if mask else None

    a, b = centroid(actual), centroid(expected)
    return {'actual_pixels': len(actual), 'expected_pixels': len(expected),
            'missing_pixels': len(expected - actual), 'extra_pixels': len(actual - expected),
            'detail_recall': overlap / len(expected) if expected else None,
            'intersection_over_union': overlap / union if union else 1.0,
            'centroid_error_pixels': math.dist(a, b) if a and b else None,
            'actual_centroid': a, 'expected_centroid': b}