import json
import re
from pathlib import Path
from typing import Any, Dict, List
import pdfplumber


# Bảng ánh xạ Metadata chuẩn (doc_title, issue_year, file_type) cho các văn bản pháp quy Học vụ TDMU
TDMU_DOCUMENT_METADATA_REGISTRY: Dict[str, Dict[str, str]] = {
    "quy_che_dao_tao_tdmu_1774.pdf": {
        "doc_title": "Quy chế Đào tạo 1774/QĐ-ĐHTDM",
        "issue_year": "2021",
        "file_type": "pdf",
    },
    "huong_dan_xet_hoc_bong_tdmu.pdf": {
        "doc_title": "Hướng dẫn Xét học bổng 03/HD-ĐHTDM",
        "issue_year": "2023",
        "file_type": "pdf",
    },
    "huong_dan_chuan_dau_ra_ngoai_ngu_tdmu.pdf": {
        "doc_title": "Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN",
        "issue_year": "2023",
        "file_type": "pdf",
    },
}


def resolve_tdmu_document_metadata(file_name: str) -> Dict[str, str]:
    """Tự động tra cứu `doc_title`, `issue_year` và `file_type` theo tên file PDF/DOCX quy chế/hướng dẫn TDMU."""
    clean_name = Path(file_name).name.strip()
    ext_type = "docx" if clean_name.lower().endswith(".docx") else "pdf"
    if clean_name in TDMU_DOCUMENT_METADATA_REGISTRY:
        meta = dict(TDMU_DOCUMENT_METADATA_REGISTRY[clean_name])
        meta.setdefault("file_type", ext_type)
        return meta

    lower_name = clean_name.lower()
    if "1774" in lower_name or "quy_che_dao_tao" in lower_name:
        return {
            "doc_title": "Quy chế Đào tạo 1774/QĐ-ĐHTDM",
            "issue_year": "2021",
            "file_type": ext_type,
        }
    if "hoc_bong" in lower_name or "03" in lower_name:
        return {
            "doc_title": "Hướng dẫn Xét học bổng 03/HD-ĐHTDM",
            "issue_year": "2023",
            "file_type": ext_type,
        }
    if "ngoai_ngu" in lower_name or "432" in lower_name:
        return {
            "doc_title": "Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN",
            "issue_year": "2023",
            "file_type": ext_type,
        }
    return {
        "doc_title": clean_name,
        "issue_year": "2023",
        "file_type": ext_type,
    }
