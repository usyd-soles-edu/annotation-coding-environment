"""Tests for AgreementComputer."""

import pytest

from ace.services.agreement_types import (
    AgreementDataset,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)
from ace.services.agreement_computer import compute_agreement


def _make_dataset(annotations: list[MatchedAnnotation], n_coders=2) -> AgreementDataset:
    """Helper to build a minimal dataset."""
    coders = [CoderInfo(id=f"c{i}", label=f"Coder {i}", source_file=f"f{i}.ace") for i in range(n_coders)]
    return AgreementDataset(
        sources=[MatchedSource(
            content_hash="hash1",
            display_id="S001",
            content_text="I enjoyed the group work but lectures were too fast",
        )],
        coders=coders,
        codes=[MatchedCode(name="Positive", present_in={"c0", "c1"})],
        annotations=annotations,
        warnings=[],
    )


def _make_dataset_from_parts(
    sources: list[MatchedSource],
    coders: list[CoderInfo],
    codes: list[MatchedCode],
    annotations: list[MatchedAnnotation],
) -> AgreementDataset:
    return AgreementDataset(
        sources=sources,
        coders=coders,
        codes=codes,
        annotations=annotations,
        warnings=[],
    )


def test_sparse_compute_preserves_current_coded_position_rule():
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="x" * 12)]
    coders = [
        CoderInfo(id="c1", label="C1", source_file="a.ace"),
        CoderInfo(id="c2", label="C2", source_file="b.ace"),
    ]
    codes = [
        MatchedCode(name="A", present_in={"c1", "c2"}),
        MatchedCode(name="B", present_in={"c1", "c2"}),
    ]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A", start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A", start_offset=2, end_offset=7),
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="B", start_offset=8, end_offset=10),
    ]

    dataset = _make_dataset_from_parts(sources, coders, codes, annotations)
    result = compute_agreement(dataset)

    assert result.per_code["A"].n_positions == 9
    assert result.per_code["B"].n_positions == 9
    assert result.per_source["S1"].n_positions == 18
    assert result.overall.n_positions == 18


def test_sparse_compute_treats_overlapping_same_coder_annotations_as_binary():
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="x" * 10)]
    coders = [
        CoderInfo(id="c1", label="C1", source_file="a.ace"),
        CoderInfo(id="c2", label="C2", source_file="b.ace"),
    ]
    codes = [MatchedCode(name="A", present_in={"c1", "c2"})]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A", start_offset=0, end_offset=6),
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A", start_offset=3, end_offset=9),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A", start_offset=0, end_offset=9),
    ]

    dataset = _make_dataset_from_parts(sources, coders, codes, annotations)
    result = compute_agreement(dataset)

    assert result.per_code["A"].n_positions == 9
    assert result.per_code["A"].percent_agreement == pytest.approx(1.0)


def test_sparse_compute_clips_annotations_at_source_length():
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="x" * 5)]
    coders = [
        CoderInfo(id="c1", label="C1", source_file="a.ace"),
        CoderInfo(id="c2", label="C2", source_file="b.ace"),
    ]
    codes = [MatchedCode(name="A", present_in={"c1", "c2"})]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A", start_offset=2, end_offset=99),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A", start_offset=2, end_offset=5),
    ]

    dataset = _make_dataset_from_parts(sources, coders, codes, annotations)
    result = compute_agreement(dataset)

    assert result.per_code["A"].n_positions == 3
    assert result.per_code["A"].percent_agreement == pytest.approx(1.0)


def test_perfect_agreement():
    """Both coders annotate the exact same span."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)

    assert result.overall.percent_agreement > 0.99
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa > 0.9
    assert result.n_coders == 2
    assert result.n_sources == 1
    assert "Positive" in result.per_code


def test_no_agreement():
    """Coders annotate completely different spans with the same code."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=10),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=30, end_offset=40),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)

    assert result.overall.percent_agreement < 0.5
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa < 0.1


def test_empty_annotations():
    """Dataset with no annotations produces zero metrics."""
    ds = _make_dataset([])
    result = compute_agreement(ds)
    assert result.overall.percent_agreement == 0.0
    assert result.overall.n_positions == 0


def test_krippendorff_alpha_computed():
    """Verify Krippendorff's alpha is computed."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert result.overall.krippendorffs_alpha is not None


def test_irrcac_metrics_computed():
    """Verify irrCAC metrics are computed for 2+ coders."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    # For 2 coders, Fleiss' kappa should still compute (it generalises)
    assert result.overall.gwets_ac1 is not None
    assert result.overall.brennan_prediger is not None


def test_per_source_metrics():
    """Verify per-source metrics are computed."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=10),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=10),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert "S001" in result.per_source
    assert result.per_source["S001"].percent_agreement > 0.9


def test_pairwise_alpha():
    """Verify pairwise returns CodeMetrics with krippendorffs_alpha."""
    anns = [
        MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
        MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
    ]
    ds = _make_dataset(anns)
    result = compute_agreement(ds)
    assert len(result.pairwise) == 1  # one pair for 2 coders
    pair_key = list(result.pairwise.keys())[0]
    assert result.pairwise[pair_key].krippendorffs_alpha > 0.9


def test_multi_code_dataset():
    """Two codes, partial agreement."""
    ds = AgreementDataset(
        sources=[MatchedSource(
            content_hash="hash1",
            display_id="S001",
            content_text="I enjoyed the group work but lectures were too fast",
        )],
        coders=[
            CoderInfo(id="c0", label="Alice", source_file="a.ace"),
            CoderInfo(id="c1", label="Bob", source_file="b.ace"),
        ],
        codes=[
            MatchedCode(name="Positive", present_in={"c0", "c1"}),
            MatchedCode(name="Negative", present_in={"c0", "c1"}),
        ],
        annotations=[
            # Both agree on Positive span
            MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Positive", start_offset=2, end_offset=28),
            MatchedAnnotation(source_hash="hash1", coder_id="c1", code_name="Positive", start_offset=2, end_offset=28),
            # Only Alice applies Negative
            MatchedAnnotation(source_hash="hash1", coder_id="c0", code_name="Negative", start_offset=33, end_offset=51),
        ],
        warnings=[],
    )
    result = compute_agreement(ds)
    assert result.per_code["Positive"].percent_agreement > result.per_code["Negative"].percent_agreement
    assert result.n_codes == 2
