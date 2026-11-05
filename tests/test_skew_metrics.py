"""Ordinary Python regression tests for skew acceptance measurements."""
import unittest

from skew_metrics import compare_masks, image_digest, normal_detail


class SkewMetricTests(unittest.TestCase):
    def test_repeat_checks_every_sample(self):
        self.assertEqual(image_digest([.5, .5, 1, 1]), image_digest([.5, .5, 1, 1]))
        self.assertNotEqual(image_digest([.5, .5, 1, 1]), image_digest([.5, .5, .99, 1]))

    def test_missing_detail_is_not_a_success(self):
        result = compare_masks(set(), {12, 13}, 10)
        self.assertEqual(result['detail_recall'], 0)
        self.assertEqual(result['intersection_over_union'], 0)
        self.assertIsNone(result['centroid_error_pixels'])

    def test_same_centroid_does_not_prove_shape(self):
        result = compare_masks({11, 13}, {2, 22}, 10)
        self.assertEqual(result['centroid_error_pixels'], 0)
        self.assertEqual(result['intersection_over_union'], 0)

    def test_translation_is_measured_in_pixels(self):
        self.assertEqual(compare_masks({13}, {12}, 10)['centroid_error_pixels'], 1)

    def test_normal_detail_threshold_and_region(self):
        pixels = [.5, .5, 1, 1, .8, .5, 1, 1, .5, .8, 1, 1]
        self.assertEqual(normal_detail(pixels, 3, {0, 1}), {1})


if __name__ == '__main__':
    unittest.main(verbosity=2)