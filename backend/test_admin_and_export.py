import asyncio
import base64
import io
import sys
import wave
from pathlib import Path
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import (
    ChatRequest,
    MessageFeedbackRequest,
    TTSRequest,
    chat_academic,
    export_pdf_document_to_docx,
    get_admin_analytics,
    speech_to_text_endpoint,
    submit_message_feedback,
    text_to_speech_vietnamese,
)
from backend.parsers.docx_extractor import (
    export_pdf_to_clean_docx,
    extract_docx_structured,
)


class _DummySpeechRequest:
    def __init__(self, headers: dict, body_bytes: bytes):
        self.headers = headers
        self._body = body_bytes

    async def body(self) -> bytes:
        return self._body


def _build_silent_wav_b64() -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 4000)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def run_verification() -> None:
    print("=" * 88)
    print("1. KIỂM THỬ CHUYỂN ĐỔI PDF SANG DOCX (/export-docx/huong_dan_xet_hoc_bong_tdmu.pdf)")
    print("=" * 88)
    buf, cached_path, dl_name = export_pdf_to_clean_docx(
        "huong_dan_xet_hoc_bong_tdmu.pdf"
    )
    print(f"  [+] Đã tạo file DOCX: {cached_path} ({len(buf.getvalue())} bytes)")
    parsed_docx = extract_docx_structured(cached_path)
    para_count = len(
        [b for b in parsed_docx["ordered_blocks"] if b["type"] == "paragraph"]
    )
    print(f"  [+] Số đoạn văn tiếng Việt đọc lại từ DOCX : {para_count}")
    print(f"  [+] Số bảng biểu đọc lại từ DOCX           : {parsed_docx['tables_count']}")
    assert para_count > 10, "File DOCX phải chứa đầy đủ các đoạn văn quy định!"
    assert parsed_docx["tables_count"] == 1, "File DOCX phải chứa đúng 1 bảng quy đổi học bổng!"

    resp = await export_pdf_document_to_docx("huong_dan_xet_hoc_bong_tdmu.pdf")
    print(f"  [+] Header Content-Disposition: {resp.headers.get('content-disposition')}")
    assert "huong_dan_xet_hoc_bong_tdmu.docx" in str(
        resp.headers.get("content-disposition")
    )

    print("\n" + "=" * 88)
    print("2. KIỂM THỬ HYBRID SPEECH-TO-TEXT ENDPOINT (POST /api/speech-to-text)")
    print("=" * 88)
    import json

    wav_b64 = _build_silent_wav_b64()
    stt_req = _DummySpeechRequest(
        headers={"content-type": "application/json"},
        body_bytes=json.dumps(
            {"filename": "test_edge_voice.wav", "audio_base64": wav_b64}
        ).encode("utf-8"),
    )
    stt_res = await speech_to_text_endpoint(stt_req)  # type: ignore
    print(f"  [+] Phản hồi /api/speech-to-text: status={stt_res['status']}, engine={stt_res['engine']}")
    assert stt_res["status"] in ("ok", "no_speech_detected")

    print("\n" + "=" * 88)
    print("2.5. KIỂM THỬ VIETNAMESE TEXT-TO-SPEECH ENDPOINT + LRU CACHE (< 5ms)")
    print("=" * 88)
    import time

    tts_sample_text = (
        "**Quy chế Đào tạo 1774/QĐ-ĐHTDM:** Sinh viên tích lũy từ **12 tín chỉ** trở lên "
        "được hưởng hệ số học bổng **1,00**."
    )
    t_start_1 = time.perf_counter()
    tts_resp = await text_to_speech_vietnamese(TTSRequest(text=tts_sample_text))
    miss_ms = (time.perf_counter() - t_start_1) * 1000.0
    mp3_chunks = []
    async for chunk in tts_resp.body_iterator:
        mp3_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    mp3_bytes = b"".join(mp3_chunks)
    print(
        f"  [+] Lần 1 (Cache {tts_resp.headers.get('x-tts-cache')}): "
        f"engine={tts_resp.headers.get('x-tts-engine')}, size={len(mp3_bytes)} bytes, latency={miss_ms:.2f} ms"
    )
    assert tts_resp.media_type == "audio/mpeg"
    assert len(mp3_bytes) > 1000, "File âm thanh MP3 tiếng Việt phải có kích thước hợp lệ (>1KB)!"

    # Gọi lần 2 với cùng nội dung -> Kiểm tra LRU Cache HIT (< 5 ms)
    t_start_2 = time.perf_counter()
    tts_resp_cached = await text_to_speech_vietnamese(TTSRequest(text=tts_sample_text))
    hit_ms = (time.perf_counter() - t_start_2) * 1000.0
    print(
        f"  [+] Lần 2 (Cache {tts_resp_cached.headers.get('x-tts-cache')}): "
        f"latency={hit_ms:.3f} ms (< 5 ms)"
    )
    assert tts_resp_cached.headers.get("x-tts-cache") == "HIT"
    assert hit_ms < 5.0, f"Thời gian phản hồi LRU Cache phải < 5ms, nhận {hit_ms:.3f}ms"

    print("\n" + "=" * 88)
    print("3. KIỂM THỬ PHÂN QUYỀN GUEST BLOCKER (403 FORBIDDEN) & ADMIN ANALYTICS")
    print("=" * 88)

    # 3.1. Kiểm thử truy cập /api/admin/analytics ở Chế độ Khách (không có X-User-Email hoặc Gmail ngoài) -> Phải bị chặn 403
    blocked_guest = False
    try:
        await get_admin_analytics(x_user_email=None)
    except HTTPException as exc:
        print(f"  [+] Chặn Guest (x_user_email=None) thành công -> HTTP {exc.status_code}: {exc.detail}")
        assert exc.status_code == 403
        blocked_guest = True
    assert blocked_guest, "Guest không có X-User-Email phải bị chặn 403 Forbidden!"

    blocked_external = False
    try:
        await get_admin_analytics(x_user_email="sinhvienngoai@gmail.com")
    except HTTPException as exc:
        print(f"  [+] Chặn Email ngoài (@gmail.com) thành công -> HTTP {exc.status_code}")
        assert exc.status_code == 403
        blocked_external = True
    assert blocked_external, "Email ngoài @student.tdmu.edu.vn phải bị chặn 403 Forbidden!"

    # 3.2. Kiểm thử Chat + Feedback + Truy cập Admin Analytics với email hợp lệ @student.tdmu.edu.vn
    q1 = await chat_academic(
        ChatRequest(
            message="Khi nào sinh viên TDMU bị cảnh báo học vụ hoặc buộc thôi học (Điều 23)?",
            user_email="2224801030361@student.tdmu.edu.vn",
            user_name="Lê Quốc Bảo",
        )
    )
    q2 = await chat_academic(
        ChatRequest(
            message="Tích lũy 10 tín chỉ trong học kỳ thì hệ số hưởng học bổng khuyến khích học tập là bao nhiêu?",
        )
    )
    fb1 = await submit_message_feedback(q1.message_id, MessageFeedbackRequest(feedback="like"))
    fb2 = await submit_message_feedback(q2.message_id, MessageFeedbackRequest(feedback="like"))
    print(f"  [+] Đã ghi nhận đánh giá 👍 Hữu ích: {fb1['updated']}, {fb2['updated']}")

    analytics = await get_admin_analytics(
        x_user_email="2224801030361@student.tdmu.edu.vn"
    )
    print(f"  [+] Xác thực Admin TDMU        : {analytics['authenticated_admin_email']} (MSSV: {analytics['authenticated_student_id']})")
    print(f"  [+] Tổng số văn bản chính thức : {analytics['active_documents_count']}")
    print(f"  [+] Tổng số Chunks Qdrant      : {analytics['total_chunks_indexed']}")
    print(f"  [+] Tổng số câu hỏi đã xử lý   : {analytics['total_queries']}")
    print(f"  [+] Thống kê hài lòng          : {analytics['feedback_summary']}")

    assert analytics["active_documents_count"] == 3
    assert analytics["total_chunks_indexed"] == 113
    assert analytics["feedback_summary"]["like_count"] >= 2
    print("\n[OK] Kiểm thử Hybrid Voice STT, Guest Blocker 403 & Admin Analytics ĐẠT 100%!")


if __name__ == "__main__":
    asyncio.run(run_verification())
