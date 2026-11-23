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
    GoogleAuthVerifyRequest,
    MessageFeedbackRequest,
    TTSRequest,
    chat_academic,
    export_pdf_document_to_docx,
    get_admin_analytics,
    handle_messenger_webhook,
    speech_to_text_endpoint,
    submit_message_feedback,
    text_to_speech_vietnamese,
    verify_google_oauth,
    verify_messenger_webhook,
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
    print("3. KIỂM THỬ XÁC THỰC GOOGLE OAUTH ID TOKEN & PHÂN QUYỀN DUY NHẤT ADMIN (2224801030361)")
    print("=" * 88)
    from unittest.mock import patch

    # 3.0. Kiểm thử verify_google_oauth:
    # (a) Không truyền credential -> HTTP 400
    missing_cred = False
    try:
        await verify_google_oauth(GoogleAuthVerifyRequest())
    except HTTPException as exc:
        print(f"  [+] Chặn request thiếu Google ID Token -> HTTP {exc.status_code}: {exc.detail}")
        assert exc.status_code == 400
        missing_cred = True
    assert missing_cred

    # (b) Token từ tài khoản @gmail.com cá nhân -> HTTP 403 Forbidden
    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "nguoila@gmail.com",
            "email_verified": True,
            "name": "Người Lạ",
        }
        gmail_blocked = False
        try:
            await verify_google_oauth(
                GoogleAuthVerifyRequest(credential="fake_gmail_jwt_token")
            )
        except HTTPException as exc:
            print(f"  [+] Chặn Google Token @gmail.com -> HTTP {exc.status_code}: {exc.detail}")
            assert exc.status_code == 403
            gmail_blocked = True
        assert gmail_blocked

    # (c) Token từ sinh viên TDMU khác (2224801030999@student.tdmu.edu.vn) -> Thành công nhưng is_admin = False
    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "2224801030999@student.tdmu.edu.vn",
            "email_verified": True,
            "name": "Sinh Viên Khác",
            "picture": "https://lh3.googleusercontent.com/a/default-user",
        }
        other_sv_res = await verify_google_oauth(
            GoogleAuthVerifyRequest(credential="valid_other_sv_jwt_token")
        )
        print(
            f"  [+] Sinh viên TDMU khác ({other_sv_res['email']}): "
            f"authenticated={other_sv_res['authenticated']}, is_admin={other_sv_res['is_admin']}"
        )
        assert other_sv_res["authenticated"] is True
        assert other_sv_res["is_admin"] is False

    # (d) Token từ Quản trị viên Lê Quốc Bảo (2224801030361@student.tdmu.edu.vn) -> is_admin = True
    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "2224801030361@student.tdmu.edu.vn",
            "email_verified": True,
            "name": "Lê Quốc Bảo",
            "picture": "https://lh3.googleusercontent.com/a/baolq-tdmu",
        }
        admin_res = await verify_google_oauth(
            GoogleAuthVerifyRequest(credential="valid_admin_jwt_token")
        )
        print(
            f"  [+] Quản trị viên TDMU ({admin_res['email']}): "
            f"authenticated={admin_res['authenticated']}, is_admin={admin_res['is_admin']}"
        )
        assert admin_res["authenticated"] is True
        assert admin_res["is_admin"] is True

    # 3.1. Kiểm thử truy cập /api/admin/analytics:
    # - Chế độ Khách (x_user_email=None) -> 403
    # - Email ngoài (@gmail.com) -> 403
    # - Sinh viên TDMU khác (2224801030999@student.tdmu.edu.vn) -> 403
    for unauthorized_email in [
        None,
        "sinhvienngoai@gmail.com",
        "2224801030999@student.tdmu.edu.vn",
    ]:
        blocked = False
        try:
            await get_admin_analytics(x_user_email=unauthorized_email)
        except HTTPException as exc:
            print(
                f"  [+] Chặn truy cập Admin đối với '{unauthorized_email}' -> HTTP {exc.status_code}"
            )
            assert exc.status_code == 403
            blocked = True
        assert blocked, f"Tài khoản '{unauthorized_email}' phải bị chặn 403 Forbidden!"

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

    print("\n" + "=" * 88)
    print("4. KIỂM THỬ FACEBOOK MESSENGER BOT WEBHOOK (GET & POST /api/webhooks/messenger)")
    print("=" * 88)

    # 4.1. Kiểm thử xác thực GET /api/webhooks/messenger với token đúng
    challenge_resp = await verify_messenger_webhook(
        hub_mode="subscribe",
        hub_verify_token="tdmu_rag_verify_token",
        hub_challenge="meta_challenge_2026",
    )
    challenge_body = (
        challenge_resp.body.decode("utf-8")
        if isinstance(challenge_resp.body, bytes)
        else str(challenge_resp.body)
    )
    print(
        f"  [+] Xác thực GET Webhook hợp lệ -> status={challenge_resp.status_code}, challenge='{challenge_body}'"
    )
    assert challenge_resp.status_code == 200
    assert challenge_body == "meta_challenge_2026"

    # 4.2. Kiểm thử GET /api/webhooks/messenger với token sai -> Phải trả về 403 Forbidden
    wrong_token_blocked = False
    try:
        await verify_messenger_webhook(
            hub_mode="subscribe",
            hub_verify_token="wrong_verify_token",
            hub_challenge="meta_challenge_2026",
        )
    except HTTPException as exc:
        print(f"  [+] Chặn GET Webhook sai verify_token -> HTTP {exc.status_code}: {exc.detail}")
        assert exc.status_code == 403
        wrong_token_blocked = True
    assert wrong_token_blocked

    # 4.3. Kiểm thử POST /api/webhooks/messenger (gồm 1 tin nhắn echo cần bỏ qua + 1 câu hỏi quy chế thật)
    sample_messenger_payload = {
        "object": "page",
        "entry": [
            {
                "id": "TDMU_PAGE_ID",
                "time": 1732000000,
                "messaging": [
                    {
                        "sender": {"id": "PAGE_SELF"},
                        "recipient": {"id": "SV_TDMU_001"},
                        "message": {
                            "mid": "m_echo_1",
                            "is_echo": True,
                            "text": "Tin nhắn echo phải bị bỏ qua",
                        },
                    },
                    {
                        "sender": {"id": "SV_TDMU_2224801030361"},
                        "recipient": {"id": "TDMU_PAGE_ID"},
                        "message": {
                            "mid": "m_question_1",
                            "text": "Khi nào sinh viên TDMU bị cảnh báo học vụ hoặc buộc thôi học?",
                        },
                    },
                ],
            }
        ],
    }
    webhook_post_res = await handle_messenger_webhook(sample_messenger_payload)
    print(
        f"  [+] POST Webhook xử lý: status={webhook_post_res['status']}, "
        f"processed_count={webhook_post_res['processed_count']} (đã bỏ qua tin nhắn is_echo)"
    )
    assert webhook_post_res["status"] == "EVENT_RECEIVED"
    assert webhook_post_res["processed_count"] == 1
    first_reply = webhook_post_res["replies"][0]
    print(
        f"  [+] Phản hồi Messenger cho sender={first_reply['sender_id']}: "
        f"citations={first_reply['citations_count']}, chunks={len(first_reply['messages'])}"
    )
    print(f"  [+] Nội dung tin nhắn Messenger preview:\n      {first_reply['messages'][0][:220]}...")
    assert first_reply["sender_id"] == "SV_TDMU_2224801030361"
    assert first_reply["citations_count"] > 0
    assert all(len(m) <= 1900 for m in first_reply["messages"])
    assert "Điều 23" in first_reply["messages"][0]

    print("\n[OK] Kiểm thử Hybrid Voice STT, Guest Blocker 403, Admin Analytics & Messenger Webhook ĐẠT 100%!")


if __name__ == "__main__":
    asyncio.run(run_verification())
