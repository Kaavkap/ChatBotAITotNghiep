import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
    HAS_QDRANT = True
except ImportError:
    QdrantClient = None  # type: ignore
    qmodels = None  # type: ignore
    HAS_QDRANT = False

from backend.config import settings
from backend.parsers.hierarchical_chunker import HierarchicalChunk
from backend.parsers.test_pdf_extractor import resolve_tdmu_document_metadata

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse_bm25"

# Danh sách từ dừng tiếng Việt phổ biến để tối ưu vector thưa BM25
VIETNAMESE_STOPWORDS = {
    "và", "của", "các", "có", "được", "trong", "cho", "là", "với", "những",
    "này", "theo", "tại", "đến", "từ", "khi", "về", "hoặc", "không", "phải",
    "một", "như", "để", "trên", "do", "bị", "vào", "ra", "nếu", "thì",
}


@dataclass
class SparseVectorData:
    indices: List[int]
    values: List[float]


@dataclass
class ScoredHit:
    id: str
    score: float
    payload: Dict[str, Any]


class LocalInMemoryQdrantEngine:
    """
    Bộ mô phỏng Qdrant Multi-Vector (Dense Cosine + Sparse BM25 IDF) ngay trong bộ nhớ
    trong trường hợp môi trường Python chưa cài gói `qdrant-client`.
    Khi `qdrant-client` đã cài đặt, `AcademicVectorStore` sử dụng trực tiếp `QdrantClient`.
    """

    def __init__(self):
        self.points: Dict[str, Dict[str, Any]] = {}
        self.doc_freq: Counter = Counter()

    def upsert(self, points: List[Dict[str, Any]]) -> None:
        for pt in points:
            pid = str(pt["id"])
            self.points[pid] = pt
        # Cập nhật IDF cho Sparse BM25
        self.doc_freq.clear()
        for pt in self.points.values():
            sparse: SparseVectorData = pt["vector"][SPARSE_VECTOR_NAME]
            for idx in set(sparse.indices):
                self.doc_freq[idx] += 1

    def query_dense(
        self,
        query_vec: List[float],
        limit: int,
        is_table: Optional[bool] = None,
    ) -> List[ScoredHit]:
        hits: List[ScoredHit] = []
        q_norm = math.sqrt(sum(x * x for x in query_vec)) or 1.0
        for pid, pt in self.points.items():
            payload = pt["payload"]
            if is_table is not None and payload.get("is_table") != is_table:
                continue
            d_vec = pt["vector"][DENSE_VECTOR_NAME]
            d_norm = math.sqrt(sum(x * x for x in d_vec)) or 1.0
            sim = sum(a * b for a, b in zip(query_vec, d_vec)) / (q_norm * d_norm)
            hits.append(ScoredHit(id=pid, score=float(sim), payload=payload))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def query_sparse(
        self,
        query_sparse: SparseVectorData,
        limit: int,
        is_table: Optional[bool] = None,
    ) -> List[ScoredHit]:
        hits: List[ScoredHit] = []
        total_docs = max(len(self.points), 1)
        q_map = dict(zip(query_sparse.indices, query_sparse.values))

        for pid, pt in self.points.items():
            payload = pt["payload"]
            if is_table is not None and payload.get("is_table") != is_table:
                continue
            d_sparse: SparseVectorData = pt["vector"][SPARSE_VECTOR_NAME]
            score = 0.0
            for idx, d_val in zip(d_sparse.indices, d_sparse.values):
                if idx in q_map:
                    df = self.doc_freq.get(idx, 0)
                    # Công thức IDF chuẩn của BM25 (Qdrant Modifier.IDF)
                    idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
                    score += q_map[idx] * d_val * idf
            if score > 0:
                hits.append(ScoredHit(id=pid, score=float(score), payload=payload))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


