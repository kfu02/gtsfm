"""Train a simple outlier rejection classifier based on rotation cycle consistency information and #inliers  / %inliers.

Author: John Lambert
"""

import argparse
import glob
import math
from types import SimpleNamespace
from typing import List, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset

import gtsfm.utils.io as io_utils
import gtsfm.utils.logger as logger_utils

logger = logger_utils.get_logger()

INTERP_FEATURE_DIM = 8

TRAIN_PERCENT = 80
VAL_PERCENT = 20

# From: https://github.com/pytorch/examples/blob/master/imagenet/main.py#L363
class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self, name, fmt=":f"):
        self.name = name
        self.fmt = fmt
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

    def __str__(self):
        fmtstr = "{name} {val" + self.fmt + "} ({avg" + self.fmt + "})"
        return fmtstr.format(**self.__dict__)


class SimpleModel(nn.Module):
    def __init__(self) -> None:
        """ """
        super(SimpleModel, self).__init__()
        num_classes = 2
        self.fc1 = nn.Linear(INTERP_FEATURE_DIM + 3, 256)
        self.fc2 = nn.Linear(256, num_classes)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """ """
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x


def create_fixed_length_feature(
    edge_cycle_errors: List[float], inlier_ratio_est_model: float, num_inliers_est_model: int
) -> torch.Tensor:
    """
    Form a feature from rotation cycle consistency information and #inliers  / %inliers.
    """
    num_participating_cycles = len(edge_cycle_errors)
    edge_cycle_errors.sort()
    # print("Edge cycle errors: ", edge_cycle_errors)
    edge_cycle_errors = torch.tensor(edge_cycle_errors)
    edge_cycle_errors = edge_cycle_errors.reshape(1, 1, -1)
    cycle_error_feat = torch.nn.functional.interpolate(input=edge_cycle_errors, size=INTERP_FEATURE_DIM, mode="linear")
    cycle_error_feat = cycle_error_feat.reshape(INTERP_FEATURE_DIM)

    feature_vec = torch.zeros(INTERP_FEATURE_DIM + 3)
    feature_vec[:INTERP_FEATURE_DIM] = cycle_error_feat
    feature_vec[INTERP_FEATURE_DIM] = inlier_ratio_est_model
    feature_vec[INTERP_FEATURE_DIM + 1] = num_inliers_est_model
    feature_vec[INTERP_FEATURE_DIM + 2] = num_participating_cycles
    return feature_vec


def test_create_fixed_length_feature() -> None:
    """ " """
    edge_cycle_errors = [0.08, 2.1, 2.1, 2.4, 3.0, 12.3]
    create_fixed_length_feature(edge_cycle_errors, 0.1, 0.9)

    edge_cycle_errors = [18.8, 20.8, 25.3, 27.3, 30.2, 30.7]
    create_fixed_length_feature(edge_cycle_errors, 0.1, 0.9)

    edge_cycle_errors = [6.3, 7.2, 8.5, 12.3, 16.4, 18.8]
    create_fixed_length_feature(edge_cycle_errors, 0.1, 0.9)


def compute_population_statistics(fpaths: List[str]) -> Tuple[torch.Tensor, torch.Tensor]:
    """Compute population statistics for normalizing the data."""

    features_stacked = []

    for fpath in fpaths:
        d = io_utils.read_json_file(fpath)
        feature = create_fixed_length_feature(
            d["edge_cycle_errors"], d["inlier_ratio_est_model"], d["num_inliers_est_model"]
        )
        features_stacked.append(feature)

    features_stacked = torch.stack(features_stacked)
    mean = torch.mean(features_stacked, dim=0)
    std = torch.std(features_stacked, dim=0)

    return mean, std


