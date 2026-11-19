import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import (
    ChatDatabaseManager,
    extract_student_id_from_email,
    verify_tdmu_email_domain,
)


def run_auth_and_persistence_tests() -> None:
    print("=" * 88)
    print("KIỂM THỬ XÁC THỰC DOMAIN GUARD (@student.tdmu.edu.vn) & LƯU LỊCH SỬ CHAT SQLITE")
    print("=" * 88)

    # 1. Kiểm thử Domain Guard & Bóc tách MSSV tự động
    valid_email = "2224801030361@student.tdmu.edu.vn"
    ok, mssv, msg = verify_tdmu_email_domain(valid_email)
    print(f"\n[1] Kiểm tra email hợp lệ '{valid_email}':")
    print(f"    -> is_valid={ok}, student_id='{mssv}', message='{msg}'")
    assert ok is True and mssv == "2224801030361"

    valid_email_with_name = "baolq.2224801030361@student.tdmu.edu.vn"
    ok2, mssv2, _ = verify_tdmu_email_domain(valid_email_with_name)
    assert ok2 is True and mssv2 == "2224801030361"

    invalid_email = "lequocbao@gmail.com"
    ok_guest, mssv_guest, msg_guest = verify_tdmu_email_domain(invalid_email)
    print(f"\n[2] Kiểm tra email ngoài tên miền '{invalid_email}':")
    print(f"    -> is_valid={ok_guest}, student_id='{mssv_guest}', message='{msg_guest}'")
    assert ok_guest is False and mssv_guest == ""

    # 2. Kiểm thử SQLite Persistence (users, chat_sessions, messages)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_tdmu_chat.db"
        db = ChatDatabaseManager(db_path=db_file)

        # Tài khoản ngoài không được lưu vào bảng users
        guest_user = db.get_or_create_tdmu_user(invalid_email, "Khách Gmail")
        assert guest_user is None

        # Sinh viên TDMU được tạo trong bảng users
        tdmu_user = db.get_or_create_tdmu_user(valid_email, "Lê Quốc Bảo")
        assert tdmu_user is not None
        assert tdmu_user["student_id"] == "2224801030361"

        # Tạo session và lưu 2 tin nhắn (user & assistant)
        sess = db.create_or_get_session(
            user_id=tdmu_user["id"],
            first_message_hint="Điều kiện xếp hạng tốt nghiệp Điều 28 là gì?",
        )
        session_id = sess["id"]

        db.add_message(
            session_id=session_id,
            role="user",
            content="Điều kiện xếp hạng tốt nghiệp Điều 28 là gì?",
        )
        db.add_message(
            session_id=session_id,
            role="assistant",
            content="Theo Điều 28 Khoản 1, hạng tốt nghiệp được xếp theo ĐTB tích lũy toàn khóa...",
            citations=[
                {
                    "document_name": "quy_che_dao_tao_tdmu_1774.pdf",
                    "article": "Điều 28",
                    "clause": "Khoản 1",
                    "page_number": 13,
                }
            ],
            is_safe=True,
        )

        history = db.get_user_sessions(email=valid_email)
        print(f"\n[3] Lịch sử phiên chat của MSSV {tdmu_user['student_id']}:")
        print(json.dumps(history, ensure_ascii=False, indent=2))
        assert len(history) == 1
        assert history[0]["message_count"] == 2

        # Kiểm thử xóa nội dung phiên hiện tại (POST /api/chat/clear)
        cleared = db.clear_session_messages(session_id=session_id, email=valid_email)
        assert cleared == 2
        history_after_clear = db.get_user_sessions(email=valid_email)
        assert history_after_clear[0]["message_count"] == 0

        # Kiểm thử xóa phiên chat (DELETE /api/chat/session/{session_id})
        deleted = db.delete_session(session_id=session_id, email=valid_email)
        assert deleted is True
        assert len(db.get_user_sessions(email=valid_email)) == 0

    print("\n[OK] Toàn bộ kiểm thử Domain Guard & SQLite Chat Persistence ĐẠT 100%!")


if __name__ == "__main__":
    run_auth_and_persistence_tests()

