"""Utilities for the multi-view stereo (MVS) stage of the back-end.

Authors: Ren Liu, Ayush Baid
"""
import math
from typing import Tuple

import numpy as np
from gtsam import PinholeCameraCal3Bundler, Unit3

import gtsfm.visualization.open3d_vis_utils as open3d_vis_utils
from gtsfm.utils import ellipsoid as ellipsoid_utils
from gtsfm.utils import geometry_comparisons as geometry_utils


def calculate_triangulation_angle_in_degrees(
    camera_1: PinholeCameraCal3Bundler, camera_2: PinholeCameraCal3Bundler, point_3d: np.ndarray
) -> float:
    """Calculates the angle formed at the 3D point by the rays backprojected from 2 cameras.
    In the setup with X (point_3d) and two cameras C1 and C2, the triangulation angle is the angle between rays C1-X
    and C2-X, i.e. the angle subtendted at the 3d point.
        X
       / \
      /   \
     /     \
    C1      C2
    References:
    - https://github.com/colmap/colmap/blob/dev/src/base/triangulation.cc#L122
    Args:
        camera_1: the first camera.
        camera_2: the second camera.
        point_3d: the 3d point which is imaged by the two camera centers, and where the angle between the light rays 
                  associated with the measurements are computed.
    Returns:
        the angle formed at the 3d point, in degrees.
    """
    camera_center_1: np.ndarray = camera_1.pose().translation()
    camera_center_2: np.ndarray = camera_2.pose().translation()

    # compute the two rays
    ray_1 = point_3d - camera_center_1
    ray_2 = point_3d - camera_center_2

    return geometry_utils.compute_relative_unit_translation_angle(Unit3(ray_1), Unit3(ray_2))


def piecewise_gaussian(theta: float, theta_0: float = 5, sigma_1: float = 1, sigma_2: float = 10) -> float:
    """A Gaussian function that favors a certain baseline angle (theta_0).

    The Gaussian function is divided into two pieces with different standard deviations:
    - If the input baseline angle (theta) is no larger than theta_0, the standard deviation will be sigma_1;
    - If theta is larger than theta_0, the standard deviation will be sigma_2.

    More details can be found in "View Selection" paragraphs in Yao's paper https://arxiv.org/abs/1804.02505.

    Args:
        theta: the input baseline angle.
        theta_0: defaults to 5, the expected baseline angle of the function.
        sigma_1: defaults to 1, the standard deviation of the function when the angle is no larger than theta_0.
        sigma_2: defaults to 10, the standard deviation of the function when the angle is larger than theta_0.

    Returns:
        the result of the Gaussian function, in range (0, 1]
    """

    # Decide the standard deviation according to theta and theta_0
    # if theta is no larger than theta_0, the standard deviation is sigma_1
    if theta <= theta_0:
        sigma = sigma_1
    # if theta is larger than theta_0, the standard deviation is sigma_2
    else:
        sigma = sigma_2

    return math.exp(-((theta - theta_0) ** 2) / (2 * sigma ** 2))


def cart_to_homogenous(
    non_homogenous_coordinates: np.ndarray,
) -> np.ndarray:
    """Convert cartesian coordinates to homogenous system (by appending a row of ones).
    Args:
        non_homogenous_coordinates: d-dim non-homogenous coordinates, of shape dxN.

    Returns:
        (d+1)-dim homogenous coordinates, of shape (d+1)xN.

    Raises:
        TypeError if input non_homogenous_coordinates is not 2 dimensional.
    """

    if len(non_homogenous_coordinates.shape) != 2:
        raise TypeError("Input non-homogenous coordinates should be 2 dimensional")

    n = non_homogenous_coordinates.shape[1]

    return np.vstack([non_homogenous_coordinates, np.ones((1, n))])


def estimate_minimum_voxel_size(points: np.ndarray, scale: float = 0.02) -> float:
    """Estimate the minimum voxel size for point cloud simplification by downsampling
        1. compute the minimum semi-axis length of a centered point cloud by eigendecomposition,
            See Ellipsoid from point cloud: https://forge.epn-campus.eu/svn/vtas/vTIU/doc/ellipsoide.pdf
        2. scale it to obtain the minimum voxel size for point cloud simplification by downsampling

    Args:
        points: array of shape (N,3)
        scale: expected scale from the minimum semi-axis length to the output voxel size. Defaults to 0.02.

    Returns:
        the minimum voxel size for point cloud simplification by downsampling
    """
    N = points.shape[0]

    # center the point cloud
    centered_points = ellipsoid_utils.center_point_cloud(points)

    # get squared semi-axis lengths in all axes of the centered point cloud
    eigvals, _ = ellipsoid_utils.sorted_eigendecomposition(centered_points / np.sqrt(N - 1))

    # set the minimum voxel size as the scaled minimum semi-axis length
    return np.sqrt(eigvals[-1]) * scale


def downsample_point_cloud(
    points: np.ndarray, rgb: np.ndarray, voxel_size: float = 0.02
) -> Tuple[np.ndarray, np.ndarray]:
    """Use voxel downsampling to create a uniformly downsampled point cloud from an input point cloud.

    The algorithm uses a regular voxel grid and operates in two steps
        1. Points are bucketed into voxels.
        2. Each occupied voxel generates exactly one point by averaging all points inside.
    See http://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html#Voxel-downsampling

    Args:
        points: array of shape (N,3)
        rgb: array of shape (N,3)
        voxel_size: size of voxel.

    Returns:
        points_downsampled: array of shape (M,3) where M <= N
        rgb_downsampled: array of shape (M,3) where M <= N
    """

    # if voxel_size is invalid, do not downsample the point cloud
    if voxel_size <= 0:
        return points, rgb

    pcd = open3d_vis_utils.create_colored_point_cloud_open3d(point_cloud=points, rgb=rgb)
    pcd = pcd.voxel_down_sample(voxel_size=voxel_size)

    points_downsampled, rgb_downsampled = open3d_vis_utils.convert_colored_open3d_point_cloud_to_numpy(pcd)
    return points_downsampled, rgb_downsampled
