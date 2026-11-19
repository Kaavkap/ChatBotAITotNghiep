import re
import unicodedata
from typing import Any, Dict, List, Optional

try:
    import cohere
except ImportError:
    cohere = None  # type: ignore

from backend.config import settings

# Danh sách từ khóa chung / thực thể chung không mang nghĩa chuyên môn học vụ (GENERIC_STOP_ENTITY_TOKENS)
# Được loại bỏ hoàn toàn trước khi tính độ khớp nghiệp vụ (`specific_overlap`)
GENERIC_STOP_ENTITY_TOKENS = {
    # Tên trường, đối tượng chung & đại từ nghi vấn / hư từ tiếng Việt (có dấu & không dấu)
    "trường", "truong",
    "đại", "dai",
    "học", "hoc",
    "thủ", "thu",
    "dầu", "dau",
    "một", "mot",
    "tdmu",
    "sinh", "viên", "vien",
    "nằm", "nam",
    "ở", "o",
    "đâu", "dau",
    "địa", "dia",
    "chỉ", "chi",
    "là", "la",
    "gì", "gi",
    "ai",
    "bao", "nhiêu", "nhieu",
    "nào", "nao",
    "khi",
    "thế", "the",
    "sao",
    "có", "co",
    "không", "khong",
    "được", "duoc",
    "của", "cua",
    "về", "ve",
    "cho",
    "tại", "tai",
    # Các từ nối, chức danh hành chính chung hoặc từ phụ trợ không phân biệt Điều khoản
    "va", "trong", "theo", "voi", "cac", "nhung", "phai", "neu", "thi", "ma",
    "de", "tu", "den", "hai", "ba", "nay", "may", "tren", "duoi", "nganh",
    "ky", "thuat", "phan", "mem", "hieu", "truong", "pho", "ts", "ths", "ubnd",
    "tinh", "binh", "duong", "quyet", "dinh", "so", "ngay", "thang", "ban", "hanh",
    "quy", "che", "dao", "tao", "tin", "hom", "qua", "mai", "cu", "duong", "phuong",
    "thanh", "khu", "toa", "nha", "bat", "dau",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def extract_specific_academic_tokens(text: str) -> List[str]:
    """
    Trích xuất các từ khóa nghiệp vụ đào tạo thực sự từ câu hỏi hoặc nội dung Điều khoản,
    sau khi đã loại bỏ toàn bộ `GENERIC_STOP_ENTITY_TOKENS`.
    """
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens: List[str] = []
    for tok in cleaned.split():
        folded = _strip_accents(tok)
        if (
            len(folded) >= 2
            and tok not in GENERIC_STOP_ENTITY_TOKENS
            and folded not in GENERIC_STOP_ENTITY_TOKENS
        ):
            tokens.append(folded)
    return tokens


def _extract_meaningful_tokens(text: str, remove_generic: bool = False) -> List[str]:
    if remove_generic:
        return extract_specific_academic_tokens(text)

    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    basic_stopwords = {
        "la", "va", "cua", "cho", "trong", "theo", "tai", "voi", "cac", "nhung",
        "duoc", "phai", "khi", "neu", "thi", "ma", "de", "ve", "tu", "den", "co",
        "khong", "mot", "hai", "ba",
    }
    tokens = []
    for tok in cleaned.split():
        folded = _strip_accents(tok)
        if len(folded) >= 2 and folded not in basic_stopwords:
            tokens.append(folded)
    return tokens


# Bản đồ ánh xạ khái niệm học vụ TDMU sang số Điều chính xác trong Quy chế 1774/QĐ-ĐHTDM
TDMU_INTENT_ARTICLE_HINTS: List[tuple[List[str], List[int]]] = [
    (
        ["bảo lưu", "nghỉ học tạm thời", "nghỉ tạm", "tạm nghỉ", "thôi học vì lý do cá nhân", "điều động lực lượng vũ trang", "thai sản", "điều 21"],
        [21],
    ),
    (
        ["đuổi học", "buộc thôi học", "cảnh báo học vụ", "cảnh báo kết quả học tập", "rớt bao nhiêu tín chỉ", "nợ đọng", "quá 24 tín chỉ", "quá 50%", "điều 23"],
        [23],
    ),
    (
        ["rút bớt học phần", "rút môn", "hủy học phần", "điểm rt", "hoàn trả học phí", "điều 22"],
        [22],
    ),
    (
        ["đăng ký tối thiểu", "học lại", "cải thiện điểm", "12 tín chỉ", "8 tín chỉ", "dưới 5", "điều 19"],
        [19],
    ),
    (
        ["xét tốt nghiệp", "công nhận tốt nghiệp", "điều kiện tốt nghiệp", "hội đồng xét tốt nghiệp", "điều 27"],
        [27],
    ),
    (
        ["xếp hạng tốt nghiệp", "hạng tốt nghiệp", "giảm hạng", "hạ bậc", "xuất sắc", "giỏi", "khá", "vượt quá 5%", "điều 28"],
        [28],
    ),
    (
        ["chuẩn đầu ra", "thiết kế chương trình", "120 tín chỉ", "150 tín chỉ", "chất lượng cao", "chuẩn quốc tế", "điều 11", "điều 12"],
        [11, 12],
    ),
    (
        ["thời gian khóa học", "thời gian tối đa", "mấy năm", "cộng tối đa 2 năm", "điều 15"],
        [15],
    ),
    (
        ["học cùng lúc hai chương trình", "song ngành", "chương trình thứ hai", "điều 24"],
        [24],
    ),
    (
        ["chuyển ngành", "chuyển trường", "chuyển cơ sở đào tạo", "chuyển hình thức học", "điều 25"],
        [25],
    ),
    (
        ["miễn học", "tạm hoãn", "giáo dục quốc phòng", "giáo dục thể chất", "gdqp", "gdtc", "điều 26"],
        [26],
    ),
    (
        ["trực tuyến", "học online", "30% tổng khối lượng", "điều 20"],
        [20],
    ),
]


class AcademicReranker:
    """
    Tầng Re-ranking (Cross-Scoring) kết hợp Lọc Ngữ Nghĩa Tổng Quát (General Out-of-Domain Gate):
    - Loại bỏ toàn bộ `GENERIC_STOP_ENTITY_TOKENS` trước khi tính `specific_overlap`.
    - Nếu sau khi loại bỏ nhóm từ chung mà câu hỏi không còn từ khóa nghiệp vụ đào tạo nào khớp với
      nội dung các Điều khoản (`specific_overlap == 0.0`), trả về điểm khớp bằng 0 để kích hoạt từ chối an toàn.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        resolved_key = (api_key if api_key is not None else settings.cohere_api_key).strip()
        self.model = model or settings.cohere_rerank_model or "rerank-multilingual-v3.0"
        has_valid_key = bool(
            cohere is not None
            and resolved_key
            and resolved_key != "your_cohere_api_key_here"
        )
        self.cohere_client = cohere.Client(resolved_key) if has_valid_key else None

    @staticmethod
    def _detect_target_articles(combined_query_text: str) -> List[int]:
        lowered = combined_query_text.lower()
        target_articles: List[int] = []

        for m in re.finditer(r"\bđiều\s+(\d{1,2})\b", lowered):
            art_num = int(m.group(1))
            if art_num not in target_articles:
                target_articles.append(art_num)

        for trigger_phrases, art_nums in TDMU_INTENT_ARTICLE_HINTS:
            if any(phrase in lowered for phrase in trigger_phrases):
                for num in art_nums:
                    if num not in target_articles:
                        target_articles.append(num)

        return target_articles

    def _local_cross_score(
        self,
        query: str,
        expanded_queries: List[str],
        candidate: Dict[str, Any],
    ) -> tuple[float, float]:
        """
        Chấm điểm Cross-Scoring cục bộ và trả về `(final_score, specific_query_overlap_ratio)`:
        - BẮT BUỘC lọc bỏ `GENERIC_STOP_ENTITY_TOKENS` khỏi câu hỏi gốc `query`.
        - Nếu câu hỏi gốc sau khi lọc không còn từ khóa nghiệp vụ nào (VD: "Trường Đại học Thủ Dầu Một nằm ở đâu",
          "Hiệu trưởng trường là ai") hoặc không có từ khóa nghiệp vụ nào khớp với chunk (`specific_ratio == 0.0`),
          và cũng không chỉ định đích danh `Điều X` hợp lệ -> `specific_overlap = 0.0`.
        """
        base_hybrid_score = float(candidate.get("score", 0.0))
        doc_name = str(candidate.get("document_name", "")).strip().lower()
        article_title = str(candidate.get("article", "")).strip()
        clause_title = str(candidate.get("clause", "")).strip()
        content_text = str(candidate.get("content", "")).strip()

        # Không bao giờ chấm điểm cao cho chunk không thuộc Điều/Mục cụ thể nào
        # hoặc thuộc Trang 1 của văn bản Quy chế 1774 (phần tiêu ngữ/quyết định ban hành)
        page_number = int(candidate.get("page_number", 1))
        if not article_title:
            return 0.0, 0.0
        if "1774" in doc_name and page_number == 1:
            return 0.0, 0.0

        all_query_text = " ".join([query] + expanded_queries)
        all_lower = all_query_text.lower()
        user_target_articles = self._detect_target_articles(query)
        all_target_articles = self._detect_target_articles(all_query_text)

        cand_art_match = re.search(r"Điều\s+(\d{1,2})\b", article_title, flags=re.IGNORECASE)
        cand_art_num = int(cand_art_match.group(1)) if cand_art_match else None

        # Tách từ khóa chuyên môn từ câu hỏi gốc của người dùng (đã loại bỏ GENERIC_STOP_ENTITY_TOKENS)
        specific_user_tokens = extract_specific_academic_tokens(query)
        doc_specific_tokens = extract_specific_academic_tokens(
            f"{article_title} {clause_title} {content_text}"
        )

        # Nếu câu hỏi hoàn toàn chỉ chứa từ chung (như "Trường Đại học Thủ Dầu Một nằm ở đâu", "Hiệu trưởng trường là ai")
        # và không có intent học vụ rõ ràng trong câu hỏi gốc -> specific_overlap = 0.0
        if not specific_user_tokens and not user_target_articles:
            return 0.0, 0.0

        doc_specific_set = set(doc_specific_tokens)
        if specific_user_tokens:
            matched_specific = sum(
                1 for t in set(specific_user_tokens) if t in doc_specific_set
            )
            specific_ratio = matched_specific / len(set(specific_user_tokens))
        else:
            specific_ratio = 1.0 if (cand_art_num and cand_art_num in user_target_articles) else 0.0

        # Nếu không có bất kỳ từ khóa chuyên môn nào khớp và cũng không khớp intent học vụ
        if specific_ratio == 0.0 and not user_target_articles:
            return 0.0, 0.0

        article_boost = 0.0
        if cand_art_num is not None and all_target_articles:
            if cand_art_num == all_target_articles[0]:
                article_boost = 0.55
            elif cand_art_num in all_target_articles:
                article_boost = 0.40

        # Điểm thưởng định tuyến văn bản chuyên đề (Multi-Document Routing Boost):
        # - Khi hỏi về Học bổng / hệ số học bổng -> Ưu tiên `huong_dan_xet_hoc_bong_tdmu.pdf` (03/HD-ĐHTDM)
        # - Khi hỏi về Chuẩn đầu ra ngoại ngữ / NNKC / EPT / FPT / CPT / IELTS / TOEIC -> Ưu tiên `huong_dan_chuan_dau_ra_ngoai_ngu_tdmu.pdf` (432/ĐHTDM-TTNN)
        doc_routing_boost = 0.0
        if any(
            kw in all_lower
            for kw in ["học bổng", "khuyến khích học tập", "hệ số hưởng", "03/hd", "qđ56"]
        ) and "hoc_bong" in doc_name:
            doc_routing_boost = 0.55
        elif any(
            kw in all_lower
            for kw in [
                "chuẩn đầu ra ngoại ngữ",
                "nnkc",
                "ngoại ngữ không chuyên",
                "ept",
                "fpt",
                "cpt",
                "ielts",
                "toeic",
                "432",
                "6 học phần ngoại ngữ",
            ]
        ) and "ngoai_ngu" in doc_name:
            doc_routing_boost = 0.55

        query_tokens = _extract_meaningful_tokens(all_query_text, remove_generic=False)
        doc_tokens = _extract_meaningful_tokens(
            f"{article_title} {clause_title} {content_text}", remove_generic=False
        )
        doc_token_set = set(doc_tokens)
        matched_unigrams = sum(1 for t in set(query_tokens) if t in doc_token_set)
        unigram_ratio = matched_unigrams / max(1, len(set(query_tokens)))

        query_bigrams = {
            f"{query_tokens[i]}_{query_tokens[i + 1]}"
            for i in range(len(query_tokens) - 1)
        }
        doc_bigrams = {
            f"{doc_tokens[i]}_{doc_tokens[i + 1]}"
            for i in range(len(doc_tokens) - 1)
        }
        bigram_matches = len(query_bigrams & doc_bigrams)
        bigram_score = min(0.35, bigram_matches * 0.06)

        clause_priority = 0.0
        if (
            "khoản 1" in clause_title.lower()
            or "khoản 2" in clause_title.lower()
            or "tiểu mục 1.1" in clause_title.lower()
            or "tiểu mục 1.2" in clause_title.lower()
            or "bảng biểu" in clause_title.lower()
        ):
            clause_priority = 0.06

        final_score = (
            base_hybrid_score * 0.35
            + article_boost
            + doc_routing_boost
            + unigram_ratio * 0.15
            + specific_ratio * 0.30
            + bigram_score
            + clause_priority
        )
        return round(final_score, 4), round(specific_ratio, 4)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: int = 5,
        expanded_queries: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sắp xếp lại danh sách `candidates` thu được từ Multi-Query Hybrid Search
        và trả về `top_n` chunks có mức độ liên quan cao nhất kèm `specific_overlap`.
        """
        if not candidates:
            return []

        exp_list = expanded_queries or []

        if self.cohere_client is not None:
            try:
                docs_for_cohere = [
                    f"{c.get('article', '')} {c.get('clause', '')}: {c.get('content', '')}"
                    for c in candidates
                ]
                rerank_query = (
                    f"{query} ({'; '.join(exp_list)})" if exp_list else query
                )
                response = self.cohere_client.rerank(
                    model=self.model,
                    query=rerank_query,
                    documents=docs_for_cohere,
                    top_n=min(top_n, len(candidates)),
                )
                reranked_results: List[Dict[str, Any]] = []
                for item in response.results:
                    cand_copy = dict(candidates[item.index])
                    _, spec_overlap = self._local_cross_score(query, exp_list, cand_copy)
                    cand_copy["rerank_score"] = round(float(item.relevance_score), 4)
                    cand_copy["specific_overlap"] = spec_overlap
                    cand_copy["score"] = cand_copy["rerank_score"]
                    reranked_results.append(cand_copy)
                return reranked_results
            except Exception as exc:
                print(
                    f"[!] Cảnh báo Cohere Rerank ({exc}) -> Chuyển sang Local Cross-Scoring Fallback."
                )

        scored_candidates: List[Dict[str, Any]] = []
        for cand in candidates:
            cand_copy = dict(cand)
            cross_score, spec_overlap = self._local_cross_score(query, exp_list, cand_copy)
            cand_copy["rerank_score"] = cross_score
            cand_copy["specific_overlap"] = spec_overlap
            cand_copy["score"] = cross_score
            scored_candidates.append(cand_copy)

        scored_candidates.sort(
            key=lambda x: (
                x.get("rerank_score", 0.0),
                x.get("specific_overlap", 0.0),
                x.get("sparse_score", 0.0),
            ),
            reverse=True,
        )
        return scored_candidates[:top_n]