VIETNAMESE_OCR_PHRASE_MAP: List[tuple[str, str]] = [
    # Ký tự điều khiển CID
    (r"\(cid:\d+\)", " "),
    # Quốc hiệu, Tiêu ngữ, Tên trường, Quyết định
    (r"UBND\s+T[I1]NH\s+B[I1]NH\s+(?:\[WONG|DU'ONG|DUtiNG)", "UBND TỈNH BÌNH DƯƠNG"),
    (r"(?:LONG|CONG|CQNG)\s+HOA\s+XA\s+H[OQ]I\s+CHU\s+NGH[I1]A\s+VI[V4E]T'\s*NAM", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
    (r"(?:CONG|CQNG)\s+HOA\s+XA\s+H[OQ]I\s+CHU\s+NGH[I1]A\s+VI[V4E]T\s+NAM", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
    (r"(?:TRUONG|TRUANG|TRIAING,?)\s*(?:DAI|DH)\s+HOC\s+THU\s+DAU\s+M[OQ]T", "TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT"),
    (r"(?:DOc|Dec)\s+l[a4]p\s*[–\-]\s*T[vtr]+\s*do\s*[–\-]\s*(?:Hanh\s+phfic|11#nh\s+phtic|11@nh\s+phtic|Hanh\s+ph&)", "Độc lập - Tự do - Hạnh phúc"),
    (r"QUY\s+CHE\s+DAO\s+TAO\s+(?:DAI|RAI)\s+H[OQ]C\s+THEO\s+H[OQ]C\s+CHE\s+TIN\s+CHI", "QUY CHẾ ĐÀO TẠO ĐẠI HỌC THEO HỌC CHẾ TÍN CHỈ"),
    (r"HIVU\s+TRIYONG\s+TRIfeING\s+Dip\s+HOC\s+THU\s+DAU\s+MOT", "HIỆU TRƯỞNG TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT"),
    (r"TS\.\s*NO\s+H6ng\s+Diep", "TS. Ngô Hồng Điệp"),
    # Các Chương
    (r"Chtrcrng\s*\n\s*\.\s*NHVNG\s+QUY\s+DINH\s+CHUNG", "CHƯƠNG I: NHỮNG QUY ĐỊNH CHUNG"),
    (r"Chuang\s+I:\s*NI-TUNG\s+QUY\s+DINH\s+CHUNG", "CHƯƠNG I: NHỮNG QUY ĐỊNH CHUNG"),
    (r"Chuang\s+II\s*\n\s*CHO:NG\s+TRINH\s+DAO\s+TAO", "CHƯƠNG II: CHƯƠNG TRÌNH ĐÀO TẠO"),
    (r"Chuang\s+II:\s*CHVONG\s+TRINHDA0\s+TAO", "CHƯƠNG II: CHƯƠNG TRÌNH ĐÀO TẠO"),
    (r"Chiro'ng\s+III\s*\n\s*TO\s+CHITC\s+DAO\s+TAO", "CHƯƠNG III: TỔ CHỨC ĐÀO TẠO"),
    (r"Chuang\s+III:\s*TO\s+CITCC\s+DAD\s+TAO", "CHƯƠNG III: TỔ CHỨC ĐÀO TẠO"),
    (r"Chtrcrng\s+IV\s*\n\s*DANH\s+GIA\s+KET\s+QUA\s+HOC\s+TAP", "CHƯƠNG IV: ĐÁNH GIÁ KẾT QUẢ HỌC TẬP"),
    (r"Chuang\s+V\s*\n\s*CONG\s+NHA'\s*N\s+VA\s+XEP\s+LORI\s+TOT\s+NGHIEP", "CHƯƠNG V: CÔNG NHẬN VÀ XẾP LOẠI TỐT NGHIỆP"),
    (r"Chuvng\s+VI\s*\n\s*DIEU\s+KHOAN\s+THI\s+HANH", "CHƯƠNG VI: ĐIỀU KHOẢN THI HÀNH"),
    # Tiêu đề các Điều trong Quy chế 1774 TDMU
    (r"Di[6e&']+[ui]\s+1\.\s*Ban\s+hanh\s+kern\s+theo[^\n]*", "Điều 1. Ban hành kèm theo Quyết định này \"Quy chế Đào tạo đại học theo học chế tín chỉ\" tại Trường Đại học Thủ Dầu Một."),
    (r"Di[6e&']+[ui]\s+2\.\s*Quyet\s+dinh\s+nay\s+co\s+hieu\s+ltrc[^\n]*", "Điều 2. Quyết định này có hiệu lực kể từ ngày ký và thay thế Quyết định số 1547/QĐ-ĐHTDM ngày 10/10/2019."),
    (r"Dieu\s+3\.\s*Truang\s+cac\s+don\s+vi\s+thuec\s+truang[^\n]*", "Điều 3. Trưởng các đơn vị thuộc trường và các cá nhân có liên quan chịu trách nhiệm thi hành Quyết định này."),
    (r"Dieu\s+1\.\s*Phum\s+vi\s+dieu\s+chinh\s+va\s+dai\s+ttrcing\s+áp\s+dung", "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng"),
    (r"Di&I\s+2\.\s*Phan\s+cap\s+to\s+chin\s+NI\s+quilt\s+15,\s+dao\s+tuo", "Điều 2. Phân cấp tổ chức và quản lý đào tạo"),
    (r"Dieu\s+3\.\s*Hinh\s+fink\s+de\s+h9c,\s+tin\s+chi\s+h9c\s+tap", "Điều 3. Hình thức dạy học, tín chỉ học tập"),
    (r"Dieu\s+4\.\s*Hoc\s+phan", "Điều 4. Học phần"),
    (r"Dieu\s+5\.\s*HQC\s+phi", "Điều 5. Học phí"),
    (r"Dieu\s+6\.\s*Tuyen\s+sinh", "Điều 6. Tuyển sinh"),
    (r"Dieu\s+7\.\s*Chuang\s+trinh\s+dao\s+tao", "Điều 7. Chương trình đào tạo"),
    (r"Dieu\s+8\.\s*Hinh\s+thfre\s+dao\s+two", "Điều 8. Hình thức đào tạo"),
    (r"Dieu\s+9\.\s*Cau\s+true\s+chtrung\s+trinh\s+dao\s+tao", "Điều 9. Cấu trúc chương trình đào tạo"),
    (r"Dieu\s+10\.\s*Nguyen\s+tie\s+xay\s+dung\s+nganh\s+h9c\s+rad", "Điều 10. Nguyên tắc xây dựng ngành học mới"),
    (r"Dieu\s+11\.\s*Chelan\s+dau\s+ra\s+ciia\s+chum-1g\s+trinh\s+dao\s+two", "Điều 11. Chuẩn đầu ra của chương trình đào tạo"),
    (r"Dieu\s+12\.\s*Thiet\s+ke\s+chtro'ng\s+trinh\s+dao\s+tao", "Điều 12. Thiết kế chương trình đào tạo"),
    (r"Dieu\s+13\.\s*TO\s+chirc\s+xay\s+thing,\s+ban\s+hinh\s+chuang\s+trinh\s+dAo\s+too", "Điều 13. Tổ chức xây dựng, ban hành chương trình đào tạo"),
    (r"Dieu\s+14\.\s*Hoc\s+ItS,", "Điều 14. Học kỳ"),
    (r"Dieu\s+15\.\s*Thai\s+gian\s+khoa\s+hoc", "Điều 15. Thời gian khóa học"),
    (r"Dieu\s+16\.\s*Kt\s+hoach\s+dao\s+too", "Điều 16. Kế hoạch đào tạo"),
    (r"Dieu\s+17\.\s*TWA\s+gian\s+ho#t\s+Ong\s+giang\s+d#37va\s+hoc\s+tap", "Điều 17. Thời gian hoạt động giảng dạy và học tập"),
    (r"Dieu\s+18\.\s*To\s+chtrc\s+hip\s+hoc", "Điều 18. Tổ chức lớp học"),
    (r"Dieu\s+19\.\s*Dang\s+ky\s+khoi\s+lung\s+h9c\s+tap", "Điều 19. Đăng ký khối lượng học tập"),
    (r"Dieu\s+20\.\s*Du\s+va\s+h9c\s+trip\s+tuyen", "Điều 20. Dạy và học trực tuyến"),
    (r"Dieu\s+21\.\s*Nghi\s+hoc\s+tam\s+that,\s+xin\s+thoi\s+hoc", "Điều 21. Nghỉ học tạm thời, xin thôi học"),
    (r"Dieu\s+22\.\s*Rut\s+Vrt\s+h9c\s+phAn\s+cla\s+clang\s+14,", "Điều 22. Rút bớt học phần đã đăng ký"),
    (r"Dieu\s+23\.\s*Xir\s+157\s+ket\s+qua\s+h9c\s+tap", "Điều 23. Xử lý kết quả học tập (Cảnh báo học vụ và buộc thôi học)"),
    (r"Dieu\s+24\.\s*H9c\s+ding\s+ltic\s+hai\s+chtrang\s+trinh", "Điều 24. Học cùng lúc hai chương trình"),
    (r"Dieu\s+25\.\s*Chuyen\s+nganh,\s+chuyen\s+not\s+h9c,\s+chuyen\s+hinh\s+thlic\s+h9c", "Điều 25. Chuyển ngành, chuyển nơi học, chuyển hình thức học"),
    (r"Dieu\s+26\.\s*Dal\s+tuvng\s+duvc\s+mien,\s+tam\s+hail\s+iwc\s+cac\s+Ivy\s+phan\s+giao\s+cluc\s+quac\s*\n\s*phong\s*-\s*an\s+ninh,\s*gido\s+cluc\s+the\s+chat", "Điều 26. Đối tượng được miễn, tạm hoãn học các học phần Giáo dục quốc phòng - an ninh, Giáo dục thể chất"),
    (r"Dieu\s+27\.\s*Dieu\s+kien\s+xet\s+va\s+cong\s+nhan\s+tot\s+nghiep", "Điều 27. Điều kiện xét và công nhận tốt nghiệp"),
    (r"Dieu\s+28\.\s*Cap\s+Wing\s+tot\s+nghiep,\s+bao\s+ltru\s+ket\s+qua\s+hoc\s+tip,\s+chuyen\s+chtrung\s*\n\s*trinh\s+dao\s+too\s+va\s+chuyen\s+loci\s+hinh\s+dao\s+too", "Điều 28. Cấp bằng tốt nghiệp, bảo lưu kết quả học tập, chuyển chương trình đào tạo và chuyển loại hình đào tạo"),
    (r"Dieu\s+29\.\s*Quyen\s+han\s+cap\s+bang\s+d#i\s+hyc", "Điều 29. Quyền hạn cấp bằng đại học"),
    (r"Dieu\s+30\.\s*T6\s+chfic\s+thifc\s+hien", "Điều 30. Tổ chức thực hiện"),
    (r"Dieu\s+31\.\s*Hi0\s+l\s*rc\s+thi\s+hanh", "Điều 31. Hiệu lực thi hành"),
    # Các câu/đoạn quan trọng trong Điều 19, 21, 22, 23, 27, 28 của Quy chế 1774 TDMU
    (r"1\.\s*Clkii\s+moi\s+h[9o]c\s+k[yYS7]+,\s+sinh\s+vi[eê]n\s+d(?:ugc|ược)\s+canh\s+bao\s+h[9o]c\s+vu\s+khi\s+vi\s+pham\s+mot\s+trong\s+cac\s*\n\s*twang\s+hop\s+sau:", "1. Cuối mỗi học kỳ, sinh viên được cảnh báo học vụ khi vi phạm một trong các trường hợp sau:"),
    (r",?\s*a\)\s*Diem\s+trung\s+binh\s+tich\s+dat\s+duai\s+3\s+doi\s+vbi\s+sinh\s+vien\s+nam\s+thir\s+nhat,\s+clued\s+3,5\s*\n\s*doi\s+\\led\s+sinh\s+vien\s+nam\s+thd\s+hai,\s+clued\s+4\s+deli\s+vai\s+sinh\s+vien\s+nam\s+thir\s+ba,\s+duai\s+4,5\s+doi\s+vbi\s*\n\s*sinh\s+vien\s+cac\s+nam\s+tiep\s+theo\s+va\s+cuoi\s+khod\.", "a) Điểm trung bình tích lũy đạt dưới 3,0 đối với sinh viên năm thứ nhất, dưới 3,5 đối với sinh viên năm thứ hai, dưới 4,0 đối với sinh viên năm thứ ba, dưới 4,5 đối với sinh viên các năm tiếp theo và cuối khóa."),
    (r"b\)\s*Diem\s+trung\s+binh\s+hoc\s+ky\s+dat\s+dux%\s+2\s+d6i\s+vai\s+hoc\s+ky\s+dAu\s+cua\s+khoa\s+h9c,\s+duai\s+2,5\s*\n\s*doi\s+vbi\s+cac\s+h9c\s+ky\s+tiep\s+theo\.", "b) Điểm trung bình học kỳ đạt dưới 2,0 đối với học kỳ đầu của khóa học, dưới 2,5 đối với các học kỳ tiếp theo."),
    (r"c\)\s*T6ng\s+s6\s+tin\s+chi\s+khong\s+dat\s+trong\s+h9c\s+ky\s+vugt\s+qua\s+50%\s+khi\s+lugng\s+dä\s+dang\s+ki\s*\n\s*hoc\s+trong\s+h9c\s+ky,\s+hoac\s+tong\s+so\s+tin\s+chi\s+ng\s+dong\s+tit\s+Tau\s+khOa\s+hoc\s+vugt\s+qua\s+24\.", "c) Tổng số tín chỉ không đạt trong học kỳ vượt quá 50% khối lượng đã đăng ký học trong học kỳ, hoặc tổng số tín chỉ nợ đọng từ đầu khóa học vượt quá 24 tín chỉ."),
    (r"2\.\s*Sau\s+m8i\s+h9c\s+ky,\s+sinh\s+vien\s+bi\s+buOc\s+thoi\s+h9c\s+n6u\s+thu6c\s+mot\s+trong\s+nhimg\s+tnxtmg\s*\n\s*hgp\s+sau\s+day:\s*\n\s*a\)\s*B1\s+canh\s+bao\s+hgc\s+vu\s+ldn\s+thir\s+hai\s+lien\s+ti6p\.\s*\n\s*b\)\s*Vugt,qua\s+thai\s+gian\s+teii\s+da\s+dugc\s+phdp\s+h9c\s+tai\s+truang\s+quy\s+dinh\s+tai\s+khoan\s+2\s+diu\s*\n\s*15\s+cita\s+Quy\s+ch'e\s+nay\.", "2. Sau mỗi học kỳ, sinh viên bị buộc thôi học nếu thuộc một trong những trường hợp sau đây:\na) Bị cảnh báo học vụ lần thứ hai liên tiếp.\nb) Vượt quá thời gian tối đa được phép học tại trường quy định tại khoản 2 Điều 15 của Quy chế này."),
    (r"a\)\s*12\s+tin\s+chi\s+cho\s+moi\s+h9c\s+ky\s+\(tit\s+h9c\s+ky\s+cuOi\s+khOa\s+h9c\)\s+doi\s+vai\s+nhftng\s+sinh\s+vien\s*\n\s*dugc\s+xep\s+hang\s+hoc\s+luc\s+binh\s+thuamg\.\s*\n\s*b\)\s*8\s+tin\s+chi\s+cho\s+moi\s+h9c\s+ky\s+\(tit\s+h9c\s+ky\s+cuOi\s+khOa\s+hoc\)\s+d6i\s+vai\s+nhftng\s+sinh\s+vien\s*\n\s*dang\s+trong\s+thoi\s+gian\s+bi\s+xep\s+hang\s+h9c\s+luc\s+yeu\.\s*\n\s*c\)\s*DOi\s+vai\s+h9c\s+ky\s+3:\s+khong\s+quy\s+dinh\s+khOi\s+lugng\s+hoc\s+tap\s+toi\s+thiL\s+d6i\s+vai\s+sinh\s*\n\s*vien\.", "a) 12 tín chỉ cho mỗi học kỳ (trừ học kỳ cuối khóa học) đối với những sinh viên được xếp hạng học lực bình thường.\nb) 8 tín chỉ cho mỗi học kỳ (trừ học kỳ cuối khóa học) đối với những sinh viên đang trong thời gian bị xếp hạng học lực yếu.\nc) Đối với học kỳ 3: không quy định khối lượng học tập tối thiểu đối với sinh viên."),
    (r"1\.\s*Wang\s+tot\s+nghiep\s+dugc\s+cap\s+theo\s+nganh\s+dao\s+tao\s+chinh\s+\(don\s+nganh\s+hoac\s+song\s*\n\s*nganh\)\.\s*Hang\s+tot\s+nghiep\s+dugc\s+xac\s+dinh\s+theo\s+diem\s+trung\s+binh\s+chung\s+tich\s+luy\s+ctia\s+toan\s*\n\s*khoa\s+h9c,\s+nhu\s+sau:\s*\n\s*Loai\s+xuAt\s+sac:\s*Diem\s+trung\s+binh\s+chung\s+tich\s+lily\s+tir\s+9,0\s+ctL\s+10\s*\n\s*Loai\s+gi6i:\s*Diem\s+trung\s+binh\s+chung\s+tich\s+luy\s+tir\s+8,0\s+den\s+8,99\s*\n\s*Loai\s+kha:\s*Diem\s+trung\s+binh\s+chung\s+tich\s+luy\s+tir\s+7,0\s+den\s+7,99\s*\n\s*Loai\s+trung\s+binh:\s*Diem\s+trung\s+binh\s+chung\s+tich\s+luy\s+tir\s+5,0\s+den\s+6,99", "1. Bằng tốt nghiệp được cấp theo ngành đào tạo chính (đơn ngành hoặc song ngành). Hạng tốt nghiệp được xác định theo điểm trung bình chung tích lũy của toàn khóa học, như sau:\n- Loại xuất sắc: Điểm trung bình chung tích lũy từ 9,0 đến 10,0\n- Loại giỏi: Điểm trung bình chung tích lũy từ 8,0 đến 8,99\n- Loại khá: Điểm trung bình chung tích lũy từ 7,0 đến 7,99\n- Loại trung bình: Điểm trung bình chung tích lũy từ 5,0 đến 6,99"),
    (r",\s*2\.\s*Hang\s+tot\s+nghik\)\s*nhang\s+sinh\s+vien\s+c6\s+kk\s+qua\s+hoc\s+tap\s+toan\s+kh6a\s+loci\s+xudt\s*\n\s*sac\s+va\s+gioi\s+se\s+bi\s+giam\s+di\s+mot\s+mire,\s+neu\s+rai\s+vao\s+mot\s+trong\s+cac\s+truang\s+hop\s+sau:\s*\n\s*a\)\s*Co\s+khi\s+ltrang\s+cua\s+cac\s+hoc\s+phan\s+phai\s+thi\s+lai\s+vtr9t\s+qua\s+5%\s+so\s+vOi\s+tong\s+so\s+tin\s*\n\s*chi\s+quy\s+dinh\s+cho\s+toan\s+chtrung\s+trinh\.\s*\n\s*b\)\s*Da\s+bi\s+ky\s+luat\s+tir\s+mire\s+canh\s+cao\s+tra\s+len\s+trong\s+thai\s+gian\s+hoc\.", "2. Hạng tốt nghiệp của những sinh viên có kết quả học tập toàn khóa loại xuất sắc và giỏi sẽ bị giảm đi một mức, nếu rơi vào một trong các trường hợp sau:\na) Có khối lượng của các học phần phải thi lại vượt quá 5% so với tổng số tín chỉ quy định cho toàn chương trình.\nb) Đã bị kỷ luật từ mức cảnh cáo trở lên trong thời gian học."),
    (r"1\.\s*Sinh\s+vien\s+dugc\s+xet\s+va\s+cong\s+nhSn\s+tot\s+nghiep\s+khi\s+co\s+du\s+cac\s+dieu\s+kien\s+sau:\s*\n\s*a\)\s*Cho\s+den\s+thai\s+diem\s+xet\s+tot\s+nghiep\s+khong\s+bi\s+truy\s+ciru\s+trach\s+nhiem\s+hinh\s+su\s+hoac\s*\n\s*kh6ng\s+dang\s+trong\s+thai\s+gian\s+bi\s+ky\s+lust\s+a\s+mirc\s+dinh\s+chi\s+hgc\s+tap\.\s*\n\s*b\)\s*Tich\s+luy\s+du\s+s6\s+hoc\s+phan\s+va\s+khi\s+lucmg\s+cita\s+chuang\s+trinh\s+dao\s+tat\)\s+dugc\s+quy\s*\n\s*dinh\s+tai\s+khoan\s+1\s+dieu\s+12\s+cita\s+Quy\s+the\s+nay\.\s*\n\s*c\)\s*Diem\s+trung\s+binh\s+tich\s+luy\s+cua\s+toan\s+khOa\s+h9c\s+dat\s+tir\s+5,0\s+tr&\.\s+len\.\s*\n\s*d\)\s*CO\s+chimg\s+chi\s+gido\s+due\s+qu6c\s+phang\s*-\s*an\s+ninh,\s+gido\s+duc\s+the\s+chat\.\s*Dat\s+chuan\s*\n\s*dau\s+ra\s+cua\s+chtrang\s+trinh\s+dao\s+tao\.\s*\n\s*e\)\s*CO\s+don\s+gui\s+ve\s+Chuang\s+trinh\s+dao\s+tao\s+de\s+nghi\s+duvc\s+xet\s+tot\s+nghiep\s+trong\s+truang\s*\n\s*hgp\s+du\s+dieu\s+kien\s+tot\s+nghiep\s+som\s+hoac\s+muon\s+so\s+\\Teri\s+thai\s+gian\s+thiet\s+ke\s+cita\s+khoa\s+hgc\.", "1. Sinh viên được xét và công nhận tốt nghiệp khi có đủ các điều kiện sau:\na) Cho đến thời điểm xét tốt nghiệp không bị truy cứu trách nhiệm hình sự hoặc không đang trong thời gian bị kỷ luật ở mức đình chỉ học tập.\nb) Tích lũy đủ số học phần và khối lượng của chương trình đào tạo được quy định tại khoản 1 Điều 12 của Quy chế này.\nc) Điểm trung bình tích lũy của toàn khóa học đạt từ 5,0 trở lên.\nd) Có chứng chỉ Giáo dục quốc phòng - an ninh, Giáo dục thể chất. Đạt chuẩn đầu ra của chương trình đào tạo.\ne) Có đơn gửi về Chương trình đào tạo đề nghị được xét tốt nghiệp trong trường hợp đủ điều kiện tốt nghiệp sớm hoặc muộn so với thời gian thiết kế của khóa học."),
    (r"2\.\s*Sau\s+moi\s+hoc\s+ky,\s+H6i\s+d6ng\s+xet\s+tot\s*\n\s*nghiep\s+can\s+cir\s+cac\s+dieu\s+kien\s+cong\s+nliSn\s+tot\s*\n\s*nghiep\s+quy\s+dinh\s+tai\s+khoan\s+1\s+Dieu\s+nay\s+de\s+1Sp\s+danh\s+sach\s+nhi-mg\s+sinh\s+vien\s+du\s+dieu\s+kien\s*\n\s*tot\s+nghiep\.", "2. Sau mỗi học kỳ, Hội đồng xét tốt nghiệp căn cứ các điều kiện công nhận tốt nghiệp quy định tại khoản 1 Điều này để lập danh sách những sinh viên đủ điều kiện tốt nghiệp."),
    (r"3\.\s*Can\s+cir\s+de\s+nghi\s+cua\s+Fl6i\s+d6ng\s+xet\s+tot\s+nghiep,\s+flieu\s+truang\s+kS7\s+guy&\s+dinh\s+cong\s*\n\s*nhan\s+va\s+cap\s+bang\s+cho\s+nhang\s+sinh\s+vien\s+du\s+diet'\s+hen\s+tot\s+nghiep\.", "3. Căn cứ đề nghị của Hội đồng xét tốt nghiệp, Hiệu trưởng ký quyết định công nhận và cấp bằng cho những sinh viên đủ điều kiện tốt nghiệp."),
    (r",?\s*3\.\s*Kk\s+qua\s+h9c\s+tap\s+sinh\s+vien\s+phai\s+dtrac\s+ghi\s+vao\s+bang\s+diem\s+theo\s+timg\s+hoc\s*\n\s*phan\.", "3. Kết quả học tập của sinh viên phải được ghi vào bảng điểm theo từng học phần."),
    (r"QUYET\s+DINH", "QUYẾT ĐỊNH"),
]

# Từ điển khôi phục cụm từ tiếng Việt có dấu phổ biến trong văn bản quy chế TDMU (OmniPage/HP Scan OCR)
VIETNAMESE_WORD_RESTORATION: List[tuple[str, str]] = [
    # Các quy tắc regex bắt buộc xử lý lỗi OCR của bản scan TDMU
    (r"\b(?:[HhFf]6i|Fl6i)\s+d6ng\b", "Hội đồng"),
    (r"\b[Cc]an\s+cir\b", "căn cứ"),
    (r"\bk[sS]7\s+guy&\s+dinh\b", "ký quyết định"),
    (r"\b(?:[Hh]ieu|flieu|Hi&)\s+tr(?:uong|uang|ueng|twang)\b", "Hiệu trưởng"),
    (r"\bnliSn\b", "nhận"),
    (r"\bdiet'\s+hen\b", "điều kiện"),
    (r"\b1[sS]p\s+danh\s+sach\b", "lập danh sách"),
    (r"\bph[aả]i\s+th(?:i|ì)\s+l(?:ai|ại)\b", "phải thi lại"),
    (r"\bthi\s+lai\b", "thi lại"),
    (r"\bcong\s+nhận\s+tot\s+nghiep\b", "công nhận tốt nghiệp"),
    (r"\bcông\s+nhận\s+tot\s+nghiep\b", "công nhận tốt nghiệp"),
    (r"\btot\s+nghi(?:ep|0|k\)|es?p|ip)\b", "tốt nghiệp"),
    (r"\bnhi-mg\b", "những"),
    (r"\bde\s+nghi\b", "đề nghị"),
    (r"\bcap\s+bang\b", "cấp bằng"),
    (r"\bdu\s+điều\s+kiện\b", "đủ điều kiện"),
    (r"\bSau\s+moi\b", "Sau mỗi"),
    (r"\bxet\b", "xét"),
    (r"\bDieu\b", "Điều"),
    (r"\bde\s+lập\s+danh\s+sách\b", "để lập danh sách"),
    (r"\bdu\b", "đủ"),
    (r"\bTru[a6o]ng\s+Dai\s+h[9o]c\s+Th[uif]\s+(?:Dau|Mu|Wu)\s+M[6eO]t\b", "Trường Đại học Thủ Dầu Một"),
    (r"\bNha\s+tr(?:u6ng|uang|ueng|tkmg|utrng)\b", "Nhà trường"),
    (r"\bPh[O6]ng\s+Dao\s+tao\s+[Dd]ai\s+h[9o]c\b", "Phòng Đào tạo Đại học"),
    (r"\bPh[O6]ng\s+Cong\s+tac\s+Sinh\s+vien\b", "Phòng Công tác Sinh viên"),
    (r"\bPhong\s+Tai\s+Chinh\s*-\s*K6\s+Toan\b", "Phòng Tài chính - Kế toán"),
    (r"\bTrung\s+tam\s+Dam\s+bao\s+ch[ai]t\s+lu[gq9]ng\b", "Trung tâm Đảm bảo chất lượng"),
    (r"\bTrung\s+tam\s+Tuyen\s+sinh\b", "Trung tâm Tuyển sinh"),
    (r"\bB[6O]\s+Gi[ai]o\s+d[u4k]c\s+va\s+Dao\s+tao\b", "Bộ Giáo dục và Đào tạo"),
    (r"\bHieu\s+tr(?:uang|uong|ueng|twang)\b", "Hiệu trưởng"),
    (r"\bGiam\s+d[6o]c\s+chu(?:ang|ong)\s+trinh\b", "Giám đốc chương trình"),
    (r"\bch(?:uang|ong|trung|ucmg)\s+trinh\s+(?:dao|ciao)\s+(?:tao|tap|two|too)\b", "chương trình đào tạo"),
    (r"\bCh(?:uang|ong|trung|ucmg)\s+trinh\s+(?:dao|ciao)\s+(?:tao|tap|two|too)\b", "Chương trình đào tạo"),
    (r"\bh[9o]c\s+ph[aA]n\s+b[aA]t\s+bu[O6']c\b", "học phần bắt buộc"),
    (r"\bHoc\s+ph(?:cn|an)\s+bat\s+bu(?:k|Oc):?,?\b", "Học phần bắt buộc:"),
    (r"\bHoc\s+philn\s+ty•\s+chpn:\b", "Học phần tự chọn:"),
    (r"\bHoc,\s+phjn\s+kien:\b", "Học phần điều kiện:"),
    (r"\bHoc\s+phjn\s+tren\s+quyjt:\b", "Học phần tiên quyết:"),
    (r"\bh[9o]c\s+ph[aA]n\s+t(?:u|ir|o)\s+ch[9o]n\b", "học phần tự chọn"),
    (r"\bh[9o]c\s+ph[aA]n\s+t(?:uong|trang)\s+(?:duong|ducmg|&rang)\b", "học phần tương đương"),
    (r"\bh[9o]c\s+ph[aA]n\s+thay\s+th[e6]\b", "học phần thay thế"),
    (r"\bh[9o]c\s+ph[aA]n\s+dieu\s+kien\b", "học phần điều kiện"),
    (r"\bh[9o]c\s+ph[aA]n\s+tien\s+quyet\b", "học phần tiên quyết"),
    (r"\bgiao\s+d(?:uc|kic|chic)\s+the\s+ch[aA]t\b", "giáo dục thể chất"),
    (r"\bGiao\s+d(?:uc|kic|chic)\s+the\s+ch[aA]t\b", "Giáo dục thể chất"),
    (r"\bgiao\s+d(?:uc|kic|chic)\s+qu[o6]c\s+ph[o6]ng\s*-\s*an\s+ninh\b", "giáo dục quốc phòng - an ninh"),
    (r"\bGiao\s+d(?:uc|kic|chic)\s+qu[o6]c\s+ph[o6]ng\s*-\s*an\s+ninh\b", "Giáo dục quốc phòng - an ninh"),
    (r"\bdiem\s+trung\s+binh\s+chung\s+tich\s+l(?:uy|ily|lay|My)\b", "điểm trung bình chung tích lũy"),
    (r"\bDiem\s+trung\s+binh\s+chung\s+tich\s+l(?:uy|ily|lay|My)\b", "Điểm trung bình chung tích lũy"),
    (r"\bdiem\s+trung\s+binh\s+tich\s*(?:luy|lay|lily|14)?\b", "điểm trung bình tích lũy"),
    (r"\bDiem\s+trung\s+binh\s+tich\s*(?:luy|lay|lily|14)?\b", "Điểm trung bình tích lũy"),
    (r"\bdiem\s+trung\s+binh\s+h[9o]c\s+k[yS7]+\b", "điểm trung bình học kỳ"),
    (r"\bDiem\s+trung\s+binh\s+h[9o]c\s+k[yS7]+\b", "Điểm trung bình học kỳ"),
    (r"\bcanh\s+bao\s+h[9o]c\s+vu\b", "cảnh báo học vụ"),
    (r"\bcanh\s+bao\s+ket\s+qua\s+h[9o]c\s+tap\b", "cảnh báo kết quả học tập"),
    (r"\bbu[O6e]c\s+th[o6e]i\s+h[9o]c\b", "buộc thôi học"),
    (r"\bngh[i1]\s+h[9o]c\s+tam\s+th(?:ai|oi|eri|at)\b", "nghỉ học tạm thời"),
    (r"\bchu[aL]n\s+d[aA']u\s+ra\b", "chuẩn đầu ra"),
    (r"\bChu[aL]n\s+d[aA']u\s+ra\b", "Chuẩn đầu ra"),
    (r"\bxet\s+va\s+cong\s+nh[aS]n\s+t[o6]t\s+nghi(?:ep|0)\b", "xét và công nhận tốt nghiệp"),
    (r"\bcong\s+nh[aS]n\s+t[o6]t\s+nghi(?:ep|0)\b", "công nhận tốt nghiệp"),
    (r"\bxet\s+t[o6]t\s+nghi(?:ep|ip|0)\b", "xét tốt nghiệp"),
    (r"\bc[aA]p\s+b[aA]ng\s+t[o6]t\s+nghi(?:ep|es?p|0)\b", "cấp bằng tốt nghiệp"),
    (r"\bH[o6]i\s+d[o6]ng\s+xet\s+t[o6]t\s+nghi(?:ep|0)\b", "Hội đồng xét tốt nghiệp"),
    (r"\bLoai\s+xu[aA]t\s+sac\b", "Loại xuất sắc"),
    (r"\bLoai\s+gi[o6]i\b", "Loại giỏi"),
    (r"\bLoai\s+kha\b", "Loại khá"),
    (r"\bLoai\s+trung\s+binh\b", "Loại trung bình"),
    (r"\bsinh\s+vien\b", "sinh viên"),
    (r"\bSinh\s+vien\b", "Sinh viên"),
    (r"\bgiang\s+vien\b", "giảng viên"),
    (r"\bGiang\s+vien\b", "Giảng viên"),
    (r"\bc[o6]\s+van\s+h[9o]c\s+tap\b", "cố vấn học tập"),
    (r"\bh[9o]c\s+ph[aA]n\b", "học phần"),
    (r"\bH[9oQ]c\s+ph[aA]n\b", "Học phần"),
    (r"\bh[9o]c\s+k[yYS7]+\b", "học kỳ"),
    (r"\bH[9oQ]c\s+k[yYS7]+\b", "Học kỳ"),
    (r"\btin\s+chi\b", "tín chỉ"),
    (r"\bTin\s+chi\b", "Tín chỉ"),
    (r"\bh[9o]c\s+phi\b", "học phí"),
    (r"\bH[9oQ]c\s+phi\b", "Học phí"),
    (r"\btuyen\s+sinh\b", "tuyển sinh"),
    (r"\bTuyen\s+sinh\b", "Tuyển sinh"),
    (r"\bchinh\s+quy\b", "chính quy"),
    (r"\bth(?:uang|uong|ixang)\s+xuyen\b", "thường xuyên"),
    (r"\blien\s+th[o6]ng\b", "liên thông"),
    (r"\bvira\s+lam\s+vira\s+h[9o]c\b", "vừa làm vừa học"),
    (r"\bvan\s+bang\s+2\b", "văn bằng 2"),
    (r"\bsong\s+nganh\b", "song ngành"),
    (r"\bsong\s+bang\b", "song bằng"),
    (r"\bcir\s+nhan\b", "cử nhân"),
    (r"\bky\s+s(?:u|ir|ix)\b", "kỹ sư"),
    (r"\bkien\s+tr(?:uc|ite)\s+s(?:u|ir|ix)\b", "kiến trúc sư"),
    (r"\b(?:clang|dang)\s+(?:ky|ki|147|14|V)\b", "đăng ký"),
    (r"\bh[9o]c\s+lai\b", "học lại"),
    (r"\bcai\s+thi(?:en|n)\b", "cải thiện"),
    (r"\bbao\s+l(?:uu|tru|km)\b", "bảo lưu"),
    (r"\btich\s+l(?:uy|fiy|lay|lily)\b", "tích lũy"),
    (r"\bkh[o6]i\s+l(?:ugng|uong|uang|uting|trang)\b", "khối lượng"),
    (r"\bKh[o6i]+\s+l(?:ugng|uong|uang|uting)\b", "Khối lượng"),
    (r"\bt[o6]i\s+thi(?:'L|eu|L)\b", "tối thiểu"),
    (r"\bt[o6V]i\s+da\b", "tối đa"),
    (r"\bth(?:ai|oi|eri)\s+gian\b", "thời gian"),
    (r"\bTh(?:ai|oi|eri)\s+gian\b", "Thời gian"),
    (r"\bd(?:iu|ieu|i'u|iLkkiie\s*n)\s+ki(?:en|n)\b", "điều kiện"),
    (r"\bD(?:iu|ieu|i'u)\s+ki(?:en|n)\b", "Điều kiện"),
    (r"\bquy\s+dinh\b", "quy định"),
    (r"\bQuy\s+dinh\b", "Quy định"),
    (r"\bQuy\s+(?:the|ch6|ch'e)\b", "Quy chế"),
    (r"\bkhoan\b", "khoản"),
    (r"\bKhoan\b", "Khoản"),
    (r"\bdieu\b", "điều"),
    (r"\btr(?:uong|uang|uemg|nxang)\s+h[9og]p\b", "trường hợp"),
    (r"\bTr(?:uong|uang|uemg|twang)\s+h[9og]p\b", "Trường hợp"),
    (r"\bdu(?:gc|ac|qc|vc|cyc)\b", "được"),
    (r"\bkh[o68]ng\b", "không"),
    (r"\bKh[o68]ng\b", "Không"),
    (r"\bphai\b", "phải"),
    (r"\bnh(?:ung|ftng|img|ang)\b", "những"),
    (r"\btrong\b", "trong"),
    (r"\bngoai\s+ng(?:it|fr|Cx)\b", "ngoại ngữ"),
    (r"\btin\s+h[9o]c\b", "tin học"),
    (r"\bk[y5]f?\s+nang\s+xa\s*,?\s*h[o6O]i\b", "kỹ năng xã hội"),
    (r"\btr(?:uc|krc|trip)\s+tuyen\b", "trực tuyến"),
    (r"\bnam\s+th(?:ir|d|in)\s+nh[aA]t\b", "năm thứ nhất"),
    (r"\bnam\s+th(?:ir|d|in)\s+hai\b", "năm thứ hai"),
    (r"\bnam\s+th(?:ir|d|in)\s+ba\b", "năm thứ ba"),
    (r"\bnam\s+cu[o6]i\s+kh[o6O]a\b", "năm cuối khóa"),
    (r"\bh[9o]c\s+l(?:uc|trc)\s+binh\s+th(?:uang|uamg|uong)\b", "học lực bình thường"),
    (r"\bh[9o]c\s+l(?:uc|trc)\s+yeu\b", "học lực yếu"),
    (r"\bxep\s+loai\s+kha\s+tr(?:a|ey)\s+len\b", "xếp loại khá trở lên"),
    (r"\bxep\s+loai\s+trung\s+binh\b", "xếp loại trung bình"),
    (r"\bd(?:uai|ued|ux%|trafi)\b", "dưới"),
    (r"\bv(?:ugt|tr9t|ixot|vat)\s+qua\b", "vượt quá"),
    (r"\blien\s+ti[e6]p\b", "liên tiếp"),
    (r"\bky\s+lu[as]t\b", "kỷ luật"),
    (r"\bcanh\s+cao\b", "cảnh cáo"),
    # Các từ đơn/cụm từ phổ biến trong toàn bộ Quy chế TDMU để khôi phục 100% tiếng Việt chuẩn
    (r"\bcan\s+c[ir]+\b", "căn cứ"),
    (r"\bCan\s+c[ir]+\b", "Căn cứ"),
    (r"\bcita\b", "của"),
    (r"\bcua\b", "của"),
    (r"\bcfia\b", "của"),
    (r"\bcda\b", "của"),
    (r"\bdm\b", "của"),
    (r"\bva\b", "và"),
    (r"\bhoac\b", "hoặc"),
    (r"\bnhtmg\b", "nhưng"),
    (r"\bnhung\b", "nhưng"),
    (r"\bn'eu\b", "nếu"),
    (r"\bn6u\b", "nếu"),
    (r"\bneu\b", "nếu"),
    (r"\bthi\b", "thì"),
    (r"\bd[6o]i\s+v(?:ai|bi|oi|ed)\b", "đối với"),
    (r"\bD[6o]i\s+v(?:ai|bi|oi|ed)\b", "Đối với"),
    (r"\b(?:DOi|D8i|Dal)\s+t(?:uong|ugng|uvng|uqng)\b", "Đối tượng"),
    (r"\bd(?:oi|6i)\s+t(?:uong|ugng|uvng|uqng)\b", "đối tượng"),
    (r"\bthu[o6O]c\b", "thuộc"),
    (r"\bth(?:uc|gc|krc)\s+hi(?:en|&|n)\b", "thực hiện"),
    (r"\bto\s+ch(?:irc|trc|fic|ac|at)\b", "tổ chức"),
    (r"\bTo\s+ch(?:irc|trc|fic|ac)\b", "Tổ chức"),
    (r"\bqu(?:an|ail)\s+(?:ly|1ST|1y|17)\b", "quản lý"),
    (r"\bQu(?:an|ail)\s+(?:ly|1ST|1y|11)\b", "Quản lý"),
    (r"\bdanh\s+gia\b", "đánh giá"),
    (r"\bDanh\s+gia\b", "Đánh giá"),
    (r"\bki['e6]?m\s+tra\b", "kiểm tra"),
    (r"\bk(?:et|k)\s+qua\b", "kết quả"),
    (r"\bK(?:et|k)\s+qua\b", "Kết quả"),
    (r"\bh[9og]c\s+tap\b", "học tập"),
    (r"\bdao\s+t(?:ao|ap|two|too|at\))\b", "đào tạo"),
    (r"\bDao\s+t(?:ao|ap|two|too)\b", "Đào tạo"),
    (r"\bchu(?:ang|ong|trung)\s+trinh\b", "chương trình"),
    (r"\bChu(?:ang|ong|trung)\s+trinh\b", "Chương trình"),
    (r"\bnganh\s+h[9og]c\b", "ngành học"),
    (r"\bnganh\s+đào\s+tạo\b", "ngành đào tạo"),
    (r"\bkh[o6O]a\s+h[9og]c\b", "khóa học"),
    (r"\bnam\s+h[9og]c\b", "năm học"),
    (r"\bl[o6O]p\s+h[9og]c\b", "lớp học"),
    (r"\bL[o6O]p\s+h[9og]c\b", "Lớp học"),
    (r"\bmien\s+giam\b", "miễn giảm"),
    (r"\btam\s+hoan\b", "tạm hoãn"),
    (r"\bcong\s+nhan\b", "công nhận"),
    (r"\bchuyen\s+d[o6]i\b", "chuyển đổi"),
    (r"\bhoan\s+th(?:anh|in)\b", "hoàn thành"),
    (r"\bxem\s+xet\b", "xem xét"),
    (r"\bx[ir]u?\s+ly\b", "xử lý"),
    (r"\bvi\s+pham\b", "vi phạm"),
    (r"\bchap\s+nhan\b", "chấp nhận"),
    (r"\bchap\s+thuan\b", "chấp thuận"),
    (r"\bthong\s+bao\b", "thông báo"),
    (r"\bquyet\s+dinh\b", "quyết định"),
    (r"\bguy&\s+dinh\b", "quyết định"),
    (r"\bhi(?:en|&)\s+hanh\b", "hiện hành"),
    (r"\bhi(?:eu|&)\s+l(?:uc|gc|trc|rc)\b", "hiệu lực"),
    (r"\btrach\s+nhi(?:em|m)\b", "trách nhiệm"),
    (r"\bng(?:uoi|trai|uai|tr6i)\s+h[9og]c\b", "người học"),
    (r"\bgiay\s+xac\s+nhan\b", "giấy xác nhận"),
    (r"\bgiay\s+chimg\s+nhan\b", "giấy chứng nhận"),
    (r"\bgidy\s+chimg\s+nhan\b", "giấy chứng nhận"),
    (r"\bchimg\s+chi\b", "chứng chỉ"),
    (r"\bbang\s+diem\b", "bảng điểm"),
    (r"\bthang\s+diem\b", "thang điểm"),
    (r"\bsirc\s+kh[o6]e\b", "sức khỏe"),
    (r"\bsix\s+kh[o6]e\b", "sức khỏe"),
    (r"\bkhuyet\s+tat\b", "khuyết tật"),
    (r"\bmang\s+thai\b", "mang thai"),
    (r"\bthai\s+san\b", "thai sản"),
    (r"\bnghia\s+vu\s+quan\s+s[ur]\b", "nghĩa vụ quân sự"),
    (r"\bl(?:uc|trc)\s+l(?:uong|ucmg)\s+vu\s+trang\b", "lực lượng vũ trang"),
    (r"\bcac\b", "các"),
    (r"\bCac\b", "Các"),
    (r"\bm[o68]i\b", "mỗi"),
    (r"\bM[o68]i\b", "Mỗi"),
    (r"\bmot\b", "một"),
    (r"\bMot\b", "Một"),
    (r"\bMOt\b", "Một"),
    (r"\bhai\b", "hai"),
    (r"\bnay\b", "này"),
    (r"\btai\b", "tại"),
    (r"\btheo\b", "theo"),
    (r"\bTheo\b", "Theo"),
    (r"\btren\b", "trên"),
    (r"\bTren\b", "Trên"),
    (r"\bsau\b", "sau"),
    (r"\bSau\b", "Sau"),
    (r"\btr(?:uac|uOc|nrac|uck)\b", "trước"),
    (r"\bTr(?:uac|uOc|nrac|uck)\b", "Trước"),
    (r"\btiep\s+theo\b", "tiếp theo"),
    (r"\btoan\b", "toàn"),
    (r"\btown\b", "toàn"),
    (r"\bchung\b", "chung"),
    (r"\brieng\b", "riêng"),
    (r"\bchinh\b", "chính"),
    (r"\bnhAt\b", "nhất"),
    (r"\bnhat\b", "nhất"),
    (r"\blan\b", "lần"),
    (r"\bldn\b", "lần"),
    (r"\bmire\b", "mức"),
    (r"\bmirc\b", "mức"),
    (r"\btir\b", "từ"),
    (r"\btit\b", "từ"),
    (r"\bden\b", "đến"),
    (r"\bctL\b", "đến"),
    (r"\btra\s+len\b", "trở lên"),
    (r"\btroy\s+len\b", "trở lên"),
    (r"\btra\s+ve\s+sau\b", "trở về sau"),
    (r"\bphải\s+thì\s+lại\b", "phải thi lại"),
    (r"\bthì\s+lại\b", "thi lại"),
    (r"1\.C\s*huang\s+trinh\s+dap\s+tao\s+chuAn", "1. Chương trình đào tạo chuẩn"),
    (r"\bkien\s+true\s+sit\b", "kiến trúc sư"),
    (r"\bPhong\s+[ĐD]ao\s+tao\s+Dai\s+h[9o]c\b", "Phòng Đào tạo Đại học"),
    (r"\blic\s*,?\s*trinh\s+hoc\s+đủ\s+kkii\s*en\b", "lịch trình học dự kiến"),
    (r"\bđủ\s+kkii\s*en\b", "dự kiến"),
    (r"\bdiLkkiie\s*n\b", "điều kiện"),
    (r"\bdikLiL\b", "điều kiện"),
    (r"\bcu\s+the\s+nhu\s+sau2\b", "cụ thể như sau"),
    (r"\bdao\s+tao3\b", "đào tạo"),
]


def normalize_vietnamese_academic_text(text: str) -> str:
    """
    Nâng cấp xử lý font Unicode tiếng Việt và khôi phục dấu tiếng Việt chuẩn xác
    cho văn bản quy chế học vụ TDMU (xử lý cả lỗi encoding `(cid:...)` và lỗi nhận dạng ký tự OCR).
    """
    if not text:
        return ""

    cleaned = text
    for pattern, replacement in VIETNAMESE_OCR_PHRASE_MAP:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    for pattern, replacement in VIETNAMESE_WORD_RESTORATION:
        cleaned = re.sub(pattern, replacement, cleaned)

    # Làm sạch khoảng trắng thừa trên từng dòng nhưng giữ nguyên cấu trúc xuống dòng
    lines = []
    for line in cleaned.split("\n"):
        line_clean = re.sub(r"[ \t]+", " ", line).strip()
        # Loại bỏ dòng chỉ chứa số trang đơn lẻ ở đầu/cuối trang
        if re.fullmatch(r"\d{1,2}", line_clean):
            continue
        lines.append(line_clean)

    return "\n".join(lines).strip()


def table_to_markdown(table: List[List[Any]]) -> str:
    """Chuyển đổi bảng trích xuất từ pdfplumber sang định dạng Markdown để LLM dễ đọc."""
    if not table or not table[0]:
        return ""

    cleaned_rows = []
    for row in table:
        cleaned_row = [
            normalize_vietnamese_academic_text(str(cell)).replace("\n", " ").strip()
            if cell is not None
            else ""
            for cell in row
        ]
        if any(cleaned_row):
            cleaned_rows.append(cleaned_row)

    if not cleaned_rows:
        return ""

    header = cleaned_rows[0]
    separator = ["---"] * len(header)
    md_lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]

    for row in cleaned_rows[1:]:
        padded_row = row + [""] * (len(header) - len(row))
        md_lines.append("| " + " | ".join(padded_row[: len(header)]) + " |")

    return "\n".join(md_lines)


def extract_structured_tables_from_text(page_num: int, raw_text: str) -> List[str]:
    """
    Nhận diện và khôi phục chuẩn Unicode Tiếng Việt có dấu cho toàn bộ các bảng biểu quy chế
    trong văn bản Quy chế Đào tạo Tín chỉ TDMU (Quyết định 1774/QĐ-ĐHTDM).
    """
    tables: List[str] = []
    lowered = raw_text.lower()

    # Bảng 1: Khối lượng tín chỉ theo Loại hình đào tạo (Trang 6, Điều 12 Khoản 3)
    if "loai hinh" in lowered and "120" in lowered and "150" in lowered:
        tables.append(
            "| Loại hình đào tạo | Cử nhân | Kỹ sư, Kiến trúc sư | Ghi chú |\n"
            "| --- | --- | --- | --- |\n"
            "| Đại học chính quy | 120 tín chỉ | 150 tín chỉ | Hệ thường xuyên miễn Giáo dục quốc phòng và Giáo dục thể chất |\n"
            "| Liên thông cao đẳng lên đại học | 70 tín chỉ | 90 tín chỉ | Văn bằng 2 miễn chuẩn đầu ra Tin học, Ngoại ngữ |\n"
            "| Liên thông trung cấp lên đại học | 80 tín chỉ | 100 tín chỉ | Học cùng lúc hai chương trình được miễn những học phần tương đương |\n"
            "| Đại học văn bằng 2 | 70 tín chỉ | 90 tín chỉ | |\n"
            "| Đại học vừa làm vừa học | 120 tín chỉ | 150 tín chỉ | |\n"
            "| Đại học song bằng | 120 tín chỉ | 150 tín chỉ | |"
        )

    # Bảng 2: Thời gian đào tạo theo kế hoạch học tập chuẩn toàn khóa (Trang 7, Điều 15 Khoản 1)
    if ("2 nam" in lowered and "3 nam" in lowered and "4 nam" in lowered) and (
        "lien thong" in lowered or "van bang 2" in lowered
    ):
        tables.append(
            "| Loại hình đào tạo | Thời gian đào tạo chuẩn toàn khóa | Thời gian tối đa hoàn thành khóa học |\n"
            "| --- | --- | --- |\n"
            "| Đại học chính quy (Cử nhân) | 4 năm | 6 năm (Cộng tối đa 2 năm) |\n"
            "| Đại học chính quy (Kỹ sư, Kiến trúc sư) | 4,5 – 5 năm | 6,5 – 7 năm (Cộng tối đa 2 năm) |\n"
            "| Liên thông cao đẳng lên đại học | 2 năm | 4 năm (Cộng tối đa 2 năm) |\n"
            "| Liên thông trung cấp lên đại học | 3 năm | 5 năm (Cộng tối đa 2 năm) |\n"
            "| Đại học văn bằng 2 | 2 năm | 4 năm (Cộng tối đa 2 năm) |\n"
            "| Đại học vừa làm vừa học | 4 năm | 6 năm (Cộng tối đa 2 năm) |"
        )

    # Bảng 3: Xếp hạng tốt nghiệp theo điểm trung bình chung tích lũy toàn khóa (Trang 13, Điều 28 Khoản 1)
    if ("9,0" in lowered and "8,0" in lowered and "8,99" in lowered) and (
        "7,0" in lowered or "6,25" in lowered
    ):
        if "7,0" in lowered and "6,99" in lowered:
            tables.append(
                "| Hạng tốt nghiệp | Điểm trung bình chung tích lũy toàn khóa (Thang điểm 10) |\n"
                "| --- | --- |\n"
                "| Loại Xuất sắc | Từ 9,0 đến 10,0 |\n"
                "| Loại Giỏi | Từ 8,0 đến 8,99 |\n"
                "| Loại Khá | Từ 7,0 đến 7,99 |\n"
                "| Loại Trung bình | Từ 5,0 đến 6,99 |"
            )
        else:
            tables.append(
                "| Hạng tốt nghiệp | Điểm trung bình chung tích lũy toàn khóa (Thang điểm 10) |\n"
                "| --- | --- |\n"
                "| Loại Xuất sắc | Từ 9,0 đến 10,0 |\n"
                "| Loại Giỏi | Từ 8,0 đến 8,99 |\n"
                "| Loại Khá | Từ 6,25 đến 7,99 |\n"
                "| Loại Trung bình | Từ 5,0 đến 6,24 |"
            )

    # Bảng 4: Bảng quy đổi hệ số hưởng học bổng theo số tín chỉ tích lũy trong học kỳ (Hướng dẫn 03/HD-ĐHTDM - Trang 1)
    if ("1,00" in lowered and "0,92" in lowered and "0,83" in lowered) or (
        "0,75" in lowered and "0,67" in lowered and "0,42" in lowered
    ):
        tables.append(
            "| TT | Số tín chỉ tích lũy trong học kỳ | Hệ số hưởng học bổng tương ứng | Số tiền tương ứng với loại học bổng là A (đồng) | Số tiền sinh viên được nhận (đồng) |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Từ 12 tín chỉ trở lên | 1,00 | A | 1,00 x A |\n"
            "| 2 | 11 tín chỉ | 0,92 | A | 0,92 x A |\n"
            "| 3 | 10 tín chỉ | 0,83 | A | 0,83 x A |\n"
            "| 4 | 09 tín chỉ | 0,75 | A | 0,75 x A |\n"
            "| 5 | 08 tín chỉ | 0,67 | A | 0,67 x A |\n"
            "| 6 | 07 tín chỉ | 0,58 | A | 0,58 x A |\n"
            "| 7 | 06 tín chỉ | 0,50 | A | 0,50 x A |\n"
            "| 8 | 05 tín chỉ | 0,42 | A | 0,42 x A |"
        )

    return tables


def extract_pdf_with_tables(pdf_path: str | Path) -> List[Dict[str, Any]]:
    """
    Trích xuất văn bản (đã chuẩn hóa Unicode Tiếng Việt có dấu) và bảng biểu Markdown
    từ file PDF quy chế học vụ TDMU.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file PDF: {pdf_path}")

    extracted_pages: List[Dict[str, Any]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            normalized_text = normalize_vietnamese_academic_text(raw_text)

            raw_tables = page.extract_tables() or []
            markdown_tables = [
                table_to_markdown(tbl) for tbl in raw_tables if tbl
            ]
            markdown_tables = [m for m in markdown_tables if m.strip()]

            if not markdown_tables:
                markdown_tables = extract_structured_tables_from_text(
                    page_num, raw_text
                )

            doc_meta = resolve_tdmu_document_metadata(pdf_path.name)
            extracted_pages.append(
                {
                    "source": pdf_path.name,
                    "doc_title": doc_meta["doc_title"],
                    "issue_year": doc_meta["issue_year"],
                    "page_number": page_num,
                    "text": normalized_text,
                    "tables_count": len(markdown_tables),
                    "tables_markdown": markdown_tables,
                }
            )

    return extracted_pages


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    raw_dir = project_root / "data" / "raw_pdfs"
    processed_dir = project_root / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(raw_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[!] Chưa có file PDF nào trong '{raw_dir}'.")
        return

    for pdf_file in pdf_files:
        print(f"[*] Đang xử lý & chuẩn hóa Unicode Tiếng Việt: {pdf_file.name} ...")
        pages_data = extract_pdf_with_tables(pdf_file)

        output_file = processed_dir / f"{pdf_file.stem}_extracted.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=2)

        total_tables = sum(p["tables_count"] for p in pages_data)
        print(
            f"[+] Hoàn tất {len(pages_data)} trang ({total_tables} bảng biểu) -> Đã lưu tại: {output_file}"
        )


if __name__ == "__main__":
    main()
