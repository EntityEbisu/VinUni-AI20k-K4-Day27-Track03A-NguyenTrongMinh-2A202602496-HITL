"""Đảm bảo gốc repo nằm trên sys.path để `import exercises.exercise_1_confidence` chạy được."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
