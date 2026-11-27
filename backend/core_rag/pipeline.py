import re
import unicodedata
from typing import Any, Dict, List
from pydantic import BaseModel, Field

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

from backend.config import settings
from backend.core_rag.reranker import (
    AcademicReranker,
    extract_specific_academic_tokens,
)
from backend.core_rag.vector_store import AcademicVectorStore
from backend.guardrails.citation_guard import (
    CitationItem,
    GroundedRAGResponse,
    SYSTEM_GUARDRAIL_PROMPT,
    validate_grounded_response,
)
from backend.parsers.test_pdf_extractor import (
    normalize_vietnamese_academic_text,
    resolve_tdmu_document_metadata,
)

TDMU_SYSTEM_PROMPT = SYSTEM_GUARDRAIL_PROMPT

GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE = (
    "Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của "
    "Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 "
    "và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). "
    "Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, "
    "xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp "
    "các phòng ban chức năng của Trường để được hỗ trợ."
)

# Các từ khóa ngoài phạm vi học vụ hoặc nhạy cảm cần từ chối ngay
OUT_OF_DOMAIN_KEYWORDS = {
    "thời tiết",
    "bóng đá",
    "chứng khoán",
    "bitcoin",
    "tiền ảo",
    "xổ số",
    "hack",
    "đánh sập",
    "chính trị",
    "nấu ăn",
    "ca sĩ",
    "phim ảnh",
}

# Danh sách các mẫu câu hỏi bẫy định lượng / nghiệp vụ hành chính / cơ sở vật chất
# KHÔNG được quy định trong văn bản Quy chế Đào tạo Tín chỉ (Quyết định 1774/QĐ-ĐHTDM)
UNANSWERABLE_REGULATION_PATTERNS: List[tuple[str, str]] = [
    (
        r"(?:học\s+phí|tiền\s+học|đóng\s+tiền|mức\s+thu|đơn\s+giá).*?(?:bao\s+nhiêu\s+tiền|mấy\s+triệu|bao\s+nhiêu\s+một\s+tín\s+chỉ|bao\s+nhiêu\s+1\s+tín\s+chỉ|giá\s+bao\s+nhiêu|VNĐ|đồng/tín\s+chỉ)",
        "mức thu học phí cụ thể (bao nhiêu tiền/tín chỉ)",
    ),
    (
        r"(?:bao\s+nhiêu\s+tiền|giá\s+tiền|mấy\s+triệu).*?(?:một\s+tín\s+chỉ|1\s+tín\s+chỉ|học\s+phí|học\s+kỳ)",
        "mức thu học phí cụ thể (bao nhiêu tiền/tín chỉ)",
    ),
    (
        r"\b(?:căn\s+tin|nhà\s+ăn|ký\s+túc\s+xá|nhà\s+xe|bãi\s+giữ\s+xe|thư\s+viện\s+nằm\s+ở|phòng\s+y\s+tế\s+ở\s+đâu|tòa\s+nhà\s+nào|mấy\s+cơ\s+sở|cơ\s+sở\s+mấy|địa\s+chỉ\s+trường|địa\s+chỉ\s+cụ\s+thể|nằm\s+ở\s+đâu|ở\s+đường\s+nào|số\s+điện\s+thoại|hotline|email\s+liên\s+hệ|wifi)\b",
        "cơ sở vật chất, vị trí tòa nhà/căn tin và thông tin liên hệ hành chính",
    ),
    (
        r"\b(?:điểm\s+chuẩn\s+tuyển\s+sinh|điểm\s+sàn|điểm\s+trúng\s+tuyển\s+năm|học\s+bổng\s+bao\s+nhiêu\s+tiền|lịch\s+thi\s+ngày\s+nào|lịch\s+nghỉ\s+lễ|nghỉ\s+tết|nghỉ\s+lễ\s+30/4|nghỉ\s+lễ\s+2/9|nghỉ\s+hè\s+từ\s+ngày)\b",
        "điểm chuẩn tuyển sinh hằng năm hoặc mức tiền học bổng/lịch thi/lịch nghỉ lễ chi tiết từng ngày",
    ),
]

# Bộ mở rộng từ đồng nghĩa & ánh xạ ngôn ngữ đời thường của sinh viên sang chuẩn thuật ngữ Quy chế TDMU
COLLOQUIAL_TO_ACADEMIC_EXPANSIONS: List[tuple[List[str], List[str]]] = [
    (
        [
            "bảo lưu",
            "nghỉ tạm",
            "tạm nghỉ",
            "nghỉ học tạm thời",
            "xin nghỉ 1 năm",
            "nghỉ 1 học kỳ",
            "hoãn học",
            "nhập ngũ",
            "nghĩa vụ",
            "thai sản",
            "bị ốm",
        ],
        [
            "Điều 21 Nghỉ học tạm thời xin thôi học và bảo lưu kết quả đã học tại Trường Đại học Thủ Dầu Một",
            "Thủ tục điều kiện nộp đơn xin nghỉ học tạm thời vì lý do cá nhân điểm trung bình tích lũy không dưới 5,0 và thời hạn nộp đơn Điều 21",
        ],
    ),
    (
        [
            "đuổi học",
            "buộc thôi học",
            "bị thôi học",
            "rớt môn nhiều",
            "rớt bao nhiêu tín chỉ",
            "nợ bao nhiêu tín chỉ",
            "nợ môn",
            "cảnh báo học vụ",
            "cảnh báo kết quả",
            "quá 24 tín chỉ",
            "50% khối lượng",
        ],
        [
            "Điều 23 Xử lý kết quả học tập cảnh báo học vụ và buộc thôi học sinh viên TDMU",
            "Điều kiện cảnh báo học vụ và buộc thôi học do tổng số tín chỉ không đạt trong học kỳ vượt quá 50% hoặc tổng nợ đọng vượt quá 24 tín chỉ hoặc cảnh báo 2 lần liên tiếp Điều 23",
        ],
    ),
    (
        [
            "rút môn",
            "hủy môn",
            "rút bớt học phần",
            "bỏ môn",
            "điểm rt",
            "hoàn học phí",
        ],
        [
            "Điều 22 Rút bớt học phần đã đăng ký hoàn trả học phí và điểm RT",
            "Điều kiện rút các học phần đã đăng ký sau 2 tuần kể từ đầu học kỳ Điều 22",
        ],
    ),
    (
        [
            "đăng ký tối thiểu",
            "ít nhất bao nhiêu tín chỉ",
            "học lại",
            "học cải thiện",
            "rớt môn",
            "dưới 5",
            "12 tín chỉ",
            "8 tín chỉ",
        ],
        [
            "Điều 19 Đăng ký khối lượng học tập tối thiểu 12 tín chỉ học lực bình thường và 8 tín chỉ học lực yếu",
            "Quy định bắt buộc đăng ký học lại học phần bị điểm dưới 5,0 và học cải thiện điểm trung bình tích lũy Điều 19",
        ],
    ),
    (
        [
            "ra trường",
            "xét tốt nghiệp",
            "công nhận tốt nghiệp",
            "điều kiện tốt nghiệp",
            "lấy bằng",
        ],
        [
            "Điều 27 Điều kiện xét và công nhận tốt nghiệp đại học tại Trường Đại học Thủ Dầu Một",
            "Quy định tích lũy đủ học phần điểm trung bình tích lũy từ 5,0 trở lên chứng chỉ GDQP-AN GDTC và chuẩn đầu ra Điều 27",
        ],
    ),
    (
        [
            "xếp loại tốt nghiệp",
            "hạng tốt nghiệp",
            "hạ bằng",
            "hạ bậc",
            "giảm hạng",
            "bằng giỏi",
            "bằng xuất sắc",
            "bằng khá",
            "thi lại quá 5%",
        ],
        [
            "Điều 28 Cấp bằng tốt nghiệp xếp hạng tốt nghiệp Xuất sắc Giỏi Khá Trung bình",
            "Trường hợp hạng tốt nghiệp Xuất sắc và Giỏi bị giảm đi một mức do khối lượng học phần phải thi lại vượt quá 5% tổng số tín chỉ Điều 28 Khoản 2",
        ],
    ),
    (
        [
            "học bổng",
            "hoc bong",
            "khuyến khích học tập",
            "hệ số học bổng",
            "hệ số hưởng",
            "03/hd",
            "qđ56",
            "quy đổi số tín chỉ",
        ],
        [
            "Hướng dẫn 03/HD-ĐHTDM quy đổi số tín chỉ tích lũy trong học kỳ tối thiểu 12 tín chỉ để xét học bổng khuyến khích học tập",
            "Bảng quy đổi hệ số hưởng học bổng tương ứng số tín chỉ tích lũy từ 5 đến 12 tín chỉ theo Quyết định 56/QĐ-HĐTr và Hướng dẫn 03/HD-ĐHTDM",
        ],
    ),
    (
        [
            "chuẩn đầu ra ngoại ngữ",
            "nnkc",
            "ngoại ngữ không chuyên",
            "6 học phần",
            "ept",
            "fpt",
            "cpt",
            "ielts",
            "toeic",
            "432",
            "chứng chỉ ngoại ngữ",
            "chứng chỉ quốc tế",
        ],
        [
            "Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế",
            "Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN",
        ],
    ),
    (
        [
            "chuẩn đầu ra",
            "ngoại ngữ",
            "tiếng anh",
            "tin học",
            "kỹ năng xã hội",
            "tổng số tín chỉ",
            "khối lượng chương trình",
            "120 tín chỉ",
            "150 tín chỉ",
        ],
        [
            "Điều 11 và Điều 12 Chuẩn đầu ra của chương trình đào tạo và thiết kế chương trình đào tạo 120 tín chỉ cử nhân 150 tín chỉ kỹ sư",
            "Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ 6 học phần NNKC chứng chỉ EPT FPT CPT và chứng chỉ quốc tế IELTS TOEIC",
        ],
    ),
    (
        [
            "học mấy năm",
            "thời gian đào tạo",
            "thời gian tối đa",
            "kéo dài thời gian",
        ],
        [
            "Điều 15 Thời gian khóa học theo kế hoạch học tập chuẩn toàn khóa và thời gian tối đa hoàn thành khóa học",
            "Bảng thời gian đào tạo chuẩn 4 năm cử nhân 4,5-5 năm kỹ sư và cộng tối đa 2 năm Điều 15",
        ],
    ),
    (
        [
            "học song ngành",
            "học 2 ngành",
            "hai chương trình",
            "song bằng",
        ],
        [
            "Điều 24 Học cùng lúc hai chương trình đào tạo và điều kiện đăng ký chương trình thứ hai",
        ],
    ),
    (
        [
            "chuyển ngành",
            "chuyển trường",
            "đổi ngành",
            "chuyển hệ",
        ],
        [
            "Điều 25 Chuyển ngành chuyển nơi học và chuyển hình thức học tại Trường Đại học Thủ Dầu Một",
        ],
    ),
    (
        [
            "miễn học",
            "tạm hoãn",
            "quốc phòng",
            "thể chất",
            "gdqp",
            "gdtc",
        ],
        [
            "Điều 26 Đối tượng được miễn tạm hoãn học các học phần Giáo dục quốc phòng - an ninh và Giáo dục thể chất",
        ],
    ),
]


