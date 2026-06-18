"""Computes inter-coder agreement metrics from an AgreementDataset.

Pure Python — no numpy, scipy, or pandas required.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from ace.services.agreement_types import (
    AgreementDataset,
    AgreementResult,
    CodeMetrics,
)


def _build_sparse_counts(
    dataset: AgreementDataset,
    coder_ids: Sequence[str],
    code_names: Sequence[str],
    progress_callback=None,
) -> tuple[dict[str, Counter[int]], dict[str, Counter[int]], dict[str, set[str]]]:
    """Build per-code/per-source bitmask counts and per-code source sets."""
    coder_bit = {cid: bit for bit, cid in enumerate(coder_ids)}
    code_index = {name: i for i, name in enumerate(code_names)}
    source_by_hash = {s.content_hash: s for s in dataset.sources}

    code_source_sets: dict[str, set[str]] = {name: set() for name in code_names}
    for ann in dataset.annotations:
        if ann.code_name in code_source_sets:
            code_source_sets[ann.code_name].add(ann.source_hash)

    annotations_by_source: dict[str, list] = defaultdict(list)
    for ann in dataset.annotations:
        if ann.source_hash not in source_by_hash:
            continue
        if ann.coder_id not in coder_bit:
            continue
        if ann.code_name not in code_index:
            continue
        annotations_by_source[ann.source_hash].append(ann)

    per_code_counts: dict[str, Counter[int]] = {name: Counter() for name in code_names}
    per_source_counts: dict[str, Counter[int]] = {}

    n_sources = len(dataset.sources)
    for src_i, source in enumerate(dataset.sources, start=1):
        if progress_callback:
            progress_callback(src_i, f"Computing agreement · {src_i} of {n_sources} sources")
        text_len = len(source.content_text)
        if text_len == 0:
            continue

        events: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        for ann in annotations_by_source.get(source.content_hash, []):
            start = max(0, min(ann.start_offset, text_len))
            end = max(0, min(ann.end_offset, text_len))
            if end <= start:
                continue
            events[start].append((1, code_index[ann.code_name], coder_bit[ann.coder_id]))
            events[end].append((-1, code_index[ann.code_name], coder_bit[ann.coder_id]))

        if not events:
            continue

        active = [[0] * len(coder_ids) for _ in code_names]
        current_masks = [0] * len(code_names)
        active_total = 0
        per_source = per_source_counts.setdefault(source.display_id, Counter())

        prev_pos: int | None = None
        for pos in sorted(events):
            if prev_pos is not None and pos > prev_pos and active_total > 0:
                width = pos - prev_pos
                for idx, code_name in enumerate(code_names):
                    mask = current_masks[idx]
                    per_code_counts[code_name][mask] += width
                    per_source[mask] += width

            for delta, code_idx, bit in events[pos]:
                before = active[code_idx][bit]
                active[code_idx][bit] += delta
                after = active[code_idx][bit]
                if before == 0 and after > 0:
                    current_masks[code_idx] |= 1 << bit
                    active_total += 1
                elif before > 0 and after == 0:
                    current_masks[code_idx] &= ~(1 << bit)
                    active_total -= 1

            prev_pos = pos

    return per_code_counts, per_source_counts, code_source_sets


def compute_agreement(
    dataset: AgreementDataset,
    progress_callback=None,
) -> AgreementResult:
    """Compute all agreement metrics from a matched dataset.

    ``progress_callback`` is an optional ``Callable[[done, stage], None]``
    invoked during the expensive per-source counting loop. It is pure
    synchronous code and must not block on I/O.
    """
    if not dataset.annotations or not dataset.sources or not dataset.codes:
        empty = CodeMetrics(percent_agreement=0.0, n_positions=0)
        return AgreementResult(
            overall=empty,
            per_code={},
            per_source={},
            pairwise={},
            n_coders=len(dataset.coders),
            n_sources=0,
            n_codes=0,
        )

    coder_ids = [c.id for c in dataset.coders]
    code_names = [c.name for c in dataset.codes]

    if progress_callback:
        progress_callback(0, "Counting annotation overlaps")

    per_code_counts, per_source_counts, code_source_sets = _build_sparse_counts(
        dataset,
        coder_ids,
        code_names,
        progress_callback=progress_callback,
    )

    # Compute per-code metrics
    per_code_results: dict[str, CodeMetrics] = {}
    for cn in code_names:
        metrics = _compute_metrics_from_counts(per_code_counts[cn], coder_ids)
        metrics.n_sources = len(code_source_sets[cn])
        per_code_results[cn] = metrics

    # Compute per-source metrics
    per_source_results: dict[str, CodeMetrics] = {}
    for src_key, counts in per_source_counts.items():
        per_source_results[src_key] = _compute_metrics_from_counts(counts, coder_ids)

    # Compute overall (pooled across all codes)
    pooled_counts: Counter[int] = Counter()
    for cn in code_names:
        pooled_counts.update(per_code_counts[cn])
    overall = _compute_metrics_from_counts(pooled_counts, coder_ids)
    overall.n_sources = len(dataset.sources)

    # Compute pairwise
    pairwise = _compute_pairwise_from_counts(per_code_counts, coder_ids)

    return AgreementResult(
        overall=overall,
        per_code=per_code_results,
        per_source=per_source_results,
        pairwise=pairwise,
        n_coders=len(dataset.coders),
        n_sources=len(per_source_counts),
        n_codes=len(code_names),
    )


def _counts_to_rating_patterns(
    counts: Mapping[int | tuple[int, ...], int],
    n_coders: int,
) -> Counter[tuple[int, ...]]:
    pattern_counts: Counter[tuple[int, ...]] = Counter()
    for key, count in counts.items():
        if count <= 0:
            continue
        if isinstance(key, int):
            pattern = tuple((key >> bit) & 1 for bit in range(n_coders))
        else:
            pattern = tuple(key)
        pattern_counts[pattern] += count
    return pattern_counts


def _compute_metrics_from_counts(
    counts: Mapping[int | tuple[int, ...], int],
    coder_ids: Sequence[str],
) -> CodeMetrics:
    """Compute all metrics from counted coder rating patterns."""
    pattern_counts = _counts_to_rating_patterns(counts, len(coder_ids))
    n_units = sum(pattern_counts.values())
    if n_units == 0:
        return CodeMetrics(percent_agreement=0.0, n_positions=0)

    n_coders = len(coder_ids)
    cohens_k = _cohens_kappa_from_counts(pattern_counts, n_units) if n_coders == 2 else None

    return CodeMetrics(
        percent_agreement=_percent_agreement_from_counts(pattern_counts, n_units, n_coders),
        n_positions=n_units,
        cohens_kappa=cohens_k,
        krippendorffs_alpha=_krippendorffs_alpha_from_counts(pattern_counts),
        fleiss_kappa=_fleiss_kappa_from_counts(pattern_counts, n_units, n_coders),
        congers_kappa=_congers_kappa_from_counts(pattern_counts, n_units, n_coders),
        gwets_ac1=_gwets_ac1_from_counts(pattern_counts, n_units, n_coders),
        brennan_prediger=_brennan_prediger_from_counts(pattern_counts, n_units, n_coders),
    )


def _categories_from_counts(counts: Mapping[tuple[int, ...], int]) -> list[int]:
    categories: set[int] = set()
    for ratings, count in counts.items():
        if count > 0:
            categories.update(ratings)
    return sorted(categories)


def _mask_category_counts(ratings: tuple[int, ...], categories: Sequence[int]) -> list[int]:
    return [sum(1 for rating in ratings if rating == category) for category in categories]


def _percent_agreement_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
) -> float:
    if n_coders < 2:
        return 0.0

    pair_agrees = []
    for i in range(n_coders):
        for j in range(i + 1, n_coders):
            agree = sum(
                count
                for ratings, count in counts.items()
                if count > 0 and ratings[i] == ratings[j]
            ) / n_units
            pair_agrees.append(agree)
    return sum(pair_agrees) / len(pair_agrees) if pair_agrees else 0.0


def _cohens_kappa_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
) -> float | None:
    if n_units == 0:
        return None

    a11 = a10 = a01 = a00 = 0
    for ratings, count in counts.items():
        if count <= 0:
            continue
        if ratings[0] and ratings[1]:
            a11 += count
        elif ratings[0] and not ratings[1]:
            a10 += count
        elif not ratings[0] and ratings[1]:
            a01 += count
        else:
            a00 += count

    po = (a11 + a00) / n_units
    pe = ((a11 + a10) * (a11 + a01) + (a01 + a00) * (a10 + a00)) / (n_units * n_units)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0

    kappa = (po - pe) / (1 - pe)
    if math.isnan(kappa):
        all_same = all(ratings[0] == ratings[1] for ratings, count in counts.items() if count > 0)
        return 1.0 if all_same else None
    return kappa


def _krippendorffs_alpha_from_counts(counts: Mapping[tuple[int, ...], int]) -> float | None:
    """Krippendorff's alpha for nominal data from counted rating patterns."""
    n_units = sum(count for count in counts.values() if count > 0)
    if n_units == 0:
        return None

    if all(len(set(ratings)) <= 1 for ratings, count in counts.items() if count > 0):
        return 1.0

    categories = _categories_from_counts(counts)
    cat_idx = {c: i for i, c in enumerate(categories)}
    q = len(categories)
    coincidence = [[0.0] * q for _ in range(q)]

    for ratings, count in counts.items():
        if count <= 0:
            continue
        n_r = len(ratings)
        if n_r < 2:
            continue
        weight = count / (n_r - 1)
        for i in range(n_r):
            for j in range(n_r):
                if i != j:
                    ci = cat_idx[ratings[i]]
                    cj = cat_idx[ratings[j]]
                    coincidence[ci][cj] += weight

    n_total = sum(sum(row) for row in coincidence)
    if n_total == 0:
        return None
    marginals = [sum(coincidence[c]) for c in range(q)]

    do = 0.0
    for c in range(q):
        for k in range(q):
            if c != k:
                do += coincidence[c][k]
    do /= n_total

    de = 0.0
    for c in range(q):
        for k in range(q):
            if c != k:
                de += marginals[c] * marginals[k]
    de /= (n_total * (n_total - 1))

    if de == 0:
        return 1.0
    alpha = 1.0 - do / de
    return None if math.isnan(alpha) else alpha


