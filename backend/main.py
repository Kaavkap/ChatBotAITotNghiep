from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from backend.config import settings
from backend.core_rag.pipeline import AcademicRAGPipeline
from backend.core_rag.vector_store import AcademicVectorStore
from backend.database import (
    ChatDatabaseManager,
    decode_google_jwt_credential,
    verify_tdmu_email_domain,
)
from backend.parsers.docx_extractor import (
    export_pdf_to_clean_docx,
    extract_docx_as_pages,
    render_docx_to_html_preview,
)
from backend.parsers.hierarchical_chunker import HierarchicalChunker
from backend.parsers.test_chunker import create_sample_extracted_json
from backend.parsers.test_pdf_extractor import resolve_tdmu_document_metadata

try:
    from backend.parsers.test_pdf_extractor import extract_pdf_with_tables
except ImportError:
    extract_pdf_with_tables = None  # type: ignore

app = FastAPI(
    title="TDMU Academic AI Chatbot Backend",
    description=(
        "Trợ lý AI Học vụ chính thức của Trường Đại học Thủ Dầu Một (TDMU) — "
        "Đồ án Tốt nghiệp: SV Lê Quốc Bảo (MSSV: 2224801030361, Lớp: D22KTPM01) - GVHD: ThS. Lê Từ Minh Trí"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cấu hình StaticFiles phục vụ thư mục data/raw_pdfs/ tại đường dẫn /pdfs (bao gồm cả .pdf và .docx)
raw_pdfs_path = Path(settings.raw_pdfs_dir)
raw_pdfs_path.mkdir(parents=True, exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=str(raw_pdfs_path)), name="pdfs")

vector_store = AcademicVectorStore()
rag_pipeline = AcademicRAGPipeline(vector_store=vector_store)
chunker = HierarchicalChunker()
chat_db = ChatDatabaseManager()


def _bootstrap_initial_knowledge_base() -> tuple[int, List[str], Dict[str, int]]:
    """
    Tự động nạp toàn bộ 3 văn bản quy chế & hướng dẫn chính thức thật của TDMU (tổng cộng 113 chunks)
    vào Qdrant ngay khi khởi động, đồng thời tự động nạp thêm bất kỳ file `.docx` thật nào
    được người dùng đưa vào `data/raw_pdfs/`:
    1. `quy_che_dao_tao_tdmu_1774.pdf` (Quy chế Đào tạo 1774/QĐ-ĐHTDM — Năm 2021)
    2. `huong_dan_xet_hoc_bong_tdmu.pdf` (Hướng dẫn Xét học bổng 03/HD-ĐHTDM — Năm 2023)
    3. `huong_dan_chuan_dau_ra_ngoai_ngu_tdmu.pdf` (Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN — Năm 2023)
    """
    import json

    processed_dir = Path(settings.processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(settings.raw_pdfs_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    official_stems = [
        "quy_che_dao_tao_tdmu_1774",
        "huong_dan_xet_hoc_bong_tdmu",
        "huong_dan_chuan_dau_ra_ngoai_ngu_tdmu",
    ]
    # Tự động phát hiện thêm các file .docx thật nếu người dùng thả vào data/raw_pdfs/
    for docx_file in sorted(raw_dir.glob("*.docx")):
        if docx_file.stem not in official_stems:
            official_stems.append(docx_file.stem)

    chunk_files: List[Path] = []
    for stem in official_stems:
        chunks_path = processed_dir / f"{stem}_chunks.json"
        extracted_path = processed_dir / f"{stem}_extracted.json"
        pdf_path = raw_dir / f"{stem}.pdf"
        docx_path = raw_dir / f"{stem}.docx"

        if not chunks_path.exists():
            if not extracted_path.exists():
                if pdf_path.exists() and extract_pdf_with_tables is not None:
                    pages_data = extract_pdf_with_tables(pdf_path)
                    with open(extracted_path, "w", encoding="utf-8") as f:
                        json.dump(pages_data, f, ensure_ascii=False, indent=2)
                elif docx_path.exists():
                    pages_data = extract_docx_as_pages(str(docx_path))
                    with open(extracted_path, "w", encoding="utf-8") as f:
                        json.dump(pages_data, f, ensure_ascii=False, indent=2)
            if extracted_path.exists():
                chunker.process_extracted_json_file(extracted_path, chunks_path)

        if chunks_path.exists():
            chunk_files.append(chunks_path)

    if not chunk_files:
        chunk_files = sorted(
            f for f in processed_dir.glob("*_chunks.json") if "sample_" not in f.name
        )
        if not chunk_files:
            sample_extracted = processed_dir / "sample_quy_che_extracted.json"
            sample_chunks = processed_dir / "sample_quy_che_chunks.json"
            if not sample_extracted.exists():
                create_sample_extracted_json(sample_extracted)
            chunker.process_extracted_json_file(sample_extracted, sample_chunks)
            chunk_files = [sample_chunks]

    vector_store.reset_collection()
    total = 0
    loaded_files: List[str] = []
    per_doc_counts: Dict[str, int] = {}
    for cf in chunk_files:
        try:
            count = vector_store.ingest_chunks(cf)
            total += count
            loaded_files.append(cf.name)
            per_doc_counts[cf.name] = count
        except Exception as exc:
            print(f"[!] Lỗi nạp file chunk {cf.name}: {exc}")
    return total, loaded_files, per_doc_counts


INITIAL_CHUNKS_COUNT, LOADED_CHUNK_FILES, DOCUMENT_CHUNK_COUNTS = _bootstrap_initial_knowledge_base()


class ChatRequest(BaseModel):
    """Hỗ trợ nhận `{ "message": str }` kèm thông tin phiên đăng nhập TDMU (nếu có)."""

    message: Optional[str] = Field(default=None, description="Tin nhắn câu hỏi học vụ TDMU của sinh viên")
    question: Optional[str] = Field(default=None, description="Trường tương thích ngược cho câu hỏi")
    top_k: int = Field(default=6, ge=1, le=15)
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    user_email: Optional[str] = Field(
        default=None,
        description="Email đăng nhập của sinh viên (chỉ lưu lịch sử nếu thuộc @student.tdmu.edu.vn)",
    )
    user_name: Optional[str] = Field(
        default=None,
        description="Họ tên sinh viên hiển thị từ Google OAuth",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Mã phiên hội thoại hiện tại (nếu đã đăng nhập)",
    )

    @model_validator(mode="after")
    def validate_query_text(self) -> "ChatRequest":
        text = (self.message or self.question or "").strip()
        if not text:
            raise ValueError("Trường 'message' không được để trống.")
        self.message = text
        return self


class ChatAPIResponse(BaseModel):
    """Cấu trúc phản hồi chuẩn cho Frontend: `{ "answer": str, "citations": list, "is_safe": bool, "expanded_queries": list }` kèm thông tin lưu vết."""

    answer: str
    citations: List[Dict[str, Any]]
    is_safe: bool
    confidence_level: str = "high"
    expanded_queries: List[str] = Field(default_factory=list)
    message_id: Optional[str] = None
    session_id: Optional[str] = None
    persisted: bool = False
    student_id: Optional[str] = None
    auth_mode: str = "guest"


class MessageFeedbackRequest(BaseModel):
    """Payload đánh giá mức độ hài lòng cho câu trả lời AI (`like` | `dislike` | `null`)."""

    feedback: Optional[str] = Field(
        default=None,
        description="Giá trị đánh giá: 'like', 'dislike', hoặc null để hủy đánh giá",
    )


class TTSRequest(BaseModel):
    """Payload chuyển đổi văn bản câu trả lời AI sang giọng đọc tiếng Việt tự nhiên (`POST /api/tts`)."""

    text: str = Field(..., description="Nội dung câu trả lời cần đọc bằng tiếng Việt")
    voice: str = Field(
        default="vi-VN-HoaiMyNeural",
        description="Giọng đọc tiếng Việt (edge-tts hoặc gTTS fallback)",
    )


class GoogleAuthVerifyRequest(BaseModel):
    """Payload xác thực đăng nhập Google OAuth & kiểm tra Domain Guard `@student.tdmu.edu.vn`."""

    email: Optional[str] = Field(default=None, description="Email Google của người dùng")
    full_name: Optional[str] = Field(default=None, description="Họ và tên người dùng từ Google")
    avatar_url: Optional[str] = Field(default=None, description="URL ảnh đại diện Google")
    google_credential: Optional[str] = Field(
        default=None,
        description="Chuỗi JWT ID Token trả về từ Google Identity Services (nếu có)",
    )


class ClearChatRequest(BaseModel):
    """Payload cho endpoint `POST /api/chat/clear`."""

    session_id: Optional[str] = Field(default=None, description="ID của phiên chat cần xóa nội dung")
    email: Optional[str] = Field(default=None, description="Email sinh viên TDMU")


class IngestResponse(BaseModel):
    processed_files: int
    total_chunks_indexed: int
    details: list[dict]


@app.get("/")
async def root_info():
    """Route trang chủ Backend hiển thị thông tin Trường Đại học Thủ Dầu Một (TDMU) và Đồ án Tốt nghiệp."""
    return {
        "university": "TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT (TDMU)",
        "system": "Trợ lý Trí tuệ Nhân tạo Hỗ trợ Thông tin Học vụ",
        "assistant_role": "Trợ lý AI Học vụ chính thức của Trường Đại học Thủ Dầu Một",
        "student": {
            "name": "Lê Quốc Bảo",
            "mssv": "2224801030361",
            "class": "D22KTPM01",
            "advisor": "ThS. Lê Từ Minh Trí",
        },
        "status": "running",
        "qdrant_collection": settings.qdrant_collection_name,
        "active_regulation_documents": [
            {
                "file": "quy_che_dao_tao_tdmu_1774.pdf",
                "doc_title": "Quy chế Đào tạo 1774/QĐ-ĐHTDM",
                "issue_year": "2021",
                "file_type": "pdf",
            },
            {
                "file": "huong_dan_xet_hoc_bong_tdmu.pdf",
                "doc_title": "Hướng dẫn Xét học bổng 03/HD-ĐHTDM",
                "issue_year": "2023",
                "file_type": "pdf",
            },
            {
                "file": "huong_dan_chuan_dau_ra_ngoai_ngu_tdmu.pdf",
                "doc_title": "Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN",
                "issue_year": "2023",
                "file_type": "pdf",
            },
        ],
        "loaded_chunk_files": LOADED_CHUNK_FILES,
        "document_chunk_counts": DOCUMENT_CHUNK_COUNTS,
        "indexed_chunks": INITIAL_CHUNKS_COUNT,
        "endpoints": {
            "chat": "POST /api/chat",
            "chat_history": "GET /api/chat/history",
            "speech_to_text": "POST /api/speech-to-text",
            "text_to_speech": "POST /api/tts",
            "message_feedback": "POST /api/messages/{message_id}/feedback",
            "admin_analytics": "GET /api/admin/analytics",
            "delete_chat_session": "DELETE /api/chat/session/{session_id}",
            "clear_chat_session": "POST /api/chat/clear",
            "auth_google": "POST /api/auth/google",
            "pdfs": "GET /pdfs/{filename}#page={page_number}",
            "export_docx": "GET /export-docx/{pdf_filename}",
            "preview_docx": "GET /preview-docx/{filename}",
            "ingest": "POST /api/ingest",
            "health": "GET /health",
            "docs": "GET /docs",
        },
    }


# Bộ nhớ đệm In-Memory LRU Cache (tối đa 100 đoạn âm thanh theo mã băm SHA-256)
# giúp trả về file MP3 ngay lập tức (< 5 ms) khi người dùng bấm nghe lại
from collections import OrderedDict

_TTS_LRU_CACHE_MAX_SIZE = 100
_TTS_AUDIO_LRU_CACHE: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()


def _clean_markdown_for_vietnamese_tts(raw_text: str, max_chars: int = 500) -> str:
    """
    Làm sạch toàn bộ ký tự định dạng Markdown (`**`, `#`, `|`, `-`, link...)
    và giới hạn mỗi request tối đa 500 ký tự để thời gian sinh MP3 luôn dưới 1 giây.
    """
    import re

    text = (raw_text or "").strip()
    if not text:
        return ""

    # Loại bỏ dòng phân cách bảng Markdown (| --- | --- |)
    text = re.sub(r"\|[\s\-:]+\|", " ", text)
    # Thay ký tự cột bảng '|' bằng dấu phẩy ngắt nhịp
    text = text.replace("|", ", ")
    # Chuyển link Markdown [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Loại bỏ các ký hiệu trang trí Markdown (**, *, _, ~, `, #, >)
    text = re.sub(r"[*_~`#>]+", "", text)
    # Thay gạch đầu dòng bằng khoảng trắng
    text = re.sub(r"^\s*[\-\+•]\s+", "", text, flags=re.MULTILINE)
    # Gộp khoảng trắng thừa
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_chars:
        clipped = text[:max_chars]
        last_dot = max(clipped.rfind("."), clipped.rfind(";"), clipped.rfind(" "))
        if last_dot > int(max_chars * 0.65):
            clipped = clipped[: last_dot + 1]
        text = clipped.strip()

    return text


async def _synthesize_edge_tts_bytes(clean_text: str, voice: str) -> bytes:
    """Hàm bất đồng bộ gọi edge-tts (`vi-VN-HoaiMyNeural`) để bọc trong `asyncio.wait_for(..., timeout=3.0)`."""
    import edge_tts  # type: ignore

    out_chunks: List[bytes] = []
    communicate = edge_tts.Communicate(
        text=clean_text,
        voice=voice or "vi-VN-HoaiMyNeural",
    )
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            out_chunks.append(chunk["data"])
    return b"".join(out_chunks)


def _synthesize_gtts_bytes(clean_text: str) -> bytes:
    """Hàm đồng bộ gọi `gTTS(lang='vi')` làm phương án chuyển đổi nhanh khi edge-tts quá 3.0 giây."""
    from io import BytesIO
    from gtts import gTTS  # type: ignore

    buf = BytesIO()
    tts = gTTS(text=clean_text, lang="vi", slow=False)
    tts.write_to_fp(buf)
    return buf.getvalue()


@app.post("/api/tts")
async def text_to_speech_vietnamese(request: TTSRequest):
    """
    Endpoint chuyển đổi văn bản câu trả lời sang âm thanh tiếng Việt tự nhiên tốc độ cao (`POST /api/tts`):
    - Giới hạn mỗi request tối đa 500 ký tự đã làm sạch Markdown để thời gian sinh MP3 luôn dưới 1 giây.
    - Kiểm tra bộ nhớ đệm In-Memory LRU Cache (tối đa 100 đoạn theo SHA-256 hash): nếu trúng cache trả về ngay lập tức (`< 5 ms`).
    - Đặt timeout ngắn (`3.0` giây với `asyncio.wait_for`) cho `edge-tts` (`vi-VN-HoaiMyNeural`);
      nếu kết nối tới máy chủ Microsoft chậm quá 3 giây thì chuyển ngay lập tức sang `gTTS(lang="vi")`.
    """
    import asyncio
    import hashlib
    from io import BytesIO

    clean_text = _clean_markdown_for_vietnamese_tts(request.text, max_chars=500)
    if not clean_text:
        raise HTTPException(
            status_code=400,
            detail="Nội dung văn bản cần đọc không được để trống.",
        )

    voice_name = (request.voice or "vi-VN-HoaiMyNeural").strip()
    cache_key = hashlib.sha256(f"{voice_name}::{clean_text}".encode("utf-8")).hexdigest()

    # 1. Kiểm tra In-Memory LRU Cache (< 5 ms)
    if cache_key in _TTS_AUDIO_LRU_CACHE:
        cached_bytes, cached_engine = _TTS_AUDIO_LRU_CACHE.pop(cache_key)
        _TTS_AUDIO_LRU_CACHE[cache_key] = (cached_bytes, cached_engine)
        return StreamingResponse(
            BytesIO(cached_bytes),
            media_type="audio/mpeg",
            headers={
                "X-TTS-Engine": cached_engine,
                "X-TTS-Cache": "HIT",
                "Cache-Control": "public, max-age=3600",
            },
        )

    audio_bytes = b""
    tts_engine = "none"
    errors: List[str] = []

    # 2. Thử edge-tts (`vi-VN-HoaiMyNeural`) với timeout nghiêm ngặt 3.0 giây
    try:
        audio_bytes = await asyncio.wait_for(
            _synthesize_edge_tts_bytes(clean_text, voice_name),
            timeout=3.0,
        )
        if audio_bytes:
            tts_engine = "edge_tts_vi_hoaimy"
    except asyncio.TimeoutError:
        errors.append("edge-tts timeout (>3.0s) -> fallback to gTTS")
        audio_bytes = b""
    except Exception as exc:
        errors.append(f"edge-tts: {exc}")
        audio_bytes = b""

    # 3. Nếu edge-tts quá 3.0 giây hoặc lỗi -> chuyển ngay lập tức sang gTTS(lang="vi") trong threadpool
    if not audio_bytes:
        try:
            audio_bytes = await asyncio.to_thread(_synthesize_gtts_bytes, clean_text)
            if audio_bytes:
                tts_engine = "gtts_vi"
        except Exception as exc:
            errors.append(f"gTTS: {exc}")
            audio_bytes = b""

    if not audio_bytes or tts_engine == "none":
        raise HTTPException(
            status_code=502,
            detail=f"Không thể kết nối dịch vụ sinh giọng đọc tiếng Việt. Chi tiết: {'; '.join(errors)}",
        )

    # 4. Lưu vào In-Memory LRU Cache (tối đa 100 đoạn)
    _TTS_AUDIO_LRU_CACHE[cache_key] = (audio_bytes, tts_engine)
    while len(_TTS_AUDIO_LRU_CACHE) > _TTS_LRU_CACHE_MAX_SIZE:
        _TTS_AUDIO_LRU_CACHE.popitem(last=False)

    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={
            "X-TTS-Engine": tts_engine,
            "X-TTS-Cache": "MISS",
            "Cache-Control": "public, max-age=3600",
        },
    )


def _require_authenticated_tdmu_user(
    x_user_email: Optional[str] = None,
) -> tuple[str, str]:
    """
    Kiểm tra quyền truy cập Quản trị (`/api/admin/analytics`, `/api/ingest`):
    - Yêu cầu header `X-User-Email` thuộc miền `@student.tdmu.edu.vn`.
    - Nếu không có hoặc thuộc tài khoản Khách (Guest), trả về lỗi `403 Forbidden`.
    """
    cleaned_email = (x_user_email or "").strip().lower()
    is_valid, student_id, reason = verify_tdmu_email_domain(cleaned_email)
    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail=(
                "Truy cập bị từ chối (403 Forbidden): Chức năng Quản trị & Thống kê chỉ dành cho "
                f"tài khoản đã xác thực thuộc tên miền @student.tdmu.edu.vn. ({reason})"
            ),
        )
    return cleaned_email, student_id


def _extract_upload_from_request(
    content_type: str, raw_body: bytes
) -> tuple[Optional[str], Optional[bytes]]:
    """
    Trích xuất `(filename, file_bytes)` từ request body (hỗ trợ cả JSON `{filename, file_base64/audio_base64}`
    lẫn `multipart/form-data` mà không phụ thuộc `python-multipart`).
    """
    import base64
    import json
    import re

    if not raw_body:
        return None, None

    ct_lower = (content_type or "").lower()
    if "application/json" in ct_lower:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            if isinstance(payload, dict):
                fname = str(payload.get("filename") or "voice_input.wav").strip()
                b64_str = str(
                    payload.get("file_base64")
                    or payload.get("audio_base64")
                    or ""
                ).strip()
                if b64_str:
                    if "," in b64_str:
                        b64_str = b64_str.split(",", 1)[1]
                    return fname, base64.b64decode(b64_str)
        except Exception:
            return None, None
    elif "multipart/form-data" in ct_lower:
        boundary_match = re.search(r"boundary=([^;]+)", ct_lower)
        if boundary_match:
            boundary_bytes = (
                "--" + boundary_match.group(1).strip().strip('"')
            ).encode("utf-8")
            parts = raw_body.split(boundary_bytes)
            for part in parts:
                if b"Content-Disposition" in part and b"filename=" in part:
                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        header_text = part[:header_end].decode(
                            "utf-8", errors="ignore"
                        )
                        fn_match = re.search(r'filename="([^"]+)"', header_text)
                        fname = (
                            fn_match.group(1).strip()
                            if fn_match
                            else "uploaded_file"
                        )
                        file_content = part[header_end + 4 :]
                        if file_content.endswith(b"\r\n"):
                            file_content = file_content[:-2]
                        return fname, file_content
    return None, None


@app.post("/api/speech-to-text")
async def speech_to_text_endpoint(request: Request):
    """
    Endpoint chuyển đổi giọng nói sang văn bản tiếng Việt (`POST /api/speech-to-text`):
    - Giải quyết triệt để lỗi `webkitSpeechRecognition` (`network`) trên trình duyệt Microsoft Edge.
    - Nhận file âm thanh (WAV / WebM / OGG) từ `MediaRecorder` phía Frontend.
    - Chuyển đổi sang văn bản tiếng Việt (`vi-VN`) ưu tiên qua:
      1. OpenAI Whisper API (`whisper-1` nếu có cấu hình `OPENAI_API_KEY` hợp lệ).
      2. Thư viện `SpeechRecognition` (`recognize_google(language="vi-VN")`) nếu file WAV chuẩn PCM.
    """
    from io import BytesIO

    content_type = request.headers.get("content-type") or ""
    raw_body = await request.body()
    filename, audio_bytes = _extract_upload_from_request(content_type, raw_body)

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="Không nhận được dữ liệu âm thanh để nhận diện giọng nói.",
        )

    safe_filename = Path(filename or "voice_input.wav").name
    transcript_text = ""
    engine_used = "none"
    errors_log: List[str] = []

    # Tầng 1: Sử dụng OpenAI Whisper API (`whisper-1`) nếu đã cấu hình OPENAI_API_KEY
    if rag_pipeline.openai_client is not None:
        try:
            audio_file = BytesIO(audio_bytes)
            audio_file.name = safe_filename
            whisper_resp = rag_pipeline.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="vi",
            )
            transcript_text = (getattr(whisper_resp, "text", "") or "").strip()
            if transcript_text:
                engine_used = "openai_whisper_1"
        except Exception as exc:
            errors_log.append(f"OpenAI Whisper: {exc}")

    # Tầng 2: Sử dụng thư viện SpeechRecognition (Google Web Speech API `vi-VN`) cho định dạng WAV PCM
    if not transcript_text:
        try:
            import speech_recognition as sr  # type: ignore

            recognizer = sr.Recognizer()
            with sr.AudioFile(BytesIO(audio_bytes)) as source:
                audio_data = recognizer.record(source)
            transcript_text = (
                recognizer.recognize_google(audio_data, language="vi-VN") or ""
            ).strip()
            if transcript_text:
                engine_used = "speech_recognition_google_vi"
        except ImportError:
            errors_log.append("Chưa cài đặt thư viện SpeechRecognition.")
        except Exception as exc:
            errors_log.append(f"SpeechRecognition: {exc}")

    if not transcript_text:
        return {
            "status": "no_speech_detected",
            "text": "",
            "engine": engine_used,
            "message": (
                "Không nhận diện được câu nói rõ ràng từ bản ghi âm hoặc chưa cấu hình OPENAI_API_KEY cho Whisper. "
                + (f"Chi tiết: {'; '.join(errors_log)}" if errors_log else "")
            ),
        }

    return {
        "status": "ok",
        "text": transcript_text,
        "engine": engine_used,
        "filename": safe_filename,
    }


