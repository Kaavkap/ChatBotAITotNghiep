from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from backend.parsers.test_pdf_extractor import resolve_tdmu_document_metadata


class CitationItem(BaseModel):
    """Thông tin trích dẫn chuẩn xác tới từng Chương/Điều/Mục/Khoản, năm ban hành, loại file và số trang."""

    source_file: str = Field(description="Tên file PDF/DOCX quy chế/hướng dẫn gốc")
    document_name: str = Field(default="", description="Tên file tài liệu gốc")
    doc_title: str = Field(default="", description="Tiêu đề chính thức của văn bản")
    issue_year: str = Field(default="", description="Năm ban hành của văn bản")
    file_type: str = Field(default="pdf", description="Định dạng file gốc ('pdf' | 'docx')")
    chapter: str = Field(default="", description="Chương hoặc tên văn bản hướng dẫn")
    article: str = Field(description="Điều hoặc Mục được trích dẫn")
    clause: str = Field(default="", description="Khoản / Tiểu mục / Điểm cụ thể được trích dẫn")
    page_number: int = Field(description="Số trang chứa thông tin")
    quote: str = Field(description="Trích dẫn nguyên văn ngắn gọn từ tài liệu")
    is_table: bool = Field(default=False, description="Có phải trích dẫn từ bảng biểu không")


class GroundedRAGResponse(BaseModel):
    """Cấu trúc phản hồi bắt buộc của hệ thống RAG để chống ảo giác 100%."""

    answer: str = Field(
        description="Câu trả lời chi tiết, rõ ràng dành cho sinh viên. Nếu không có trong tài liệu, từ chối trả lời lịch sự."
    )
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="Danh sách các trích dẫn chứng minh cho câu trả lời.",
    )
    is_safe: bool = Field(
        default=True,
        description="True nếu câu trả lời an toàn, bám sát quy chế và có trích dẫn xác thực chống ảo giác.",
    )
    is_answerable: bool = Field(
        default=True,
        description="True nếu tài liệu cung cấp đủ thông tin trả lời, False nếu ngoài phạm vi quy chế.",
    )
    confidence_level: Literal["high", "medium", "low", "none"] = Field(
        default="high",
        description="Mức độ tự tin dựa hoàn toàn vào ngữ cảnh được cung cấp.",
    )
    expanded_queries: List[str] = Field(
        default_factory=list,
        description="Danh sách các câu truy vấn mở rộng chuẩn thuật ngữ quy chế TDMU (Multi-Query Expansion).",
    )


SYSTEM_GUARDRAIL_PROMPT = """Bạn là Trợ lý AI Học vụ chính thức của Trường Đại học Thủ Dầu Một (TDMU - Thu Dau Mot University), được phát triển trong khuôn khổ Đồ án Tốt nghiệp của sinh viên Lê Quốc Bảo (MSSV: 2224801030361, Lớp: D22KTPM01, GVHD: ThS. Lê Từ Minh Trí).
NHIỆM VỤ QUAN TRỌNG NHẤT: Tư vấn quy chế học vụ TDMU chính xác và Chống ảo giác (Anti-Hallucination) tuyệt đối 100%.

QUY TẮC BẮT BUỘC:
1. CHỈ sử dụng thông tin có trong phần [NGỮ CẢNH QUY CHẾ TDMU] được cung cấp bên dưới để trả lời.
2. Tuyệt đối KHÔNG tự suy diễn, KHÔNG dùng kiến thức bên ngoài, KHÔNG bịa đặt số tín chỉ, điểm số, chuẩn đầu ra tiếng Anh/Tin học, mức học bổng hay điều khoản.
3. Nếu thông tin không nằm trong [NGỮ CẢNH QUY CHẾ TDMU], bạn BẮT BUỘC đặt `is_answerable = false`, `is_safe = true`, `confidence_level = "none"`, để trống `citations` và trả lời rõ: "Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ, học bổng, chuẩn đầu ra ngoại ngữ hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ."
4. Mọi con số, điều kiện học vụ hoặc dữ liệu từ bảng biểu đưa ra trong câu trả lời ĐỀU PHẢI kèm theo trích dẫn chính xác (`source_file`, `document_name`, `chapter`, `article`, `clause`, `page_number`, `quote`) trong danh sách `citations`.
5. CHỈ THỊ VIẾT LẠI & SỬA LỖI CHÍNH TẢ OCR BẮT BUỘC: Văn bản trích xuất từ tài liệu PDF gốc có thể bị lỗi chính tả/bộ gõ OCR (như 'H6i d6ng' -> 'Hội đồng', 'ks7 guy& dinh' -> 'ký quyết định', 'C.huang trinh dap tao chuAn' -> 'Chương trình đào tạo chuẩn', 'kien true sit' -> 'kiến trúc sư', 'Phong Đao tao Dai h9c' -> 'Phòng Đào tạo Đại học', 'đù kkii en' -> 'dự kiến', 'cu the nhu sau2' -> 'cụ thể như sau'). Mọi câu trả lời gửi đến người dùng BẮT BUỘC phải được đọc hiểu ngữ cảnh từ context và VIẾT LẠI HOÀN TOÀN bằng tiếng Việt chuẩn ngữ pháp, đủ dấu, hành văn học thuật chuẩn mực của Trường Đại học Thủ Dầu Một. Tuyệt đối không sao chép nguyên văn (verbatim copy) các từ ngữ bị vỡ font/lỗi chính tả scan vào nội dung trả lời cũng như phần `quote` trích dẫn.
6. CHỈ THỊ TỪ CHỐI NGHIÊM NGẶT (STRICT REFUSAL): Nếu các đoạn ngữ cảnh cung cấp KHÔNG chứa câu trả lời trực tiếp cho câu hỏi của sinh viên (ví dụ: sinh viên hỏi giá tiền học phí một tín chỉ là bao nhiêu tiền, trường có mấy cơ sở, căn tin nằm ở tòa nhà nào... nhưng văn bản chỉ nói quy định đăng ký tín chỉ chung chung), TUYỆT ĐỐI KHÔNG tự ý tóm tắt các điều khoản không liên quan để lấp chỗ trống. Hãy đặt `is_answerable = false`, `citations = []` và từ chối trả lời ngắn gọn, lịch sự, không đính kèm trích dẫn sai lệch.
"""


