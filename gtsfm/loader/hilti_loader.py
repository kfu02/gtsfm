"""Hilti dataset loader.

The dataset should be preprocessed to extract images in sync with the lidar information.

Folder structure:
- images/*.jpg: contains images from the 5 cameras with the following naming convention: 0-4 from the 0th lidar
    timestamp, 5-9 from the 1st, and so on.
- calibration/: contains the calibration data downloaded from Hilti's official website
- lidar/ contains files fastlio2.g2o and fastlio2_odom.txt from the SLAM.

Dataset ref: https://rpg.ifi.uzh.ch/docs/Arxiv21_HILTI.pdf
Kalibr format for intrinsics: https://github.com/ethz-asl/kalibr/wiki/yaml-formats

Authors: Ayush Baid
"""
import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml

import numpy as np
import gtsam
from gtsam import Cal3Fisheye, Pose3, Rot3, Point3
from gtsfm.pose_slam.pose_slam import PoseSlam

import gtsfm.utils.io as io_utils
import gtsfm.utils.logger as logger_utils
from gtsfm.common.constraint import Constraint
from gtsfm.common.image import Image
from gtsfm.common.pose_prior import PosePrior, PosePriorType
from gtsfm.loader.loader_base import LoaderBase


logger = logger_utils.get_logger()

NUM_CAMS = 5

CAM_IDX_TO_KALIBR_FILE_MAP = {
    0: "calib_3_cam0-1-camchain-imucam.yaml",
    1: "calib_3_cam0-1-camchain-imucam.yaml",
    2: "calib_3_cam2-camchain-imucam.yaml",
    3: "calib_3_cam3-camchain-imucam.yaml",
    4: "calib_3_cam4-camchain-imucam.yaml",
}

GT_POSE_RELATIVE_PATH = "lidar/fastlio_odom.txt"
LIDAR_POSE_RELATIVE_PATH = "lidar/fastlio2.g2o"
LIDAR_CONSTRAINTS_RELATIVE_PATH = "lidar/constraints.txt"
IMAGES_FOLDER = "images"

HARD_POSE_PRIOR_COVARIANCE = np.eye(6) * 1e-8
STATIONARY_POSE_PRIOR_COVARIANCE = np.eye(6) * 1e-7
CAM2_BACKBONE_POSE_PRIOR_COVARIANCE = np.diag(np.array([np.deg2rad(30.0), np.deg2rad(30.0), np.deg2rad(30.0), 1, 1, 1]))


