import html
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.shared import Pt, RGBColor
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    HAS_PYTHON_DOCX = True
except ImportError:
    docx = None  # type: ignore
    WD_ALIGN_PARAGRAPH = None  # type: ignore
    qn = None  # type: ignore
    CT_Tbl = None  # type: ignore
    CT_P = None  # type: ignore
    Pt = None  # type: ignore
    RGBColor = None  # type: ignore
    Table = None  # type: ignore
    Paragraph = None  # type: ignore
    HAS_PYTHON_DOCX = False

from backend.parsers.test_pdf_extractor import (
    extract_pdf_with_tables,
    normalize_vietnamese_academic_text,
    resolve_tdmu_document_metadata,
)

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _clean_cell_text(text: str) -> str:
    """Làm sạch khoảng trắng thừa và chuẩn hóa Unicode NFC cho văn bản trong đoạn hoặc ô bảng."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _rows_to_markdown_table(rows: List[List[str]]) -> str:
    """Chuyển đổi ma trận hàng/cột của bảng Word (.docx) thành Markdown Table chuẩn."""
    cleaned_rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not cleaned_rows:
        return ""

    header = cleaned_rows[0]
    col_count = len(header)
    separator = ["---"] * col_count

    md_lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in cleaned_rows[1:]:
        padded = row + [""] * (col_count - len(row))
        md_lines.append("| " + " | ".join(padded[:col_count]) + " |")

    return "\n".join(md_lines)


def _extract_ordered_blocks_python_docx(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Duyệt tuần tự các phần tử con trong `doc.element.body` bằng `python-docx`
    theo đúng thứ tự xuất hiện của đoạn văn (`Paragraph`) và bảng biểu (`Table`).
    """
    doc = docx.Document(str(docx_path))
    blocks: List[Dict[str, Any]] = []

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            cleaned_p = _clean_cell_text(para.text)
            if cleaned_p:
                blocks.append({"type": "paragraph", "text": cleaned_p})
        elif isinstance(child, CT_Tbl):
            tbl = Table(child, doc)
            matrix: List[List[str]] = []
            for row in tbl.rows:
                row_cells = [_clean_cell_text(cell.text) for cell in row.cells]
                matrix.append(row_cells)
            cleaned_rows = [r for r in matrix if any(c.strip() for c in r)]
            md_tbl = _rows_to_markdown_table(cleaned_rows)
            if md_tbl:
                blocks.append(
                    {
                        "type": "table",
                        "rows": cleaned_rows,
                        "markdown": md_tbl,
                    }
                )
    return blocks