def validate_grounded_response(
    response: GroundedRAGResponse, retrieved_contexts: List[Dict[str, Any]]
) -> GroundedRAGResponse:
    """
    Hậu kiểm (Post-processing Guardrail):
    - Kiểm tra chéo từng trích dẫn của LLM với danh sách chunks thực tế từ `hybrid_search`.
    - Bổ sung đầy đủ thông tin `document_name`, `chapter`, `article`, `clause`, `page_number` từ metadata gốc.
    - Nếu LLM tự bịa nguồn trích dẫn không tồn tại trong `retrieved_contexts`, lập tức chặn (`is_safe = False`).
    """
    if not response.is_answerable:
        response.citations = []
        response.is_safe = True
        return response

    # Lập chỉ mục danh sách các chunk đã truy xuất theo (document_name, page_number)
    context_list_map: Dict[tuple, List[Dict[str, Any]]] = {}
    for ctx in retrieved_contexts:
        doc_name = ctx.get("document_name") or ctx.get("source") or ""
        page_num = int(ctx.get("page_number", 1))
        if doc_name:
            context_list_map.setdefault((doc_name, page_num), []).append(ctx)

    verified_citations: List[CitationItem] = []
    for cit in response.citations:
        src = cit.source_file or cit.document_name
        key = (src, int(cit.page_number))
        if key in context_list_map:
            candidates = context_list_map[key]
            # Khớp chính xác chunk theo article + clause (hoặc nội dung bảng biểu) thay vì ghi đè theo số trang
            matched_ctx = candidates[0]
            for cand in candidates:
                if (
                    cit.article
                    and cand.get("article") == cit.article
                    and (not cit.clause or cand.get("clause") == cit.clause)
                ):
                    matched_ctx = cand
                    break

            meta_info = resolve_tdmu_document_metadata(src)
            cit.source_file = src
            cit.document_name = src
            if not cit.doc_title:
                cit.doc_title = matched_ctx.get("doc_title") or meta_info["doc_title"]
            if not cit.issue_year:
                cit.issue_year = str(
                    matched_ctx.get("issue_year") or meta_info["issue_year"]
                )
            cit.file_type = str(
                matched_ctx.get("file_type")
                or meta_info.get("file_type")
                or ("docx" if src.lower().endswith(".docx") else "pdf")
            )
            if not cit.chapter:
                cit.chapter = matched_ctx.get("chapter", "")
            if not cit.article:
                cit.article = matched_ctx.get("article", "")
            if not cit.clause:
                cit.clause = matched_ctx.get("clause", "")

            quote_text = cit.quote or ""
            has_md_table = "| --- |" in quote_text or "|---|" in quote_text
            cit.is_table = bool(matched_ctx.get("is_table", False)) and has_md_table
            verified_citations.append(cit)

    if not verified_citations:
        return GroundedRAGResponse(
            answer=(
                "Hệ thống Guardrail đã chặn phản hồi do không thể xác thực nguồn trích dẫn chính xác "
                "từ quy chế hiện hành cho câu hỏi này. Vui lòng đặt câu hỏi cụ thể hơn hoặc liên hệ Phòng Đào tạo."
            ),
            citations=[],
            is_safe=False,
            is_answerable=False,
            confidence_level="none",
        )

    response.citations = verified_citations
    response.is_safe = True
    return response