@app.get("/export-docx/{pdf_filename}")
async def export_pdf_document_to_docx(pdf_filename: str):
    """
    Endpoint chuyển đổi văn bản PDF quy chế/hướng dẫn TDMU sang file Microsoft Word (`.docx`) sạch sẽ:
    - Đọc dữ liệu văn bản tiếng Việt chuẩn xác và bảng biểu từ file JSON đã bóc tách trong `data/processed/`
      (hoặc bóc tách trực tiếp từ file PDF gốc trong `data/raw_pdfs/`).
    - Dùng `python-docx` tạo file Word (`.docx`) chuẩn hành chính (font Times New Roman, tiêu đề Chương/Điều/Mục,
      kèm bảng biểu Word thực thụ có kẻ khung `Table Grid`).
    - Trả về `StreamingResponse` với header `Content-Disposition: attachment; filename="..."` để trình duyệt tải thẳng về máy.
    """
    try:
        docx_stream, _, download_filename = export_pdf_to_clean_docx(
            pdf_filename=pdf_filename,
            save_cache=True,
        )
        return StreamingResponse(
            docx_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"'
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xuất file Word (.docx) cho '{pdf_filename}': {exc}",
        ) from exc


@app.get("/preview-docx/{filename}", response_class=HTMLResponse)
async def preview_docx_document(filename: str):
    """
    Endpoint xem trước trực tiếp văn bản Microsoft Word (`.docx`) trên Tab mới của trình duyệt:
    - Tự động đọc cấu trúc đoạn văn và bảng biểu từ file `.docx` trong `data/raw_pdfs/`.
    - Render sang bản xem trước trang giấy văn bản hành chính sạch sẽ (kèm nút In/Lưu PDF và nút Tải file DOCX gốc)
      để trình duyệt mở trực tiếp trên Tab mới mà không bắt tải về máy.
    """
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Endpoint /preview-docx/{filename} chỉ hỗ trợ định dạng file .docx.",
        )

    target_docx = Path(settings.raw_pdfs_dir) / safe_name
    if not target_docx.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy file DOCX '{safe_name}' trong thư mục data/raw_pdfs/.",
        )

    try:
        html_preview = render_docx_to_html_preview(
            file_path=target_docx,
            download_url=f"/pdfs/{safe_name}",
        )
        return HTMLResponse(content=html_preview, status_code=200)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi tạo bản xem trước cho file DOCX '{safe_name}': {exc}",
        ) from exc


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "university": "Trường Đại học Thủ Dầu Một (TDMU)",
        "project": "ChatbotAITotnghiep",
        "qdrant_collection": settings.qdrant_collection_name,
        "in_memory_qdrant": settings.use_in_memory_qdrant,
        "indexed_chunks": INITIAL_CHUNKS_COUNT,
    }


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_regulations(
    request: Request,
    x_user_email: Optional[str] = Header(
        default=None,
        alias="X-User-Email",
        description="Email xác thực sinh viên/quản trị viên TDMU (@student.tdmu.edu.vn)",
    ),
):
    """
    Quét toàn bộ PDF và DOCX trong `data/raw_pdfs` (hoặc lưu thêm file mới được tải lên từ trang Quản trị `/admin`),
    bóc tách văn bản & bảng biểu, chia chunk phân cấp và nạp vào Qdrant.
    Bắt buộc xác thực header `X-User-Email` thuộc miền `@student.tdmu.edu.vn` (trả về 403 nếu ở chế độ Khách).
    """
    _require_authenticated_tdmu_user(x_user_email)

    global INITIAL_CHUNKS_COUNT, LOADED_CHUNK_FILES, DOCUMENT_CHUNK_COUNTS
    import json

    raw_dir = Path(settings.raw_pdfs_dir)
    processed_dir = Path(settings.processed_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    content_type = request.headers.get("content-type") or ""
    raw_body = await request.body()
    uploaded_name, uploaded_bytes = _extract_upload_from_request(
        content_type, raw_body
    )

    if uploaded_name and uploaded_bytes is not None:
        safe_upload_name = Path(uploaded_name).name.strip()
        if not (
            safe_upload_name.lower().endswith(".pdf")
            or safe_upload_name.lower().endswith(".docx")
        ):
            raise HTTPException(
                status_code=400,
                detail="Chỉ hỗ trợ tải lên định dạng văn bản .pdf hoặc .docx.",
            )
        dest_path = raw_dir / safe_upload_name
        dest_path.write_bytes(uploaded_bytes)

    pdf_files = sorted(raw_dir.glob("*.pdf"))
    docx_files = sorted(raw_dir.glob("*.docx"))

    if not pdf_files and not docx_files:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy file PDF hoặc DOCX nào trong thư mục data/raw_pdfs/",
        )

    if pdf_files and extract_pdf_with_tables is None:
        raise HTTPException(
            status_code=500,
            detail="Thư viện pdfplumber chưa được cài đặt trong môi trường hiện tại.",
        )

    total_indexed = 0
    details = []
    new_loaded_files: List[str] = []
    new_doc_counts: Dict[str, int] = {}

    try:
        vector_store.reset_collection()
        for pdf_path in pdf_files:
            stem = pdf_path.stem
            extracted_json = processed_dir / f"{stem}_extracted.json"
            chunks_json = processed_dir / f"{stem}_chunks.json"

            if extracted_json.exists():
                with open(extracted_json, "r", encoding="utf-8") as f:
                    pages_data = json.load(f)
            else:
                pages_data = extract_pdf_with_tables(pdf_path)
                with open(extracted_json, "w", encoding="utf-8") as f:
                    json.dump(pages_data, f, ensure_ascii=False, indent=2)

            chunks = chunker.process_extracted_json_file(extracted_json, chunks_json)
            count = vector_store.ingest_chunks(chunks)
            total_indexed += count
            new_loaded_files.append(chunks_json.name)
            new_doc_counts[chunks_json.name] = count
            details.append(
                {
                    "file": pdf_path.name,
                    "file_type": "pdf",
                    "pages": len(pages_data),
                    "chunks_indexed": count,
                }
            )
        for docx_path in docx_files:
            stem = docx_path.stem
            extracted_json = processed_dir / f"{stem}_extracted.json"
            chunks_json = processed_dir / f"{stem}_chunks.json"

            pages_data = extract_docx_as_pages(str(docx_path))
            with open(extracted_json, "w", encoding="utf-8") as f:
                json.dump(pages_data, f, ensure_ascii=False, indent=2)

            chunks = chunker.process_extracted_json_file(extracted_json, chunks_json)
            count = vector_store.ingest_chunks(chunks)
            total_indexed += count
            new_loaded_files.append(chunks_json.name)
            new_doc_counts[chunks_json.name] = count
            details.append(
                {
                    "file": docx_path.name,
                    "file_type": "docx",
                    "pages": len(pages_data),
                    "chunks_indexed": count,
                }
            )

        INITIAL_CHUNKS_COUNT = total_indexed
        LOADED_CHUNK_FILES = new_loaded_files
        DOCUMENT_CHUNK_COUNTS = new_doc_counts
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IngestResponse(
        processed_files=len(pdf_files) + len(docx_files),
        total_chunks_indexed=total_indexed,
        details=details,
    )


