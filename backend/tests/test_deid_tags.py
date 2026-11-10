from __future__ import annotations

import pytest
from pydicom.datadict import tag_for_keyword

from app.modules.deid import tags


@pytest.mark.parametrize("keyword", [*tags.REPLACE, *tags.REMOVE, *tags.RETAIN])
def test_every_configured_keyword_is_a_real_dicom_tag(keyword):
    assert tag_for_keyword(keyword) is not None, f"{keyword} is not a DICOM keyword"


def test_no_keyword_appears_in_two_lists():
    replaced = set(tags.REPLACE)
    removed = set(tags.REMOVE)
    retained = set(tags.RETAIN)
    assert not replaced & removed
    assert not replaced & retained
    assert not removed & retained


def test_class_uids_and_transfer_syntax_are_not_remapped():
    assert tags.is_remappable_uid("StudyInstanceUID")
    assert not tags.is_remappable_uid("SOPClassUID")
    assert not tags.is_remappable_uid("TransferSyntaxUID")
