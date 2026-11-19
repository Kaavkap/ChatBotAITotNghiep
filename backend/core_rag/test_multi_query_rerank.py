import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import DOCUMENT_CHUNK_COUNTS, INITIAL_CHUNKS_COUNT, rag_pipeline


def run_multi_query_rerank_tests() -> None:
    print("=" * 92)
    print(f"KHO TRI THỨC CHÍNH THỨC TDMU: {INITIAL_CHUNKS_COUNT} CHUNKS ({DOCUMENT_CHUNK_COUNTS})")
    print("KIỂM THỬ KIẾN TRÚC MULTI-QUERY EXPANSION & RE-RANKING (3 VĂN BẢN CHÍNH THỨC TDMU)")
    print("=" * 92)

    assert INITIAL_CHUNKS_COUNT == 113, (
        f"Lỗi: Kho tri thức chính thức TDMU phải có đúng 113 chunks từ 3 văn bản thật, nhưng nhận {INITIAL_CHUNKS_COUNT}"
    )

    test_cases = [
        (
            "Đang học mà muốn bảo lưu nghỉ tạm 1 năm thì thủ tục sao?",
            "Điều 21",
            "2021",
            "pdf",
        ),
        (
            "Thi rớt bao nhiêu tín chỉ thì bị đuổi học?",
            "Điều 23",
            "2021",
            "pdf",
        ),
        (
            "Học kỳ này mình tích lũy được 10 tín chỉ thì hệ số hưởng học bổng khuyến khích học tập là bao nhiêu?",
            "Mục 1",
            "2023",
            "pdf",
        ),
        (
            "Có những hình thức nào để hoàn thành chuẩn đầu ra ngoại ngữ và điểm chuẩn EPT/IELTS/TOEIC tại TDMU?",
            "Mục 3",
            "2023",
            "pdf",
        ),
    ]

    for idx, (question, expected_article, expected_year, expected_type) in enumerate(test_cases, start=1):
        print(f"\n[KỊCH BẢN #{idx}] Câu hỏi: \"{question}\"")
        result = rag_pipeline.answer_question(question=question, top_k=5)

        print("  -> Truy vấn mở rộng (expanded_queries):")
        for eq in result.expanded_queries:
            print(f"     + {eq}")

        cited_summary = [
            f"[{c.file_type.upper()}] {c.doc_title} (Ban hành: {c.issue_year}) | {c.article} | Trang {c.page_number}"
            for c in result.citations
        ]
        print(f"  -> Các trích dẫn sau Re-ranking: {cited_summary}")

        assert any(
            expected_article in c.article
            and c.issue_year == expected_year
            and c.file_type == expected_type
            for c in result.citations
        ), f"Lỗi: Kỳ vọng tìm trúng '{expected_article}' ({expected_year}, {expected_type}) nhưng nhận {cited_summary}"

    print("\n[OK] Toàn bộ 4 kịch bản trên 3 văn bản chính thức TDMU (113 chunks) đều mở rộng truy vấn và Rerank chính xác 100%!")

    print("\n" + "=" * 92)
    print("KIỂM THỬ RELEVANCE GATE & STRICT REFUSAL VỚI CÂU HỎI BẪY NGOÀI DỮ LIỆU")
    print("=" * 92)

    trap_questions = [
        "Học phí một tín chỉ ngành Kỹ thuật phần mềm năm nay ở TDMU là bao nhiêu tiền?",
        "Trường Đại học Thủ Dầu Một có mấy cơ sở và căn tin nằm ở tòa nhà nào?",
        "Trường Đại học Thủ Dầu Một nằm ở đâu",
        "Hiệu trưởng trường là ai",
        "Hôm nay trời có mưa không",
    ]

    for idx, trap_q in enumerate(trap_questions, start=1):
        print(f"\n[CÂU HỎI BẪY #{idx}]: \"{trap_q}\"")
        res = rag_pipeline.answer_question(question=trap_q, top_k=5)
        print(f"  -> is_safe: {res.is_safe} | is_answerable: {res.is_answerable} | citations: {len(res.citations)}")
        print(f"  -> Câu trả lời từ chối an toàn:\n     {res.answer}")

        assert res.is_safe is True, "Phải giữ trạng thái is_safe = True!"
        assert res.is_answerable is False, "Phải đánh dấu is_answerable = False!"
        assert len(res.citations) == 0, "Không được phép gắn trích dẫn sai lệch cho câu hỏi ngoài dữ liệu!"
        assert "1774/QĐ-ĐHTDM" in res.answer, "Phải thông báo rõ không có trong Quy chế 1774/QĐ-ĐHTDM!"

    print("\n[OK] Kiểm thử Strict Refusal (Chống ảo giác & Từ chối câu hỏi bẫy) ĐẠT 100%!")


if __name__ == "__main__":
    run_multi_query_rerank_tests()