@app.post("/api/auth/google")
async def verify_google_oauth(request: GoogleAuthVerifyRequest):
    """
    Endpoint xác thực Google OAuth & kiểm tra Domain Guard `@student.tdmu.edu.vn`:
    - Tự động giải mã JWT credential từ Google Identity Services (nếu có) hoặc nhận email/full_name.
    - Chỉ cho phép tài khoản có đuôi `@student.tdmu.edu.vn` kích hoạt chế độ Sinh viên TDMU (lưu lịch sử).
    - Tự động bóc tách MSSV từ tiền tố email và lưu vào bảng `users` trong SQLite.
    - Nếu email ngoài tên miền hoặc trống: trả về `is_tdmu_student = False` (Chế độ Khách / Guest).
    """
    email = (request.email or "").strip().lower()
    full_name = (request.full_name or "").strip()
    avatar_url = (request.avatar_url or "").strip()

    if request.google_credential:
        decoded = decode_google_jwt_credential(request.google_credential)
        if decoded:
            email = str(decoded.get("email") or email).strip().lower()
            full_name = str(decoded.get("name") or full_name).strip()
            avatar_url = str(decoded.get("picture") or avatar_url).strip()

    is_valid, student_id, message = verify_tdmu_email_domain(email)

    if not is_valid:
        return {
            "authenticated": False,
            "is_tdmu_student": False,
            "mode": "guest",
            "email": email or None,
            "student_id": None,
            "full_name": full_name or "Khách (Guest)",
            "avatar_url": avatar_url or None,
            "persistence_enabled": False,
            "message": message,
        }

    user_record = chat_db.get_or_create_tdmu_user(email=email, full_name=full_name)
    resolved_name = (
        user_record["full_name"] if user_record else (full_name or f"Sinh viên TDMU ({student_id})")
    )

    return {
        "authenticated": True,
        "is_tdmu_student": True,
        "mode": "tdmu_student",
        "user_id": user_record["id"] if user_record else None,
        "email": email,
        "student_id": student_id,
        "full_name": resolved_name,
        "avatar_url": avatar_url or None,
        "persistence_enabled": True,
        "message": message,
    }


