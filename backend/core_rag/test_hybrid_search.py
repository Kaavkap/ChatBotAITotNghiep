import json
import sys
from pathlib import Path

# Đảm bảo import được package backend khi chạy trực tiếp từ thư mục gốc
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core_rag.vector_store import AcademicVectorStore
from backend.parsers.test_chunker import main as generate_sample_chunks


def print_search_results(title: str, query: str, alpha: float, results: list[dict]) -> None:
    print("\n" + "=" * 90)
    print(f"THỬ NGHIỆM: {title}")
    print(f"Câu hỏi   : \"{query}\"")
    print(f"Tham số   : top_k={len(results)}, alpha={alpha} (Kết hợp RRF + Score Fusion)")
    print("=" * 90)

    for rank, item in enumerate(results, start=1):
        print(
            f"\n[Hạng #{rank}] Hybrid Score: {item['score']:.6f} "
            f"(RRF: {item['rrf_score']:.6f} | "
            f"Dense: {item['dense_score']:.4f} [rank={item['dense_rank']}] | "
            f"Sparse BM25: {item['sparse_score']:.4f} [rank={item['sparse_rank']}])"
        )
        print("  ├─ Metadata trích dẫn:")
        print(f"  │    • chunk_id      : {item['chunk_id']}")
        print(f"  │    • document_name : {item['document_name']}")
        print(f"  │    • page_number   : {item['page_number']}")
        print(f"  │    • chapter       : {item['chapter']}")
        print(f"  │    • article       : {item['article']}")
        print(f"  │    • clause        : {item['clause']}")
        print(f"  │    • is_table      : {item['is_table']}")
        preview = item["content"].replace("\n", "\n  │      ")
        print(f"  └─ Nội dung Chunk:\n  │      {preview}")


def main():
    chunks_path = ROOT_DIR / "data" / "processed" / "quy_che_dao_tao_tdmu_1774_chunks.json"
    if not chunks_path.exists():
        chunks_path = ROOT_DIR / "data" / "processed" / "sample_quy_che_chunks.json"
        if not chunks_path.exists():
            print("[*] Đang tạo chunks từ test_chunker.py...")
            generate_sample_chunks()

    print(f"[*] Khởi tạo Qdrant Hybrid Vector Store (Collection: academic_regulations)...")
    store = AcademicVectorStore()
    store.reset_collection()

    count = store.ingest_chunks(chunks_path)
    print(f"[+] Đã nạp thành công {count} HierarchicalChunk từ '{chunks_path.name}' vào Qdrant (Thay thế bộ cũ)!")

    # Câu hỏi 1: Tìm kiếm ngữ nghĩa (Semantic Search) trên Quy chế TDMU
    semantic_query = (
        "Sinh viên TDMU bị cảnh báo học tập hoặc buộc thôi học trong những trường hợp nào?"
    )
    semantic_results = store.hybrid_search(
        query=semantic_query,
        top_k=3,
        alpha=0.5,
    )
    print_search_results(
        title="1. TÌM KIẾM NGỮ NGHĨA (SEMANTIC QUERY - QUY CHẾ TDMU)",
        query=semantic_query,
        alpha=0.5,
        results=semantic_results,
    )

    # Câu hỏi 2: Tìm kiếm từ khóa / mã điều khoản chính xác trên Quy chế TDMU
    keyword_query = "Quy định tại Điều 28 về xếp hạng tốt nghiệp loại xuất sắc, giỏi, khá và cấp bằng tốt nghiệp"
    keyword_results = store.hybrid_search(
        query=keyword_query,
        top_k=3,
        alpha=0.4,
    )
    print_search_results(
        title="2. TÌM KIẾM TỪ KHÓA / MÃ ĐIỀU KHOẢN CHÍNH XÁC (ĐIỀU 28 - QUY CHẾ TDMU)",
        query=keyword_query,
        alpha=0.4,
        results=keyword_results,
    )


if __name__ == "__main__":
    main()

