import re
import uuid
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class AcademicChunk(BaseModel):
    """Mô hình dữ liệu cho một Chunk quy chế học vụ kèm metadata trích dẫn."""

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str
    page_number: int
    chapter: str = ""
    article: str = ""
    chunk_type: str = "text"  # "text" hoặc "table"
    content: str


class RegulationChunker:
    """
    Bộ chia nhỏ văn bản quy chế học vụ theo cấu trúc phân cấp (Chương -> Điều -> Khoản)
    và tách riêng các bảng biểu Markdown để giữ nguyên ngữ cảnh tra cứu.
    """

    CHAPTER_PATTERN = re.compile(
        r"^(CHƯƠNG\s+[IVXLCDM\d]+[^\n]*)", re.IGNORECASE | re.MULTILINE
    )
    ARTICLE_PATTERN = re.compile(
        r"(?=^(?:Điều\s+\d+[\.:]?[^\n]*))", re.IGNORECASE | re.MULTILINE
    )

    def __init__(self, max_chunk_chars: int = 1500, overlap_chars: int = 200):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def _split_long_text(self, text: str) -> List[str]:
        """Chia nhỏ đoạn văn bản nếu vượt quá độ dài tối đa, ưu tiên ngắt theo dòng/khoản."""
        if len(text) <= self.max_chunk_chars:
            return [text.strip()]

        lines = text.split("\n")
        sub_chunks: List[str] = []
        current_lines: List[str] = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > self.max_chunk_chars and current_lines:
                chunk_str = "\n".join(current_lines).strip()
                sub_chunks.append(chunk_str)
                # Giữ lại phần đuôi làm overlap ngữ cảnh
                overlap_text = chunk_str[-self.overlap_chars :] if self.overlap_chars > 0 else ""
                current_lines = [overlap_text, line] if overlap_text else [line]
                current_len = sum(len(l) + 1 for l in current_lines)
            else:
                current_lines.append(line)
                current_len += line_len

        if current_lines:
            sub_chunks.append("\n".join(current_lines).strip())

        return [c for c in sub_chunks if c]

    def chunk_extracted_pages(
        self, pages_data: List[Dict[str, Any]]
    ) -> List[AcademicChunk]:
        """
        Nhận đầu vào là danh sách các trang từ `extract_pdf_with_tables`
        và trả về danh sách các `AcademicChunk` có đầy đủ thông tin Chương/Điều/Trang.
        """
        chunks: List[AcademicChunk] = []
        current_chapter = "Quy định chung"
        current_article = ""

        for page in pages_data:
            source = page.get("source", "unknown.pdf")
            page_num = page.get("page_number", 1)
            raw_text = page.get("text", "")
            tables_md = page.get("tables_markdown", [])

            # Cập nhật Chương nếu xuất hiện trên trang
            chapter_matches = self.CHAPTER_PATTERN.findall(raw_text)
            if chapter_matches:
                current_chapter = chapter_matches[-1].strip()

            # Tách văn bản theo từng "Điều X."
            article_blocks = self.ARTICLE_PATTERN.split(raw_text)
            for block in article_blocks:
                block = block.strip()
                if not block:
                    continue

                first_line = block.split("\n", 1)[0].strip()
                if re.match(r"^Điều\s+\d+", first_line, re.IGNORECASE):
                    current_article = first_line

                for sub_text in self._split_long_text(block):
                    header_prefix = f"[{source} | Trang {page_num}"
                    if current_chapter:
                        header_prefix += f" | {current_chapter}"
                    if current_article:
                        header_prefix += f" | {current_article}"
                    header_prefix += "]\n"

                    chunks.append(
                        AcademicChunk(
                            source=source,
                            page_number=page_num,
                            chapter=current_chapter,
                            article=current_article,
                            chunk_type="text",
                            content=header_prefix + sub_text,
                        )
                    )

            # Đóng gói từng bảng biểu thành chunk độc lập kèm ngữ cảnh Điều/Chương hiện tại
            for idx, tbl_md in enumerate(tables_md, start=1):
                if not tbl_md.strip():
                    continue
                table_header = (
                    f"[BẢNG BIỂU {idx} | {source} | Trang {page_num} | "
                    f"{current_chapter} | {current_article or 'Bảng quy chế'}]\n"
                )
                chunks.append(
                    AcademicChunk(
                        source=source,
                        page_number=page_num,
                        chapter=current_chapter,
                        article=current_article or f"Bảng biểu trang {page_num}",
                        chunk_type="table",
                        content=table_header + tbl_md,
                    )
                )

        return chunks