@app.get("/api/chat/history")
async def get_chat_history(
    email: Optional[str] = Query(default=None, description="Email sinh viên TDMU (@student.tdmu.edu.vn)"),
    student_id: Optional[str] = Query(default=None, description="MSSV TDMU"),
):
    """
    Lấy danh sách các phiên chat (`chat_sessions` + `messages`) của sinh viên TDMU đã đăng nhập.
    Đối với tài khoản ngoài hoặc chế độ Khách, trả về danh sách rỗng.
    """
    if email:
        is_valid, extracted_mssv, msg = verify_tdmu_email_domain(email)
        if not is_valid:
            return {
                "is_tdmu_student": False,
                "student_id": None,
                "sessions": [],
                "message": msg,
            }
        sessions = chat_db.get_user_sessions(email=email)
        return {
            "is_tdmu_student": True,
            "student_id": extracted_mssv,
            "email": email.strip().lower(),
            "sessions": sessions,
        }

    if student_id:
        sessions = chat_db.get_user_sessions(student_id=student_id)
        return {
            "is_tdmu_student": True,
            "student_id": student_id.strip(),
            "sessions": sessions,
        }

    return {
        "is_tdmu_student": False,
        "student_id": None,
        "sessions": [],
        "message": "Chế độ Khách (Không lưu lịch sử chat).",
    }


