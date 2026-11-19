import base64
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings

ALLOWED_DOMAIN = settings.allowed_email_domain.lower()  # "@student.tdmu.edu.vn"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def extract_student_id_from_email(email: str) -> str:
    """
    Tự động bóc tách MSSV từ tiền tố email `@student.tdmu.edu.vn`.
    Ví dụ:
      - `2224801030361@student.tdmu.edu.vn` -> `2224801030361`
      - `2224801030361.baolq@student.tdmu.edu.vn` -> `2224801030361`
      - `baolq.2224801030361@student.tdmu.edu.vn` -> `2224801030361`
    Nếu không chứa dãy số MSSV điển hình, lấy toàn bộ phần tiền tố trước `@`.
    """
    prefix = email.strip().split("@")[0].strip()
    digits_match = re.search(r"\b(\d{8,15})\b", prefix)
    if digits_match:
        return digits_match.group(1)
    consecutive_digits = re.search(r"(\d{7,15})", prefix)
    if consecutive_digits:
        return consecutive_digits.group(1)
    return prefix.upper()


def verify_tdmu_email_domain(email: str) -> tuple[bool, str, str]:
    """
    Domain Guard kiểm tra email sinh viên TDMU:
    - Chỉ chấp nhận đuôi `@student.tdmu.edu.vn` để lưu lịch sử.
    - Trả về `(is_valid_tdmu_student, student_id, reason_message)`.
    """
    cleaned = (email or "").strip().lower()
    if not cleaned or "@" not in cleaned:
        return (
            False,
            "",
            "Chế độ Khách (Chưa đăng nhập email sinh viên TDMU — Không lưu lịch sử chat).",
        )

    if not cleaned.endswith(ALLOWED_DOMAIN):
        return (
            False,
            "",
            f"Tài khoản '{cleaned}' không thuộc tên miền '{ALLOWED_DOMAIN}'. Hệ thống chuyển sang Chế độ Khách (Không lưu lịch sử chat).",
        )

    student_id = extract_student_id_from_email(cleaned)
    return (
        True,
        student_id,
        f"Xác thực thành công sinh viên TDMU (MSSV: {student_id}). Đã bật lưu trữ lịch sử hội thoại.",
    )


def decode_google_jwt_credential(credential: str) -> Optional[Dict[str, Any]]:
    """
    Giải mã payload của Google Identity Services ID Token (JWT) phía Backend
    để lấy `email`, `name`, `picture` khi người dùng đăng nhập qua Google OAuth.
    """
    try:
        parts = credential.strip().split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception:
        return None


