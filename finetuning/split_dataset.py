"""Split the OpsTune dataset into train / val / test, stratified by primary mode.

Splits both `ai4i_finetune.jsonl` (the SFT chat-format pairs) and the
companion `ai4i_labeled.jsonl` (the rich metadata file) using the same
UDI partition, so eval has full per-row context.

Outputs:
    finetuning/splits/train.jsonl       # SFT pairs for training
    finetuning/splits/val.jsonl         # SFT pairs for validation
    finetuning/splits/test.jsonl        # SFT pairs for held-out eval
    finetuning/splits/train.labeled.jsonl   # rich metadata for analysis
    finetuning/splits/val.labeled.jsonl
    finetuning/splits/test.labeled.jsonl
    finetuning/splits/manifest.json     # {udi: split, fractions, stratum counts}

Run:
    .venv/bin/python finetuning/split_dataset.py
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FT_PATH = ROOT / "finetuning" / "ai4i_finetune.jsonl"
LB_PATH = ROOT / "finetuning" / "ai4i_labeled.jsonl"
OUT_DIR = ROOT / "finetuning" / "splits"

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15  # implied
SEED = 17


def _stratum_key(primary_mode: str | None) -> str:
    return primary_mode or "HEALTHY"


def stratified_split(
    udis_by_stratum: dict[str, list[int]],
    rng: random.Random,
) -> dict[int, str]:
    """Assign every UDI to 'train', 'val', or 'test', stratified per-mode.

    Smallest strata: each gets at least 1 in train if possible. For strata
    of size >= 3 we guarantee at least 1 in val and 1 in test.
    """
    assignment: dict[int, str] = {}
    for stratum, udis in udis_by_stratum.items():
        udis = list(udis)
        rng.shuffle(udis)
        n = len(udis)
        if n == 0:
            continue
        if n == 1:
            assignment[udis[0]] = "train"
            continue
        if n == 2:
            assignment[udis[0]] = "train"
            assignment[udis[1]] = "test"
            continue
        # n >= 3: enforce at least 1 in val and 1 in test
        n_val = max(1, round(n * VAL_FRAC))
        n_test = max(1, round(n * TEST_FRAC))
        n_train = n - n_val - n_test
        if n_train < 1:
            n_train, n_val, n_test = max(1, n - 2), 1, 1
        for u in udis[:n_train]:
            assignment[u] = "train"
        for u in udis[n_train : n_train + n_val]:
            assignment[u] = "val"
        for u in udis[n_train + n_val : n_train + n_val + n_test]:
            assignment[u] = "test"
    return assignment


def main() -> int:
    rng = random.Random(SEED)

    finetune = [json.loads(l) for l in FT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    labeled = [json.loads(l) for l in LB_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

    ft_by_udi = {r["metadata"]["udi"]: r for r in finetune}
    lb_by_udi = {r["udi"]: r for r in labeled}

    common = sorted(set(ft_by_udi) & set(lb_by_udi))
    if len(common) != len(finetune) or len(common) != len(labeled):
        print(f"[warn] mismatch: finetune={len(finetune)} labeled={len(labeled)} common={len(common)}")

    udis_by_stratum: dict[str, list[int]] = defaultdict(list)
    for udi in common:
        primary = ft_by_udi[udi]["metadata"]["primary_mode"]
        udis_by_stratum[_stratum_key(primary)].append(udi)

    assignment = stratified_split(udis_by_stratum, rng)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "val": [], "test": []}
    for udi in common:
        splits[assignment[udi]].append(udi)
    for s, udis in splits.items():
        rng.shuffle(udis)

    # Write SFT pairs
    for split_name, udis in splits.items():
        path = OUT_DIR / f"{split_name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for u in udis:
                f.write(json.dumps(ft_by_udi[u], ensure_ascii=False) + "\n")

    # Write labeled companions
    for split_name, udis in splits.items():
        path = OUT_DIR / f"{split_name}.labeled.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for u in udis:
                f.write(json.dumps(lb_by_udi[u], ensure_ascii=False) + "\n")

    # Manifest
    manifest = {
        "seed": SEED,
        "fractions": {"train": TRAIN_FRAC, "val": VAL_FRAC, "test": TEST_FRAC},
        "counts": {s: len(u) for s, u in splits.items()},
        "stratum_counts": {
            split_name: dict(
                Counter(_stratum_key(ft_by_udi[u]["metadata"]["primary_mode"]) for u in udis)
            )
            for split_name, udis in splits.items()
        },
        "udi_to_split": {str(u): s for u, s in sorted(assignment.items())},
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Summary
    total = sum(len(u) for u in splits.values())
    print(f"Wrote splits to {OUT_DIR}/")
    for s, udis in splits.items():
        print(f"  {s}: {len(udis):4d} ({len(udis)/total:.0%})")
    print("\nStratification (rows per primary mode per split):")
    all_strata = sorted({k for v in manifest["stratum_counts"].values() for k in v})
    print(f"  {'mode':<10}" + "".join(f"  {s:>6}" for s in splits))
    for stratum in all_strata:
        print(
            f"  {stratum:<10}"
            + "".join(f"  {manifest['stratum_counts'][s].get(stratum, 0):>6}" for s in splits)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
