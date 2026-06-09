"""Verdict logic for agreement results.

Classifies per-code metrics into status/colour/guidance using Gwet's AC1
as the primary metric. Detects the prevalence paradox (Feinstein & Cicchetti, 1990).
"""

from __future__ import annotations

from dataclasses import dataclass

from ace.services.agreement_types import AgreementResult, CodeMetrics

_MIN_POSITIONS = 50

# AC1 thresholds
_RELIABLE = 0.80
_TENTATIVE = 0.60

# Paradox detection thresholds
_PARADOX_AGREE = 0.85
_PARADOX_ALPHA = 0.60
_PARADOX_AC1 = 0.70

_CODE_COLOURS = {
    "reliable": "green",
    "tentative": "amber",
    "unreliable": "red",
    "insufficient": "grey",
}


@dataclass
class CodeVerdict:
    status: str  # "reliable", "tentative", "unreliable", "insufficient"
    colour: str  # "green", "amber", "red", "grey"
    paradox: bool
    guidance: str
    metadata_line: str  # remaining metrics as compact string


@dataclass
class VerdictCodeList:
    names: list[str]
    colour: str  # "amber" or "red"
    indices: list[int]
    use_indices: bool


@dataclass
class OverallVerdict:
    colour: str  # "green", "amber", "red", "grey"
    title: str
    paragraphs: list[str | VerdictCodeList]


def _fmt(val: float | None) -> str:
    """Format a float as '0.41' or an en-dash if None."""
    if val is None:
        return "\u2013"
    return f"{val:.2f}"


def _pct(val: float) -> str:
    """Format a float as a percentage string like '93%'."""
    return f"{round(val * 100)}%"


def _meta_line(m: CodeMetrics, paradox: bool = False, pairwise: bool = False) -> str:
    """Compact metadata line with key metrics."""
    kappa_val = m.cohens_kappa if m.cohens_kappa is not None else m.fleiss_kappa
    parts = [
        f"Kappa {_fmt(kappa_val)}",
        f"Conger {_fmt(m.congers_kappa)}",
        f"B-P {_fmt(m.brennan_prediger)}",
    ]
    if not pairwise:
        parts.append(f"{m.n_sources} sources")
    return " \u00b7 ".join(parts)


def _is_paradox(m: CodeMetrics) -> bool:
    """True when the prevalence paradox is detected.

    Requires all three conditions:
    - percent_agreement >= 0.85
    - krippendorffs_alpha < 0.60
    - gwets_ac1 >= 0.70
    Returns False if any metric needed for the check is None.
    """
    if m.krippendorffs_alpha is None or m.gwets_ac1 is None:
        return False
    return (
        m.percent_agreement >= _PARADOX_AGREE
        and m.krippendorffs_alpha < _PARADOX_ALPHA
        and m.gwets_ac1 >= _PARADOX_AC1
    )


def _status_for_metrics(m: CodeMetrics) -> str:
    if m.n_positions < _MIN_POSITIONS or m.gwets_ac1 is None:
        return "insufficient"
    if m.gwets_ac1 >= _RELIABLE:
        return "reliable"
    if m.gwets_ac1 >= _TENTATIVE:
        return "tentative"
    return "unreliable"


def _paradox_guidance(m: CodeMetrics, *, pairwise: bool) -> str:
    paradox_intro = (
        "This is a known statistical phenomenon called the prevalence "
        "paradox (Feinstein & Cicchetti, 1990), where alpha and kappa "
        "underestimate agreement when a code is applied to only a small "
        "fraction of the text. "
    )
    evidence = (
        f"AC1 ({_fmt(m.gwets_ac1)}) and % Agreement ({_pct(m.percent_agreement)}) "
        "both indicate strong agreement."
    )
    if pairwise:
        return f"Alpha looks low, but this is a statistical artefact. {paradox_intro}{evidence}"
    return (
        "Alpha looks low for this code, but this is a statistical artefact. "
        f"{paradox_intro}{evidence} No action needed \u2014 focus revision efforts "
        "on other codes."
    )


def _guidance_for_code(
    status: str,
    m: CodeMetrics,
    *,
    paradox: bool,
    pairwise: bool,
) -> str:
    if status == "insufficient":
        return (
            "Not enough coded data to assess."
            if pairwise
            else "Not enough coded data to assess this code."
        )
    if status == "reliable":
        if paradox:
            return _paradox_guidance(m, pairwise=pairwise)
        return (
            "This pair agrees strongly across all codes."
            if pairwise
            else "Agreement is strong. This code can be used with confidence."
        )
    if status == "tentative":
        return (
            "This pair shows moderate agreement. A calibration session between "
            "these two coders may help align their interpretations."
            if pairwise
            else "Agreement is moderate but not yet strong. Discuss borderline cases with "
            "your team \u2014 the code definition may need tighter boundaries."
        )
    return (
        "This pair disagrees substantially. Review specific examples where "
        "they diverged and discuss the differences."
        if pairwise
        else "Coders disagree on when to apply this code. Review the code definition "
        "with your team, discuss concrete examples, and re-code a sample."
    )