class ChatDatabaseManager:
    """
    Quản lý cơ sở dữ liệu SQLite cục bộ lưu trữ người dùng và lịch sử hội thoại TDMU:
    - Bảng `users`: id, email, student_id, full_name, created_at
    - Bảng `chat_sessions`: id, user_id, title, created_at
    - Bảng `messages`: id, session_id, role ('user' | 'assistant'), content, citations (JSON), is_safe, created_at
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or settings.sqlite_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    student_id TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    citations TEXT NOT NULL DEFAULT '[]',
                    is_safe INTEGER NOT NULL DEFAULT 1,
                    feedback TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS query_analytics_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    citations_count INTEGER NOT NULL DEFAULT 0,
                    is_answerable INTEGER NOT NULL DEFAULT 1,
                    feedback TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_student_id ON users(student_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON chat_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_analytics_message_id ON query_analytics_logs(message_id);
                """
            )
            # Tự động nâng cấp bảng messages nếu DB cũ chưa có cột feedback
            cols = [
                r["name"]
                for r in conn.execute("PRAGMA table_info(messages);").fetchall()
            ]
            if "feedback" not in cols:
                conn.execute("ALTER TABLE messages ADD COLUMN feedback TEXT DEFAULT NULL;")
            conn.commit()

    def get_or_create_tdmu_user(
        self, email: str, full_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Kiểm tra Domain Guard (`@student.tdmu.edu.vn`) và tạo/lấy thông tin sinh viên trong bảng `users`.
        Nếu không thuộc `@student.tdmu.edu.vn`, trả về `None` (Chế độ Khách).
        """
        is_valid, student_id, _ = verify_tdmu_email_domain(email)
        if not is_valid:
            return None

        cleaned_email = email.strip().lower()
        resolved_name = (full_name or "").strip() or f"Sinh viên TDMU ({student_id})"
        now_str = _utc_now_iso()

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, email, student_id, full_name, created_at FROM users WHERE email = ?",
                (cleaned_email,),
            ).fetchone()

            if row:
                if full_name and full_name.strip() and row["full_name"] != full_name.strip():
                    conn.execute(
                        "UPDATE users SET full_name = ? WHERE id = ?",
                        (full_name.strip(), row["id"]),
                    )
                    conn.commit()
                return {
                    "id": row["id"],
                    "email": row["email"],
                    "student_id": row["student_id"],
                    "full_name": full_name.strip() if (full_name and full_name.strip()) else row["full_name"],
                    "created_at": row["created_at"],
                }

            cursor = conn.execute(
                """
                INSERT INTO users (email, student_id, full_name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cleaned_email, student_id, resolved_name, now_str),
            )
            conn.commit()
            user_id = cursor.lastrowid
            return {
                "id": user_id,
                "email": cleaned_email,
                "student_id": student_id,
                "full_name": resolved_name,
                "created_at": now_str,
            }

    def create_or_get_session(
        self,
        user_id: int,
        session_id: Optional[str] = None,
        first_message_hint: str = "Cuộc trò chuyện học vụ mới",
    ) -> Dict[str, Any]:
        """Tạo mới hoặc lấy phiên hội thoại (`chat_sessions`) gắn với `user_id`."""
        now_str = _utc_now_iso()
        clean_title = (first_message_hint or "Cuộc trò chuyện học vụ mới").strip()
        if len(clean_title) > 70:
            clean_title = clean_title[:67] + "..."

        with self._get_conn() as conn:
            if session_id:
                row = conn.execute(
                    "SELECT id, user_id, title, created_at FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_id),
                ).fetchone()
                if row:
                    return dict(row)

            new_session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
            # Đảm bảo không đụng độ ID của user khác
            existing_any = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ?", (new_session_id,)
            ).fetchone()
            if existing_any:
                new_session_id = f"sess-{uuid.uuid4().hex[:12]}"

            conn.execute(
                """
                INSERT INTO chat_sessions (id, user_id, title, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (new_session_id, user_id, clean_title, now_str),
            )
            conn.commit()
            return {
                "id": new_session_id,
                "user_id": user_id,
                "title": clean_title,
                "created_at": now_str,
            }

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        is_safe: bool = True,
    ) -> Dict[str, Any]:
        """Thêm tin nhắn (`user` hoặc `assistant`) vào bảng `messages`."""
        now_str = _utc_now_iso()
        citations_json = json.dumps(citations or [], ensure_ascii=False)
        safe_int = 1 if is_safe else 0

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, citations, is_safe, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, citations_json, safe_int, now_str),
            )
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "session_id": session_id,
                "role": role,
                "content": content,
                "citations": citations or [],
                "is_safe": is_safe,
                "created_at": now_str,
            }

    def get_user_sessions(
        self, email: Optional[str] = None, student_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các phiên chat của sinh viên (kèm số lượng tin nhắn và danh sách tin nhắn trong phiên).
        """
        with self._get_conn() as conn:
            user_row = None
            if email:
                user_row = conn.execute(
                    "SELECT id, email, student_id, full_name FROM users WHERE email = ?",
                    (email.strip().lower(),),
                ).fetchone()
            elif student_id:
                user_row = conn.execute(
                    "SELECT id, email, student_id, full_name FROM users WHERE student_id = ?",
                    (student_id.strip(),),
                ).fetchone()

            if not user_row:
                return []

            sessions_rows = conn.execute(
                """
                SELECT id, user_id, title, created_at
                FROM chat_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_row["id"],),
            ).fetchall()

            result: List[Dict[str, Any]] = []
            for s_row in sessions_rows:
                msg_rows = conn.execute(
                    """
                    SELECT id, session_id, role, content, citations, is_safe, feedback, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (s_row["id"],),
                ).fetchall()

                messages_list = []
                for m in msg_rows:
                    try:
                        parsed_citations = json.loads(m["citations"] or "[]")
                    except Exception:
                        parsed_citations = []
                    messages_list.append(
                        {
                            "id": str(m["id"]),
                            "session_id": m["session_id"],
                            "role": m["role"],
                            "content": m["content"],
                            "citations": parsed_citations,
                            "is_safe": bool(m["is_safe"]),
                            "feedback": m["feedback"],
                            "created_at": m["created_at"],
                        }
                    )

                result.append(
                    {
                        "id": s_row["id"],
                        "user_id": s_row["user_id"],
                        "student_id": user_row["student_id"],
                        "email": user_row["email"],
                        "title": s_row["title"],
                        "created_at": s_row["created_at"],
                        "message_count": len(messages_list),
                        "messages": messages_list,
                    }
                )

            return result

    def delete_session(self, session_id: str, email: Optional[str] = None) -> bool:
        """Xóa hoàn toàn một phiên chat (`DELETE /api/chat/session/{session_id}`)."""
        with self._get_conn() as conn:
            if email:
                user_row = conn.execute(
                    "SELECT id FROM users WHERE email = ?",
                    (email.strip().lower(),),
                ).fetchone()
                if not user_row:
                    return False
                conn.execute(
                    "DELETE FROM messages WHERE session_id = ?", (session_id,)
                )
                cur = conn.execute(
                    "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_row["id"]),
                )
            else:
                conn.execute(
                    "DELETE FROM messages WHERE session_id = ?", (session_id,)
                )
                cur = conn.execute(
                    "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
                )
            conn.commit()
            return cur.rowcount > 0

    def clear_session_messages(
        self, session_id: str, email: Optional[str] = None
    ) -> int:
        """Xóa toàn bộ nội dung tin nhắn của phiên hiện tại (`POST /api/chat/clear`)."""
        with self._get_conn() as conn:
            if email:
                user_row = conn.execute(
                    "SELECT id FROM users WHERE email = ?",
                    (email.strip().lower(),),
                ).fetchone()
                if not user_row:
                    return 0
                session_row = conn.execute(
                    "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_row["id"]),
                ).fetchone()
                if not session_row:
                    return 0

            cur = conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            conn.commit()
            return cur.rowcount

    @staticmethod
    def classify_academic_topic(
        question: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        is_answerable: bool = True,
    ) -> str:
        """
        Phân loại câu hỏi của sinh viên vào 4 nhóm chủ đề chính phục vụ Thống kê Admin Analytics:
        1. `Quy chế đào tạo` (Quyết định 1774/QĐ-ĐHTDM)
        2. `Học bổng` (Hướng dẫn 03/HD-ĐHTDM)
        3. `Chuẩn đầu ra ngoại ngữ` (Công văn 432/ĐHTDM-TTNN)
        4. `Ngoài phạm vi` (Out-of-domain / Unanswerable)
        """
        if not is_answerable or not citations:
            q_lower = (question or "").lower()
            if not citations and not is_answerable:
                return "Ngoài phạm vi"
            if any(
                kw in q_lower
                for kw in ["học bổng", "khuyến khích học tập", "hệ số hưởng", "03/hd"]
            ):
                return "Học bổng"
            if any(
                kw in q_lower
                for kw in ["ngoại ngữ", "nnkc", "ept", "fpt", "cpt", "ielts", "toeic", "432"]
            ):
                return "Chuẩn đầu ra ngoại ngữ"
            if not citations:
                return "Ngoài phạm vi"

        for cit in citations or []:
            doc_name = str(
                cit.get("document_name") or cit.get("source_file") or cit.get("doc_title") or ""
            ).lower()
            if "hoc_bong" in doc_name or "học bổng" in doc_name or "03/hd" in doc_name:
                return "Học bổng"
            if "ngoai_ngu" in doc_name or "ngoại ngữ" in doc_name or "432" in doc_name:
                return "Chuẩn đầu ra ngoại ngữ"

        return "Quy chế đào tạo"

    def record_query_analytics(
        self,
        question: str,
        answer: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        is_answerable: bool = True,
        linked_message_id: Optional[str] = None,
    ) -> str:
        """
        Ghi nhận lượt hỏi-đáp vào bảng `query_analytics_logs` (áp dụng cho cả Sinh viên đăng nhập và Khách)
        và trả về `message_id` định danh duy nhất để Frontend gửi đánh giá 👍/👎.
        """
        now_str = _utc_now_iso()
        resolved_msg_id = str(linked_message_id or f"msg-{uuid.uuid4().hex[:12]}")
        topic = self.classify_academic_topic(
            question=question,
            citations=citations,
            is_answerable=is_answerable,
        )
        cit_count = len(citations or [])
        ans_int = 1 if is_answerable else 0

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO query_analytics_logs
                (message_id, question, answer, topic, citations_count, is_answerable, feedback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (resolved_msg_id, question, answer, topic, cit_count, ans_int, now_str),
            )
            conn.commit()
        return resolved_msg_id

    def update_message_feedback(
        self, message_id: str, feedback: Optional[str]
    ) -> Dict[str, Any]:
        """
        Cập nhật trạng thái đánh giá (`"like"` | `"dislike"` | `None`) cho tin nhắn phản hồi của AI
        trong cả bảng `messages` và `query_analytics_logs`.
        """
        normalized_fb: Optional[str] = None
        if feedback in ("like", "dislike"):
            normalized_fb = feedback

        clean_id = str(message_id).strip()
        updated_rows = 0

        with self._get_conn() as conn:
            if clean_id.isdigit():
                cur1 = conn.execute(
                    "UPDATE messages SET feedback = ? WHERE id = ?",
                    (normalized_fb, int(clean_id)),
                )
                updated_rows += cur1.rowcount

            cur2 = conn.execute(
                "UPDATE query_analytics_logs SET feedback = ? WHERE message_id = ?",
                (normalized_fb, clean_id),
            )
            updated_rows += cur2.rowcount

            # Nếu người dùng đánh giá một tin nhắn cũ chưa có trong query_analytics_logs, tự tạo bản ghi đồng bộ
            if updated_rows == 0 and clean_id:
                now_str = _utc_now_iso()
                conn.execute(
                    """
                    INSERT INTO query_analytics_logs
                    (message_id, question, answer, topic, citations_count, is_answerable, feedback, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_id,
                        "Truy vấn học vụ TDMU",
                        "Phản hồi Trợ lý AI TDMU",
                        "Quy chế đào tạo",
                        1,
                        1,
                        normalized_fb,
                        now_str,
                    ),
                )
                updated_rows = 1

            conn.commit()

        return {
            "message_id": clean_id,
            "feedback": normalized_fb,
            "updated": updated_rows > 0,
        }

    def get_admin_analytics_summary(self) -> Dict[str, Any]:
        """
        Tổng hợp số liệu thống kê cho Trang Quản trị (`/admin`):
        - Tổng số câu hỏi đã xử lý (`total_queries`)
        - Thống kê đánh giá hài lòng (`like_count`, `dislike_count`, `satisfaction_rate`)
        - Thống kê 4 nhóm chủ đề sinh viên hỏi nhiều nhất (`topic_distribution`)
        - Danh sách các câu hỏi gần đây kèm trạng thái đánh giá (`recent_queries`)
        """
        topics_counter: Dict[str, int] = {
            "Quy chế đào tạo": 0,
            "Học bổng": 0,
            "Chuẩn đầu ra ngoại ngữ": 0,
            "Ngoài phạm vi": 0,
        }

        with self._get_conn() as conn:
            logs_rows = conn.execute(
                """
                SELECT message_id, question, topic, citations_count, is_answerable, feedback, created_at
                FROM query_analytics_logs
                ORDER BY id DESC
                """
            ).fetchall()

            # Đồng bộ thêm các cặp tin nhắn cũ trong bảng messages nếu chưa nằm trong query_analytics_logs
            logged_ids = {str(r["message_id"]) for r in logs_rows}
            assistant_msgs = conn.execute(
                """
                SELECT id, session_id, content, citations, is_safe, feedback, created_at
                FROM messages
                WHERE role = 'assistant'
                ORDER BY id DESC
                """
            ).fetchall()

            user_msgs_by_session: Dict[str, List[str]] = {}
            for u_row in conn.execute(
                "SELECT session_id, content FROM messages WHERE role = 'user' ORDER BY id ASC"
            ).fetchall():
                user_msgs_by_session.setdefault(u_row["session_id"], []).append(
                    u_row["content"]
                )

            total_queries = len(logs_rows)
            like_count = 0
            dislike_count = 0

            for r in logs_rows:
                t_name = r["topic"] if r["topic"] in topics_counter else "Quy chế đào tạo"
                topics_counter[t_name] += 1
                if r["feedback"] == "like":
                    like_count += 1
                elif r["feedback"] == "dislike":
                    dislike_count += 1

            for m_row in assistant_msgs:
                mid_str = str(m_row["id"])
                if mid_str in logged_ids:
                    continue
                total_queries += 1
                try:
                    cits = json.loads(m_row["citations"] or "[]")
                except Exception:
                    cits = []
                is_ans = len(cits) > 0
                session_qs = user_msgs_by_session.get(m_row["session_id"], [])
                q_text = session_qs[-1] if session_qs else ""
                t_name = self.classify_academic_topic(q_text, cits, is_ans)
                topics_counter[t_name] = topics_counter.get(t_name, 0) + 1
                if m_row["feedback"] == "like":
                    like_count += 1
                elif m_row["feedback"] == "dislike":
                    dislike_count += 1

            rated_total = like_count + dislike_count
            satisfaction_rate = (
                round((like_count / rated_total) * 100.0, 1)
                if rated_total > 0
                else 100.0
            )

            topic_distribution = []
            for topic_label, count_val in topics_counter.items():
                pct = (
                    round((count_val / total_queries) * 100.0, 1)
                    if total_queries > 0
                    else 0.0
                )
                topic_distribution.append(
                    {
                        "topic": topic_label,
                        "count": count_val,
                        "percentage": pct,
                    }
                )

            recent_queries = [
                {
                    "message_id": r["message_id"],
                    "question": r["question"],
                    "topic": r["topic"],
                    "citations_count": r["citations_count"],
                    "is_answerable": bool(r["is_answerable"]),
                    "feedback": r["feedback"],
                    "created_at": r["created_at"],
                }
                for r in logs_rows[:12]
            ]

            total_users = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
            total_sessions = conn.execute(
                "SELECT COUNT(*) AS cnt FROM chat_sessions"
            ).fetchone()["cnt"]

        return {
            "total_queries": total_queries,
            "total_users": total_users,
            "total_sessions": total_sessions,
            "feedback_summary": {
                "like_count": like_count,
                "dislike_count": dislike_count,
                "total_rated": rated_total,
                "satisfaction_rate": satisfaction_rate,
            },
            "topic_distribution": topic_distribution,
            "recent_queries": recent_queries,
        }

