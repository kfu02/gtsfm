"""Utility functions for comparing different types related to geometry.

Authors: Ayush Baid
"""
from typing import List, Optional

import numpy as np
from gtsam import Pose3, Rot3

EPSILON = np.finfo(float).eps


def align_rotations(input_list: List[Rot3], ref_list: List[Rot3]) -> List[Rot3]:
    """Aligns the list of rotations to the reference list by shifting origin.

    Args:
        input_list: input rotations which need to be aligned.
        ref_list: reference rotations which are target for alignment.

    Returns:
        transformed rotations which have the same origin as reference.
    """
    # map the origin of the input list to the reference list
    origin_transform = ref_list[0].compose(input_list[0].inverse())

    # apply the coordinate shift to all entries in input
    return [origin_transform.compose(x) for x in input_list]


def align_poses(input_list: List[Pose3], ref_list: List[Pose3]) -> List[Pose3]:
    """Aligns the list of poses to the reference list by shifting origin and
    scaling translations.

    Args:
        input_list: input poses which need to be aligned.
        ref_list: reference poses which are target for alignment.

    Returns:
        transformed poses which have the same origin and scale as reference.
    """
    origin_transform = ref_list[0].compose(input_list[0].inverse())

    origin_shifted_list = [origin_transform.compose(x) for x in input_list]

    # get distances w.r.t origin for both the list to compute the scale
    input_distances = np.array(
        [
            np.linalg.norm((x.between(origin_shifted_list[0])).translation())
            for x in origin_shifted_list[1:]
        ]
    )

    ref_distances = (
        np.array(
            [
                np.linalg.norm((x.between(ref_list[0])).translation())
                for x in ref_list[1:]
            ]
        )
        + EPSILON
    )

    scales = ref_distances / input_distances
    scaling_factor = np.median(scales)

    return [
        Pose3(x.rotation(), x.translation() * scaling_factor)
        for x in origin_shifted_list
    ]


def compare_rotations(
    wRi_list: List[Optional[Rot3]], wRi_list_: List[Optional[Rot3]]
) -> bool:
    """Helper function to compare two lists of global Rot3, considering the
    origin as ambiguous.

    Notes:
    1. The input lists have the rotations in the same order, and can contain
       None entries.
    2. To resolve global origin ambiguity, we will fix one image index as
       origin in both the inputs and transform both the lists to the new
       origins.

    Args:
        wRi_list: 1st list of rotations.
        wRi_list_: 2nd list of rotations.

    Returns:
        result of the comparison.
    """

    if len(wRi_list) != len(wRi_list_):
        return False

    # check the presense of valid Rot3 objects in the same location
    wRi_valid = [i for (i, wRi) in enumerate(wRi_list) if wRi is not None]
    wRi_valid_ = [i for (i, wRi) in enumerate(wRi_list_) if wRi is not None]
    if wRi_valid != wRi_valid_:
        return False

    if len(wRi_valid) <= 1:
        # we need >= two entries going forward for meaningful comparisons
        return False

    wRi_list = [wRi_list[i] for i in wRi_valid]
    wRi_list_ = [wRi_list_[i] for i in wRi_valid_]

    wRi_list = align_rotations(wRi_list, wRi_list_)

    return all(
        [wRi.equals(wRi_, 1e-1) for (wRi, wRi_) in zip(wRi_list, wRi_list_)]
    )


def compare_global_poses(
    wTi_list: List[Optional[Pose3]], wTi_list_: List[Optional[Pose3]]
) -> bool:
    """Helper function to compare two lists of global Pose3, considering the
    origin and scale ambiguous.

    Notes:
    1. The input lists have the poses in the same order, and can contain
       None entries.
    2. To resolve global origin ambiguity, we will fix one image index as
       origin in both the inputs and transform both the lists to the new
       origins.
    3. As there is a scale ambiguity, we use the median scaling factor to
       resolve the ambiguity.

    Args:
        wTi_list: 1st list of poses.
        wTi_list_: 2nd list of poses.

    Returns:
        results of the comparison.
    """

    # check the length of the input lists
    if len(wTi_list) != len(wTi_list_):
        return False

    # check the presense of valid Pose3 objects in the same location
    wTi_valid = [i for (i, wTi) in enumerate(wTi_list) if wTi is not None]
    wTi_valid_ = [i for (i, wTi) in enumerate(wTi_list_) if wTi is not None]
    if wTi_valid != wTi_valid_:
        return False

    if len(wTi_valid) <= 1:
        # we need >= two entries going forward for meaningful comparisons
        return False

    # align the remaining poses
    wTi_list = [wTi_list[i] for i in wTi_valid]
    wTi_list_ = [wTi_list_[i] for i in wTi_valid_]

    wTi_list = align_poses(wTi_list, wTi_list_)

    return all(
        [wTi.equals(wTi_, 1e-1) for (wTi, wTi_) in zip(wTi_list, wTi_list_)]
    )
