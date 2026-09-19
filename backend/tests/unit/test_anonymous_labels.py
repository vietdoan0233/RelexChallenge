import pytest

from app.core import anonymous_labels


@pytest.mark.parametrize("label", ["Me", "Them", "Unknown Speaker"])
def test_structural_anonymous_labels_are_non_person(label):
    assert anonymous_labels.is_non_person_label(label) is True


@pytest.mark.parametrize("marker", ["[REDACTED PERSON]", "[REDACTED SPEAKER]", "[REDACTED SENDER]"])
def test_every_reserved_marker_is_non_person(marker):
    assert anonymous_labels.is_non_person_label(marker) is True


def test_none_is_not_a_non_person_label():
    assert anonymous_labels.is_non_person_label(None) is False


@pytest.mark.parametrize(
    "value",
    [
        "Marco Rossi",
        "Redacted",
        "This is a [REDACTED SPEAKER] mention inside a sentence",
        "[redacted speaker]",  # wrong case: exact match only, no case-folding
        " ",
    ],
)
def test_arbitrary_or_near_miss_text_is_not_a_non_person_label(value):
    assert anonymous_labels.is_non_person_label(value) is False


def test_surrounding_whitespace_is_trimmed_before_comparison():
    assert anonymous_labels.is_non_person_label("  [REDACTED SENDER]  ") is True
    assert anonymous_labels.is_non_person_label("\tUnknown Speaker\n") is True


def test_non_person_labels_is_exactly_anonymous_labels_union_redaction_markers():
    assert anonymous_labels.NON_PERSON_LABELS == (
        anonymous_labels.ANONYMOUS_SPEAKER_LABELS | anonymous_labels.REDACTION_MARKERS
    )
    assert len(anonymous_labels.NON_PERSON_LABELS) == 6


@pytest.mark.parametrize("label", ["+358 40 5512 097", "+1 555 010 0199", "  +44 20 7946 0000 "])
def test_phone_number_speaker_labels_are_non_person(label):
    assert anonymous_labels.is_phone_number_label(label) is True
    assert anonymous_labels.is_non_person_label(label) is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        "358 40 5512 097",  # no leading plus
        "+",
        "+358 call me",
        "Call +358 40 5512 097",
        "Marco Rossi",
    ],
)
def test_near_miss_text_is_not_a_phone_number_label(value):
    assert anonymous_labels.is_phone_number_label(value) is False


@pytest.mark.parametrize("label", ["Guest 1", "Guest 12", "  Guest 2 "])
def test_guest_speaker_labels_are_non_person(label):
    assert anonymous_labels.is_guest_label(label) is True
    assert anonymous_labels.is_unlisted_participant_label(label) is True
    assert anonymous_labels.is_non_person_label(label) is True


@pytest.mark.parametrize(
    "value", [None, "Guest", "Guest one", "guest 1", "Guest 1 said", "The Guest 1", "Guest Speaker"]
)
def test_near_miss_text_is_not_a_guest_label(value):
    assert anonymous_labels.is_guest_label(value) is False