def _extract_ordered_blocks_xml_fallback(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Bộ đọc cấu trúc XML OpenXML (`word/document.xml`) dự phòng trường hợp chạy bằng trình thông dịch
    chưa cài `python-docx`, vẫn đảm bảo duyệt đúng thứ tự `w:p` (Paragraph) và `w:tbl` (Table).
    """
    blocks: List[Dict[str, Any]] = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        xml_bytes = zf.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    body = root.find(f"{W_NS}body")
    if body is None:
        return blocks

    for child in list(body):
        if child.tag == f"{W_NS}p":
            texts = [t.text for t in child.iter(f"{W_NS}t") if t.text]
            cleaned_p = _clean_cell_text("".join(texts))
            if cleaned_p:
                blocks.append({"type": "paragraph", "text": cleaned_p})
        elif child.tag == f"{W_NS}tbl":
            matrix: List[List[str]] = []
            for tr in child.findall(f"{W_NS}tr"):
                row_cells: List[str] = []
                for tc in tr.findall(f"{W_NS}tc"):
                    cell_texts = [t.text for t in tc.iter(f"{W_NS}t") if t.text]
                    row_cells.append(_clean_cell_text(" ".join(cell_texts)))
                matrix.append(row_cells)
            cleaned_rows = [r for r in matrix if any(c.strip() for c in r)]
            md_tbl = _rows_to_markdown_table(cleaned_rows)
            if md_tbl:
                blocks.append(
                    {
                        "type": "table",
                        "rows": cleaned_rows,
                        "markdown": md_tbl,
                    }
                )
    return blocks


def extract_docx_structured(file_path: str | Path) -> Dict[str, Any]:
    """
    Bóc tách văn bản và bảng biểu từ file Microsoft Word (`.docx`):
    - Duyệt tuần tự các phần tử con trong `doc.element.body` theo đúng thứ tự xuất hiện
      của đoạn văn (`Paragraph`) và bảng biểu (`Table`).
    - Làm sạch khoảng trắng thừa, chuẩn hóa Unicode (`NFC`) và chuyển đổi toàn bộ các bảng biểu
      trong `.docx` thành định dạng **Markdown Table** chuẩn xác.
    - Trả về cấu trúc dữ liệu tương thích hoàn toàn với đầu ra của `test_pdf_extractor.py`
      (kèm danh sách `pages` để truyền trực tiếp vào `HierarchicalChunker.chunk_pages`).
    """
    docx_path = Path(file_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file DOCX: {docx_path}")

    if HAS_PYTHON_DOCX:
        ordered_blocks = _extract_ordered_blocks_python_docx(docx_path)
    else:
        ordered_blocks = _extract_ordered_blocks_xml_fallback(docx_path)

    paragraphs = [b["text"] for b in ordered_blocks if b["type"] == "paragraph"]
    markdown_tables = [b["markdown"] for b in ordered_blocks if b["type"] == "table"]

    full_text = "\n".join(paragraphs).strip()
    doc_meta = resolve_tdmu_document_metadata(docx_path.name)

    page_record: Dict[str, Any] = {
        "source": docx_path.name,
        "document_name": docx_path.name,
        "doc_title": doc_meta["doc_title"],
        "issue_year": doc_meta["issue_year"],
        "file_type": "docx",
        "page_number": 1,
        "text": full_text,
        "tables_count": len(markdown_tables),
        "tables_markdown": markdown_tables,
    }

    return {
        "source": docx_path.name,
        "doc_title": doc_meta["doc_title"],
        "issue_year": doc_meta["issue_year"],
        "file_type": "docx",
        "page_number": 1,
        "text": full_text,
        "tables_count": len(markdown_tables),
        "tables_markdown": markdown_tables,
        "ordered_blocks": ordered_blocks,
        "pages": [page_record],
    }


def extract_docx_as_pages(file_path: str | Path) -> List[Dict[str, Any]]:
    """Trả về danh sách trang từ `extract_docx_structured` để tương thích 100% với `extract_pdf_with_tables`."""
    structured = extract_docx_structured(file_path)
    return structured["pages"]


def render_docx_to_html_preview(
    file_path: str | Path,
    download_url: str | None = None,
) -> str:
    """
    Render trực tiếp file `.docx` sang giao diện trang giấy văn bản hành chính HTML chuẩn mực
    (kèm nút tải file `.docx` gốc và nút In / Lưu PDF) để mở trực tiếp trên Tab mới của trình duyệt.
    """
    docx_path = Path(file_path)
    structured = extract_docx_structured(docx_path)
    doc_title = html.escape(structured.get("doc_title") or docx_path.name)
    issue_year = html.escape(str(structured.get("issue_year") or ""))
    safe_filename = html.escape(docx_path.name)
    resolved_download_url = html.escape(download_url or f"/pdfs/{docx_path.name}")

    body_html_parts: List[str] = []
    for block in structured.get("ordered_blocks", []):
        if block["type"] == "paragraph":
            raw_p = block["text"]
            esc_p = html.escape(raw_p)
            if re.match(r"^(?:CHƯƠNG|MỤC|ĐIỀU)\s+", raw_p, flags=re.IGNORECASE):
                body_html_parts.append(f'<h2 class="doc-section">{esc_p}</h2>')
            elif re.match(r"^\d+\.\d+", raw_p):
                body_html_parts.append(f'<h3 class="doc-subsection">{esc_p}</h3>')
            elif raw_p.isupper() and len(raw_p) < 140:
                body_html_parts.append(f'<p class="doc-heading-upper">{esc_p}</p>')
            else:
                body_html_parts.append(f'<p class="doc-paragraph">{esc_p}</p>')
        elif block["type"] == "table":
            rows = block.get("rows") or []
            if not rows:
                continue
            header = rows[0]
            th_cells = "".join(f"<th>{html.escape(c)}</th>" for c in header)
            tbody_rows = []
            for r in rows[1:]:
                td_cells = "".join(f"<td>{html.escape(c)}</td>" for c in r)
                tbody_rows.append(f"<tr>{td_cells}</tr>")
            table_html = (
                '<div class="table-wrapper">'
                '<table class="doc-table">'
                f"<thead><tr>{th_cells}</tr></thead>"
                f"<tbody>{''.join(tbody_rows)}</tbody>"
                "</table>"
                "</div>"
            )
            body_html_parts.append(table_html)

    content_html = "\n".join(body_html_parts) or "<p>Văn bản không có nội dung.</p>"

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Xem trước DOCX: {doc_title} — TDMU</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: #e2e8f0;
      font-family: "Times New Roman", Times, serif;
      color: #0f172a;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 20;
      background: #0054A6;
      color: #ffffff;
      border-bottom: 3px solid #fbbf24;
      padding: 10px 20px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }}
    .topbar-title {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .topbar-title strong {{
      font-size: 14px;
    }}
    .topbar-title span {{
      font-size: 12px;
      color: #fde68a;
    }}
    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      border: none;
    }}
    .btn-download {{
      background: #fbbf24;
      color: #003f7d;
    }}
    .btn-download:hover {{
      background: #f59e0b;
    }}
    .btn-print {{
      background: rgba(255, 255, 255, 0.15);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.35);
    }}
    .btn-print:hover {{
      background: rgba(255, 255, 255, 0.25);
    }}
    .page-container {{
      max-width: 860px;
      margin: 28px auto;
      background: #ffffff;
      padding: 48px 56px;
      border-radius: 6px;
      box-shadow: 0 10px 25px rgba(15, 23, 42, 0.12);
      line-height: 1.65;
      font-size: 16px;
    }}
    .doc-heading-upper {{
      text-align: center;
      font-weight: 700;
      margin: 6px 0;
      font-size: 15px;
    }}
    .doc-section {{
      font-size: 17px;
      font-weight: 700;
      color: #0054A6;
      margin: 22px 0 10px 0;
      border-bottom: 1px solid #cbd5e1;
      padding-bottom: 4px;
    }}
    .doc-subsection {{
      font-size: 16px;
      font-weight: 700;
      color: #1e293b;
      margin: 14px 0 6px 0;
    }}
    .doc-paragraph {{
      margin: 8px 0;
      text-align: justify;
    }}
    .table-wrapper {{
      margin: 18px 0;
      overflow-x: auto;
    }}
    .doc-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .doc-table th, .doc-table td {{
      border: 1px solid #64748b;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .doc-table th {{
      background: #eff6ff;
      color: #0054A6;
      font-weight: 700;
    }}
    @media print {{
      body {{ background: #ffffff; }}
      .topbar {{ display: none; }}
      .page-container {{
        margin: 0;
        padding: 0;
        box-shadow: none;
      }}
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-title">
      <strong>📝 {doc_title} {f"(Ban hành: {issue_year})" if issue_year else ""}</strong>
      <span>Bản xem trước trực tuyến văn bản Word (.docx) — File gốc: {safe_filename}</span>
    </div>
    <div class="topbar-actions">
      <button type="button" class="btn btn-print" onclick="window.print()">🖨 In / Lưu PDF</button>
      <a class="btn btn-download" href="{resolved_download_url}" download="{safe_filename}">⬇ Tải file DOCX gốc</a>
    </div>
  </div>
  <main class="page-container">
    {content_html}
  </main>
</body>
</html>"""


def _parse_markdown_table_to_rows(md_table: str) -> List[List[str]]:
    """Chuyển đổi chuỗi Markdown Table về ma trận danh sách hàng và cột để tạo bảng Word thực thụ."""
    rows: List[List[str]] = []
    for raw_line in (md_table or "").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("|"):
            continue
        inner = line.strip("|")
        cells = [c.strip() for c in inner.split("|")]
        # Bỏ qua dòng phân cách "| --- | --- |"
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue
        if any(cells):
            rows.append(cells)
    return rows


def export_pdf_to_clean_docx(
    pdf_filename: str,
    save_cache: bool = True,
) -> tuple[BytesIO, Path, str]:
    """
    Chuyển đổi văn bản PDF quy chế/hướng dẫn TDMU sang file Microsoft Word (`.docx`) sạch sẽ:
    - Đọc dữ liệu đã bóc tách sạch (tiếng Việt có dấu chuẩn xác + bảng biểu) từ file JSON tương ứng
      trong `data/processed/` (hoặc bóc tách trực tiếp từ file PDF trong `data/raw_pdfs/`).
    - Dùng `python-docx` tạo file Word (`.docx`) định dạng văn bản hành chính sạch sẽ:
      + Font chữ chuẩn: `Times New Roman`
      + Tiêu đề văn bản, giữ nguyên cấu trúc Chương / Điều / Khoản / Mục / Tiểu mục
      + Render toàn bộ các bảng biểu Markdown thành bảng Word thực thụ có kẻ khung (`Table Grid`).
    - Lưu bản cache vào `data/exported_docx/<stem>.docx` và trả về `(BytesIO, cached_docx_path, download_filename)`.
    """
    safe_name = Path(pdf_filename).name.strip()
    stem = Path(safe_name).stem
    download_filename = f"{stem}.docx"

    raw_dir = ROOT_DIR / "data" / "raw_pdfs"
    processed_dir = ROOT_DIR / "data" / "processed"
    export_dir = ROOT_DIR / "data" / "exported_docx"
    export_dir.mkdir(parents=True, exist_ok=True)
    cached_docx_path = export_dir / download_filename

    # Nếu bản thân file gốc trong data/raw_pdfs/ đã là .docx thì trả về trực tiếp
    raw_docx_candidate = raw_dir / download_filename
    if raw_docx_candidate.exists() and safe_name.lower().endswith(".docx"):
        raw_bytes = raw_docx_candidate.read_bytes()
        return BytesIO(raw_bytes), raw_docx_candidate, download_filename

    extracted_json_path = processed_dir / f"{stem}_extracted.json"
    raw_pdf_path = raw_dir / f"{stem}.pdf"

    pages_data: List[Dict[str, Any]] = []
    if extracted_json_path.exists():
        with open(extracted_json_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, list):
                pages_data = loaded
            elif isinstance(loaded, dict) and "pages" in loaded:
                pages_data = loaded["pages"]
    elif raw_pdf_path.exists():
        pages_data = extract_pdf_with_tables(raw_pdf_path)
    else:
        raise FileNotFoundError(
            f"Không tìm thấy dữ liệu nguồn cho văn bản '{safe_name}' trong data/processed/ hoặc data/raw_pdfs/."
        )

    doc_meta = resolve_tdmu_document_metadata(f"{stem}.pdf")
    doc_title = doc_meta.get("doc_title") or stem
    issue_year = doc_meta.get("issue_year") or ""

    if HAS_PYTHON_DOCX:
        doc = docx.Document()

        # Thiết lập font mặc định Times New Roman cỡ 13pt chuẩn văn bản hành chính Việt Nam
        normal_style = doc.styles["Normal"]
        normal_style.font.name = "Times New Roman"
        normal_style.font.size = Pt(13)
        if qn is not None and normal_style._element.rPr is not None:
            normal_style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")

        # Header tiêu đề tổng quát của văn bản
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_p.add_run(
            f"{doc_title.upper()}" + (f" (BAN HÀNH NĂM {issue_year})" if issue_year else "")
        )
        title_run.bold = True
        title_run.font.name = "Times New Roman"
        title_run.font.size = Pt(14)
        title_run.font.color.rgb = RGBColor(0x00, 0x54, 0xA6)

        subtitle_p = doc.add_paragraph()
        subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = subtitle_p.add_run(
            f"Trường Đại học Thủ Dầu Một (TDMU) — Bản xuất Word (.docx) từ văn bản gốc: {stem}.pdf"
        )
        sub_run.italic = True
        sub_run.font.name = "Times New Roman"
        sub_run.font.size = Pt(11)

        for page in pages_data:
            page_num = int(page.get("page_number", 1))
            raw_text = unicodedata.normalize("NFC", str(page.get("text") or ""))
            cleaned_text = normalize_vietnamese_academic_text(raw_text)
            tables_md: List[str] = page.get("tables_markdown") or []

            # Dòng phân trang nhẹ
            if len(pages_data) > 1:
                page_p = doc.add_paragraph()
                page_run = page_p.add_run(f"— Trang {page_num} —")
                page_run.italic = True
                page_run.font.name = "Times New Roman"
                page_run.font.size = Pt(10)
                page_run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

            for raw_line in cleaned_text.splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue

                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                run = p.add_run(line)
                run.font.name = "Times New Roman"

                # Định dạng theo cấp độ cấu trúc hành chính (Chương / Điều / Mục / Tiểu mục)
                if re.match(r"^(?:CHƯƠNG|QUYẾT\s+ĐỊNH|HƯỚNG\s+DẪN)\b", line, flags=re.IGNORECASE):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run.bold = True
                    run.font.size = Pt(13.5)
                    run.font.color.rgb = RGBColor(0x00, 0x54, 0xA6)
                elif re.match(
                    r"^(?:UBND\s+TỈNH|TRƯỜNG\s+ĐẠI\s+HỌC\s+THỦ\s+DẦU\s+MỘT|Số:\s*\d+)",
                    line,
                    flags=re.IGNORECASE,
                ):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run.bold = True
                    run.font.size = Pt(12.5)
                elif re.match(r"^(?:Điều\s+\d+|Mục\s+\d+)\b", line, flags=re.IGNORECASE):
                    run.bold = True
                    run.font.size = Pt(13)
                    run.font.color.rgb = RGBColor(0x00, 0x54, 0xA6)
                elif re.match(r"^\d+\.\d+(?:\.\d+)?\.?\s+", line):
                    run.bold = True
                    run.font.size = Pt(13)
                else:
                    run.font.size = Pt(13)

            # Render các bảng biểu trong trang thành bảng Word thực thụ có kẻ khung
            for tbl_md in tables_md:
                matrix = _parse_markdown_table_to_rows(tbl_md)
                if not matrix:
                    continue
                col_count = max(len(r) for r in matrix)
                word_tbl = doc.add_table(rows=len(matrix), cols=col_count)
                try:
                    word_tbl.style = "Table Grid"
                except KeyError:
                    pass

                for r_idx, row_cells in enumerate(matrix):
                    for c_idx in range(col_count):
                        val = row_cells[c_idx] if c_idx < len(row_cells) else ""
                        val_clean = normalize_vietnamese_academic_text(
                            unicodedata.normalize("NFC", val)
                        )
                        cell = word_tbl.cell(r_idx, c_idx)
                        cell.text = val_clean
                        for cp in cell.paragraphs:
                            for cr in cp.runs:
                                cr.font.name = "Times New Roman"
                                cr.font.size = Pt(11.5)
                                if r_idx == 0:
                                    cr.bold = True

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        if save_cache:
            cached_docx_path.write_bytes(buf.getvalue())
            buf.seek(0)
        return buf, cached_docx_path, download_filename

    # Dự phòng nếu chạy trong môi trường không có python-docx: đóng gói chuẩn OpenXML .docx
    from xml.sax.saxutils import escape

    body_parts: List[str] = [
        f"<w:p><w:r><w:t>{escape(doc_title)}</w:t></w:r></w:p>"
    ]
    for page in pages_data:
        cleaned_text = normalize_vietnamese_academic_text(
            unicodedata.normalize("NFC", str(page.get("text") or ""))
        )
        for raw_line in cleaned_text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                body_parts.append(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>")
        for tbl_md in page.get("tables_markdown") or []:
            matrix = _parse_markdown_table_to_rows(tbl_md)
            if not matrix:
                continue
            tbl_xml = ["<w:tbl>"]
            for row_cells in matrix:
                tbl_xml.append("<w:tr>")
                for c_val in row_cells:
                    tbl_xml.append(
                        f"<w:tc><w:p><w:r><w:t>{escape(c_val)}</w:t></w:r></w:p></w:tc>"
                    )
                tbl_xml.append("</w:tr>")
            tbl_xml.append("</w:tbl>")
            body_parts.append("".join(tbl_xml))

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_parts)}</w:body>"
        "</w:document>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", document_xml)
    buf.seek(0)
    if save_cache:
        cached_docx_path.write_bytes(buf.getvalue())
        buf.seek(0)
    return buf, cached_docx_path, download_filename


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent
    raw_dir = project_root / "data" / "raw_pdfs"
    processed_dir = project_root / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    docx_files = sorted(raw_dir.glob("*.docx"))
    if not docx_files:
        print("[*] Hiện không có file .docx nào trong data/raw_pdfs/ (Kho tri thức chỉ gồm 3 văn bản PDF chính thức TDMU).")
        return

    for docx_file in docx_files:
        print(f"[*] Đang bóc tách cấu trúc văn bản & bảng biểu từ DOCX: {docx_file.name}")
        structured = extract_docx_structured(docx_file)
        output_json = processed_dir / f"{docx_file.stem}_extracted.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(structured["pages"], f, ensure_ascii=False, indent=2)
        print(
            f"[+] Hoàn tất bóc tách DOCX ({structured['tables_count']} bảng biểu Markdown) -> {output_json}"
        )


if __name__ == "__main__":
    main()