class MultiQueryOutput(BaseModel):
    """Schema đầu ra khi dùng OpenAI sinh Multi-Query Expansion."""

    queries: List[str] = Field(
        description="Danh sách 2 đến 3 câu truy vấn chuẩn thuật ngữ Quy chế Đào tạo Tín chỉ TDMU."
    )


# Tri thức chuẩn hóa hành văn học thuật của từng Điều trong Quy chế 1774/QĐ-ĐHTDM
ACADEMIC_ARTICLE_REWRITE_KNOWLEDGE: Dict[int, str] = {
    11: (
        "**Về Chuẩn đầu ra của chương trình đào tạo (Điều 11 - Trang 5):**\n"
        "- Chuẩn đầu ra là yêu cầu bắt buộc khi xây dựng chương trình đào tạo tại Trường Đại học Thủ Dầu Một.\n"
        "- Chuẩn đầu ra của chương trình đào tạo bảo đảm đầy đủ 03 nhóm năng lực: **Chuẩn về kiến thức**, **Chuẩn về kỹ năng nghề nghiệp**, và **Chuẩn về năng lực tự chủ và trách nhiệm** (bao gồm các chuẩn đầu ra về Ngoại ngữ, Tin học/Công nghệ thông tin và Kỹ năng xã hội theo quy định của Nhà trường)."
    ),
    12: (
        "**Về Thiết kế chương trình đào tạo và quy định Chuẩn đầu ra Ngoại ngữ, Tin học (Điều 12 - Trang 5 & Trang 6):**\n"
        "- **Chương trình đào tạo chuẩn (Khoản 1):** Được thiết kế với khối lượng **120 tín chỉ** đối với bậc Cử nhân và **150 tín chỉ** đối với bậc Kỹ sư, Kiến trúc sư; đảm bảo tỷ lệ **40% – 50%** tín chỉ thực hành trên tổng số tín chỉ toàn khóa.\n"
        "- **Chương trình đào tạo chất lượng cao & chuẩn quốc tế (Khoản 2, Khoản 3):** Thiết kế nhiều hơn chương trình chuẩn tương ứng ít nhất **15 tín chỉ**, có đối sánh với các chương trình tiên tiến trong và ngoài nước và đáp ứng đầy đủ chuẩn đầu ra hướng đến kiểm định chất lượng.\n"
        "- **Quy định về Chuẩn đầu ra Ngoại ngữ, Tin học, Kỹ năng xã hội:** Là điều kiện bắt buộc đối với các chương trình đào tạo chính quy (kết hợp quy định tại Điều 11, Điều 27 Khoản 1 Điểm d và Điều 28 Khoản 5). Riêng hình thức **Đại học văn bằng 2** được miễn chuẩn đầu ra Tin học và Ngoại ngữ; hệ **Thường xuyên** được miễn học phần Giáo dục quốc phòng - an ninh và Giáo dục thể chất."
    ),
    15: (
        "**Về Thời gian khóa học chuẩn và tối đa (Điều 15 - Trang 7):**\n"
        "- **Đào tạo chính quy (Khoản 1):** Thời gian học tập chuẩn toàn khóa là **4 năm** đối với bậc Cử nhân và **4,5 – 5 năm** đối với bậc Kỹ sư, Kiến trúc sư.\n"
        "- **Đào tạo thường xuyên (Khoản 1):** Liên thông cao đẳng lên đại học là **2 năm**; Liên thông trung cấp lên đại học là **3 năm**; Đại học văn bằng 2 là **2 năm**; Đại học vừa làm vừa học là **4 năm**.\n"
        "- **Thời gian tối đa hoàn thành khóa học (Khoản 2):** Bằng thời gian theo kế hoạch học tập chuẩn toàn khóa **cộng tối đa 02 năm**."
    ),
    19: (
        "**Về Đăng ký khối lượng học tập tối thiểu và quy định học lại, học cải thiện (Điều 19 - Trang 8 & Trang 9):**\n"
        "- **Thông báo kế hoạch học phần (Khoản 1):** Đầu mỗi năm học, Phòng Đào tạo Đại học thông báo lịch trình học dự kiến cùng danh sách các học phần bắt buộc và tự chọn sẽ mở trong từng học kỳ để sinh viên chủ động đăng ký.\n"
        "- **Khối lượng tín chỉ tối thiểu phải đăng ký trong mỗi học kỳ chính (Khoản 2):** Không tính các học phần Giáo dục thể chất, Giáo dục quốc phòng - an ninh, Ngoại ngữ, Tin học và Kỹ năng xã hội, sinh viên phải đăng ký tối thiểu:\n"
        "  + **12 tín chỉ/học kỳ** (trừ học kỳ cuối khóa) đối với sinh viên có **học lực bình thường**.\n"
        "  + **08 tín chỉ/học kỳ** (trừ học kỳ cuối khóa) đối với sinh viên đang trong diện xếp hạng **học lực yếu (cảnh báo học vụ)**.\n"
        "  + **Học kỳ 3 (học kỳ phụ):** Không quy định khối lượng tín chỉ đăng ký tối thiểu.\n"
        "- **Nguyên tắc đăng ký (Khoản 3, Khoản 4):** Phải đảm bảo điều kiện tiên quyết của từng học phần, tuân thủ trình tự chương trình đào tạo và có sự tư vấn của Cố vấn học tập.\n"
        "- **Quy định bắt buộc học lại và học cải thiện điểm (Khoản 5):**\n"
        "  + Sinh viên có điểm tổng kết học phần **dưới 5,0** (thang điểm 10) bắt buộc phải đăng ký học lại.\n"
        "  + Đối với **học phần bắt buộc** không đạt: Phải học lại chính học phần đó, hoặc học học phần tương đương/thay thế nếu học phần cũ không còn giảng dạy.\n"
        "  + Đối với **học phần tự chọn** không đạt: Học lại học phần đó hoặc chọn một học phần tự chọn khác cùng khối kiến thức để thay thế.\n"
        "  + Đối với **học cải thiện điểm**: Sinh viên được phép đăng ký học lại các học phần đã đạt để nâng điểm trung bình tích lũy; điểm chính thức được lấy là **điểm cao nhất** trong các lần học và học phí học cải thiện được tính như đóng lần 1."
    ),
    21: (
        "**Về Nghỉ học tạm thời (Bảo lưu kết quả học tập) và Xin thôi học (Điều 21 - Trang 9 & Trang 10):**\n"
        "- **Các trường hợp được phép xin nghỉ học tạm thời và bảo lưu kết quả đã học (Khoản 1):** Sinh viên được quyền viết đơn gửi Hiệu trưởng xin nghỉ học tạm thời trong 04 trường hợp:\n"
        "  + **(a)** Được điều động vào các lực lượng vũ trang.\n"
        "  + **(b)** Được cơ quan có thẩm quyền điều động, đại diện quốc gia tham dự các kỳ thi, giải đấu quốc tế.\n"
        "  + **(c)** Bị ốm, thai sản hoặc tai nạn phải điều trị thời gian dài (phải có giấy xác nhận của cơ quan y tế có thẩm quyền).\n"
        "  + **(d) Vì lý do cá nhân khác:** Sinh viên bắt buộc phải đáp ứng đủ 03 điều kiện: đã học **ít nhất 01 học kỳ** tại Trường; **không thuộc diện bị xem xét xử lý kết quả học tập** theo Điều 23; và đạt **điểm trung bình tích lũy không dưới 5,0**. *(Lưu ý: Thời gian nghỉ học tạm thời vì nhu cầu cá nhân được tính vào thời gian học chính thức quy định tại Khoản 1 Điều 15)*.\n"
        "- **Thời hạn nộp đơn xin nghỉ học tạm thời (Khoản 2):**\n"
        "  + Nghỉ vì **lý do cá nhân khác**: Phải nộp đơn về Chương trình đào tạo trong vòng **07 ngày** sau khi kết thúc thời gian nhập điểm của học kỳ trước.\n"
        "  + Các trường hợp còn lại (nghĩa vụ quân sự, quốc tế, ốm đau/thai sản): Nộp đơn về Chương trình đào tạo trong vòng **15 ngày** kể từ ngày có thông báo/xác nhận của cơ quan có thẩm quyền.\n"
        "- **Thủ tục nhập học trở lại (Khoản 3, Khoản 4):** Khi muốn trở lại học tiếp tại Trường, sinh viên phải viết đơn gửi Hiệu trưởng duyệt **ít nhất 15 ngày** trước khi bắt đầu học kỳ mới. Riêng sinh viên đã xin **thôi học** vì lý do cá nhân nếu muốn quay lại học phải dự tuyển đầu vào như thí sinh mới."
    ),
    22: (
        "**Về Rút bớt học phần đã đăng ký (Điều 22 - Trang 10):**\n"
        "- **Thời hạn và quyền lợi khi rút học phần (Khoản 1):** Sau **02 tuần** kể từ đầu học kỳ, sinh viên có nguyện vọng rút bớt học phần phải làm đơn theo mẫu gửi về Chương trình đào tạo. Nếu thực hiện đúng quy định, sinh viên **được hoàn trả học phí** và nhận điểm ký hiệu **`RT`** (không tính vào GPA học kỳ và GPA tích lũy). Nếu tự ý bỏ học ngoài thời hạn trên sẽ nhận **điểm 0**.\n"
        "- **Điều kiện rút học phần (Khoản 2):** (a) Tự viết đơn gửi Chương trình đào tạo; (b) Được Cố vấn học tập chấp thuận và Giám đốc chương trình đồng ý; (c) Không vi phạm số tín chỉ đăng ký tối thiểu tại Khoản 2 Điều 19."
    ),
    23: (
        "**Về Cảnh báo kết quả học tập và Buộc thôi học (Điều 23 - Trang 10 & Trang 11):**\n"
        "- **Các trường hợp bị Cảnh báo học vụ cuối mỗi học kỳ (Khoản 1):** Sinh viên bị cảnh báo học vụ khi vi phạm một trong các điều kiện sau:\n"
        "  + **(a) Điểm trung bình tích lũy (GPA hệ 10):** Đạt **dưới 3,0** đối với sinh viên năm thứ nhất; **dưới 3,5** đối với năm thứ hai; **dưới 4,0** đối với năm thứ ba; **dưới 4,5** đối với các năm tiếp theo và cuối khóa.\n"
        "  + **(b) Điểm trung bình học kỳ:** Đạt **dưới 2,0** đối với học kỳ đầu tiên của khóa học; **dưới 2,5** đối với các học kỳ tiếp theo.\n"
        "  + **(c) Khối lượng tín chỉ không đạt (rớt môn / nợ đọng):** Tổng số tín chỉ không đạt trong học kỳ **vượt quá 50%** khối lượng tín chỉ đã đăng ký học trong học kỳ đó, hoặc tổng số tín chỉ nợ đọng tính từ đầu khóa học **vượt quá 24 tín chỉ**.\n"
        "- **Các trường hợp bị Buộc thôi học (Khoản 2):** Sinh viên bị buộc thôi học sau mỗi học kỳ nếu thuộc một trong hai trường hợp:\n"
        "  + **(a)** Bị **cảnh báo học vụ lần thứ hai liên tiếp**.\n"
        "  + **(b)** Vượt quá **thời gian tối đa** được phép học tại Trường quy định tại Khoản 2 Điều 15."
    ),
    24: (
        "**Về Học cùng lúc hai chương trình (Điều 24 - Trang 11):**\n"
        "- Sinh viên được đăng ký học chương trình thứ hai sớm nhất khi đã được xếp trình độ **năm thứ hai** của chương trình thứ nhất và đáp ứng 01 trong 02 điều kiện: (a) Điểm trung bình tích lũy xếp loại **Khá trở lên** và đạt ngưỡng bảo đảm chất lượng của chương trình thứ hai; hoặc (b) Xếp loại **Trung bình** và đáp ứng điều kiện trúng tuyển của chương trình thứ hai trong năm tuyển sinh."
    ),
    25: (
        "**Về Chuyển ngành, chuyển nơi học và chuyển hình thức học (Điều 25 - Trang 11 & Trang 12):**\n"
        "- Sinh viên được xem xét chuyển ngành hoặc chuyển cơ sở đào tạo khi: không phải sinh viên năm thứ nhất hoặc năm cuối khóa; không thuộc diện bị xử lý học vụ theo Điều 23; ngành chuyển đến thuộc cùng nhóm ngành và đạt điều kiện trúng tuyển cùng khóa; được sự đồng ý của Giám đốc chương trình và Hiệu trưởng."
    ),
    26: (
        "**Về Miễn, tạm hoãn học các học phần Giáo dục quốc phòng - an ninh và Giáo dục thể chất (Điều 26 - Trang 12 & Trang 13):**\n"
        "- Quy định cụ thể các đối tượng được miễn học hoàn toàn (có bằng trường quân đội/công an, chứng chỉ tương ứng, sinh viên hệ thường xuyên, người nước ngoài), miễn thực hành (khuyết tật, hoàn thành nghĩa vụ quân sự) hoặc tạm hoãn (điều trị bệnh dài ngày có xác nhận bệnh viện, phụ nữ mang thai/nghỉ thai sản)."
    ),
    27: (
        "**Về Điều kiện xét và công nhận tốt nghiệp đại học tại TDMU (Điều 27 - Trang 13):**\n"
        "- **Điều kiện công nhận tốt nghiệp (Khoản 1):** Sinh viên được Hội đồng xét tốt nghiệp xem xét khi đáp ứng đầy đủ 05 điều kiện:\n"
        "  + **(a)** Cho đến thời điểm xét tốt nghiệp không bị truy cứu trách nhiệm hình sự hoặc không đang trong thời gian bị kỷ luật ở mức đình chỉ học tập.\n"
        "  + **(b)** Tích lũy đủ số học phần và khối lượng tín chỉ của chương trình đào tạo theo quy định tại Khoản 1 Điều 12 (120 tín chỉ đối với Cử nhân; 150 tín chỉ đối với Kỹ sư, Kiến trúc sư).\n"
        "  + **(c)** Điểm trung bình tích lũy của toàn khóa học đạt từ **5,0 trở lên** (theo thang điểm 10).\n"
        "  + **(d)** Có đầy đủ chứng chỉ **Giáo dục quốc phòng - an ninh**, **Giáo dục thể chất** và đạt **Chuẩn đầu ra** của chương trình đào tạo (Ngoại ngữ, Tin học, Kỹ năng xã hội).\n"
        "  + **(e)** Có đơn gửi về Chương trình đào tạo đề nghị xét tốt nghiệp trong trường hợp tốt nghiệp sớm hoặc muộn hơn so với thời gian thiết kế chuẩn.\n"
        "- **Quy trình xét và cấp bằng (Khoản 2, Khoản 3):** Sau mỗi học kỳ, Hội đồng xét tốt nghiệp lập danh sách sinh viên đủ điều kiện và trình Hiệu trưởng ký quyết định công nhận tốt nghiệp, cấp bằng đại học."
    ),
    28: (
        "**Về Xếp hạng tốt nghiệp và các trường hợp bị giảm hạng tốt nghiệp (Điều 28 - Trang 13 & Trang 14):**\n"
        "- **Cách xác định hạng tốt nghiệp (Khoản 1):** Hạng tốt nghiệp được xếp dựa trên Điểm trung bình chung tích lũy (GPA) toàn khóa theo thang điểm 10:\n"
        "  + **Loại Xuất sắc:** Từ **9,0 đến 10,0**.\n"
        "  + **Loại Giỏi:** Từ **8,0 đến 8,99**.\n"
        "  + **Loại Khá:** Từ **7,0 đến 7,99**.\n"
        "  + **Loại Trung bình:** Từ **5,0 đến 6,99**.\n"
        "- **Trường hợp bị hạ 01 bậc xếp hạng tốt nghiệp (Khoản 2):** Sinh viên có kết quả học tập toàn khóa đạt loại **Xuất sắc** hoặc **Giỏi** sẽ bị giảm đi **01 mức** (Xuất sắc xuống Giỏi; Giỏi xuống Khá) nếu thuộc một trong hai trường hợp:\n"
        "  + **(a)** Tổng khối lượng các học phần phải **thi lại / học lại vượt quá 5%** so với tổng số tín chỉ quy định cho toàn chương trình (ví dụ: vượt quá 6 tín chỉ đối với chương trình Cử nhân 120 tín chỉ).\n"
        "  + **(b)** Đã bị xử lý **kỷ luật từ mức Cảnh cáo trở lên** trong thời gian học tập tại Trường.\n"
        "- **Hoàn thiện chuẩn đầu ra sau thời gian học tối đa (Khoản 5):** Sinh viên hết thời gian học tối đa nhưng còn nợ chứng chỉ GDQP-AN, GDTC hoặc chuẩn đầu ra Ngoại ngữ, Công nghệ thông tin, Kỹ năng xã hội được phép hoàn thiện các điều kiện còn thiếu trong thời hạn **03 năm** tính từ khi thôi học để đề nghị xét công nhận tốt nghiệp."
    ),
}


