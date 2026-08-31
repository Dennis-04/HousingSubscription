from io import BytesIO
from zipfile import ZipFile

from housing_backend.application.collection import _extract_document_text


def test_hwpx_xml_text_is_extracted() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            '<hp:section xmlns:hp="urn:test">'
            "<hp:t>청약 자격</hp:t><hp:t>소득 기준</hp:t>"
            "</hp:section>",
        )
    text, parser = _extract_document_text(
        buffer.getvalue(),
        "application/vnd.hancom.hwpx",
        ".hwpx",
    )
    assert text == "청약 자격 소득 기준"
    assert parser == "zip-xml-1"