class SimpleData(Dataset):
    def __init__(self, split: str, train_data_dirpath: str, test_data_dirpath: str) -> None:
        """
        Args:
            split
            train_data_dirpath
            test_data_dirpath
        """
        if test_data_dirpath is None:
            # siphon off val split from training data
            all_fpaths = glob.glob(f"{train_data_dirpath}/*.json")
            all_fpaths.sort()

            num_train_examples = math.ceil(len(all_fpaths) * TRAIN_PERCENT / 100)
            train_fpaths = all_fpaths[:num_train_examples]
            val_fpaths = all_fpaths[num_train_examples:]
        else:
            train_fpaths = glob.glob(f"{train_data_dirpath}/*.json")
            val_fpaths = glob.glob(f"{test_data_dirpath}/*.json")

        self.mean, self.std = compute_population_statistics(train_fpaths)

        if split == "train":
            self.fpaths = train_fpaths

        elif split == "val":
            self.fpaths = val_fpaths

        self.split = split

        logger.info("%s has %d examples", split, len(self.fpaths))

    def __len__(self) -> int:
        return len(self.fpaths)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
        """ """
        fpath = self.fpaths[index]
        d = io_utils.read_json_file(fpath)
        feature = create_fixed_length_feature(
            d["edge_cycle_errors"], d["inlier_ratio_est_model"], d["num_inliers_est_model"]
        )

        if self.split == "train":

            if np.random.rand() < 0.5:
                # on num edges
                feature[-1] += 1

            noise = torch.randn(8)
            noise, _ = torch.sort(noise)
            feature[:INTERP_FEATURE_DIM] += noise
            feature[:INTERP_FEATURE_DIM] = torch.clamp(feature[:INTERP_FEATURE_DIM], min=0.01)

            if np.random.rand() < 0.5:
                noise = torch.zeros(1)
                noise.uniform_(-0.03, 0.03)
                # inlier ratio
                feature[-3] += noise.squeeze()

            if np.random.rand() < 0.5:
                noise = torch.randint(low=-5, high=5, size=(1, 1))
                # inliers
                feature[-2] += noise.squeeze()

        # TODO: zero-center and normalize the data.
        feature = (feature - self.mean) / self.std

        y = 1 if d["R_error_deg"] < 5 else 0
        return feature, y


def get_dataloader(split_data: SimpleData, batch_size: int, workers: int) -> torch.utils.data.DataLoader:
    """ """
    split = split_data.split
    drop_last = True if split == "train" else False

    # note: we don't shuffle for the "val" or "test" splits
    split_loader = torch.utils.data.DataLoader(
        split_data,
        batch_size=batch_size,
        shuffle=True if split == "train" else False,
        num_workers=workers,
        pin_memory=True,
        drop_last=drop_last,
        sampler=None,
    )
    return split_loader


def compute_accuracy(logits: torch.Tensor, y_true: torch.Tensor) -> Tuple[float, float, float]:
    """Compute f1-score, precision, and recall of predictions."""
    y_pred = logits.argmax(dim=1)

    tp = torch.logical_and(y_true == 1, y_pred == 1).sum()
    fp = torch.logical_and(y_true == 0, y_pred == 1).sum()
    fn = torch.logical_and(y_true == 1, y_pred == 0).sum()

    eps = 1e-12
    precision = tp * 1.0 / (tp + fp + eps)
    recall = tp * 1.0 / (tp + fn + eps)
    f1 = 2 * (precision * recall) / (precision + recall + eps)

    return f1, precision, recall


def test_compute_accuracy_perfect() -> None:
    """ """
    # fmt: off
    logits = torch.tensor(
        [
            [0.3, 0.7],
            [0.9, 0.1],
            [0.6, 0.4]
        ]
    )
    # fmt: on
    y_true = torch.tensor([1, 0, 0])

    f1, prec, rec = compute_accuracy(logits, y_true)
    assert f1 == 1
    assert prec == 1
    assert rec == 1


def test_compute_accuracy_all_incorrect() -> None:
    """ """
    # fmt: off
    logits = torch.tensor(
        [
            [0.3, 0.7],
            [0.9, 0.1],
            [0.6, 0.4]
        ]
    )
    # fmt: on
    y_true = torch.tensor([0, 1, 1])

    f1, prec, rec = compute_accuracy(logits, y_true)
    assert f1 == 0
    assert prec == 0
    assert rec == 0


def poly_learning_rate(base_lr: float, curr_iter: int, max_iter: int, power: float = 0.9) -> float:
    """Polynomial-decay learning rate policy."""
    lr = base_lr * (1 - float(curr_iter) / max_iter) ** power
    return lr


