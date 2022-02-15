"""Unit tests for the SequentialRetriever.

Author: John Lambert
"""

from pathlib import Path

from gtsfm.loader.olsson_loader import OlssonLoader
from gtsfm.retriever.sequential_retriever import SequentialRetriever

DATA_ROOT_PATH = Path(__file__).resolve().parent.parent / "data"
DEFAULT_FOLDER = DATA_ROOT_PATH / "set1_lund_door"


def test_sequential_retriever() -> None:
    """Assert that we get 30 total matches with a lookahead of 3 frames on the Door Dataset."""
    loader = OlssonLoader(str(DEFAULT_FOLDER), image_extension="JPG", max_frame_lookahead=12)
    
    retriever = SequentialRetriever(max_frame_lookahead=3)
    pairs = retriever.run(loader=loader)

    expected_pairs = [
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 2),
        (1, 3),
        (1, 4),
        (2, 3),
        (2, 4),
        (2, 5),
        (3, 4),
        (3, 5),
        (3, 6),
        (4, 5),
        (4, 6),
        (4, 7),
        (5, 6),
        (5, 7),
        (5, 8),
        (6, 7),
        (6, 8),
        (6, 9),
        (7, 8),
        (7, 9),
        (7, 10),
        (8, 9),
        (8, 10),
        (8, 11),
        (9, 10),
        (9, 11),
        (10, 11),
    ]
    assert pairs == expected_pairs
    # all images have 3 potential forward match pairs, except last three which have only 2, 1, and 0 such forward pairs
    assert len(pairs) == (9 * 3) + 2 + 1


if __name__ == "__main__":
    test_sequential_retriever()