import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.parsers.test_pdf_extractor import resolve_tdmu_document_metadata


class HierarchicalChunk(BaseModel):
    """
    Cấu trúc Chunk phân cấp chuẩn cho văn bản pháp quy / quy chế / công văn hướng dẫn học vụ Việt Nam.
    Đảm bảo lưu giữ đầy đủ ngữ cảnh cha (Chương -> Điều/Mục -> Khoản/Tiểu mục -> Điểm)
    cùng `doc_title`, `issue_year` và `file_type` ("pdf" | "docx") để trích dẫn đa văn bản chính xác 100%.
    """

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_name: str
    doc_title: str = ""
    issue_year: str = ""
    file_type: str = "pdf"
    chapter: str = ""
    article: str = ""
    clause: str = ""
    page_number: int
    content: str  # Nội dung đầy đủ kèm header ngữ cảnh cha
    is_table: bool = False


class HierarchicalChunker:
    """
    Bộ chia nhỏ văn bản học vụ TDMU hỗ trợ 2 dạng cấu trúc pháp quy:
    1. Dạng Quy chế (`quy_che_dao_tao_tdmu_1774.pdf`):
       - Phân cấp theo: `Chương (I, II...)` -> `Điều (Điều 1, Điều 2...)` -> `Khoản (1., 2...)` -> `Điểm (a), b)...)`.
    2. Dạng Công văn / Hướng dẫn (`03/HD-ĐHTDM` và `432/ĐHTDM-TTNN`):
       - Phân cấp theo: `Mục lớn (Mục 1., 1., 2., 3...)` -> `Tiểu mục (1.1., 2.1., 2.2.1...)` -> `Điểm (a), b)...)`.
    - Bảo toàn 100% các bảng biểu Markdown (`is_table=True`), không bao giờ cắt vụn bảng.
    - Tự động gắn `doc_title` và `issue_year` cho từng văn bản.
    """

    CHAPTER_REGEX = re.compile(
        r"^\s*((?:CHƯƠNG|CHUONG|CHUANG|CHƯONG)\s+(?:[IVXLCDM]+|\d+)(?:[\s\.:–\-]+[^\n]*)?)",
        re.IGNORECASE | re.MULTILINE,
    )

    # Regex nhận diện Điều (Dạng Quy chế)
    ARTICLE_SPLIT_REGEX = re.compile(
        r"(?=^\s*(?:[•,\.\s]*)(?:Điều|Dieu|Di'u|Di&I|!Neu|lieu|Di'eu|Di4u|Di'h|Dih|Dan)[\.\s]+\d+[\.:„,])",
        re.IGNORECASE | re.MULTILINE,
    )
    ARTICLE_HEADER_REGEX = re.compile(
        r"^\s*(?:[•,\.\s]*)((?:Điều|Dieu|Di'u|Di&I|!Neu|lieu|Di'eu|Di4u|Di'h|Dih|Dan)[\.\s]+(\d+)[\.:„,]\s*[^\n]*)",
        re.IGNORECASE,
    )

    # Regex nhận diện Mục lớn trong văn bản Hướng dẫn / Công văn (VD: "Mục 1. ...", "1. Nguyên tắc chung...", "2. Hướng dẫn...")
    SECTION_SPLIT_REGEX = re.compile(
        r"(?=^\s*(?:Mục\s+\d+[\.:]|\d+\.)\s+[A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ])",
        re.MULTILINE,
    )
    SECTION_HEADER_REGEX = re.compile(
        r"^\s*(?:Mục\s+)?(\d+)[\.:]\s*([^\n]+)",
        re.IGNORECASE,
    )

    # Regex nhận diện Tiểu mục trong văn bản Hướng dẫn / Công văn (VD: "1.1. ...", "2.1. ...", "2.2.1. ...")
    SUBSECTION_SPLIT_REGEX = re.compile(
        r"(?=^\s*\d+\.\d+(?:\.\d+)?\.?\s+[A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ])",
        re.MULTILINE,
    )
    SUBSECTION_HEADER_REGEX = re.compile(
        r"^\s*(\d+\.\d+(?:\.\d+)?)\.?\s*([^\n]*)",
    )

    # Regex nhận diện Khoản trong Quy chế: "1. ", "2. ", hoặc "Khoản 1." ở đầu dòng
    CLAUSE_SPLIT_REGEX = re.compile(
        r"(?=^\s*(?:[•,\.\s]*)(?:Khoản\s+\d+[\.:]?|\d+\.)\s*[A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ])",
        re.MULTILINE,
    )
    CLAUSE_HEADER_REGEX = re.compile(
        r"^\s*(?:[•,\.\s]*)(Khoản\s+\d+[\.:]?|\d+\.)\s*",
        re.IGNORECASE,
    )

    # Regex nhận diện Điểm: "a) ", "b) ", "đ) " hoặc "a. " ở đầu dòng
    POINT_REGEX = re.compile(
        r"^\s*([a-eđghiklmnoôơpqrstuưvxy][\)\.])\s+",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(self, max_chunk_chars: int = 1200):
        self.max_chunk_chars = max_chunk_chars

    @staticmethod
    def _build_context_header(
        document_name: str,
        doc_title: str,
        issue_year: str,
        page_number: int,
        chapter: str,
        article: str,
        clause: str,
        points: List[str] | None = None,
        is_table: bool = False,
    ) -> str:
        """Tạo chuỗi Header ngữ cảnh cha chuẩn hóa đứng đầu mỗi chunk."""
        parts = [
            f"Tài liệu: {doc_title} ({document_name})",
            f"Năm ban hành: {issue_year}",
            f"Trang: {page_number}",
        ]
        if chapter:
            parts.append(chapter)
        if article:
            parts.append(article)
        if clause:
            parts.append(clause)
        if points:
            parts.append(f"Điểm: {', '.join(points)}")
        if is_table:
            parts.append("Loại: Bảng biểu quy chế")

        return "[" + " | ".join(parts) + "]\n"

    def _extract_points_summary(self, text: str) -> List[str]:
        """Tìm danh sách các Điểm (a), b), c)...) xuất hiện bên trong một Khoản / Tiểu mục."""
        matches = self.POINT_REGEX.findall(text)
        seen = []
        for m in matches:
            if m not in seen:
                seen.append(m)
        return seen

    def _split_oversized_clause(self, text: str) -> List[str]:
        """
        Nếu một Khoản / Tiểu mục quá dài (vượt `max_chunk_chars`), ưu tiên tách theo từng Điểm (`a)`, `b)`...)
        hoặc theo dòng để không cắt ngang câu.
        """
        if len(text) <= self.max_chunk_chars:
            return [text.strip()]

        point_split_pattern = re.compile(
            r"(?=^\s*[a-eđghiklmnoôơpqrstuưvxy][\)\.]\s+)",
            re.IGNORECASE | re.MULTILINE,
        )
        segments = [s.strip() for s in point_split_pattern.split(text) if s.strip()]
        if len(segments) <= 1:
            segments = [line.strip() for line in text.split("\n") if line.strip()]

        results: List[str] = []
        current_buf: List[str] = []
        current_len = 0

        for seg in segments:
            if current_len + len(seg) + 1 > self.max_chunk_chars and current_buf:
                results.append("\n".join(current_buf).strip())
                current_buf = [seg]
                current_len = len(seg)
            else:
                current_buf.append(seg)
                current_len += len(seg) + 1

        if current_buf:
            results.append("\n".join(current_buf).strip())

        return results

    @staticmethod
    def _is_guideline_document(doc_name: str, pages_data: List[Dict[str, Any]]) -> bool:
        """
        Kiểm tra xem văn bản thuộc dạng Công văn / Hướng dẫn (`03/HD-ĐHTDM`, `432/ĐHTDM-TTNN`)
        phân cấp theo Mục lớn (`1.`, `2.`) -> Tiểu mục (`2.1.`, `2.2.`) hay dạng Quy chế (`Điều 1`, `Điều 2`).
        """
        lower_name = doc_name.lower()
        if "huong_dan" in lower_name or "cong_van" in lower_name:
            return True
        combined_sample = "\n".join((p.get("text") or "") for p in pages_data[:2])
        has_dieu = bool(re.search(r"^\s*Điều\s+\d+\.", combined_sample, re.MULTILINE))
        return not has_dieu

    def _chunk_guideline_pages(
        self,
        pages_data: List[Dict[str, Any]],
        doc_name: str,
        doc_title: str,
        issue_year: str,
        file_type: str = "pdf",
    ) -> List[HierarchicalChunk]:
        """
        Phân mảnh chuyên biệt cho văn bản Công văn / Hướng dẫn (`03/HD-ĐHTDM` và `432/ĐHTDM-TTNN`)
        theo cấu trúc: `Mục lớn (1., 2., 3.)` -> `Tiểu mục (1.1., 2.1., 2.2.1.)` -> `Điểm (a), b))`.
        """
        chunks: List[HierarchicalChunk] = []
        current_chapter = doc_title
        current_section = ""
        current_subsection = ""

        for page in pages_data:
            page_num = int(page.get("page_number", 1))
            raw_text = (page.get("text") or "").strip()
            tables_md: List[str] = page.get("tables_markdown") or []

            if raw_text:
                section_blocks = self.SECTION_SPLIT_REGEX.split(raw_text)
                for s_block in section_blocks:
                    s_block = s_block.strip()
                    if not s_block:
                        continue

                    sec_match = self.SECTION_HEADER_REGEX.match(s_block)
                    if sec_match:
                        sec_num = sec_match.group(1)
                        sec_title = " ".join(sec_match.group(2).split())
                        current_section = f"Mục {sec_num}. {sec_title}"
                        current_subsection = ""
                        lines = s_block.split("\n")
                        section_body = "\n".join(lines[1:]).strip()
                    else:
                        section_body = s_block

                    if not section_body:
                        continue

                    # Nếu là đoạn tiêu ngữ mở đầu (chưa vào Mục 1), vẫn lưu nhưng đánh dấu rõ article=""
                    if not current_section:
                        header = self._build_context_header(
                            document_name=doc_name,
                            doc_title=doc_title,
                            issue_year=issue_year,
                            page_number=page_num,
                            chapter=current_chapter,
                            article="",
                            clause="Thông tin ban hành",
                            is_table=False,
                        )
                        chunks.append(
                            HierarchicalChunk(
                                document_name=doc_name,
                                doc_title=doc_title,
                                issue_year=issue_year,
                                file_type=file_type,
                                chapter=current_chapter,
                                article="",
                                clause="Thông tin ban hành",
                                page_number=page_num,
                                content=header + section_body,
                                is_table=False,
                            )
                        )
                        continue

                    # Tách theo Tiểu mục (1.1., 2.1., 2.2.1...)
                    sub_blocks = self.SUBSECTION_SPLIT_REGEX.split(section_body)
                    for sub_b in sub_blocks:
                        sub_b = sub_b.strip()
                        if not sub_b:
                            continue

                        sub_match = self.SUBSECTION_HEADER_REGEX.match(sub_b)
                        if sub_match:
                            sub_num = sub_match.group(1)
                            current_subsection = f"Tiểu mục {sub_num}"
                        elif not current_subsection:
                            current_subsection = "Nội dung chi tiết"

                        sub_segments = self._split_oversized_clause(sub_b)
                        for seg in sub_segments:
                            points_found = self._extract_points_summary(seg)
                            clause_label = current_subsection
                            if points_found and clause_label:
                                clause_label = (
                                    f"{current_subsection} (Điểm {', '.join(points_found)})"
                                )

                            header = self._build_context_header(
                                document_name=doc_name,
                                doc_title=doc_title,
                                issue_year=issue_year,
                                page_number=page_num,
                                chapter=current_chapter,
                                article=current_section,
                                clause=clause_label,
                                is_table=False,
                            )
                            chunks.append(
                                HierarchicalChunk(
                                    document_name=doc_name,
                                    doc_title=doc_title,
                                    issue_year=issue_year,
                                    file_type=file_type,
                                    chapter=current_chapter,
                                    article=current_section,
                                    clause=clause_label,
                                    page_number=page_num,
                                    content=header + seg,
                                    is_table=False,
                                )
                            )

            # Bảng biểu Markdown trong văn bản Hướng dẫn
            for tbl_idx, tbl_md in enumerate(tables_md, start=1):
                tbl_md = tbl_md.strip()
                if not tbl_md:
                    continue

                table_clause_label = (
                    f"{current_subsection} - Bảng biểu {tbl_idx}"
                    if current_subsection
                    else f"Bảng biểu {tbl_idx}"
                )
                art_for_table = current_section or f"Mục 1. {doc_title}"
                header = self._build_context_header(
                    document_name=doc_name,
                    doc_title=doc_title,
                    issue_year=issue_year,
                    page_number=page_num,
                    chapter=current_chapter,
                    article=art_for_table,
                    clause=table_clause_label,
                    is_table=True,
                )
                chunks.append(
                    HierarchicalChunk(
                        document_name=doc_name,
                        doc_title=doc_title,
                        issue_year=issue_year,
                        file_type=file_type,
                        chapter=current_chapter,
                        article=art_for_table,
                        clause=table_clause_label,
                        page_number=page_num,
                        content=header + tbl_md,
                        is_table=True,
                    )
                )

        return chunks

    def chunk_pages(
        self, pages_data: List[Dict[str, Any]] | Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Nhận dữ liệu đầu ra từ `test_pdf_extractor.py` hoặc `docx_extractor.py`
        và phân mảnh thành danh sách `HierarchicalChunk` có đầy đủ `doc_title`, `issue_year`, `file_type`.
        """
        if isinstance(pages_data, dict):
            if "pages" in pages_data and isinstance(pages_data["pages"], list):
                pages_list = pages_data["pages"]
            else:
                pages_list = [pages_data]
        else:
            pages_list = pages_data

        if not pages_list:
            return []

        first_page = pages_list[0]
        doc_name = (
            first_page.get("source")
            or first_page.get("document_name")
            or "unknown.pdf"
        )
        meta_info = resolve_tdmu_document_metadata(doc_name)
        doc_title = first_page.get("doc_title") or meta_info["doc_title"]
        issue_year = str(first_page.get("issue_year") or meta_info["issue_year"])
        file_type = str(first_page.get("file_type") or meta_info.get("file_type", "pdf"))

        # Nhánh 1: Văn bản dạng Công văn / Hướng dẫn (Mục 1 -> Tiểu mục 1.1)
        if self._is_guideline_document(doc_name, pages_list):
            guideline_chunks = self._chunk_guideline_pages(
                pages_data=pages_list,
                doc_name=doc_name,
                doc_title=doc_title,
                issue_year=issue_year,
                file_type=file_type,
            )
            return [c.model_dump() for c in guideline_chunks]

        # Nhánh 2: Văn bản dạng Quy chế (Chương -> Điều -> Khoản -> Điểm)
        chunks: List[HierarchicalChunk] = []
        current_chapter = "Quy định chung"
        current_article = ""
        current_clause = ""

        for page in pages_list:
            page_num = int(page.get("page_number", 1))
            raw_text = (page.get("text") or "").strip()
            tables_md: List[str] = page.get("tables_markdown") or []

            if raw_text:
                article_blocks = self.ARTICLE_SPLIT_REGEX.split(raw_text)

                for block in article_blocks:
                    block = block.strip()
                    if not block:
                        continue

                    chapter_matches = self.CHAPTER_REGEX.findall(block)
                    if chapter_matches:
                        current_chapter = " ".join(chapter_matches[-1].split())
                        current_article = ""
                        current_clause = ""
                        block_without_chapter = self.CHAPTER_REGEX.sub("", block).strip()
                        if not block_without_chapter:
                            continue
                        block = block_without_chapter

                    article_match = self.ARTICLE_HEADER_REGEX.match(block)
                    if article_match:
                        raw_art_header = " ".join(article_match.group(1).split())
                        art_num = article_match.group(2)
                        normalized_art = re.sub(
                            r"^(?:Điều|Dieu|Di'u|Di&I|!Neu|lieu|Di'eu|Di4u|Di'h|Dih|Dan)[\.\s]+\d+[\.:„,]?\s*",
                            f"Điều {art_num}. ",
                            raw_art_header,
                            flags=re.IGNORECASE,
                        )
                        current_article = normalized_art.strip()
                        current_clause = ""
                        lines = block.split("\n")
                        article_body = "\n".join(lines[1:]).strip()
                    else:
                        article_body = block

                    if not article_body:
                        header = self._build_context_header(
                            document_name=doc_name,
                            doc_title=doc_title,
                            issue_year=issue_year,
                            page_number=page_num,
                            chapter=current_chapter,
                            article=current_article,
                            clause=current_clause,
                            is_table=False,
                        )
                        chunks.append(
                            HierarchicalChunk(
                                document_name=doc_name,
                                doc_title=doc_title,
                                issue_year=issue_year,
                                file_type=file_type,
                                chapter=current_chapter,
                                article=current_article,
                                clause=current_clause,
                                page_number=page_num,
                                content=header + current_article,
                                is_table=False,
                            )
                        )
                        continue

                    clause_blocks = self.CLAUSE_SPLIT_REGEX.split(article_body)

                    for c_block in clause_blocks:
                        c_block = c_block.strip()
                        if not c_block:
                            continue

                        clause_match = self.CLAUSE_HEADER_REGEX.match(c_block)
                        if clause_match:
                            raw_clause_num = clause_match.group(1).rstrip(".:").strip()
                            if raw_clause_num.lower().startswith("khoản"):
                                current_clause = raw_clause_num
                            else:
                                current_clause = f"Khoản {raw_clause_num}"

                        sub_segments = self._split_oversized_clause(c_block)
                        for seg in sub_segments:
                            points_found = self._extract_points_summary(seg)
                            clause_label = current_clause
                            if points_found and clause_label:
                                clause_label = f"{current_clause} (Điểm {', '.join(points_found)})"
                            elif points_found:
                                clause_label = f"Điểm {', '.join(points_found)}"

                            header = self._build_context_header(
                                document_name=doc_name,
                                doc_title=doc_title,
                                issue_year=issue_year,
                                page_number=page_num,
                                chapter=current_chapter,
                                article=current_article,
                                clause=clause_label,
                                is_table=False,
                            )

                            chunks.append(
                                HierarchicalChunk(
                                    document_name=doc_name,
                                    doc_title=doc_title,
                                    issue_year=issue_year,
                                    file_type=file_type,
                                    chapter=current_chapter,
                                    article=current_article,
                                    clause=clause_label,
                                    page_number=page_num,
                                    content=header + seg,
                                    is_table=False,
                                )
                            )

            for tbl_idx, tbl_md in enumerate(tables_md, start=1):
                tbl_md = tbl_md.strip()
                if not tbl_md:
                    continue

                table_clause_label = (
                    f"{current_clause} - Bảng biểu {tbl_idx}"
                    if current_clause
                    else f"Bảng biểu {tbl_idx}"
                )
                header = self._build_context_header(
                    document_name=doc_name,
                    doc_title=doc_title,
                    issue_year=issue_year,
                    page_number=page_num,
                    chapter=current_chapter,
                    article=current_article or "Bảng quy định học vụ",
                    clause=table_clause_label,
                    is_table=True,
                )

                chunks.append(
                    HierarchicalChunk(
                        document_name=doc_name,
                        doc_title=doc_title,
                        issue_year=issue_year,
                        file_type=file_type,
                        chapter=current_chapter,
                        article=current_article or "Bảng quy định học vụ",
                        clause=table_clause_label,
                        page_number=page_num,
                        content=header + tbl_md,
                        is_table=True,
                    )
                )

        return [c.model_dump() for c in chunks]

    def process_extracted_json_file(
        self,
        input_json_path: str | Path,
        output_json_path: Optional[str | Path] = None,
    ) -> List[Dict[str, Any]]:
        input_path = Path(input_json_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file JSON đầu vào: {input_path}")

        with open(input_path, "r", encoding="utf-8") as f:
            pages_data = json.load(f)

        chunks_data = self.chunk_pages(pages_data)

        if output_json_path:
            out_path = Path(output_json_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(chunks_data, f, ensure_ascii=False, indent=2)

        return chunks_data