class HiltiLoader(LoaderBase):
    def __init__(
        self,
        base_folder: str,
        max_length: Optional[int] = None,
        max_resolution: int = 1080,
        subsample: int = 1,
        old_style: bool = False,
        add_backbone: bool = True,
    ) -> None:
        """Initializes, loads calibration, constraints, and pose priors.

        Args:
            base_folder: top-level folder, expects calibration, images and lidar subfolders.
            max_length: limit poses to read. Defaults to None.
            max_resolution: integer representing maximum length of image's short side
               e.g. for 1080p (1920 x 1080), max_resolution would be 1080
            subsample: subsample along the time axis, default 1 (none).
            old_style: Use old-style sequential image numbering.
            add_backbone: add a backbone of soft constraints for CAM2-CAM2 pairs.
        """
        super().__init__(max_resolution)
        self._base_folder: Path = Path(base_folder)
        self._max_length = max_length
        self._subsample = subsample
        self._old_style = old_style
        self._add_backbone = add_backbone

        # Load calibration.
        self._intrinsics: Dict[int, Cal3Fisheye] = {}
        self._cam_T_imu_poses: Dict[int, Pose3] = {}
        for cam_idx in range(NUM_CAMS):
            calibration = self.__load_calibration(cam_idx)
            self._intrinsics[cam_idx] = calibration[0]
            self._cam_T_imu_poses[cam_idx] = calibration[1]

        # Jacobian for transforming covariance
        self._cam2_J_imu_relative: np.array = self._cam_T_imu_poses[2].AdjointMap()

        # Check how many images are on disk.
        self.num_rig_poses: int = self.__get_num_rig_poses()
        if self._max_length is not None:
            self.num_rig_poses = min(self.num_rig_poses, self._max_length)

        # Read GT poses from odom file:
        self._fastlio_poses = self.__read_fastlio_poses()

        # Read the constraints from the lidar/constraints file
        all_constraints: Dict[Tuple[int, int], Constraint] = self.__load_constraints()
        logger.info("[hilti_loader] Number of filtered constraints: %d", len(all_constraints))
        filtered_constraints: Dict[Tuple[int, int], Constraint] = self._filter_outlier_constraints(all_constraints)
        self._constraints: Dict[Tuple[int, int], Constraint] = self._update_stationary_constraints(filtered_constraints)

        logger.info("[hilti_loader] Number of constraints: %d", len(self._constraints))

        # Read the poses for the IMU for rig indices from g2o file.
        self._w_T_imu: Dict[int, Pose3] = dict(
            enumerate(self._fastlio_poses)
        )  # Quick hack! self.__read_lidar_pose_priors()

        logger.info("[hilti_loader] Loading %d timestamps", self.num_rig_poses)
        logger.info("[hilti_loader] Lidar camera available for %d timestamps", len(self._w_T_imu))

    def __load_constraints(self) -> Dict[Tuple[int, int], Constraint]:
        constraints_path = self._base_folder / LIDAR_CONSTRAINTS_RELATIVE_PATH
        all_constraints = Constraint.read(str(constraints_path))
        constraints = PoseSlam.filter_constraints(all_constraints, self._fastlio_poses)

        # filter them according to max length
        constraints = list(filter(lambda c: c.a < self.num_rig_poses and c.b < self.num_rig_poses, constraints))

        # cast them to dictionary
        return {(constraint.a, constraint.b): constraint for constraint in constraints}

    def _update_stationary_constraints(
        self, constraints: Dict[Tuple[int, int], Constraint]
    ) -> Dict[Tuple[int, int], Constraint]:
        updated_constraints = {}
        TRANSLATION_THRESHOLD = 0.02
        ROTATION_THRESHOLD = np.deg2rad(0.5)
        num_stationary_constraints = 0
        for (a, b), constraint in constraints.items():
            # Not stationary if either rotation or translation is high enough.
            if (
                np.linalg.norm(Rot3.Logmap(constraint.aTb.rotation())) > ROTATION_THRESHOLD
                or np.linalg.norm(constraint.aTb.translation()) > TRANSLATION_THRESHOLD
            ):
                updated_constraints[(a, b)] = constraint
                continue

            updated_constraint = Constraint(
                constraint.a, constraint.b, Pose3(), STATIONARY_POSE_PRIOR_COVARIANCE, constraint.counts
            )
            updated_constraints[(a, b)] = updated_constraint
            num_stationary_constraints += 1
        logger.info(f"[hilti loader] Found {num_stationary_constraints} stationary constraints")
        return updated_constraints

    def _filter_outlier_constraints(
        self, constraints: Dict[Tuple[int, int], Constraint]
    ) -> Dict[Tuple[int, int], Constraint]:
        """Removes 1-step constraints for which the translation magnitude is greater than 2 or 3-step constraints."""
        constraint_magnitudes = {}
        for (a, b), constraint in constraints.items():
            c, d = min(a, b), max(a, b)
            # no need to invert, norm will be the same.
            constraint_magnitudes[(c, d)] = np.linalg.norm(constraint.aTb.translation())

        def is_higher_step_magnitude_lesser(a, b, all_magnitudes, step_size):
            ERROR_MARGIN = 0.1  # meters
            c, d = min(a, b), max(a, b)
            this_magnitude = all_magnitudes[(c, d)]
            step_magnitude = all_magnitudes[(c, d + step_size)] if (c, d + step_size) in all_magnitudes else None
            return step_magnitude is not None and this_magnitude - step_magnitude > ERROR_MARGIN

        filtered_constraints = {}
        rot_sigma = np.deg2rad(60)
        trans_sigma = 10  # meters
        FILTERED_COVARIANCE = np.diag([rot_sigma, rot_sigma, rot_sigma, trans_sigma, trans_sigma, trans_sigma])
        for (a, b), constraint in constraints.items():
            # Accept all constraint with step > 1
            if abs(a - b) != 1:
                filtered_constraints[(a, b)] = constraint
                continue
            # Do not include if a higher-step magnitude is lesser (for steps of size 2 and 3)
            if is_higher_step_magnitude_lesser(a, b, constraint_magnitudes, 1) or is_higher_step_magnitude_lesser(
                a, b, constraint_magnitudes, 2
            ):
                filtered_constraints[(a, b)] = Constraint(
                    constraint.a, constraint.b, constraint.aTb, FILTERED_COVARIANCE, constraint.counts
                )
                continue
            filtered_constraints[(a, b)] = constraint
        return filtered_constraints

    def get_all_constraints(self) -> List[Constraint]:
        return list(self._constraints.values())

    def get_camTimu(self) -> Dict[int, Pose3]:
        return self._cam_T_imu_poses

    def __read_lidar_pose_priors(self) -> Dict[int, Pose3]:
        """Read the poses for the IMU for rig indices."""
        filepath = str(self._base_folder / LIDAR_POSE_RELATIVE_PATH)
        _, values = gtsam.readG2o(filepath, is3D=True)

        lidar_keys = values.keys()
        logger.info("[hilti_loader] Number of keys in g2o file: %d", len(lidar_keys))

        w_T_imu: Dict[int, Pose3] = {}

        for rig_idx in range(self.num_rig_poses):
            if rig_idx in lidar_keys:
                w_T_imu[rig_idx] = values.atPose3(rig_idx)

        return w_T_imu

    def __read_fastlio_poses(self) -> List[Pose3]:
        """Read the poses for the IMU for rig indices."""
        filepath = str(self._base_folder / GT_POSE_RELATIVE_PATH)

        def pose_of_vector(pose_vector):
            """Convert from vector to Pose3"""
            pose_rotation = Rot3(pose_vector[-1], pose_vector[3], pose_vector[4], pose_vector[5])
            pose_translation = Point3(pose_vector[:3])
            return Pose3(pose_rotation, pose_translation)

        poses = np.loadtxt(filepath)[:, 1:]
        logger.info("[hilti_loader] Read %d poses from %s", poses.shape[0], filepath)
        return [pose_of_vector(pose) for pose in poses]

    def __get_num_rig_poses(self) -> int:
        """Check how many images we have on disk and deduce number of rig poses."""
        pattern = "*.jpg" if self._old_style else "*.png"
        search_path: str = str(self._base_folder / IMAGES_FOLDER / pattern)

        if self._old_style:
            image_files = glob.glob(search_path)
            total_num_images = len(image_files)
            return total_num_images // NUM_CAMS
        else:
            image_fnames = [Path(f).stem for f in glob.glob(search_path)]
            rig_indices = [int(fname.split("_")[0]) for fname in image_fnames]
            return max(rig_indices) + 1

    def __load_calibration(self, cam_idx: int) -> Tuple[Cal3Fisheye, Pose3]:
        """Load calibration from kalibr files in calibration sub-folder."""
        kalibr_file_path = self._base_folder / "calibration" / CAM_IDX_TO_KALIBR_FILE_MAP[cam_idx]

        with open(kalibr_file_path, "r") as file:
            calibration_data = yaml.safe_load(file)
            if cam_idx != 1:
                calibration_data = calibration_data["cam0"]
            else:
                calibration_data = calibration_data["cam1"]

            assert calibration_data["camera_model"] == "pinhole"
            assert calibration_data["distortion_model"] == "equidistant"

            intrinsics: Cal3Fisheye = self.__load_intrinsics(calibration_data)
            cam_T_imu: Pose3 = self.__load_pose_relative_to_imu(calibration_data)

        return intrinsics, cam_T_imu

    def __load_intrinsics(self, calibration_data: Dict[Any, Any]) -> Cal3Fisheye:
        """Create gtsam.Cal3Fisheye object from calibration data."""
        fx, fy, px, py = calibration_data["intrinsics"]
        k1, k2, k3, k4 = calibration_data["distortion_coeffs"]

        return Cal3Fisheye(fx=fx, fy=fy, s=0, u0=px, v0=py, k1=k1, k2=k2, k3=k3, k4=k4)

    def __load_pose_relative_to_imu(self, calibration_data: Dict[Any, Any]) -> Pose3:
        """Create gtsam.Pose3 object from calibration data"""
        transformation_matrix: np.ndarray = calibration_data["T_cam_imu"]
        return Pose3(transformation_matrix)

    def __len__(self) -> int:
        """
        The number of images in the dataset.

        Returns:
            the number of images.
        """
        return self.num_rig_poses * NUM_CAMS

    def get_image(self, index: int) -> Optional[Image]:
        return self.get_image_full_res(index)

    # def get_image_undistorted(self, index: int) -> Image:
    #     distorted_image: Image = self.get_image(index)
    #     calibration: Cal3Fisheye = self.get_camera_intrinsics(index)

    #     new_image_size = (1500, 1500)
    #     Knew = calibration.K()
    #     Knew[0, 2] = 750
    #     Knew[1, 2] = 750

    #     undistorted_image_array: np.ndarray = cv2.fisheye.undistortImage(
    #         distorted_image.value_array,
    #         calibration.K(),
    #         np.array([calibration.k1(), calibration.k2(), calibration.k3(), calibration.k4()]),
    #         Knew=Knew,
    #         new_size=new_image_size,
    #     )

    #     return Image(value_array=undistorted_image_array, exif_data={})

    def get_image_full_res(self, index: int) -> Optional[Image]:
        """Get the image at the given index, at full resolution.

        Args:
            index: the index to fetch.

        Raises:
            IndexError: if an out-of-bounds image index is requested.

        Returns:
            Image: the image at the query index.
        """
        if self._old_style:
            filename = f"{index}.jpg"
        else:
            filename = f"{self.rig_from_image(index)}_{self.camera_from_image(index)}.png"

        try:
            image_path: Path = self._base_folder / IMAGES_FOLDER / filename
            return io_utils.load_image(str(image_path))
        except:
            return None

    def get_camera_intrinsics(self, index: int) -> Optional[Cal3Fisheye]:
        return self.get_camera_intrinsics_full_res(index)

    def get_camera_intrinsics_full_res(self, index: int) -> Optional[Cal3Fisheye]:
        """Get the camera intrinsics at the given index, valid for a full-resolution image.

        Args:
            the index to fetch.

        Returns:
            intrinsics for the given camera.
        """
        return self._intrinsics[self.camera_from_image(index)]

    def get_camera_pose(self, index: int) -> Optional[Pose3]:
        """Get the camera pose (in world coordinates) at the given index.

        Note: temporarily using the lidar poses as ground truth

        Args:
            index: the index to fetch.

        Returns:
            the camera pose w_P_index.
        """
        rig_idx: int = self.rig_from_image(index)
        cam_idx: int = self.camera_from_image(index)

        if rig_idx in self._w_T_imu:
            return self._w_T_imu[rig_idx] * self._cam_T_imu_poses[cam_idx].inverse()

        return None

    def get_relative_pose_prior(self, i1: int, i2: int) -> Optional[PosePrior]:
        """Creates prior on relative pose i2Ti1.

        If the images are on the same rig, then creates a hard pose prior between the two images, to be used by the
        two-view estimator. If they are not, we create a soft pose prior derived from the absolute poses (w_T_imu)
        passed in the constructor.

        Args:
            i1: index of first image.
            i2: index of second image.

        Returns:
            Pose prior, if it exists.
        """
        rig_idx_for_i1: int = self.rig_from_image(i1)
        rig_idx_for_i2: int = self.rig_from_image(i2)
        cam_idx_for_i1: int = self.camera_from_image(i1)
        cam_idx_for_i2: int = self.camera_from_image(i2)

        if rig_idx_for_i1 == rig_idx_for_i2:
            i1_T_imu: Pose3 = self._cam_T_imu_poses[cam_idx_for_i1]
            i2_T_imu: Pose3 = self._cam_T_imu_poses[cam_idx_for_i2]
            i1Ti2 = i1_T_imu * i2_T_imu.inverse()
            return PosePrior(value=i1Ti2, covariance=HARD_POSE_PRIOR_COVARIANCE, type=PosePriorType.HARD_CONSTRAINT)
        elif cam_idx_for_i1 == 2 and cam_idx_for_i2 == 2 and (rig_idx_for_i1, rig_idx_for_i2) in self._constraints:
            constraint = self._constraints[(rig_idx_for_i1, rig_idx_for_i2)]
            imui1_T_imui2 = constraint.aTb
            i1Ti2 = self._cam_T_imu_poses[2] * imui1_T_imui2 * self._cam_T_imu_poses[2].inverse()
            cov_i1Ti2 = self._cam2_J_imu_relative @ constraint.cov @ self._cam2_J_imu_relative.T

            # Rig is stationary, add a hard constraint.
            if i1Ti2.equals(Pose3(), 1e-6):
                return PosePrior(value=i1Ti2, covariance=cov_i1Ti2, type=PosePriorType.HARD_CONSTRAINT)

            return PosePrior(value=i1Ti2, covariance=cov_i1Ti2, type=PosePriorType.SOFT_CONSTRAINT)
        elif cam_idx_for_i1 == 2 and cam_idx_for_i2 == 2:
            # CAM2-CAM2 backbone as soft prior
            w_T_imui1 = self._fastlio_poses[rig_idx_for_i1]
            w_T_imui2 = self._fastlio_poses[rig_idx_for_i2]
            imui1_T_imui2 = w_T_imui1.between(w_T_imui2)
            i1Ti2 = self._cam_T_imu_poses[2] * imui1_T_imui2 * self._cam_T_imu_poses[2].inverse()

            return PosePrior(
                value=i1Ti2, covariance=CAM2_BACKBONE_POSE_PRIOR_COVARIANCE, type=PosePriorType.SOFT_CONSTRAINT
            )

        return None

    def get_absolute_pose_prior(self, idx: int) -> Optional[PosePrior]:
        return None

    def camera_from_image(self, index: int) -> int:
        """Map image index to camera-on-rig index."""
        return index % NUM_CAMS

    def rig_from_image(self, index: int) -> int:
        """Map image index to rig index."""
        return index // NUM_CAMS

    def image_from_rig_and_camera(self, rig_index: int, camera_idx: int) -> int:
        """Map image index to rig index."""
        return rig_index * NUM_CAMS + camera_idx

    def get_relative_pose_priors(self) -> Dict[Tuple[int, int], PosePrior]:
        unique_pairs = set()
        # For every rig index, add a "star" from camera 2 to 0,1,3,4:
        for rig_index in range(0, self.num_rig_poses, self._subsample):
            camera_2 = self.image_from_rig_and_camera(rig_index, 2)
            for cam_idx in [0, 1]:
                unique_pairs.add((self.image_from_rig_and_camera(rig_index, cam_idx), camera_2))
            for cam_idx in [3, 4]:
                unique_pairs.add((camera_2, self.image_from_rig_and_camera(rig_index, cam_idx)))

        # Translate all rig level constraints to CAM2-CAM2 constraints
        for a, b in self._constraints.keys():
            unique_pairs.add((self.image_from_rig_and_camera(a, 2), self.image_from_rig_and_camera(b, 2)))

        logger.info("Pairs for relative pose before adding backbone: %d", len(unique_pairs))
        if self._add_backbone:
            # add the full backbone of CAM2-CAM2 pairs
            for a in range(self.num_rig_poses - 1):
                b = a + 1
                unique_pairs.add((self.image_from_rig_and_camera(a, 2), self.image_from_rig_and_camera(b, 2)))

        logger.info("Pairs for relative pose after adding backbone: %d", len(unique_pairs))

        import pdb

        pdb.set_trace()

        optional_priors = {pair: self.get_relative_pose_prior(*pair) for pair in unique_pairs}
        priors = {pair: prior for pair, prior in optional_priors.items() if prior is not None}

        return priors

    def get_image_fnames(self) -> List[str]:
        """Get image name for all the images."""
        image_fnames = []
        for i in range(len(self)):
            if self._old_style:
                filename = f"{i}.jpg"
            else:
                filename = f"{self.rig_from_image(i)}_{self.camera_from_image(i)}.png"

            image_fnames.append(filename)

        return image_fnames
