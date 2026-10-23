"""Embedding math accepts injected encoders and stays independent of frameworks."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

import numpy as np

from src.core.analytics.similarity import cosine_matrix, encode_texts, top_matches


class SimilarityTests(unittest.TestCase):
    def test_empty_encoding_keeps_the_placeholder_shape_without_calling_encoder(self):
        encoder = Mock()
        result = encode_texts([], encoder=encoder)
        encoder.assert_not_called()
        self.assertEqual(result.shape, (0, 1))
        self.assertEqual(result.dtype, np.float64)

    def test_encoding_preserves_array_identity_and_normalization_options(self):
        values = np.asarray([[1, 0]], dtype=np.float32)
        encoder = Mock(return_value=values)
        self.assertIs(encode_texts(['text'], encoder=encoder), values)
        encoder.assert_called_once_with(['text'], convert_to_numpy=True, normalize_embeddings=True,
                                        show_progress_bar=False, batch_size=32)

    def test_encoding_converts_lists_to_float_arrays(self):
        result = encode_texts(['a', 'b'], encoder=lambda *args, **kwargs: [[1, 0], [0, 1]])
        np.testing.assert_array_equal(result, np.eye(2))
        self.assertEqual(result.dtype, np.float64)

    def test_normalized_vectors_produce_signed_cosine_scores(self):
        left = np.asarray([[1, 0], [0, 1], [-1, 0]], dtype=np.float32)
        right = np.asarray([[1, 0], [0, -1]], dtype=np.float32)
        left_before, right_before = left.copy(), right.copy()
        result = cosine_matrix(left, right)
        np.testing.assert_array_equal(result, [[1, 0], [0, -1], [-1, 0]])
        self.assertEqual(result.dtype, np.float32)
        np.testing.assert_array_equal(left, left_before)
        np.testing.assert_array_equal(right, right_before)

    def test_matrix_does_not_apply_a_second_normalization_or_clip_scores(self):
        np.testing.assert_array_equal(cosine_matrix(np.asarray([[2.0, 0]]), np.asarray([[3.0, 0]])), [[6.0]])

    def test_empty_inputs_keep_row_counts_even_when_feature_widths_differ(self):
        for left, right, expected in ((np.empty((0, 1)), np.empty((3, 8)), (0, 3)),
                                      (np.empty((2, 8)), np.empty((0, 1)), (2, 0)),
                                      (np.empty((2, 0)), np.empty((3, 4)), (2, 3))):
            with self.subTest(shape=expected):
                result = cosine_matrix(left, right)
                self.assertEqual(result.shape, expected)
                np.testing.assert_array_equal(result, np.zeros(expected))

    def test_incompatible_nonempty_dimensions_keep_numpy_validation(self):
        with self.assertRaises(ValueError):
            cosine_matrix(np.ones((2, 3)), np.ones((4, 5)))

    def test_top_matches_preserve_indexes_descending_order_and_clipping(self):
        row = np.asarray([0.25, -0.5, 1.2, 0.75])
        original = row.copy()
        self.assertEqual(top_matches(row, 3), [(2, 1.0), (3, 0.75), (0, 0.25)])
        self.assertEqual(top_matches(row, 10)[-1], (1, 0.0))
        np.testing.assert_array_equal(row, original)

    def test_empty_and_zero_length_rankings_are_empty(self):
        self.assertEqual(top_matches(np.asarray([]), 3), [])
        self.assertEqual(top_matches(np.asarray([0.5]), 0), [])

    def test_import_and_execution_do_not_load_frameworks_or_model_runtimes(self):
        script = '''import importlib.abc,sys
class BlockFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'django','celery','modules','torch','sentence_transformers','transformers'}:
            raise ImportError('Unexpected runtime import: '+fullname)
sys.meta_path.insert(0,BlockFramework())
import numpy as np
from src.core.analytics.similarity import encode_texts,cosine_matrix,top_matches
values=encode_texts(['text'],encoder=lambda *a,**k: [[1,0]])
assert top_matches(cosine_matrix(values,values)[0],1)==[(0,1.0)]
'''
        environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4])}
        result = subprocess.run([sys.executable, '-c', script], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