@app.delete("/api/chat/session/{session_id}")
async def delete_chat_session(
    session_id: str,
    email: Optional[str] = Query(default=None, description="Email sinh viên sở hữu phiên chat"),
):
    """Xóa hoàn toàn một phiên chat (`chat_sessions` và các `messages` thuộc phiên đó)."""
    deleted = chat_db.delete_session(session_id=session_id, email=email)
    return {
        "status": "deleted" if deleted else "not_found",
        "session_id": session_id,
        "deleted": deleted,
    }


@app.post("/api/chat/clear")
async def clear_current_chat_session(request: ClearChatRequest):
    """Xóa toàn bộ nội dung tin nhắn của phiên hiện tại (`POST /api/chat/clear`)."""
    cleared_count = 0
    if request.session_id:
        cleared_count = chat_db.clear_session_messages(
            session_id=request.session_id,
            email=request.email,
        )
    return {
        "status": "cleared",
        "session_id": request.session_id,
        "deleted_messages": cleared_count,
    }


@app.post("/api/messages/{message_id}/feedback")
async def submit_message_feedback(
    message_id: str, request: MessageFeedbackRequest
):
    """
    Endpoint ghi nhận đánh giá mức độ hài lòng của sinh viên (`like` / `dislike` / `null`)
    cho từng câu trả lời của Trợ lý AI Học vụ TDMU.
    """
    fb_val = (request.feedback or "").strip().lower() or None
    if fb_val not in ("like", "dislike", None):
        raise HTTPException(
            status_code=400,
            detail="Giá trị feedback chỉ nhận 'like', 'dislike' hoặc null.",
        )
    result = chat_db.update_message_feedback(
        message_id=message_id, feedback=fb_val
    )
    return {
        "status": "ok",
        "message_id": result["message_id"],
        "feedback": result["feedback"],
        "updated": result["updated"],
    }