def run_epoch(
    args: argparse.Namespace,
    epoch: int,
    model: nn.Module,
    use_gpu: bool,
    split: str,
    dataloader: torch.utils.data.DataLoader,
    criterion,
    optimizer,
) -> None:
    """Run all data for a single split through the network once."""
    f1_meter = AverageMeter("F1", ":.4e")
    prec_meter = AverageMeter("Precision", ":.4e")
    rec_meter = AverageMeter("Recall", ":.4e")

    if split == "train":
        model.train()
    else:
        model.eval()

    for iter, (x, y) in enumerate(dataloader):

        if use_gpu:
            x = x.cuda()
            y = y.cuda()

        output = model(x)
        loss = criterion(output, y)

        # measure accuracy and record loss
        f1, prec, rec = compute_accuracy(logits=output, y_true=y)

        f1_meter.update(f1, x.size(0))
        prec_meter.update(prec, x.size(0))
        rec_meter.update(rec, x.size(0))

        if iter % 10 == 0:
            logger.info(
                "Split %s, Epoch %d Iteration %d: F1:%.2f Prec:%.2f Rec:%.2f",
                split,
                epoch,
                iter,
                f1_meter.avg,
                prec_meter.avg,
                rec_meter.avg,
            )

        if split == "train":
            # compute gradient and do SGD step
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        max_iter = args.num_epochs * len(dataloader)
        current_iter = epoch * len(dataloader) + iter + 1

        if split == "train":
            # decay learning rate only during training
            current_lr = poly_learning_rate(args.base_lr, current_iter, max_iter, power=args.poly_lr_power)

            for param_group in optimizer.param_groups:
                param_group["lr"] = current_lr


def train(args: SimpleNamespace) -> None:
    """ """
    use_gpu = torch.cuda.is_available()

    # read in the data
    train_data = SimpleData("train", args.train_data_dirpath, args.test_data_dirpath)
    val_data = SimpleData("val", args.train_data_dirpath, args.test_data_dirpath)

    train_loader = get_dataloader(train_data, args.batch_size, args.workers)
    val_loader = get_dataloader(val_data, args.batch_size, args.workers)

    model = SimpleModel()
    if use_gpu:
        model = model.cuda()
    criterion = nn.CrossEntropyLoss()
    if use_gpu:
        criterion = criterion.cuda()
    if args.optimizer_type == "sgd":
        optimizer = torch.optim.SGD(
            model.parameters(), args.base_lr, momentum=args.momentum, weight_decay=args.weight_decay
        )
    elif args.optimizer_type == "adam":
        optimizer = torch.optim.Adam(model.parameters(), lr=args.base_lr, weight_decay=args.weight_decay)

    for epoch in range(args.num_epochs):
        run_epoch(
            args,
            epoch,
            model=model,
            use_gpu=use_gpu,
            split="train",
            dataloader=train_loader,
            criterion=criterion,
            optimizer=optimizer,
        )
        run_epoch(
            args,
            epoch,
            model=model,
            use_gpu=use_gpu,
            split="val",
            dataloader=val_loader,
            criterion=criterion,
            optimizer=optimizer,
        )


if __name__ == "__main__":
    """ """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train_data_dirpath",
        type=str,
        help="Path to train data dir.",
        default="/home/jlambert/gtsfm/skydio-501-cycle-error-training-data",
    )
    parser.add_argument(
        "--test_data_dirpath",
        type=str,
        default=None,
        help="Path to test data dir. If empty, will partition 20% from train instead.",
    )
    parser.add_argument("--base_lr", type=float, default=1e-3)
    parser.add_argument("--poly_lr_power", type=float, default=0.9)
    parser.add_argument("--momentum", type=float, default=None)
    parser.add_argument("--weight_decay", type=float, default=0.0001)
    parser.add_argument("--optimizer_type", type=str, choices=["adam", "sgd"], default="adam")
    parser.add_argument("--batch_size", type=float, default=256)
    parser.add_argument("--num_epochs", type=float, default=20)
    parser.add_argument("--workers", type=float, default=1)

    args = parser.parse_args()
    print(args)
    train(args)
