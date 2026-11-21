"""Read the text layer of an uploaded document and number its source blocks."""
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.table import Table
from pypdf import PdfReader

from app.core.errors import ApiError

PARSER_VERSION = "1"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 30_000
MAX_PDF_PAGES = 20
MAX_DOCX_BYTES = 32 * 1024 * 1024
MAX_BLOCKS = 500

def validate_file(stream, file_type: str) -> None:
    try:
        signature = stream.read(5)
        stream.seek(0)
        if file_type == "pdf" and signature.startswith(b"%PDF-"):
            return
        if file_type != "docx" or not signature.startswith(b"PK\x03\x04"):
            raise ApiError(415, "FILE_TYPE_MISMATCH", "文件内容与 PDF 或 DOCX 扩展名不匹配")
        with ZipFile(stream) as package:
            entries = package.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > 1200 or sum(entry.file_size for entry in entries) > MAX_DOCX_BYTES:
                raise ApiError(413, "DOCX_TOO_COMPLEX", "DOCX 解压后超过处理上限")
            if any(entry.flag_bits & 1 or "\\" in entry.filename or entry.filename.startswith("/")
                   or ".." in entry.filename.split("/") for entry in entries):
                raise ApiError(422, "INVALID_DOCX", "DOCX 包含不支持的压缩内容")
            if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names or "word/vbaProject.bin" in names:
                raise ApiError(415, "INVALID_DOCX", "文件不是受支持的 Word DOCX 文档")
            types = package.read("[Content_Types].xml")
            if b"wordprocessingml.document.main+xml" not in types:
                raise ApiError(415, "INVALID_DOCX", "文件不是受支持的 Word DOCX 文档")
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ApiError(422, "INVALID_DOCX", "DOCX 结构已损坏") from exc
    finally:
        stream.seek(0)

def split_blocks(text: str):
    # Keep source line breaks while yielding manageable excerpts.
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")
    for paragraph in paragraphs:
        if paragraph.strip():
            yield paragraph.strip()

def pdf_sections(stream):
    reader = PdfReader(stream)
    if reader.is_encrypted:
        raise ApiError(422, "ENCRYPTED_PDF", "请先解除 PDF 密码保护再上传")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ApiError(413, "PDF_TOO_LONG", "PDF 最多支持 20 页")
    for number, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_DOCX_BYTES:
            raise ApiError(413, "PDF_TOO_COMPLEX", "PDF 页面内容超过处理上限")
        for paragraph in split_blocks(page.extract_text() or ""):
            yield f"第 {number} 页", paragraph

def docx_sections(stream):
    document = Document(stream)
    for index, element in enumerate(document.iter_inner_content(), 1):
        if isinstance(element, Table):
            for row in element.rows:
                cells = list(dict.fromkeys(cell.text.strip() for cell in row.cells if cell.text.strip()))
                if cells:
                    yield f"表格 {index}", " | ".join(cells)
        else:
            for paragraph in split_blocks(element.text):
                yield f"段落 {index}", paragraph

def parse_resume(path: Path, file_type: str) -> list[dict]:
    try:
        with path.open("rb") as stream:
            validate_file(stream, file_type)
            sections = pdf_sections(stream) if file_type == "pdf" else docx_sections(stream)
            blocks = []
            size = 0
            for location, value in sections:
                value = value.replace("\x00", "")
                size += len(value)
                if size > MAX_TEXT_CHARS or len(blocks) >= MAX_BLOCKS:
                    raise ApiError(413, "RESUME_TOO_LONG", "简历文本超出处理上限，请缩短后重新上传")
                blocks.append({"number": len(blocks) + 1, "location": location, "text": value})
    except ApiError:
        raise
    except FileNotFoundError as exc:
        raise ApiError(404, "RESUME_FILE_MISSING", "简历文件无法找到，请重新上传") from exc
    except Exception as exc:
        raise ApiError(422, "UNREADABLE_RESUME", "简历文件损坏或文字无法读取") from exc
    if not blocks or not any(char.isalpha() or char.isdigit() for block in blocks for char in block["text"]):
        raise ApiError(422, "NO_RESUME_TEXT", "文件没有可提取的文字。请上传含文字层的 PDF 或 DOCX")
    return blocks