def classify_code(m: CodeMetrics, *, pairwise: bool = False) -> CodeVerdict:
    """Classify metrics into a verdict.

    When *pairwise* is True, guidance text refers to the coder pair
    rather than a code definition.
    """
    status = _status_for_metrics(m)
    colour = _CODE_COLOURS[status]
    paradox = status == "reliable" and _is_paradox(m)
    guidance = _guidance_for_code(
        status,
        m,
        paradox=paradox,
        pairwise=pairwise,
    )

    return CodeVerdict(
        status=status,
        colour=colour,
        paradox=paradox,
        guidance=guidance,
        metadata_line=_meta_line(m, paradox=paradox, pairwise=pairwise),
    )


_MAX_INLINE_CODES = 6


def _code_list(
    names: list[str],
    colour: str,
    code_index: dict[str, int],
) -> VerdictCodeList:
    indices: list[int] = []
    if len(names) > _MAX_INLINE_CODES:
        indices = sorted(code_index[n] for n in names if n in code_index)
    return VerdictCodeList(
        names=names,
        colour=colour,
        indices=indices,
        use_indices=bool(indices),
    )


def _card_colour_for_ac1(ac1: float) -> str:
    if ac1 >= _RELIABLE:
        return "green"
    if ac1 >= _TENTATIVE:
        return "amber"
    return "red"


def _verdict(
    colour: str,
    title: str,
    *paragraphs: str | VerdictCodeList,
) -> OverallVerdict:
    return OverallVerdict(colour=colour, title=title, paragraphs=list(paragraphs))


def _names_with_colour(
    code_verdicts: dict[str, CodeVerdict],
    colour: str,
) -> list[str]:
    return [name for name, verdict in code_verdicts.items() if verdict.colour == colour]


def classify_overall(
    result: AgreementResult,
    code_verdicts: dict[str, CodeVerdict],
    code_index: dict[str, int] | None = None,
) -> OverallVerdict:
    """Classify the overall agreement result into a verdict card.

    *code_index* maps code name → row number in the per-code table (1-based).
    Used when there are many problematic codes to reference by index.
    """
    if code_index is None:
        code_index = {}

    overall_ac1 = result.overall.gwets_ac1

    # Grey: no overall AC1 available
    if overall_ac1 is None:
        return _verdict(
            "grey",
            "Not enough data",
            "There is not enough coded data to assess agreement. Ensure both coders "
            "have annotated at least two shared sources with the same codebook, "
            "then try again.",
        )

    card_colour = _card_colour_for_ac1(overall_ac1)
    amber_names = _names_with_colour(code_verdicts, "amber")
    red_names = _names_with_colour(code_verdicts, "red")

    if card_colour == "green":
        if not amber_names and not red_names:
            return _verdict(
                "green",
                "Strong agreement",
                "Agreement is strong across all codes. Your codebook is working "
                "well and you can divide the remaining coding work between coders.",
            )
        if red_names:
            code_list = _code_list(red_names, "red", code_index)
            return _verdict(
                "green",
                "Strong agreement",
                "Agreement is strong overall, but the following codes are flagged "
                "in red. Review them before using their coded data in analysis.",
                code_list,
            )
        code_list = _code_list(amber_names, "amber", code_index)
        return _verdict(
            "green",
            "Strong agreement",
            "Agreement is strong overall. Most codes show strong agreement, "
            "but the following fall in the tentative range. Review their "
            "definitions and boundary cases with your team.",
            code_list,
        )

    if card_colour == "amber":
        if not red_names:
            code_list = _code_list(amber_names, "amber", code_index)
            return _verdict(
                "amber",
                "Tentative agreement",
                "Most codes show strong agreement, but some fall in the tentative "
                "range. Review the definitions and boundary cases for the following "
                "with your team before dividing the remaining work.",
                code_list,
            )
        code_list = _code_list(red_names, "red", code_index)
        return _verdict(
            "amber",
            "Tentative agreement",
            "Overall agreement is moderate. Codes in the tentative range can "
            "support preliminary findings, but those flagged in red should be "
            "revised before their data are used in analysis. Focus your next "
            "calibration session on:",
            code_list,
        )

    # card_colour == "red"
    return _verdict(
        "red",
        "Low agreement",
        "Agreement is low across most codes. The codebook needs revision before "
        "the data can be used for analysis.",
        "We recommend: (1) meet to discuss where and why you disagreed on specific "
        "examples, (2) revise definitions based on that discussion, "
        "(3) independently code 2\u20133 shared sources, then re-run this check.",
    )
