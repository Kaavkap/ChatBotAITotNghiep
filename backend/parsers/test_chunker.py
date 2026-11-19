import json
import sys
from pathlib import Path

# Đảm bảo import được package backend khi chạy trực tiếp từ thư mục gốc
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.parsers.hierarchical_chunker import HierarchicalChunker


def create_sample_extracted_json(sample_path: Path) -> None:
    """
    Tạo một file JSON giả lập đầu ra của `test_pdf_extractor.py`
    theo sát Quy chế Học vụ Trường Đại học Thủ Dầu Một (TDMU) để kiểm thử ngay.
    """
    sample_pages = [
        {
            "source": "Quy_che_dao_tao_tin_chi_TDMU_2026.pdf",
            "page_number": 4,
            "text": (
                "CHƯƠNG II: ĐÁNH GIÁ KẾT QUẢ HỌC TẬP VÀ CẢNH BÁO HỌC VỤ TẠI TDMU\n"
                "Điều 14. Thang điểm và cách tính điểm trung bình chung học tập\n"
                "1. Điểm đánh giá bộ phận và điểm thi kết thúc học phần được chấm theo thang điểm 10 (từ 0 đến 10), làm tròn đến một chữ số thập phân.\n"
                "2. Điểm học phần được quy đổi sang điểm chữ và thang điểm 4 theo phân loại của Trường Đại học Thủ Dầu Một:\n"
                "a) Loại đạt: Từ điểm D (1.0) trở lên đối với các học phần thông thường.\n"
                "b) Loại đạt có điều kiện: Điểm C (2.0) trở lên đối với học phần cốt lõi ngành.\n"
                "c) Loại không đạt: Điểm F (0.0), sinh viên bắt buộc phải đăng ký học lại.\n"
                "Điều 15. Cảnh báo kết quả học tập và buộc thôi học\n"
                "1. Cuối mỗi học kỳ chính, sinh viên bị cảnh báo kết quả học tập nếu thuộc một trong các trường hợp:\n"
                "a) Tổng số tín chỉ không đạt trong học kỳ vượt quá 50% khối lượng đã đăng ký.\n"
                "b) Điểm trung bình chung học kỳ (GPA) đạt dưới 0.80 đối với học kỳ đầu của khóa học, dưới 1.00 đối với các học kỳ tiếp theo.\n"
                "2. Sinh viên bị buộc thôi học nếu số lần cảnh báo kết quả học tập vượt quá 2 lần liên tiếp.\n"
                "CHƯƠNG III: CHUẨN ĐẦU RA NGOẠI NGỮ, TIN HỌC VÀ HỌC BỔNG TDMU\n"
                "Điều 22. Chuẩn đầu ra tiếng Anh và Tin học đối với sinh viên đại học chính quy TDMU\n"
                "1. Chuẩn đầu ra tiếng Anh: Sinh viên khối ngành không chuyên ngữ phải đạt trình độ năng lực ngoại ngữ bậc 3/6 theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam (tương đương B1 hoặc IELTS 4.5, TOEIC 450 trở lên).\n"
                "2. Chuẩn đầu ra Tin học: Sinh viên phải đạt Chứng chỉ Ứng dụng Công nghệ Thông tin cơ bản hoặc chứng chỉ quốc tế MOS/IC3 tương đương theo quy định của Trường Đại học Thủ Dầu Một.\n"
                "Điều 28. Điều kiện xét cấp học bổng khuyến khích học tập TDMU\n"
                "1. Sinh viên được xét cấp học bổng khuyến khích học tập khi hoàn thành từ 15 tín chỉ trở lên trong học kỳ xét cấp, không có học phần nào dưới điểm B (hoặc không có môn thi lại).\n"
                "2. Điểm trung bình chung học tập (GPA) và điểm rèn luyện (ĐRL) đạt từ loại Khá trở lên: Học bổng loại Khá (GPA >= 2.50, ĐRL >= 70), loại Giỏi (GPA >= 3.20, ĐRL >= 80), loại Xuất sắc (GPA >= 3.60, ĐRL >= 90)."
            ),
            "tables_count": 1,
            "tables_markdown": [
                "| Điểm hệ 10 | Điểm chữ | Điểm hệ 4 | Xếp loại tại TDMU |\n"
                "| --- | --- | --- | --- |\n"
                "| 8.5 - 10.0 | A | 4.0 | Giỏi / Xuất sắc |\n"
                "| 7.0 - 8.4 | B | 3.0 | Khá |\n"
                "| 5.5 - 6.9 | C | 2.0 | Trung bình |\n"
                "| 4.0 - 5.4 | D | 1.0 | Trung bình yếu |\n"
                "| < 4.0 | F | 0.0 | Kém (Học lại) |"
            ],
        }
    ]
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(sample_pages, f, ensure_ascii=False, indent=2)