def strip_think_reasoning_tags(text: str) -> str:
    """Loại bỏ toàn bộ cặp thẻ suy luận `<think>...</think>` từ phản hồi của các mô hình LLM (như Qwen3, DeepSeek-R1)."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_latex_to_plain_math(text: str) -> str:
    """
    Chuyển đổi mọi ký hiệu LaTeX thô (`\\(...\\)`, `\\[...\\]`, `\\frac{a}{b}`, `\\approx`, `\\%`...)
    sang biểu thức toán học chữ thuần dễ đọc (`a/b`, `≈`, `%`) để hiển thị sạch trên Markdown UI.
    """
    if not text:
        return ""

    out = text
    # Gỡ các cặp dấu bao LaTeX \(...\), \[...\], $$...$$
    out = re.sub(r"\\\(\s*(.*?)\s*\\\)", r"\1", out, flags=re.DOTALL)
    out = re.sub(r"\\\[\s*(.*?)\s*\\\]", r"\1", out, flags=re.DOTALL)
    out = re.sub(r"\$\$\s*(.*?)\s*\$\$", r"\1", out, flags=re.DOTALL)

    # Chuyển \frac{a}{b} hoặc \dfrac{a}{b} -> a/b (lặp 2 lần cho trường hợp lồng nhau)
    for _ in range(2):
        out = re.sub(
            r"\\d?frac\s*\{\s*([^{}]+?)\s*\}\s*\{\s*([^{}]+?)\s*\}",
            r"\1/\2",
            out,
        )

    # Chuyển \text{...}, \textbf{...}, \mathrm{...} -> nội dung bên trong
    out = re.sub(
        r"\\(?:text|textbf|textit|mathrm|mathbf)\s*\{\s*([^{}]*?)\s*\}",
        r"\1",
        out,
    )

    # Thay thế các toán tử LaTeX phổ biến sang ký tự Unicode chuẩn
    latex_replacements = [
        (r"\\approx", " ≈ "),
        (r"\\times", " × "),
        (r"\\cdot", " · "),
        (r"\\div", " / "),
        (r"\\geq?", " ≥ "),
        (r"\\leq?", " ≤ "),
        (r"\\neq?", " ≠ "),
        (r"\\rightarrow|\\to\b", " → "),
        (r"\\Rightarrow", " ⇒ "),
        (r"\\%", "%"),
    ]
    for pattern, repl in latex_replacements:
        out = re.sub(pattern, repl, out)

    # Dọn khoảng trắng thừa trên cùng một dòng (giữ nguyên xuống dòng)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def format_ollama_analytical_output(raw_text: str) -> str:
    """
    Hậu xử lý phản hồi từ Ollama (`/api/chat/ai-reason`):
    1. Loại bỏ `<think>...</think>` và chuyển đổi mọi LaTeX thô sang toán học chữ thuần (`a/b`, `≈`).
    2. Bóc tách `<reasoning>...</reasoning>`, `VERDICT: Có | Không`, và `ADVICE: ...`
       (hoặc dùng regex dự phòng nếu mô hình không đóng đúng thẻ XML).
    3. Luôn lắp ráp kết quả Markdown cuối cùng với **Kết luận trực diện** ở ngay dòng đầu tiên,
       tiếp theo là **Bước 1 (Đối chiếu & Tính toán)** và **Bước 2 (Khuyến nghị học vụ)**,
       đảm bảo không bao giờ bị lặp hai mục "Kết luận".
    """
    cleaned = clean_latex_to_plain_math(strip_think_reasoning_tags(raw_text))
    if not cleaned:
        return ""

    # 1. Trích xuất khối <reasoning>...</reasoning>
    reasoning_match = re.search(
        r"<reasoning>\s*(.*?)\s*</reasoning>",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    reasoning_body = reasoning_match.group(1).strip() if reasoning_match else ""

    # Phần văn bản còn lại ngoài <reasoning>...</reasoning>
    outside_reasoning = (
        re.sub(
            r"<reasoning>.*?</reasoning>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        if reasoning_match
        else cleaned
    )
    outside_reasoning = re.sub(
        r"</?reasoning>", "", outside_reasoning, flags=re.IGNORECASE
    ).strip()

    # 2. Trích xuất VERDICT (ưu tiên dòng VERDICT: ..., sau đó đến Bước 2 / Kết luận)
    verdict_match = re.search(
        r"(?:VERDICT|KẾT\s*LUẬN(?:\s*TRỰC\s*DIỆN)?)\s*[:\-–]\s*\*{0,2}\s*([^\n\r]+)",
        outside_reasoning,
        flags=re.IGNORECASE,
    )
    if not verdict_match:
        verdict_match = re.search(
            r"(?:VERDICT|Bước\s*2\s*\(?Kết\s*luận\)?|Kết\s*luận(?:\s*trực\s*diện)?)\s*[:\-–]\s*\*{0,2}\s*([^\n\r]+)",
            cleaned,
            flags=re.IGNORECASE,
        )

    raw_verdict = verdict_match.group(1).strip() if verdict_match else ""

    # 3. Trích xuất ADVICE (ưu tiên dòng ADVICE: ..., hoặc Bước 2/Bước 3 Khuyến nghị học vụ)
    advice_match = re.search(
        r"(?:ADVICE|Bước\s*[23]\s*\(?Khuyến\s*nghị(?:\s*học\s*vụ)?\)?|Khuyến\s*nghị(?:\s*học\s*vụ)?)\*{0,2}\s*[:\-–]\*{0,2}\s*(.+)",
        outside_reasoning,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not advice_match:
        advice_match = re.search(
            r"(?:ADVICE|Bước\s*[23]\s*\(?Khuyến\s*nghị(?:\s*học\s*vụ)?\)?|Khuyến\s*nghị(?:\s*học\s*vụ)?)\*{0,2}\s*[:\-–]\*{0,2}\s*(.+)",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
    advice_body = advice_match.group(1).strip() if advice_match else ""

    # Nếu trong ADVICE vô tình dính dòng VERDICT ở phía dưới thì cắt bỏ
    advice_body = re.sub(
        r"\n\s*(?:VERDICT|KẾT\s*LUẬN).*$",
        "",
        advice_body,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    # 4. Dự phòng nếu mô hình không dùng thẻ <reasoning>...</reasoning>
    if not reasoning_body:
        fallback_text = cleaned
        # Loại bỏ các dòng VERDICT / Kết luận / ADVICE / Khuyến nghị khỏi phần tính toán
        fallback_text = re.sub(
            r"^\s*[-*•]?\s*\*{0,2}(?:VERDICT|Kết\s*luận(?:\s*trực\s*diện)?|Bước\s*2\s*\(?Kết\s*luận\)?)\*{0,2}\s*[:\-–]\*{0,2}.*$",
            "",
            fallback_text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        fallback_text = re.sub(
            r"\n?\s*[-*•]?\s*\*{0,2}(?:ADVICE|Bước\s*[23]\s*\(?Khuyến\s*nghị(?:\s*học\s*vụ)?\)?|Khuyến\s*nghị(?:\s*học\s*vụ)?)\*{0,2}\s*[:\-–]\*{0,2}.*$",
            "",
            fallback_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        reasoning_body = fallback_text.strip()

    # Làm sạch nhãn tiêu đề trùng lặp bên trong reasoning_body và advice_body
    reasoning_body = re.sub(
        r"^\s*[-*•]?\s*\*{0,2}Bước\s*1\s*\(?Đối\s*chiếu\s*(?:&|và)\s*Tính\s*toán\)?\*{0,2}\s*[:\-–]?\*{0,2}\s*",
        "",
        reasoning_body,
        flags=re.IGNORECASE,
    ).strip()
    # Loại bỏ mọi dòng hoặc cụm "VERDICT:...", "Kết luận:...", "ADVICE:...", "Khuyến nghị học vụ:..."
    # bị mô hình viết lồng vào cuối hoặc bên trong <reasoning> để Bước 1 không bao giờ lặp lại nội dung của Kết luận hay Bước 2
    reasoning_body = re.sub(
        r"(?:^|\n)\s*[-*•]?\s*\*{0,2}(?:VERDICT|Kết\s*luận(?:\s*trực\s*diện)?|Bước\s*2\s*\(?Kết\s*luận\)?)\*{0,2}\s*[:\-–]\*{0,2}[^\n\r]*",
        "",
        reasoning_body,
        flags=re.IGNORECASE,
    ).strip()
    reasoning_body = re.sub(
        r"(?:^|\n|\s+)\s*[-*•]?\s*\*{0,2}(?:ADVICE|Bước\s*[23]\s*\(?Khuyến\s*nghị(?:\s*học\s*vụ)?\)?|Khuyến\s*nghị(?:\s*học\s*vụ)?)\*{0,2}\s*[:\-–]\*{0,2}.*$",
        "",
        reasoning_body,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    reasoning_body = re.sub(
        r"\s*\b(?:VERDICT|ADVICE)\s*[:\-–].*$",
        "",
        reasoning_body,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    advice_body = re.sub(
        r"^\s*[-*•]?\s*\*{0,2}(?:ADVICE|Bước\s*[23]\s*\(?Khuyến\s*nghị(?:\s*học\s*vụ)?\)?|Khuyến\s*nghị(?:\s*học\s*vụ)?)\*{0,2}\s*[:\-–]?\*{0,2}\s*",
        "",
        advice_body,
        flags=re.IGNORECASE,
    ).strip()
    advice_body = re.sub(r"</?reasoning>", "", advice_body, flags=re.IGNORECASE).strip()
    reasoning_body = re.sub(r"</?reasoning>", "", reasoning_body, flags=re.IGNORECASE).strip()
    raw_verdict = re.sub(r"</?reasoning>", "", raw_verdict, flags=re.IGNORECASE).strip()

    # Chuẩn hóa giá trị Kết luận trực diện (Có / Không kèm giải thích ngắn nếu có)
    raw_verdict_clean = re.sub(r"^\*{1,2}|\*{1,2}$", "", raw_verdict).strip()
    if not raw_verdict_clean:
        # Suy luận từ nội dung nếu mô hình quên dòng VERDICT
        if re.search(
            r"\b(?:không\s+được|không\s+đủ|bị\s+hạ|bị\s+giảm|bị\s+cảnh\s+báo|vượt\s+quá|vi\s+phạm)\b",
            reasoning_body,
            flags=re.IGNORECASE,
        ):
            raw_verdict_clean = "Không"
        else:
            raw_verdict_clean = "Có"

    # Chuẩn hóa chữ đầu "Không" hoặc "Có" nổi bật
    if re.match(r"^không\b", raw_verdict_clean, flags=re.IGNORECASE):
        rest = re.sub(r"^không[\s,.\-–:]*", "", raw_verdict_clean, flags=re.IGNORECASE).strip()
        verdict_display = f"**Không** — {rest}" if rest else "**Không**"
    elif re.match(r"^có\b", raw_verdict_clean, flags=re.IGNORECASE):
        rest = re.sub(r"^có[\s,.\-–:]*", "", raw_verdict_clean, flags=re.IGNORECASE).strip()
        verdict_display = f"**Có** — {rest}" if rest else "**Có**"
    else:
        verdict_display = f"**{raw_verdict_clean}**"

    if not advice_body:
        advice_body = (
            "Sinh viên có thể đối chiếu thêm bảng điểm cá nhân trên cổng thông tin đào tạo "
            "hoặc liên hệ Phòng Đào tạo Đại học / Phòng Công tác Sinh viên TDMU để được hỗ trợ xác nhận."
        )

    if not reasoning_body:
        reasoning_body = cleaned

    assembled = (
        f"- **Kết luận trực diện:** {verdict_display}\n"
        f"- **Bước 1 (Đối chiếu & Tính toán):** {reasoning_body}\n"
        f"- **Bước 2 (Khuyến nghị học vụ):** {advice_body}"
    )
    return clean_latex_to_plain_math(assembled)


def clean_citation_quote_unicode(text: str, is_table: bool = False) -> str:
    """
    Hàm tự động làm sạch ký tự lạ, chuẩn hóa Unicode NFC và khôi phục tiếng Việt chuẩn
    cho trường `citations.quote` trước khi trả về Frontend.
    """
    if not text:
        return ""

    text = strip_think_reasoning_tags(text)
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalize_vietnamese_academic_text(normalized)

    if is_table or "| --- |" in normalized or "|---|" in normalized:
        clean_lines = []
        for line in normalized.split("\n"):
            line_stripped = line.strip()
            if line_stripped:
                clean_lines.append(line_stripped)
        return "\n".join(clean_lines)

    normalized = re.sub(
        r"\b(sau|tạo|phần|kỳ)\d+\b", r"\1", normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(r"\s*,\s*,+\s*", ", ", normalized)
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


class AcademicRAGPipeline:
    """
    Pipeline Advanced RAG End-to-End của Trường Đại học Thủ Dầu Một (TDMU):
    - Bước 0 (Relevance Gate): Kiểm tra sớm các câu hỏi ngoài phạm vi văn bản Quy chế 1774/QĐ-ĐHTDM
      (như đơn giá tiền học phí/tín chỉ, vị trí căn tin/cơ sở, lịch thi từng ngày...).
    - Bước 1 (Multi-Query Expansion): Tự động biến đổi câu hỏi đời thường của sinh viên thành
      2-3 câu truy vấn chuẩn thuật ngữ Quy chế Đào tạo Tín chỉ TDMU (`generate_multi_queries`).
    - Bước 2 (Multi-Query Hybrid Search & Deduplication): Thực hiện `hybrid_search` (Dense + Sparse BM25)
      trên Qdrant cho cả câu hỏi gốc lẫn các câu hỏi mở rộng, gộp ứng viên và khử trùng lặp theo `chunk_id`.
    - Bước 3 (Re-ranking & Score Gate): Đưa toàn bộ ứng viên qua `AcademicReranker.rerank(query, candidates, top_n=5)`
      và kiểm tra ngưỡng `specific_overlap` / `rerank_score` để từ chối an toàn nếu ngữ cảnh không trả lời trực tiếp câu hỏi.
    - Bước 4 (Grounded Synthesis & Guardrails): Đọc hiểu ngữ cảnh Top-5 sau Re-rank, viết lại hoàn toàn
      bằng tiếng Việt chuẩn mực TDMU và kiểm duyệt qua `validate_grounded_response`.
    """

    def __init__(
        self,
        vector_store: AcademicVectorStore | None = None,
        reranker: AcademicReranker | None = None,
    ):
        self.vector_store = vector_store or AcademicVectorStore()
        # Giữ nguyên Local Dense Embedder (1536d) cho embeddings, không gọi OpenAI/Ollama Embeddings API
        self.vector_store.openai_client = None
        self.reranker = reranker or AcademicReranker()
        self.system_prompt = TDMU_SYSTEM_PROMPT
        has_valid_key = bool(
            OpenAI is not None
            and (
                (
                    settings.openai_api_key
                    and settings.openai_api_key != "your_openai_api_key_here"
                )
                or settings.openai_base_url
            )
        )
        client_kwargs: Dict[str, Any] = {
            "api_key": settings.openai_api_key or "ollama",
        }
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        self.openai_client = (
            OpenAI(**client_kwargs) if has_valid_key else None
        )

    @staticmethod
    def _is_valid_regulation_article_chunk(chunk: Dict[str, Any]) -> bool:
        """
        Cho phép cả các chunk thuộc `Điều` (article của Quy chế 1774) lẫn `Mục` (section của văn bản
        Hướng dẫn / Công văn `03/HD-ĐHTDM` và `432/ĐHTDM-TTNN`), chỉ chặn phần tiêu ngữ mở đầu
        ("UBND TỈNH BÌNH DƯƠNG... Kính gửi..." không thuộc Điều/Mục nào hoặc Trang 1 của Quy chế 1774).
        """
        doc_name = str(chunk.get("document_name", "")).strip().lower()
        page_num = int(chunk.get("page_number", 1))
        article_str = str(chunk.get("article", "")).strip()

        if not article_str:
            return False

        # Với Quy chế 1774, Trang 1 chỉ chứa Quyết định hành chính ban hành nên loại bỏ
        if "1774" in doc_name and page_num <= 1:
            return False

        if re.search(r"\b(?:Điều|Mục)\s+\d+\b", article_str, flags=re.IGNORECASE):
            return True

        return False

    @staticmethod
    def check_direct_relevance_gate(question: str) -> tuple[bool, str]:
        """
        Kiểm tra Lọc Ngữ Nghĩa Tổng Quát (General Out-of-Domain Gate):
        - Phát hiện các câu hỏi không chứa bất kỳ từ khóa nghiệp vụ đào tạo nào sau khi lọc
          `GENERIC_STOP_ENTITY_TOKENS` (ví dụ: "Trường Đại học Thủ Dầu Một nằm ở đâu", "Hiệu trưởng trường là ai").
        - Phát hiện các câu hỏi định lượng/hành chính ngoài phạm vi Quy chế 1774/QĐ-ĐHTDM.
        - Trả về `(is_blocked, GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE)`.
        """
        q_clean = (question or "").strip()
        q_lower = q_clean.lower()

        for kw in OUT_OF_DOMAIN_KEYWORDS:
            if kw in q_lower:
                return True, GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE

        for pattern, _ in UNANSWERABLE_REGULATION_PATTERNS:
            if re.search(pattern, q_lower, flags=re.IGNORECASE):
                return True, GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE

        # Nếu sau khi loại bỏ GENERIC_STOP_ENTITY_TOKENS mà câu hỏi trống rỗng (không có từ khóa nghiệp vụ)
        # và cũng không hỏi đích danh "Điều X" -> Từ chối ngay lập tức
        specific_tokens = extract_specific_academic_tokens(q_clean)
        has_explicit_article = bool(re.search(r"\bđiều\s+\d+\b", q_lower))
        if not specific_tokens and not has_explicit_article:
            return True, GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE

        return False, ""

    def generate_multi_queries(self, user_query: str) -> List[str]:
        """
        Biến đổi câu hỏi đời thường của sinh viên thành 2-3 câu truy vấn chuẩn thuật ngữ
        Quy chế Đào tạo Tín chỉ Trường Đại học Thủ Dầu Một (Quyết định 1774/QĐ-ĐHTDM).
        """
        cleaned_query = (user_query or "").strip()
        if not cleaned_query:
            return []

        is_blocked, _ = self.check_direct_relevance_gate(cleaned_query)
        if is_blocked:
            return []

        q_lower = cleaned_query.lower()

        # Ưu tiên bộ mở rộng thuật ngữ Học vụ TDMU chuẩn xác để tránh độ trễ/nhiễu từ LLM cục bộ
        expanded: List[str] = []
        for triggers, formal_queries in COLLOQUIAL_TO_ACADEMIC_EXPANSIONS:
            if any(trig in q_lower for trig in triggers):
                for fq in formal_queries:
                    if fq not in expanded:
                        expanded.append(fq)

        if expanded:
            return expanded[:3]

        if self.openai_client is not None and not settings.openai_base_url:
            try:
                mq_prompt = (
                    "Bạn là chuyên gia Quy chế Đào tạo Tín chỉ của Trường Đại học Thủ Dầu Một (TDMU - Quyết định 1774/QĐ-ĐHTDM). "
                    "Hãy biến đổi câu hỏi đời thường dưới đây của sinh viên thành 2 đến 3 câu truy vấn tìm kiếm chuẩn thuật ngữ pháp quy học vụ "
                    "(nhắc rõ tên khái niệm quy chế và số Điều tương ứng nếu biết như: Điều 12 Thiết kế chương trình đào tạo, "
                    "Điều 15 Thời gian khóa học, Điều 19 Đăng ký khối lượng học tập & học lại, Điều 21 Nghỉ học tạm thời & bảo lưu, "
                    "Điều 22 Rút bớt học phần, Điều 23 Cảnh báo học vụ & buộc thôi học, Điều 27 Điều kiện xét tốt nghiệp, "
                    "Điều 28 Xếp hạng tốt nghiệp & giảm hạng).\n\n"
                    f"Câu hỏi của sinh viên: {cleaned_query}"
                )
                completion = self.openai_client.beta.chat.completions.parse(
                    model=settings.llm_model,
                    temperature=0.0,
                    messages=[
                        {"role": "user", "content": mq_prompt},
                    ],
                    response_format=MultiQueryOutput,
                )
                parsed = completion.choices[0].message.parsed
                if parsed and parsed.queries:
                    llm_queries = [
                        strip_think_reasoning_tags(q).strip()
                        for q in parsed.queries
                        if strip_think_reasoning_tags(q).strip()
                    ]
                    if llm_queries:
                        return llm_queries[:3]
            except Exception as exc:
                print(
                    f"[!] Cảnh báo Multi-Query OpenAI ({exc}) -> Sử dụng bộ mở rộng thuật ngữ Học vụ TDMU."
                )

        if not expanded:
            expanded = [
                f"Quy định học vụ Trường Đại học Thủ Dầu Một về: {cleaned_query}",
                f"Điều khoản hướng dẫn chi tiết trong Quy chế đào tạo tín chỉ TDMU đối với: {cleaned_query}",
            ]

        return expanded[:3]

    def multi_query_hybrid_retrieve(
        self,
        user_query: str,
        expanded_queries: List[str],
        per_query_top_k: int = 6,
        alpha: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Thực hiện gọi `hybrid_search` trên Qdrant cho câu hỏi gốc lẫn các câu hỏi mở rộng,
        sau đó gộp toàn bộ ứng viên và loại bỏ các chunk trùng lặp dựa trên `chunk_id`.
        """
        all_queries = [user_query] + [
            q for q in expanded_queries if q.strip() and q.strip() != user_query.strip()
        ]

        merged_by_id: Dict[str, Dict[str, Any]] = {}

        for q_idx, q_text in enumerate(all_queries):
            hits = self.vector_store.hybrid_search(
                query=q_text,
                top_k=per_query_top_k,
                alpha=alpha,
            )
            query_weight = 1.0 if q_idx == 0 else 0.95
            for hit in hits:
                # Loại bỏ ngay các chunk thuộc phần Tiêu ngữ mở đầu (Trang 1) hoặc không thuộc Điều khoản cụ thể nào
                if not self._is_valid_regulation_article_chunk(hit):
                    continue

                cid = str(
                    hit.get("chunk_id")
                    or f"{hit.get('document_name')}_{hit.get('page_number')}_{hit.get('article')}_{hit.get('clause')}"
                )
                weighted_score = round(float(hit.get("score", 0.0)) * query_weight, 4)

                if cid not in merged_by_id:
                    cand = dict(hit)
                    cand["score"] = weighted_score
                    cand["matched_queries"] = [q_text]
                    merged_by_id[cid] = cand
                else:
                    existing = merged_by_id[cid]
                    if q_text not in existing.get("matched_queries", []):
                        existing.setdefault("matched_queries", []).append(q_text)
                    best_base = max(float(existing.get("score", 0.0)), weighted_score)
                    existing["score"] = round(best_base + 0.03, 4)
                    existing["dense_score"] = max(
                        float(existing.get("dense_score", 0.0)),
                        float(hit.get("dense_score", 0.0)),
                    )
                    existing["sparse_score"] = max(
                        float(existing.get("sparse_score", 0.0)),
                        float(hit.get("sparse_score", 0.0)),
                    )

        return list(merged_by_id.values())

    def format_context(self, retrieved_chunks: List[Dict[str, Any]]) -> str:
        if not retrieved_chunks:
            return "Không tìm thấy đoạn quy chế TDMU nào phù hợp."

        blocks = []
        for idx, item in enumerate(retrieved_chunks, start=1):
            doc_name = item.get("document_name") or item.get("source")
            is_tbl = item.get("is_table", False)
            clean_content = clean_citation_quote_unicode(
                self._strip_context_header(item.get("content", "")),
                is_table=bool(is_tbl),
            )
            blocks.append(
                f"--- ĐOẠN TÀI LIỆU #{idx} (Rerank Score: {item.get('score', 0):.4f}) ---\n"
                f"File nguồn: {doc_name}\n"
                f"Trang: {item.get('page_number')}\n"
                f"Chương: {item.get('chapter')}\n"
                f"Điều: {item.get('article')} | Khoản: {item.get('clause')} (Bảng biểu: {is_tbl})\n"
                f"Nội dung:\n{clean_content}\n"
            )
        return "\n".join(blocks)

    @staticmethod
    def _strip_context_header(content: str) -> str:
        lines = content.strip().split("\n")
        if lines and lines[0].startswith("[") and lines[0].endswith("]"):
            return "\n".join(lines[1:]).strip()
        return content.strip()

    @staticmethod
    def _extract_article_number(article_str: str) -> int | None:
        m = re.search(r"Điều\s+(\d+)", article_str or "", flags=re.IGNORECASE)
        return int(m.group(1)) if m else None

    def _synthesize_academic_response(
        self,
        question: str,
        retrieved: List[Dict[str, Any]],
        expanded_queries: List[str],
    ) -> GroundedRAGResponse:
        """
        Đọc hiểu ngữ cảnh từ Top-5 chunks sau khi qua Multi-Query + Reranker và VIẾT LẠI HOÀN TOÀN
        bằng tiếng Việt chuẩn ngữ pháp, đủ dấu, hành văn học thuật trang trọng của TDMU.
        """
        is_blocked, refusal_msg = self.check_direct_relevance_gate(question)
        if is_blocked:
            return GroundedRAGResponse(
                answer=refusal_msg,
                citations=[],
                is_safe=True,
                is_answerable=False,
                confidence_level="none",
                expanded_queries=[],
            )

        top_hit = retrieved[0]
        # Kiểm tra điểm Rerank và độ khớp từ khóa nghiệp vụ đặc thù (`specific_overlap`)
        # Nếu `specific_overlap == 0.0` (không có bất kỳ từ khóa nghiệp vụ nào trong câu hỏi khớp với nội dung các Điều khoản)
        # hoặc điểm rerank quá thấp -> BẮT BUỘC đánh dấu `is_answerable = False` và trả về câu từ chối chuẩn
        if (
            top_hit.get("specific_overlap", 0.0) <= 0.0
            or (
                top_hit.get("specific_overlap", 0.0) < 0.20
                and top_hit.get("rerank_score", 0.0) < 0.45
            )
            or (
                top_hit.get("dense_score", 0.0) < 0.08
                and top_hit.get("sparse_score", 0.0) <= 0.0
            )
        ):
            return GroundedRAGResponse(
                answer=GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE,
                citations=[],
                is_safe=True,
                is_answerable=False,
                confidence_level="none",
                expanded_queries=[],
            )

        q_lower = question.lower()
        top_article = top_hit.get("article", "")
        top_doc_name_initial = str(
            top_hit.get("document_name") or top_hit.get("source") or ""
        )

        # Với văn bản Quy chế 1774, gom các Khoản thuộc cùng một Điều;
        # Với văn bản Hướng dẫn / Công văn (03/HD-ĐHTDM, 432/ĐHTDM-TTNN), gom các Mục và Bảng biểu thuộc cùng văn bản
        if "1774" in top_doc_name_initial:
            same_group_hits = [
                c for c in retrieved if top_article and c.get("article") == top_article
            ]
        else:
            same_group_hits = [
                c
                for c in retrieved
                if (c.get("document_name") or c.get("source")) == top_doc_name_initial
            ]

        def _clause_sort_key(hit: Dict[str, Any]) -> tuple:
            same_doc = (
                0
                if (hit.get("document_name") or hit.get("source"))
                == top_doc_name_initial
                else 1
            )
            art_str = str(hit.get("article", ""))
            art_m = re.search(r"(\d+)", art_str)
            art_num = int(art_m.group(1)) if art_m else 99
            clause_str = str(hit.get("clause", ""))
            cls_m = re.search(r"(\d+)", clause_str)
            clause_num = int(cls_m.group(1)) if cls_m else 99
            is_tbl = 1 if hit.get("is_table", False) else 0
            return (same_doc, art_num, clause_num, is_tbl, int(hit.get("page_number", 1)))

        if len(same_group_hits) >= 2:
            same_group_hits.sort(key=_clause_sort_key)
            selected_hits = same_group_hits[:4]
        else:
            selected_hits = [top_hit]
            for cand in retrieved[1:]:
                if len(selected_hits) >= 4:
                    break
                if cand.get("score", 0.0) >= top_hit.get("score", 0.0) * 0.45:
                    selected_hits.append(cand)
            selected_hits.sort(key=_clause_sort_key)

        combined_q = " ".join([q_lower] + [eq.lower() for eq in expanded_queries])
        if (
            "điều 12" in combined_q
            or "chuẩn đầu ra" in combined_q
            or "ngoại ngữ" in combined_q
            or "học bổng" in combined_q
            or "phúc khảo" in combined_q
            or "hoãn thi" in combined_q
            or "xác nhận sinh viên" in combined_q
            or "thủ tục hành chính" in combined_q
        ):
            for cand in retrieved:
                if (
                    cand.get("is_table")
                    and (cand.get("document_name") or cand.get("source"))
                    == top_doc_name_initial
                    and cand not in selected_hits
                ):
                    selected_hits.append(cand)
                    break

        top_doc_name = (
            top_hit.get("document_name")
            or top_hit.get("source")
            or "quy_che_dao_tao_tdmu_1774.pdf"
        )
        top_doc_meta = resolve_tdmu_document_metadata(top_doc_name)
        top_doc_title = top_hit.get("doc_title") or top_doc_meta["doc_title"]
        top_issue_year = str(top_hit.get("issue_year") or top_doc_meta["issue_year"])

        synthesized_sections: List[str] = [
            f"Căn cứ theo **{top_doc_title} (Ban hành năm {top_issue_year})** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:"
        ]
        used_article_nums: set[int] = set()
        included_tables: List[str] = []
        citations: List[CitationItem] = []

        for hit in selected_hits:
            doc_name = (
                hit.get("document_name")
                or hit.get("source")
                or "quy_che_dao_tao_tdmu_1774.pdf"
            )
            doc_meta = resolve_tdmu_document_metadata(doc_name)
            doc_title = hit.get("doc_title") or doc_meta["doc_title"]
            issue_year = str(hit.get("issue_year") or doc_meta["issue_year"])
            file_type = str(
                hit.get("file_type")
                or doc_meta.get("file_type")
                or ("docx" if doc_name.lower().endswith(".docx") else "pdf")
            )
            page_num = int(hit.get("page_number", 1))
            if file_type == "docx":
                chapter = (hit.get("chapter") or "").strip()
                article = (hit.get("article") or "").strip()
                clause = (hit.get("clause") or "").strip()
            else:
                chapter = clean_citation_quote_unicode(hit.get("chapter", ""))
                article = clean_citation_quote_unicode(hit.get("article", ""))
                clause = clean_citation_quote_unicode(hit.get("clause", ""))
            is_table = bool(hit.get("is_table", False))

            raw_body = self._strip_context_header(hit.get("content", ""))
            if file_type == "docx":
                clean_body = raw_body.strip()
            else:
                clean_body = clean_citation_quote_unicode(raw_body, is_table=is_table)

            art_num = (
                self._extract_article_number(article)
                if "1774" in doc_name
                else None
            )
            if art_num and art_num in ACADEMIC_ARTICLE_REWRITE_KNOWLEDGE:
                if art_num not in used_article_nums:
                    synthesized_sections.append(
                        ACADEMIC_ARTICLE_REWRITE_KNOWLEDGE[art_num]
                    )
                    used_article_nums.add(art_num)
            elif not is_table:
                loc_label = (
                    " — ".join(filter(None, [article, clause]))
                    or doc_title
                )
                synthesized_sections.append(
                    f"**{loc_label} ({doc_title} - Trang {page_num}):**\n{clean_body}"
                )

            if is_table and clean_body not in included_tables:
                included_tables.append(clean_body)
                loc_label = (
                    " — ".join(filter(None, [article, clause]))
                    or f"Bảng biểu {doc_title}"
                )
                synthesized_sections.append(
                    f"**Bảng tổng hợp ({loc_label} - Trang {page_num}):**\n\n{clean_body}"
                )

            if is_table:
                quote_preview = clean_body
            else:
                quote_preview = clean_body
                if len(quote_preview) > 280:
                    quote_preview = quote_preview[:277] + "..."

            citations.append(
                CitationItem(
                    source_file=doc_name,
                    document_name=doc_name,
                    doc_title=doc_title,
                    issue_year=issue_year,
                    file_type=file_type,
                    chapter=chapter,
                    article=article,
                    clause=clause,
                    page_number=page_num,
                    quote=quote_preview,
                    is_table=is_table,
                )
            )

        return GroundedRAGResponse(
            answer="\n\n".join(synthesized_sections).strip(),
            citations=citations,
            is_safe=True,
            is_answerable=True,
            confidence_level="high",
            expanded_queries=expanded_queries,
        )

    def answer_question(
        self,
        question: str,
        top_k: int = 5,
        alpha: float = 0.5,
    ) -> GroundedRAGResponse:
        # Bước 0: Kiểm tra Relevance Gate ngay lập tức đối với câu hỏi ngoài phạm vi Quy chế 1774
        is_blocked, refusal_msg = self.check_direct_relevance_gate(question)
        if is_blocked:
            return GroundedRAGResponse(
                answer=refusal_msg,
                citations=[],
                is_safe=True,
                is_answerable=False,
                confidence_level="none",
                expanded_queries=[],
            )

        # Bước 1: Multi-Query Expansion (biến đổi câu hỏi đời thường thành 2-3 câu chuẩn thuật ngữ TDMU)
        expanded_queries = self.generate_multi_queries(question)

        # Bước 2: Truy vấn Hybrid Search trên Qdrant cho câu hỏi gốc + các câu mở rộng và khử trùng lặp
        candidates = self.multi_query_hybrid_retrieve(
            user_query=question,
            expanded_queries=expanded_queries,
            per_query_top_k=max(6, top_k),
            alpha=alpha,
        )
        if not candidates:
            return GroundedRAGResponse(
                answer=GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE,
                citations=[],
                is_safe=True,
                is_answerable=False,
                confidence_level="none",
                expanded_queries=[],
            )

        # Bước 3: Đưa toàn bộ ứng viên qua Tầng Re-ranking (lọc ra top_n=5 ngữ cảnh điểm cao nhất)
        reranked_top_chunks = self.reranker.rerank(
            query=question,
            candidates=candidates,
            top_n=top_k,
            expanded_queries=expanded_queries,
        )

        # Kiểm tra ngưỡng `specific_overlap` & `rerank_score` từ AcademicReranker trước khi đưa vào tổng hợp / gọi LLM
        top_reranked = reranked_top_chunks[0]
        if top_reranked.get("specific_overlap", 0.0) <= 0.0 or (
            top_reranked.get("specific_overlap", 0.0) < 0.20
            and top_reranked.get("rerank_score", 0.0) < 0.45
        ):
            return GroundedRAGResponse(
                answer=GENERAL_OUT_OF_DOMAIN_REFUSAL_MESSAGE,
                citations=[],
                is_safe=True,
                is_answerable=False,
                confidence_level="none",
                expanded_queries=[],
            )

        # Bước 4: Luồng tra cứu mặc định (`/api/chat`) LUÔN sử dụng bộ Tổng hợp Học thuật tất định (Deterministic Academic Synthesis Engine)
        # để đảm bảo phản hồi tức thì, chính xác 100% trích dẫn mà không bị độ trễ LLM hay từ chối nhầm.
        synthesized_response = self._synthesize_academic_response(
            question=question,
            retrieved=reranked_top_chunks,
            expanded_queries=expanded_queries,
        )
        synthesized_response.answer = strip_think_reasoning_tags(
            synthesized_response.answer
        )
        validated = validate_grounded_response(
            synthesized_response, reranked_top_chunks
        )
        validated.answer = strip_think_reasoning_tags(validated.answer)
        validated.expanded_queries = (
            expanded_queries if validated.is_answerable else []
        )
        return validated

    def reason_with_ollama(
        self,
        question: str,
        base_answer: str,
        citations: List[Dict[str, Any]],
        custom_prompt: str | None = None,
    ) -> Dict[str, Any]:
        """
        Tầng Suy luận & Hỏi đáp sâu theo yêu cầu (On-Demand Ollama Reasoning — `POST /api/chat/ai-reason`):
        - Kết nối tới Ollama cục bộ tại `settings.openai_base_url` (`http://localhost:11434/v1`)
          với mô hình `settings.llm_model` (ví dụ: `qwen2.5:3b` hoặc `qwen3:8b`).
        - Phân tích logic từng bước để trả lời câu hỏi Có/Không hoặc tình huống cá nhân của sinh viên
          (so sánh GPA, số tín chỉ tích lũy, thời gian học... với ngưỡng quy định trong trích dẫn).
        - Tự động loại bỏ thẻ `<think>...</think>`. Nếu Ollama đang tắt hoặc quá thời gian chờ,
          ném lỗi `ConnectionError` để tầng API trả về HTTP 503 rõ ràng bằng tiếng Việt.
        """
        if OpenAI is None:
            raise ConnectionError(
                "Không thể kết nối Ollama cục bộ tại cổng 11434. Hãy kiểm tra ứng dụng Ollama đang chạy."
            )

        base_url = (settings.openai_base_url or "http://localhost:11434/v1").strip()
        api_key = (settings.openai_api_key or "ollama").strip()
        model_name = (settings.llm_model or "qwen2.5:3b").strip()

        citation_blocks: List[str] = []
        for idx, cit in enumerate(citations or [], start=1):
            doc_title = cit.get("doc_title") or cit.get("document_name") or "Quy chế TDMU"
            issue_year = cit.get("issue_year") or ""
            article = cit.get("article") or ""
            clause = cit.get("clause") or ""
            page_num = cit.get("page_number") or 1
            quote = cit.get("quote") or ""
            citation_blocks.append(
                f"[Trích dẫn #{idx}] Văn bản: {doc_title} (Năm {issue_year}) | "
                f"{article} {clause} | Trang {page_num}:\n{quote}"
            )

        citations_context = (
            "\n\n".join(citation_blocks)
            if citation_blocks
            else "Sử dụng nội dung tổng hợp quy chế bên dưới để đối chiếu."
        )

        target_scenario = (custom_prompt or "").strip()
        effective_question = (
            f"Câu hỏi gốc: {question}\nTình huống / Câu hỏi suy luận cụ thể của sinh viên: {target_scenario}"
            if target_scenario
            else f"Câu hỏi cần phân tích & kết luận Có/Không hoặc giải thích chi tiết: {question}"
        )

        analytical_system_prompt = (
            "Bạn là Chuyên gia Phân tích Quy chế & Cố vấn Học vụ của Trường Đại học Thủ Dầu Một (TDMU).\n"
            "NHIỆM VỤ BẮT BUỘC:\n"
            "1. Đọc kỹ [NỘI DUNG QUY CHẾ ĐÃ TRÍCH XUẤT] và [CÁC TRÍCH DẪN ĐIỀU KHOẢN GỐC] được cung cấp.\n"
            "2. Thực hiện đối chiếu số liệu và tính toán từng bước TRƯỚC KHI đưa ra kết luận Có/Không, theo đúng định dạng đầu ra bắt buộc sau đây:\n"
            "   - Đầu tiên, viết toàn bộ phần đối chiếu điều khoản và phép tính số học vào bên trong cặp thẻ `<reasoning>...</reasoning>`.\n"
            "     + QUY TẮC TOÁN HỌC BẮT BUỘC: Chỉ sử dụng chữ thuần dễ đọc như `7 / 120 = 5,83% > 5%` hoặc `120 × 5% = 6 tín chỉ`. TUYỆT ĐỐI KHÔNG dùng ký hiệu LaTeX như `\\frac`, `\\(`, `\\)`, `\\[`, `\\]` hay `\\approx`.\n"
            "     + Trong thẻ `<reasoning>`, chỉ đối chiếu và tính toán, chưa viết dòng VERDICT.\n"
            "   - Ngay sau thẻ `</reasoning>`, xuống dòng và xuất đúng dòng:\n"
            "     `VERDICT: Không` (nếu sinh viên vi phạm bất kỳ điều kiện nào, vượt ngưỡng giới hạn 5%, bị hạ bậc, bị cảnh báo hoặc không đủ điều kiện) HOẶC `VERDICT: Có` (chỉ khi thỏa mãn đầy đủ tất cả điều kiện).\n"
            "   - Ngay dòng tiếp theo, xuất đúng dòng:\n"
            "     `ADVICE: <ghi chú khuyến nghị học vụ ngắn gọn, hướng dẫn bước tiếp theo hoặc liên hệ Phòng Đào tạo Đại học / Phòng Công tác Sinh viên TDMU>`.\n"
            "3. TUYỆT ĐỐI KHÔNG xuất thông báo từ chối 'ngoài phạm vi dữ liệu' khi đã có trích dẫn quy chế đi kèm. "
            "Trình bày hoàn toàn bằng tiếng Việt chuẩn mực, rõ ràng, súc tích."
        )

        analytical_user_prompt = (
            f"[NỘI DUNG QUY CHẾ ĐÃ TRÍCH XUẤT]:\n{base_answer}\n\n"
            f"[CÁC TRÍCH DẪN ĐIỀU KHOẢN GỐC TDMU]:\n{citations_context}\n\n"
            f"[YÊU CẦU PHÂN TÍCH TÌNH HUỐNG]:\n{effective_question}"
        )

        try:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=45.0,
                max_retries=0,
            )
            completion = client.chat.completions.create(
                model=model_name,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": analytical_system_prompt},
                    {"role": "user", "content": analytical_user_prompt},
                ],
            )
            raw_content = (completion.choices[0].message.content or "").strip()
            cleaned_reasoning = format_ollama_analytical_output(raw_content)
            if not cleaned_reasoning:
                cleaned_reasoning = (
                    "Không nhận được nội dung phân tích từ mô hình AI cục bộ. Vui lòng thử lại."
                )
            return {
                "reasoning": cleaned_reasoning,
                "model": model_name,
                "base_url": base_url,
                "evaluated_question": target_scenario or question,
            }
        except Exception as exc:
            raise ConnectionError(
                "Không thể kết nối Ollama cục bộ tại cổng 11434. Hãy kiểm tra ứng dụng Ollama đang chạy."
            ) from exc

    def query(
        self,
        question: str,
        top_k: int = 5,
        alpha: float = 0.5,
    ) -> GroundedRAGResponse:
        """Alias cho `answer_question` phục vụ tích hợp Webhook (Facebook Messenger Bot, API đối tác...)."""
        return self.answer_question(question=question, top_k=top_k, alpha=alpha)
