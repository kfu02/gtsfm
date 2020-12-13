# """Unit tests for the the main driver class.

# Authors: John Lambert, Ayush Baid
# """
import unittest
from pathlib import Path
# from typing import List, Optional

# import dask
# import numpy as np
# from gtsam import EssentialMatrix, Pose3, Rot3, Unit3

# import utils.geometry_comparisons as geometry_comparisons
from averaging.rotation.shonan import ShonanRotationAveraging
from averaging.translation.averaging_1dsfm import TranslationAveraging1DSFM
from frontend.detector_descriptor.sift import SIFTDetectorDescriptor
from frontend.matcher.twoway_matcher import TwoWayMatcher
from frontend.verifier.degensac import Degensac
# from scene_optimizer import SceneOptimizer
# from loader.folder_loader import FolderLoader


DATA_ROOT_PATH = Path(__file__).resolve().parent / 'data'


class TestSceneOptimizer(unittest.TestCase):
	"""[summary]

	Args:
	unittest ([type]): [description]
	"""

	def setUp(self) -> None:
		self.loader = FolderLoader(
			str(DATA_ROOT_PATH / 'set1_lund_door'), image_extension='JPG'
		)
		assert len(self.loader)
		self.obj = SceneOptimizer(
			detector_descriptor=SIFTDetectorDescriptor(),
			matcher=TwoWayMatcher(),
			verifier=Degensac(),
			rotation_averaging_module=ShonanRotationAveraging(),
			translation_averaging_module=TranslationAveraging1DSFM()
		)

	def test_create_computation_graph(self):
		""" """
		pdb.set_trace()
		exact_intrinsics_flag = False

		# run normally without dask
		expected_keypoints_list, \
		expected_global_rotations, \
		expected_global_translations, \
		expected_verified_corr_indices = self.obj.run(
		self.loader, exact_intrinsics=exact_intrinsics_flag)

#         expected_wTi_list = [Pose3(wRi, wti) if wti is not None else None for (
#             wRi, wti) in zip(expected_global_rotations, expected_global_translations)]

#         # generate the dask computation graph
#         keypoints_graph, \
#             global_rotations_graph, \
#             global_translations_graph, \
#             verified_corr_graph = self.obj.create_computation_graph(
#                 len(self.loader),
#                 self.loader.get_valid_pairs(),
#                 self.loader.create_computation_graph_for_images(),
#                 self.loader.create_computation_graph_for_intrinsics(),
#                 exact_intrinsics=exact_intrinsics_flag
#             )

#         with dask.config.set(scheduler='single-threaded'):
#             computed_keypoints_list = dask.compute(keypoints_graph)[0]
#             computed_global_rotations = dask.compute(
#                 global_rotations_graph)[0]
#             computed_global_translations = dask.compute(
#                 global_translations_graph)[0]
#             computed_verified_corr_indices = dask.compute(
#                 verified_corr_graph)[0]

#         computed_wTi_list = [Pose3(wRi, wti) if wti is not None else None for (
#             wRi, wti) in zip(computed_global_rotations, computed_global_translations)]

#         # compute the number of length of lists and dictionaries
#         self.assertEqual(len(computed_keypoints_list),
#                          len(expected_keypoints_list))
#         self.assertEqual(len(computed_global_rotations),
#                          len(expected_global_rotations))
#         self.assertEqual(len(computed_global_translations),
#                          len(expected_global_translations))
#         self.assertEqual(len(computed_verified_corr_indices),
#                          len(expected_verified_corr_indices))

#         # compare keypoints for all indices
#         self.assertListEqual(computed_keypoints_list, expected_keypoints_list)

#         # assert global rotations and translations
#         self.assertTrue(geometry_comparisons.compare_rotations(
#             computed_global_rotations, expected_global_rotations))
#         self.assertTrue(geometry_comparisons.compare_global_poses(
#             computed_wTi_list, expected_wTi_list))


#     def test_find_largest_connected_component(self):
#         """Tests the function to prune the scene graph to its largest connected
#         component."""

#         # create a graph with two connected components of length 4 and 3.
#         input_essential_matrices = {
#             (0, 1): generate_random_essential_matrix(),
#             (1, 5): None,
#             (1, 3): generate_random_essential_matrix(),
#             (3, 2): generate_random_essential_matrix(),
#             (2, 7): None,
#             (4, 6): generate_random_essential_matrix(),
#             (6, 7): generate_random_essential_matrix()
#         }

#         # generate Rot3 and Unit3 inputs
#         input_relative_rotations = dict()
#         input_relative_unit_translations = dict()
#         for (i1, i2), i2Ei1 in input_essential_matrices.items():
#             if i2Ei1 is None:
#                 input_relative_rotations[(i1, i2)] = None
#                 input_relative_unit_translations[(i1, i2)] = None
#             else:
#                 input_relative_rotations[(i1, i2)] = i2Ei1.rotation()
#                 input_relative_unit_translations[(i1, i2)] = i2Ei1.direction()

#         expected_edges = [(0, 1), (3, 2), (1, 3)]

#         computed_relative_rotations, computed_relative_unit_translations = \
#             GTSFM.select_largest_connected_component(
#                 input_relative_rotations, input_relative_unit_translations)

#         # check the edges in the pruned graph
#         self.assertCountEqual(
#             list(computed_relative_rotations.keys()), expected_edges)
#         self.assertCountEqual(
#             list(computed_relative_unit_translations.keys()), expected_edges)

#         # check the actual Rot3 and Unit3 values
#         for (i1, i2) in expected_edges:
#             self.assertTrue(
#                 computed_relative_rotations[(i1, i2)].equals(
#                     input_relative_rotations[(i1, i2)], 1e-2))
#             self.assertTrue(
#                 computed_relative_unit_translations[(i1, i2)].equals(
#                     input_relative_unit_translations[(i1, i2)], 1e-2))


# def generate_random_essential_matrix() -> EssentialMatrix:
#     rotation_angles = np.random.uniform(
#         low=0.0, high=2*np.pi, size=(3,))
#     R = Rot3.RzRyRx(
#         rotation_angles[0], rotation_angles[1], rotation_angles[2])
#     t = np.random.uniform(
#         low=-1.0, high=1.0, size=(3, ))

#     return EssentialMatrix(R, Unit3(T))


if __name__ == "__main__":
    unittest.main()