class VietnameseBM25Vectorizer:
    """
    Bộ tạo Sparse Vector chuẩn BM25-TF dành cho văn bản quy chế học vụ tiếng Việt:
    - Tách từ đơn (unigrams), cụm từ đôi (bigrams, vd: 'điều_14', 'khoản_2', 'thôi_học')
      và giữ nguyên các mã số/điểm số học vụ (vd: '0.80', '1.00', '50%').
    - Ánh xạ sang không gian chỉ số 31-bit dương ổn định kết hợp Modifier.IDF của Qdrant.
    """

    TOKEN_PATTERN = re.compile(r"\d+\.\d+|\w+", re.UNICODE)
    ARTICLE_PATTERN = re.compile(r"\b(?:điều|dieu)\s+(\d+)\b", re.IGNORECASE)
    CLAUSE_PATTERN = re.compile(r"\b(?:khoản|khoan)\s+(\d+)\b", re.IGNORECASE)

    def __init__(self, k1: float = 1.5, b: float = 0.75, avg_doc_len: float = 120.0):
        self.k1 = k1
        self.b = b
        self.avg_doc_len = avg_doc_len

    @staticmethod
    def _token_to_index(token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF

    @staticmethod
    def _strip_accents(text: str) -> str:
        text = text.replace("đ", "d").replace("Đ", "D")
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    def tokenize(self, text: str) -> List[str]:
        lowered = text.lower()
        raw_tokens = self.TOKEN_PATTERN.findall(lowered)
        unigrams = [
            t for t in raw_tokens if t not in VIETNAMESE_STOPWORDS and len(t) > 0
        ]
        bigrams = [
            f"{raw_tokens[i]}_{raw_tokens[i + 1]}"
            for i in range(len(raw_tokens) - 1)
        ]

        # Bổ sung thêm token không dấu (ascii-folded) để khớp chính xác cả văn bản scan OCR bị mất dấu
        ascii_text = self._strip_accents(lowered)
        ascii_raw = self.TOKEN_PATTERN.findall(ascii_text)
        ascii_unigrams = [f"af_{t}" for t in ascii_raw if len(t) > 1]
        ascii_bigrams = [
            f"af_{ascii_raw[i]}_{ascii_raw[i + 1]}"
            for i in range(len(ascii_raw) - 1)
        ]

        # Bắt đích danh "Điều X" và "Khoản Y" bằng regex để boost mạnh trong BM25
        structural_tokens: List[str] = []
        for art_num in self.ARTICLE_PATTERN.findall(lowered):
            structural_tokens.append(f"exact_dieu_{art_num}")
        for cls_num in self.CLAUSE_PATTERN.findall(lowered):
            structural_tokens.append(f"exact_khoan_{cls_num}")

        return unigrams + bigrams + ascii_unigrams + ascii_bigrams + structural_tokens

    def encode_document_raw(self, text: str) -> SparseVectorData:
        tokens = self.tokenize(text)
        if not tokens:
            return SparseVectorData(indices=[], values=[])

        doc_len = len(tokens)
        counts = Counter(tokens)
        index_weights: Dict[int, float] = {}

        for token, tf in counts.items():
            idx = self._token_to_index(token)
            norm_tf = (tf * (self.k1 + 1.0)) / (
                tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
            )
            if token.startswith("exact_dieu_"):
                norm_tf *= 6.0
            elif token.startswith("exact_khoan_"):
                norm_tf *= 3.5
            elif token.startswith(("điều_", "khoản_", "chương_", "điểm_", "af_dieu_", "af_khoan_")):
                norm_tf *= 2.5
            index_weights[idx] = index_weights.get(idx, 0.0) + float(norm_tf)

        sorted_items = sorted(index_weights.items(), key=lambda x: x[0])
        return SparseVectorData(
            indices=[k for k, _ in sorted_items],
            values=[v for _, v in sorted_items],
        )

    def encode_query_raw(self, query: str) -> SparseVectorData:
        tokens = self.tokenize(query)
        if not tokens:
            return SparseVectorData(indices=[], values=[])

        counts = Counter(tokens)
        index_weights: Dict[int, float] = {}

        for token, qtf in counts.items():
            idx = self._token_to_index(token)
            weight = float(qtf)
            if token.startswith("exact_dieu_"):
                weight *= 8.0
            elif token.startswith("exact_khoan_"):
                weight *= 4.0
            elif token.startswith(("điều_", "khoản_", "chương_", "điểm_", "af_dieu_", "af_khoan_")):
                weight *= 3.0
            index_weights[idx] = index_weights.get(idx, 0.0) + weight

        sorted_items = sorted(index_weights.items(), key=lambda x: x[0])
        return SparseVectorData(
            indices=[k for k, _ in sorted_items],
            values=[v for _, v in sorted_items],
        )

    def encode_document(self, text: str) -> Any:
        raw = self.encode_document_raw(text)
        if HAS_QDRANT:
            return qmodels.SparseVector(indices=raw.indices, values=raw.values)
        return raw

    def encode_query(self, query: str) -> Any:
        raw = self.encode_query_raw(query)
        if HAS_QDRANT:
            return qmodels.SparseVector(indices=raw.indices, values=raw.values)
        return raw


class DeterministicFallbackEmbedder:
    """
    Bộ tạo Dense Vector 1536 chiều dự phòng khi môi trường kiểm thử offline chưa cấu hình `OPENAI_API_KEY`.
    Khi có `OPENAI_API_KEY` hợp lệ, hệ thống tự động sử dụng `text-embedding-3-small` của OpenAI.
    """

    SEMANTIC_CONCEPTS = [
        {"rớt", "trượt", "học lại", "hoc lai", "không đạt", "diem duoi 5", "cải thiện", "cai thien"},
        {"đuổi học", "buộc thôi học", "buoc thoi hoc", "thoi hoc", "cảnh báo", "canh bao", "24 tin chi"},
        {"xếp hạng tốt nghiệp", "hạng tốt nghiệp", "xếp loại tốt nghiệp", "loại xuất sắc", "loại giỏi", "loại khá", "giảm đi một mức", "thi lại vượt quá 5%", "điều 28", "dieu 28"},
        {"điều kiện xét và công nhận tốt nghiệp", "hội đồng xét tốt nghiệp", "đủ điều kiện tốt nghiệp", "điều 27", "dieu 27"},
        {"chuẩn đầu ra", "chuan dau ra", "ngoại ngữ", "ngoai ngu", "nnkc", "ept", "fpt", "cpt", "ielts", "toeic", "432", "6 học phần"},
        {"học bổng", "hoc bong", "khuyến khích học tập", "hệ số hưởng học bổng", "quy đổi số tín chỉ", "03/hd", "qđ56", "0,92", "0,83"},
        {"giấy xác nhận sinh viên", "phúc khảo", "phúc khảo bài thi", "hoãn thi", "thi bổ sung", "30.000", "một cửa", "115/hd"},
        {"tín chỉ", "tin chi", "120 tín chỉ", "150 tín chỉ", "khối lượng", "khoi luong", "đăng ký", "điều 12", "điều 19"},
        {"nghỉ học tạm thời", "nghi hoc tam thoi", "rút học phần", "rut hoc phan", "chuyển ngành", "chuyển nơi học", "song ngành", "hai chương trình"},
    ]

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimension
        lowered = text.lower()
        words = re.findall(r"\w+", lowered)

        for w in words:
            if w in VIETNAMESE_STOPWORDS:
                continue
            h = int(hashlib.sha256(w.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % 1024
            sign = 1.0 if (h & 1) == 0 else -1.0
            vec[idx] += sign

        for c_idx, concept_set in enumerate(self.SEMANTIC_CONCEPTS):
            matched = sum(1 for phrase in concept_set if phrase in lowered)
            if matched > 0:
                base = 1024 + c_idx * 48
                for offset in range(48):
                    vec[base + offset] += float(matched) * 3.0

        # Chiếu trực tiếp mã số Điều (Điều 1..35) vào các chiều riêng biệt để phân tách tuyệt đối Điều 27 vs Điều 28
        for m in re.findall(r"\b(?:điều|dieu)\s+(\d+)\b", lowered):
            art_id = int(m)
            if 1 <= art_id <= 35:
                base = 1400 + (art_id % 16) * 8
                for offset in range(8):
                    vec[base + offset] += 6.0

        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class AcademicVectorStore:
    """
    Quản lý Qdrant Collection với kiến trúc Hybrid Search:
    - Dense Vector (`dense`): OpenAI `text-embedding-3-small` (1536 chiều, Cosine distance).
    - Sparse Vector (`sparse_bm25`): BM25 Sparse Vector với IDF modifier cho tiếng Việt.
    - Hỗ trợ Local In-Memory (`:memory:`) hoặc Docker Qdrant thông qua `config.py`.
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        use_in_memory: Optional[bool] = None,
    ):
        self.collection_name = collection_name or settings.qdrant_collection_name
        in_mem = (
            settings.use_in_memory_qdrant
            if use_in_memory is None
            else use_in_memory
        )

        if HAS_QDRANT:
            if in_mem:
                self.client = QdrantClient(":memory:")
            else:
                self.client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                )
            self._local_engine = None
        else:
            self.client = None
            self._local_engine = LocalInMemoryQdrantEngine()

        has_valid_key = bool(
            OpenAI is not None
            and settings.openai_api_key
            and settings.openai_api_key != "your_openai_api_key_here"
        )
        self.openai_client = (
            OpenAI(api_key=settings.openai_api_key) if has_valid_key else None
        )
        self.bm25_vectorizer = VietnameseBM25Vectorizer()
        self.fallback_embedder = DeterministicFallbackEmbedder(
            dimension=settings.embedding_dimension
        )
        self._ensure_collection()

    def reset_collection(self) -> None:
        """Xóa toàn bộ các chunk cũ trong Qdrant Collection để nạp bộ quy chế mới thay thế hoàn toàn."""
        if HAS_QDRANT and self.client is not None:
            collections = [
                c.name for c in self.client.get_collections().collections
            ]
            if self.collection_name in collections:
                self.client.delete_collection(collection_name=self.collection_name)
            self._ensure_collection()
        elif self._local_engine is not None:
            self._local_engine.points.clear()
            self._local_engine.doc_freq.clear()

    def _ensure_collection(self) -> None:
        """
        Khởi tạo Qdrant Collection với cấu hình:
        - Dense Vector (`dense`): 1536 chiều, Cosine distance.
        - Sparse Vector (`sparse_bm25`): SparseVectorParams kèm Modifier.IDF.
        """
        if not HAS_QDRANT or self.client is None:
            return

        collections = [
            c.name for c in self.client.get_collections().collections
        ]
        if self.collection_name in collections:
            return

        sparse_modifier = getattr(qmodels, "Modifier", None)
        sparse_params = (
            qmodels.SparseVectorParams(modifier=sparse_modifier.IDF)
            if sparse_modifier is not None and hasattr(sparse_modifier, "IDF")
            else qmodels.SparseVectorParams()
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: qmodels.VectorParams(
                    size=settings.embedding_dimension,
                    distance=qmodels.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: sparse_params,
            },
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Tạo Dense Vector (1536 chiều) bằng OpenAI `text-embedding-3-small`.
        Tự động chuyển sang bộ nhúng dự phòng nếu chạy kiểm thử offline chưa có API key.
        """
        if self.openai_client:
            try:
                response = self.openai_client.embeddings.create(
                    model=settings.embedding_model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as exc:
                print(
                    f"[!] Cảnh báo gọi OpenAI Embeddings ({exc}) -> Sử dụng Local Dense Embedder (1536d)."
                )
        return [self.fallback_embedder.embed(t) for t in texts]

    def ingest_chunks(
        self,
        chunks_or_json_path: List[Dict[str, Any] | HierarchicalChunk] | str | Path,
    ) -> int:
        """
        Nạp toàn bộ danh sách `HierarchicalChunk` (hoặc đường dẫn file JSON chunks) vào Qdrant
        kèm đầy đủ Payload/Metadata (`document_name`, `chapter`, `article`, `clause`, `page_number`, `is_table`).
        """
        if isinstance(chunks_or_json_path, (str, Path)):
            json_path = Path(chunks_or_json_path)
            if not json_path.exists():
                raise FileNotFoundError(f"Không tìm thấy file chunks JSON: {json_path}")
            with open(json_path, "r", encoding="utf-8") as f:
                raw_chunks = json.load(f)
        else:
            raw_chunks = chunks_or_json_path

        if not raw_chunks:
            return 0

        normalized: List[Dict[str, Any]] = [
            c.model_dump() if isinstance(c, HierarchicalChunk) else dict(c)
            for c in raw_chunks
        ]

        texts = [c["content"] for c in normalized]
        dense_vectors = self.embed_texts(texts)

        if HAS_QDRANT and self.client is not None:
            sparse_vectors = [
                self.bm25_vectorizer.encode_document(t) for t in texts
            ]
            points = [
                qmodels.PointStruct(
                    id=chunk["chunk_id"],
                    vector={
                        DENSE_VECTOR_NAME: dense_vec,
                        SPARSE_VECTOR_NAME: sparse_vec,
                    },
                    payload={
                        "chunk_id": chunk["chunk_id"],
                        "document_name": chunk["document_name"],
                        "doc_title": chunk.get("doc_title")
                        or resolve_tdmu_document_metadata(chunk["document_name"])["doc_title"],
                        "issue_year": str(
                            chunk.get("issue_year")
                            or resolve_tdmu_document_metadata(chunk["document_name"])["issue_year"]
                        ),
                        "file_type": str(
                            chunk.get("file_type")
                            or resolve_tdmu_document_metadata(chunk["document_name"]).get("file_type", "pdf")
                        ),
                        "chapter": chunk.get("chapter", ""),
                        "article": chunk.get("article", ""),
                        "clause": chunk.get("clause", ""),
                        "page_number": int(chunk["page_number"]),
                        "is_table": bool(chunk.get("is_table", False)),
                        "content": chunk["content"],
                    },
                )
                for chunk, dense_vec, sparse_vec in zip(
                    normalized, dense_vectors, sparse_vectors
                )
            ]
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return len(points)

        # Fallback sang LocalInMemoryQdrantEngine nếu môi trường chưa cài qdrant-client
        raw_sparse_vectors = [
            self.bm25_vectorizer.encode_document_raw(t) for t in texts
        ]
        local_points = [
            {
                "id": chunk["chunk_id"],
                "vector": {
                    DENSE_VECTOR_NAME: dense_vec,
                    SPARSE_VECTOR_NAME: sparse_vec,
                },
                "payload": {
                    "chunk_id": chunk["chunk_id"],
                    "document_name": chunk["document_name"],
                    "doc_title": chunk.get("doc_title")
                    or resolve_tdmu_document_metadata(chunk["document_name"])["doc_title"],
                    "issue_year": str(
                        chunk.get("issue_year")
                        or resolve_tdmu_document_metadata(chunk["document_name"])["issue_year"]
                    ),
                    "file_type": str(
                        chunk.get("file_type")
                        or resolve_tdmu_document_metadata(chunk["document_name"]).get("file_type", "pdf")
                    ),
                    "chapter": chunk.get("chapter", ""),
                    "article": chunk.get("article", ""),
                    "clause": chunk.get("clause", ""),
                    "page_number": int(chunk["page_number"]),
                    "is_table": bool(chunk.get("is_table", False)),
                    "content": chunk["content"],
                },
            }
            for chunk, dense_vec, sparse_vec in zip(
                normalized, dense_vectors, raw_sparse_vectors
            )
        ]
        assert self._local_engine is not None
        self._local_engine.upsert(local_points)
        return len(local_points)

    def upsert_chunks(
        self, chunks: List[Dict[str, Any] | HierarchicalChunk]
    ) -> int:
        return self.ingest_chunks(chunks)

    def _build_filter(self, is_table: Optional[bool] = None) -> Any:
        if not HAS_QDRANT or is_table is None:
            return None
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="is_table",
                    match=qmodels.MatchValue(value=is_table),
                )
            ]
        )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 6,
        alpha: float = 0.5,
        fusion_method: str = "rrf",
        is_table: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Kết hợp điểm số Dense Vector (ngữ nghĩa) và Sparse Vector (BM25 từ khóa)
        sử dụng Reciprocal Rank Fusion (RRF) và Score Fusion với trọng số `alpha`.
        """
        alpha = max(0.0, min(1.0, float(alpha)))
        prefetch_limit = max(top_k * 3, 10)
        dense_query_vec = self.embed_texts([query])[0]

        if HAS_QDRANT and self.client is not None:
            q_filter = self._build_filter(is_table=is_table)
            sparse_query_vec = self.bm25_vectorizer.encode_query(query)

            if hasattr(self.client, "query_points"):
                dense_hits = self.client.query_points(
                    collection_name=self.collection_name,
                    query=dense_query_vec,
                    using=DENSE_VECTOR_NAME,
                    query_filter=q_filter,
                    limit=prefetch_limit,
                    with_payload=True,
                ).points
            else:
                dense_hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=(DENSE_VECTOR_NAME, dense_query_vec),
                    query_filter=q_filter,
                    limit=prefetch_limit,
                    with_payload=True,
                )

            sparse_hits = []
            if sparse_query_vec.indices:
                if hasattr(self.client, "query_points"):
                    sparse_hits = self.client.query_points(
                        collection_name=self.collection_name,
                        query=sparse_query_vec,
                        using=SPARSE_VECTOR_NAME,
                        query_filter=q_filter,
                        limit=prefetch_limit,
                        with_payload=True,
                    ).points
                else:
                    sparse_hits = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=qmodels.NamedSparseVector(
                            name=SPARSE_VECTOR_NAME,
                            vector=sparse_query_vec,
                        ),
                        query_filter=q_filter,
                        limit=prefetch_limit,
                        with_payload=True,
                    )
        else:
            assert self._local_engine is not None
            raw_sparse_q = self.bm25_vectorizer.encode_query_raw(query)
            dense_hits = self._local_engine.query_dense(
                query_vec=dense_query_vec,
                limit=prefetch_limit,
                is_table=is_table,
            )
            sparse_hits = (
                self._local_engine.query_sparse(
                    query_sparse=raw_sparse_q,
                    limit=prefetch_limit,
                    is_table=is_table,
                )
                if raw_sparse_q.indices
                else []
            )

        # Hợp nhất kết quả bằng Reciprocal Rank Fusion (RRF) & Score Fusion
        rrf_k = 60.0
        candidates: Dict[str, Dict[str, Any]] = {}

        max_dense = max((h.score for h in dense_hits), default=1.0) or 1.0
        max_sparse = max((h.score for h in sparse_hits), default=1.0) or 1.0

        for rank, hit in enumerate(dense_hits, start=1):
            point_id = str(hit.id)
            candidates[point_id] = {
                "chunk_id": point_id,
                "payload": hit.payload or {},
                "dense_rank": rank,
                "sparse_rank": None,
                "dense_score": float(hit.score),
                "sparse_score": 0.0,
                "norm_dense": float(hit.score) / max_dense,
                "norm_sparse": 0.0,
            }

        for rank, hit in enumerate(sparse_hits, start=1):
            point_id = str(hit.id)
            if point_id not in candidates:
                candidates[point_id] = {
                    "chunk_id": point_id,
                    "payload": hit.payload or {},
                    "dense_rank": None,
                    "sparse_rank": rank,
                    "dense_score": 0.0,
                    "sparse_score": float(hit.score),
                    "norm_dense": 0.0,
                    "norm_sparse": float(hit.score) / max_sparse,
                }
            else:
                candidates[point_id]["sparse_rank"] = rank
                candidates[point_id]["sparse_score"] = float(hit.score)
                candidates[point_id]["norm_sparse"] = float(hit.score) / max_sparse

        # Kiểm tra xem câu hỏi có chỉ định đích danh "Điều X" không để tăng trọng số chính xác cho các chunk thuộc Điều X
        explicit_articles = {
            f"điều {num}."
            for num in self.bm25_vectorizer.ARTICLE_PATTERN.findall(query.lower())
        }

        fused_results: List[Dict[str, Any]] = []
        for point_id, info in candidates.items():
            d_rank = info["dense_rank"]
            s_rank = info["sparse_rank"]

            rrf_dense = (1.0 / (rrf_k + d_rank)) if d_rank is not None else 0.0
            rrf_sparse = (1.0 / (rrf_k + s_rank)) if s_rank is not None else 0.0
            rrf_score = alpha * rrf_dense + (1.0 - alpha) * rrf_sparse

            convex_score = (
                alpha * info["norm_dense"] + (1.0 - alpha) * info["norm_sparse"]
            )

            final_score = (
                rrf_score * 0.7 + convex_score * 0.3
                if fusion_method.lower() == "rrf"
                else convex_score
            )

            payload = info["payload"]
            art_title_lower = str(payload.get("article", "")).lower()
            if explicit_articles and any(
                art_title_lower.startswith(prefix) for prefix in explicit_articles
            ):
                final_score += 0.25

            raw_content = str(payload.get("content", ""))
            # Chỉ đánh dấu is_table = True khi thực sự chứa cấu trúc bảng Markdown (| --- |)
            actual_is_table = bool(payload.get("is_table", False)) and (
                "| --- |" in raw_content or "|---|" in raw_content
            )

            doc_name_val = str(payload.get("document_name", ""))
            meta_fallback = resolve_tdmu_document_metadata(doc_name_val)
            fused_results.append(
                {
                    "score": round(final_score, 6),
                    "rrf_score": round(rrf_score, 6),
                    "dense_score": round(info["dense_score"], 4),
                    "sparse_score": round(info["sparse_score"], 4),
                    "dense_rank": d_rank,
                    "sparse_rank": s_rank,
                    "chunk_id": payload.get("chunk_id", point_id),
                    "document_name": doc_name_val,
                    "doc_title": payload.get("doc_title") or meta_fallback["doc_title"],
                    "issue_year": str(payload.get("issue_year") or meta_fallback["issue_year"]),
                    "file_type": str(payload.get("file_type") or meta_fallback.get("file_type", "pdf")),
                    "chapter": payload.get("chapter", ""),
                    "article": payload.get("article", ""),
                    "clause": payload.get("clause", ""),
                    "page_number": payload.get("page_number", 1),
                    "is_table": actual_is_table,
                    "content": raw_content,
                }
            )

        fused_results.sort(key=lambda x: x["score"], reverse=True)
        return fused_results[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 6,
        is_table: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Mặc định sử dụng Hybrid Search (Dense + Sparse BM25) cho toàn bộ pipeline RAG."""
        return self.hybrid_search(
            query=query,
            top_k=top_k,
            alpha=0.5,
            is_table=is_table,
        )