def verify_chunk_schema(chunk: dict) -> list[str]:
    """Kiểm tra tính toàn vẹn của các trường metadata theo yêu cầu kỹ thuật (bao gồm doc_title, issue_year & file_type)."""
    required_fields = {
        "chunk_id": str,
        "document_name": str,
        "doc_title": str,
        "issue_year": str,
        "file_type": str,
        "chapter": str,
        "article": str,
        "clause": str,
        "page_number": int,
        "content": str,
        "is_table": bool,
    }
    errors = []
    for field_name, expected_type in required_fields.items():
        if field_name not in chunk:
            errors.append(f"Thiếu trường '{field_name}'")
        elif not isinstance(chunk[field_name], expected_type):
            errors.append(
                f"Sai kiểu dữ liệu trường '{field_name}': kỳ vọng {expected_type.__name__}, nhận {type(chunk[field_name]).__name__}"
            )
    return errors


def main():
    processed_dir = ROOT_DIR / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Xử lý toàn bộ 3 văn bản chính thức thật trong kho tri thức TDMU
    official_stems = [
        "quy_che_dao_tao_tdmu_1774",
        "huong_dan_xet_hoc_bong_tdmu",
        "huong_dan_chuan_dau_ra_ngoai_ngu_tdmu",
    ]
    extracted_files = [
        processed_dir / f"{stem}_extracted.json"
        for stem in official_stems
        if (processed_dir / f"{stem}_extracted.json").exists()
    ]
    if not extracted_files:
        extracted_files = sorted(
            f for f in processed_dir.glob("*_extracted.json")
            if "sample_" not in f.name
        )
    if not extracted_files:
        sample_file = processed_dir / "sample_quy_che_extracted.json"
        create_sample_extracted_json(sample_file)
        extracted_files = [sample_file]

    chunker = HierarchicalChunker(max_chunk_chars=1200)

    for input_file in extracted_files:
        output_file = processed_dir / input_file.name.replace(
            "_extracted.json", "_chunks.json"
        )
        print("=" * 80)
        print(f"[*] Đang chạy HierarchicalChunker cho file: {input_file.name}")

        chunks = chunker.process_extracted_json_file(
            input_json_path=input_file,
            output_json_path=output_file,
        )

        text_chunks = [c for c in chunks if not c["is_table"]]
        table_chunks = [c for c in chunks if c["is_table"]]

        print(f"[+] Tổng số chunk sinh ra : {len(chunks)}")
        print(f"    - Chunk văn bản (Điều/Khoản/Điểm): {len(text_chunks)}")
        print(f"    - Chunk bảng biểu (Markdown)     : {len(table_chunks)}")
        print(f"[+] Đã lưu danh sách chunk tại       : {output_file}")

        # Kiểm tra độ toàn vẹn metadata
        all_errors = []
        for idx, ch in enumerate(chunks):
            errs = verify_chunk_schema(ch)
            if errs:
                all_errors.append((idx, errs))

        if not all_errors:
            print("[OK] Kiểm tra Schema & Metadata trích dẫn: ĐẠT 100%!")
        else:
            print(f"[ERROR] Phát hiện lỗi cấu trúc ở {len(all_errors)} chunk: {all_errors}")

        # In ra tối đa 4 chunk mẫu (bao gồm cả chunk văn bản và chunk bảng biểu)
        print("\n--- MỘT SỐ CHUNK MẪU ĐỂ KIỂM TRA ĐỘ TOÀN VẸN METADATA ---")
        sample_display = text_chunks[:3] + table_chunks[:1]
        for idx, sample in enumerate(sample_display, start=1):
            print(f"\n[Mẫu #{idx}] (is_table={sample['is_table']}):")
            print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