@app.get("/api/admin/analytics")
async def get_admin_analytics(
    x_user_email: Optional[str] = Header(
        default=None,
        alias="X-User-Email",
        description="Email xác thực sinh viên/quản trị viên TDMU (@student.tdmu.edu.vn)",
    ),
):
    """
    Endpoint Thống kê Quản trị & Đánh giá Mức độ Hài lòng (`GET /api/admin/analytics`):
    - Yêu cầu header `X-User-Email` thuộc miền `@student.tdmu.edu.vn` (trả về 403 Forbidden nếu truy cập ở Chế độ Khách).
    - Tổng số văn bản quy chế chính thức & tổng số chunks đang hoạt động trong Qdrant.
    - Tổng số câu hỏi đã xử lý, tổng số người dùng & phiên hội thoại.
    - Tỷ lệ hài lòng (`👍 Hữu ích` / `👎 Chưa chính xác`).
    - Thống kê nhóm chủ đề sinh viên hỏi nhiều nhất (`Quy chế đào tạo`, `Học bổng`, `Chuẩn đầu ra ngoại ngữ`, `Ngoài phạm vi`).
    """
    verified_email, verified_mssv = _require_authenticated_tdmu_user(x_user_email)
    db_stats = chat_db.get_admin_analytics_summary()
    raw_dir = Path(settings.raw_pdfs_dir)
    active_docs = []

    for f_path in sorted(list(raw_dir.glob("*.pdf")) + list(raw_dir.glob("*.docx"))):
        meta = resolve_tdmu_document_metadata(f_path.name)
        chunk_file_key = f"{f_path.stem}_chunks.json"
        active_docs.append(
            {
                "file": f_path.name,
                "doc_title": meta["doc_title"],
                "issue_year": meta["issue_year"],
                "file_type": meta["file_type"],
                "chunks_count": DOCUMENT_CHUNK_COUNTS.get(chunk_file_key, 0),
                "pdf_url": f"http://127.0.0.1:8000/pdfs/{f_path.name}",
                "export_docx_url": f"http://127.0.0.1:8000/export-docx/{f_path.name}",
            }
        )

    return {
        "status": "ok",
        "university": "TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT (TDMU)",
        "authenticated_admin_email": verified_email,
        "authenticated_student_id": verified_mssv,
        "active_documents_count": len(active_docs),
        "total_chunks_indexed": INITIAL_CHUNKS_COUNT,
        "active_documents": active_docs,
        "total_queries": db_stats["total_queries"],
        "total_users": db_stats["total_users"],
        "total_sessions": db_stats["total_sessions"],
        "feedback_summary": db_stats["feedback_summary"],
        "topic_distribution": db_stats["topic_distribution"],
        "recent_queries": db_stats["recent_queries"],
    }


