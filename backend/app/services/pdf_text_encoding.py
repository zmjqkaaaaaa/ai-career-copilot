"""Supply the standard Unicode map for PDFs declaring unmapped Adobe-GB1 CIDs."""
from functools import lru_cache
from pathlib import Path

from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

CMAP_PATH = Path(__file__).resolve().parents[1] / "data" / "pdf" / "Adobe-GB1-UCS2"


@lru_cache(maxsize=1)
def adobe_gb1_unicode_map() -> bytes:
    return CMAP_PATH.read_bytes()


def restore_gb1_text_mapping(page) -> None:
    resources = page.get("/Resources")
    if resources is None or not isinstance(resources.get_object(), DictionaryObject):
        return
    fonts = resources.get_object().get("/Font")
    if fonts is None or not isinstance(fonts.get_object(), DictionaryObject):
        return
    for reference in fonts.get_object().values():
        font = reference.get_object()
        if not isinstance(font, DictionaryObject) or "/ToUnicode" in font:
            continue
        if font.get("/Subtype") != "/Type0" or font.get("/Encoding") != "/Identity-H":
            continue
        descendants = font.get("/DescendantFonts")
        if descendants is None:
            continue
        descendants = descendants.get_object()
        if not isinstance(descendants, ArrayObject) or not descendants:
            continue
        system = descendants[0].get_object().get("/CIDSystemInfo")
        if system is None:
            continue
        info = system.get_object()
        if not isinstance(info, DictionaryObject):
            continue
        supplement = info.get("/Supplement")
        if info.get("/Registry") != "Adobe" or info.get("/Ordering") != "GB1":
            continue
        if not isinstance(supplement, int) or not 0 <= supplement <= 5:
            continue
        mapping = DecodedStreamObject()
        mapping.set_data(adobe_gb1_unicode_map())
        font[NameObject("/ToUnicode")] = mapping
