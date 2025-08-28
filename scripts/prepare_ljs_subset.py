#!/usr/bin/env python3
"""
Prepare a tiny LJSpeech subset under tests/data/ljs for quick tests.
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class Record:
    """One LJSpeech row from metadata.csv."""

    wav_id: str
    transcript: str
    normalized: str


def read_metadata(root: Path) -> List[Record]:
    """Read metadata.csv (id|transcript|normalized)."""
    meta = root / "metadata.csv"
    if not meta.is_file():
        raise FileNotFoundError(
            f"Could not find {meta}. Expected LJSpeech root with metadata.csv."
        )
    out: List[Record] = []
    with meta.open("r", encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="|"):
            if len(row) < 3:
                continue
            out.append(Record(row[0], row[1], row[2]))
    if not out:
        raise ValueError("metadata.csv parsed but no rows found.")
    return out


def choose(records: List[Record], limit: int) -> List[Record]:
    """Pick the first N records deterministically."""
    return records[:limit]


def copy_wavs(records: Iterable[Record], ljs_root: Path, dest: Path) -> None:
    """Copy .wav files for the chosen records."""
    wav_root = ljs_root / "wavs"
    if not wav_root.is_dir():
        raise FileNotFoundError(f"Wavs directory not found: {wav_root}")
    dest.mkdir(parents=True, exist_ok=True)

    for rec in records:
        src = wav_root / f"{rec.wav_id}.wav"
        if not src.is_file():
            # Some releases name the folder 'wavs' but subset may differ; skip if missing
            continue
        shutil.copy2(src, dest / src.name)


def write_index(records: List[Record], out_dir: Path) -> None:
    """Write a simple CSV index for the tiny subset."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "subset_index.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "transcript", "normalized"])
        for r in records:
            w.writerow([f"{r.wav_id}.wav", r.transcript, r.normalized])


def main() -> None:
    """Build tests/data/ljs with a tiny subset and an index CSV."""
    # Adjust this to your dataset location
    ljs_root = Path("tests/data/LJSpeech-1.1")

    # Destination for tests
    dest = Path("tests/data/ljs")
    dest.mkdir(parents=True, exist_ok=True)

    # Keep the subset small for quick live tests
    limit = 50

    records = read_metadata(ljs_root)
    chosen = choose(records, limit)
    copy_wavs(chosen, ljs_root, dest)
    write_index(chosen, dest)

    print(f"✅ Prepared {len(chosen)} items in {dest}")


if __name__ == "__main__":
    main()