@app.post("/api/chat", response_model=ChatAPIResponse)
async def chat_academic(request: ChatRequest):
    """
    Endpoint Chat học vụ TDMU End-to-End:
    - Nhận `{ "message": str }` (kèm `user_email`, `user_name`, `session_id` nếu sinh viên TDMU đã đăng nhập).
    - Truy vấn `hybrid_search` từ `vector_store` và kiểm duyệt qua `citation_guard`.
    - Nếu `user_email` hợp lệ (`@student.tdmu.edu.vn`), tự động lưu câu hỏi & câu trả lời vào SQLite (`users`, `chat_sessions`, `messages`).
    - Nếu ở Chế độ Khách (Guest), vẫn trả lời bình thường nhưng không lưu vào Database.
    - Đồng thời ghi nhận thống kê chủ đề & khởi tạo `message_id` để sinh viên đánh giá 👍/👎.
    """
    try:
        user_question = request.message or ""
        rag_result = rag_pipeline.answer_question(
            question=user_question,
            top_k=request.top_k,
            alpha=request.alpha,
        )
        citations_dump = [cit.model_dump() for cit in rag_result.citations]

        persisted = False
        active_session_id = request.session_id
        student_id: Optional[str] = None
        auth_mode = "guest"
        assistant_msg_id: Optional[str] = None

        if request.user_email:
            is_valid, extracted_id, _ = verify_tdmu_email_domain(request.user_email)
            if is_valid:
                user_record = chat_db.get_or_create_tdmu_user(
                    email=request.user_email,
                    full_name=request.user_name,
                )
                if user_record:
                    session_record = chat_db.create_or_get_session(
                        user_id=user_record["id"],
                        session_id=request.session_id,
                        first_message_hint=user_question,
                    )
                    active_session_id = session_record["id"]
                    chat_db.add_message(
                        session_id=active_session_id,
                        role="user",
                        content=user_question,
                        citations=[],
                        is_safe=True,
                    )
                    saved_bot_msg = chat_db.add_message(
                        session_id=active_session_id,
                        role="assistant",
                        content=rag_result.answer,
                        citations=citations_dump,
                        is_safe=rag_result.is_safe,
                    )
                    assistant_msg_id = str(saved_bot_msg["id"])
                    persisted = True
                    student_id = extracted_id
                    auth_mode = "tdmu_student"

        analytics_msg_id = chat_db.record_query_analytics(
            question=user_question,
            answer=rag_result.answer,
            citations=citations_dump,
            is_answerable=rag_result.is_answerable,
            linked_message_id=assistant_msg_id,
        )

        return ChatAPIResponse(
            answer=rag_result.answer,
            citations=citations_dump,
            is_safe=rag_result.is_safe,
            confidence_level=rag_result.confidence_level,
            expanded_queries=rag_result.expanded_queries,
            message_id=analytics_msg_id,
            session_id=active_session_id,
            persisted=persisted,
            student_id=student_id,
            auth_mode=auth_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