def _observed_agreement_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
    categories: Sequence[int],
) -> float:
    """Pairwise observed agreement from counted rating patterns."""
    if n_units == 0 or n_coders < 2:
        return 0.0

    po_sum = 0.0
    denom = n_coders * (n_coders - 1)
    for ratings, count in counts.items():
        if count <= 0:
            continue
        rating_counts = _mask_category_counts(ratings, categories)
        s = sum(category_count * (category_count - 1) for category_count in rating_counts)
        po_sum += count * (s / denom)
    return po_sum / n_units


def _fleiss_kappa_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
) -> float | None:
    if n_units == 0 or n_coders < 2:
        return None

    categories = _categories_from_counts(counts)
    q = len(categories)
    if q == 0:
        return None

    po = _observed_agreement_from_counts(counts, n_units, n_coders, categories)
    pe = 0.0
    for category in categories:
        category_total = sum(
            count * ratings.count(category)
            for ratings, count in counts.items()
            if count > 0
        )
        pj = category_total / (n_units * n_coders)
        pe += pj * pj

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _congers_kappa_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
) -> float | None:
    if n_units == 0 or n_coders < 2:
        return None

    categories = _categories_from_counts(counts)
    q = len(categories)
    if q == 0:
        return None

    po = _observed_agreement_from_counts(counts, n_units, n_coders, categories)

    rater_props = []
    for coder_idx in range(n_coders):
        props = [0.0] * q
        for category_idx, category in enumerate(categories):
            props[category_idx] = sum(
                count
                for ratings, count in counts.items()
                if count > 0 and ratings[coder_idx] == category
            ) / n_units
        rater_props.append(props)

    pe = 0.0
    for j in range(q):
        s = sum(rater_props[r][j] for r in range(n_coders))
        pe += s * s - sum(rater_props[r][j] ** 2 for r in range(n_coders))
    pe /= n_coders * (n_coders - 1)

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _gwets_ac1_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
) -> float | None:
    if n_units == 0 or n_coders < 2:
        return None

    categories = _categories_from_counts(counts)
    q = len(categories)
    if q == 0:
        return None

    po = _observed_agreement_from_counts(counts, n_units, n_coders, categories)
    marginals = []
    for category in categories:
        category_total = sum(
            count * ratings.count(category)
            for ratings, count in counts.items()
            if count > 0
        )
        marginals.append(category_total / (n_units * n_coders))

    pe = sum(p * (1 - p) for p in marginals) / (q - 1) if q > 1 else 0.0

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _brennan_prediger_from_counts(
    counts: Mapping[tuple[int, ...], int],
    n_units: int,
    n_coders: int,
) -> float | None:
    if n_units == 0 or n_coders < 2:
        return None

    categories = _categories_from_counts(counts)
    q = len(categories)
    if q == 0:
        return None

    po = _observed_agreement_from_counts(counts, n_units, n_coders, categories)
    pe = 1.0 / q
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Cohen's kappa (2 raters)
# ---------------------------------------------------------------------------


def _cohens_kappa(y1: list, y2: list) -> float | None:
    """Cohen's kappa for two binary raters."""
    n = len(y1)
    if n == 0:
        return None
    a11 = a10 = a01 = a00 = 0
    for i in range(n):
        if y1[i] and y2[i]:
            a11 += 1
        elif y1[i] and not y2[i]:
            a10 += 1
        elif not y1[i] and y2[i]:
            a01 += 1
        else:
            a00 += 1
    po = (a11 + a00) / n
    pe = ((a11 + a10) * (a11 + a01) + (a01 + a00) * (a10 + a00)) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _safe_kappa(vec1: list[int], vec2: list[int]) -> float | None:
    """Cohen's kappa with edge case handling."""
    k = _cohens_kappa(vec1, vec2)
    if k is None:
        return 1.0 if vec1 == vec2 else None
    if math.isnan(k):
        return 1.0 if vec1 == vec2 else None
    return k


# ---------------------------------------------------------------------------
# Pairwise
# ---------------------------------------------------------------------------


def _collapse_counts_to_pair(
    counts: Mapping[int, int],
    left_bit: int,
    right_bit: int,
) -> Counter[int]:
    pair_counts: Counter[int] = Counter()
    for mask, count in counts.items():
        pair_mask = 0
        if (mask >> left_bit) & 1:
            pair_mask |= 0b01
        if (mask >> right_bit) & 1:
            pair_mask |= 0b10
        pair_counts[pair_mask] += count
    return pair_counts


def _compute_pairwise_from_counts(
    per_code_counts: dict[str, Counter[int]],
    coder_ids: Sequence[str],
) -> dict[tuple[str, str], "CodeMetrics"]:
    """Compute full CodeMetrics for each coder pair from pooled sparse counts."""
    pairwise: dict[tuple[str, str], CodeMetrics] = {}

    for i in range(len(coder_ids)):
        for j in range(i + 1, len(coder_ids)):
            cid_i, cid_j = coder_ids[i], coder_ids[j]
            pair_counts: Counter[int] = Counter()
            for counts in per_code_counts.values():
                pair_counts.update(_collapse_counts_to_pair(counts, i, j))
            pairwise[(cid_i, cid_j)] = _compute_metrics_from_counts(
                pair_counts,
                [cid_i, cid_j],
            )

    return pairwise
