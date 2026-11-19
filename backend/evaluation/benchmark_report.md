# BÁO CÁO ĐÁNH GIÁ ĐỊNH LƯỢNG HỆ THỐNG RAG HỌC VỤ TDMU (BENCHMARK REPORT)

## 1. Thông tin Môi trường & Kho Tri thức Thực nghiệm
- **Đề tài Đồ án Tốt nghiệp:** Xây dựng Trợ lý Trí tuệ Nhân tạo Hỗ trợ Thông tin Học vụ Trường Đại học Thủ Dầu Một (TDMU) ứng dụng kiến trúc Advanced RAG
- **Sinh viên thực hiện:** Lê Quốc Bảo (MSSV: `2224801030361` — Lớp: `D22KTPM01`)
- **Giảng viên hướng dẫn:** ThS. Lê Từ Minh Trí
- **Thời điểm chạy thực nghiệm:** `2026-11-18 16:41:05`
- **Kiến trúc truy xuất:** Hierarchical Legal Chunking + Multi-Query Expansion + Hybrid Search (Dense Vector + BM25 Sparse) + Cross-Scoring Re-ranking + Strict Citation & Out-of-Domain Guardrail
- **Tổng số phân mảnh (Chunks) trong Qdrant Vector Store:** **`113 chunks`** (100% văn bản chính thức thật của TDMU)

### Bảng 1.1: Phân bổ dữ liệu trong Kho tri thức Qdrant Vector Store
| STT | Tên file văn bản gốc | Tên văn bản pháp quy TDMU | Năm ban hành | Số lượng Chunks |
| :---: | :--- | :--- | :---: | :---: |
| 1 | `quy_che_dao_tao_tdmu_1774.pdf` | Quy chế Đào tạo đại học theo học chế tín chỉ (1774/QĐ-ĐHTDM) | 2021 | **95** |
| 2 | `huong_dan_xet_hoc_bong_tdmu.pdf` | Hướng dẫn quy đổi số tín chỉ tích lũy xét học bổng (03/HD-ĐHTDM) | 2023 | **6** |
| 3 | `huong_dan_chuan_dau_ra_ngoai_ngu_tdmu.pdf` | Hướng dẫn thực hiện chuẩn đầu ra ngoại ngữ (432/ĐHTDM-TTNN) | 2023 | **12** |
| **Tổng** | **3 văn bản chính thức** | **Kho tri thức Pháp quy Học vụ TDMU** | **2021 – 2023** | **113** |

---

## 2. Tổng hợp Chỉ số Đánh giá Thực nghiệm (Overall Quantitative Metrics)

| Chỉ số Đánh giá (Evaluation Metric) | Kết quả Thực nghiệm | Số lượng đạt / Tổng | Mô tả Ý nghĩa Thực nghiệm |
| :--- | :---: | :---: | :--- |
| **Retrieval Hit Rate @ Top-5** | **100.00%** | `15 / 15` | Tỷ lệ truy xuất trúng đúng văn bản (`doc_title`) và đúng Điều/Mục mục tiêu trong Top-5 chunks sau Re-ranking |
| **Context Precision @ Top-5** | **84.33%** | `15 / 15` | Độ tinh khiết ngữ cảnh: tỷ lệ chunks trong Top-5 thuộc đúng Điều/Mục pháp quy liên quan trực tiếp |
| **Answer Faithfulness (Độ trung thực)** | **100.00%** | `15 / 15` | Tỷ lệ câu trả lời bám sát văn bản gốc, chứa đúng các mốc định lượng (`100.00%` keyword grounding) và đính kèm trích dẫn hợp lệ |
| **Out-of-Domain Refusal Accuracy** | **100.00%** | `5 / 5` | Tỷ lệ từ chối an toàn tuyệt đối (không ảo giác, `citations = []`) đối với câu hỏi bẫy ngoài phạm vi dữ liệu |
| **Overall Benchmark Accuracy** | **100.00%** | `20 / 20` | Tỷ lệ vượt qua kiểm thử toàn diện trên toàn bộ 20 kịch bản (4 nhóm câu hỏi) |
| **Average Latency (Tổng thể)** | **110.96 ms** | `20 truy vấn` | Thời gian phản hồi trung bình mỗi truy vấn (In-domain: `147.94 ms`, Out-of-domain Gate: `0.03 ms`) |

---

## 3. Thống kê Kết quả theo Từng Nhóm Kịch bản (4 Nhóm Kiểm thử)

| Nhóm Kịch bản Kiểm thử | Số câu hỏi | Số câu Đạt (Pass) | Tỷ lệ Chính xác | Độ trễ Trung bình (ms) |
| :--- | :---: | :---: | :---: | :---: |
| **Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)** | 6 | 6/6 | **100.00%** | `122.11 ms` |
| **Nhóm 2: Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023)** | 4 | 4/4 | **100.00%** | `136.20 ms` |
| **Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)** | 5 | 5/5 | **100.00%** | `188.33 ms` |
| **Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)** | 5 | 5/5 | **100.00%** | `0.03 ms` |

---

## 4. Bảng Kết quả Thực nghiệm Chi tiết Từng Câu hỏi (20 Test Cases)

| Mã | Nhóm văn bản | Câu hỏi kiểm thử | Văn bản & Điều/Mục mục tiêu | Văn bản & Điều/Mục truy xuất thực tế (Top Citations) | Hit@5 | Context Precision | Faithfulness | Số trích dẫn | Độ trễ (ms) | Kết quả |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q01** | Nhóm 1 | Sinh viên Trường Đại học Thủ Dầu Một cần đáp ứng đầy đủ những điều kiện gì để được xét và công nhận tốt nghiệp đại học? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 27) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 27. Điều kiện xét và công nhận tốt nghiệp [Tr.13] | ✅ Đạt | 100% | 100% | 3 | `146.43` | **PASS** |
| **Q02** | Nhóm 1 | Trong trường hợp nào sinh viên đạt điểm trung bình tích lũy loại Xuất sắc hoặc Giỏi bị giảm đi một mức (hạ bậc) khi xếp hạng tốt nghiệp? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 28) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 28. Cấp bằng tốt nghiệp, bảo lưu kết quả học tập, chuyển chương trình đào tạo và chuyển loại hình đào tạo [Tr.13]<br>Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 28. Cấp bằng tốt nghiệp, bảo lưu kết quả học tập, chuyển chương trình đào tạo và chuyển loại hình đào tạo [Tr.14] | ✅ Đạt | 100% | 100% | 4 | `158.17` | **PASS** |
| **Q03** | Nhóm 1 | Khi nào sinh viên TDMU bị cảnh báo kết quả học tập (cảnh báo học vụ) hoặc bị buộc thôi học? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 23) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 23. Xử lý kết quả học tập (Cảnh báo học vụ và buộc thôi học) [Tr.10]<br>Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 23. Xử lý kết quả học tập (Cảnh báo học vụ và buộc thôi học) [Tr.11] | ✅ Đạt | 100% | 100% | 2 | `107.59` | **PASS** |
| **Q04** | Nhóm 1 | Sinh viên đang học muốn xin nghỉ học tạm thời (bảo lưu kết quả học tập) vì lý do cá nhân thì cần điều kiện gì và thời hạn nộp đơn như thế nào? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 21) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 21. Nghỉ học tạm thời, xin thôi học [Tr.9]<br>Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 21. Nghỉ học tạm thời, xin thôi học [Tr.10] | ✅ Đạt | 100% | 100% | 4 | `131.97` | **PASS** |
| **Q05** | Nhóm 1 | Quy định về việc rút bớt học phần đã đăng ký, thời hạn hoàn trả học phí và nhận điểm RT tại TDMU được thực hiện ra sao? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 22) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 22. Rút bớt học phần đã đăng ký [Tr.10] | ✅ Đạt | 100% | 100% | 2 | `94.30` | **PASS** |
| **Q06** | Nhóm 1 | Thời gian đào tạo theo kế hoạch học tập chuẩn toàn khóa và thời gian tối đa được phép hoàn thành khóa học đối với bậc Cử nhân, Kỹ sư là bao nhiêu năm? | Quy chế Đào tạo 1774/QĐ-ĐHTDM (Điều 15) | Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021) - Điều 15. Thời gian khóa học [Tr.7] | ✅ Đạt | 100% | 100% | 2 | `94.21` | **PASS** |
| **Q07** | Nhóm 2 | Theo Hướng dẫn 03/HD-ĐHTDM và Quyết định 56/QĐ-HĐTr, số tín chỉ tích lũy tối thiểu trong học kỳ để được hưởng 100% mức học bổng khuyến khích học tập (hệ số 1,00) là bao nhiêu tín chỉ? | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Mục 1, Mục 2) | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ số hưởng học bổng khuyến khích học tập [Tr.1]<br>Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 2. Ví dụ minh họa cách tính hệ số hưởng học bổng khuyến khích học tập [Tr.1] | ✅ Đạt | 100% | 100% | 4 | `124.17` | **PASS** |
| **Q08** | Nhóm 2 | Nếu trong học kỳ sinh viên tích lũy được 11 tín chỉ hoặc 10 tín chỉ thì hệ số hưởng học bổng khuyến khích học tập tương ứng là bao nhiêu? | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Mục 1, Mục 2) | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ số hưởng học bổng khuyến khích học tập [Tr.1]<br>Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 2. Ví dụ minh họa cách tính hệ số hưởng học bổng khuyến khích học tập [Tr.1] | ✅ Đạt | 100% | 100% | 4 | `114.57` | **PASS** |
| **Q09** | Nhóm 2 | Sinh viên tích lũy được 09 tín chỉ hoặc 08 tín chỉ trong học kỳ xét học bổng thì được quy đổi hệ số hưởng học bổng là bao nhiêu? | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Mục 1, Mục 2) | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ số hưởng học bổng khuyến khích học tập [Tr.1]<br>Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 2. Ví dụ minh họa cách tính hệ số hưởng học bổng khuyến khích học tập [Tr.1]<br>Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 3. Hiệu lực áp dụng và tổ chức thực hiện xét học bổng [Tr.2] | ✅ Đạt | 75% | 100% | 4 | `166.25` | **PASS** |
| **Q10** | Nhóm 2 | Sinh viên năm cuối học kỳ cuối chỉ còn 05 tín chỉ tích lũy theo chương trình đào tạo và đủ điều kiện học bổng thì nhận hệ số hưởng học bổng là bao nhiêu? | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Mục 1, Mục 2) | Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ số hưởng học bổng khuyến khích học tập [Tr.1]<br>Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023) - Mục 2. Ví dụ minh họa cách tính hệ số hưởng học bổng khuyến khích học tập [Tr.1] | ✅ Đạt | 100% | 100% | 4 | `139.80` | **PASS** |
| **Q11** | Nhóm 3 | Theo Công văn 432/ĐHTDM-TTNN, sinh viên TDMU có thể lựa chọn những hình thức nào để hoàn thành chuẩn đầu ra ngoại ngữ và quy định khác nhau giữa khóa 2020 trở về trước với khóa 2021 trở về sau là gì? | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Mục 1, Mục 2, Mục 3) | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.2] | ✅ Đạt | 100% | 100% | 5 | `176.19` | **PASS** |
| **Q12** | Nhóm 3 | Điểm chuẩn đạt chứng chỉ năng lực ngoại ngữ nội bộ EPT-TDMU, FPT-TDMU, CPT-TDMU đối với hệ chính quy và hệ thường xuyên là bao nhiêu điểm? | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Mục 3) | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.2] | ✅ Đạt | 40% | 100% | 5 | `195.15` | **PASS** |
| **Q13** | Nhóm 3 | Đối với sinh viên hệ chính quy khóa 2017 đến 2022 đã hoàn thành NNKC cấp độ 3 hoặc cấp độ 4 trở lên khi chuyển sang thi chứng chỉ EPT/FPT/CPT thì quy định học ôn tập tại Trung tâm Ngoại ngữ như thế nào? | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Mục 2) | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.2]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 3. Thống nhất cách hiểu và thang điểm chuẩn đầu ra ngoại ngữ (IELTS, TOEIC, EPT/FPT/CPT) [Tr.3] | ✅ Đạt | 60% | 100% | 5 | `206.46` | **PASS** |
| **Q14** | Nhóm 3 | Quy định về chứng chỉ quốc tế IELTS (đơn vị cấp hợp lệ, loại hình Academic/General) và mức điểm chuẩn TOEIC 4 kỹ năng tại TDMU như thế nào? | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Mục 3) | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầu ra ngoại ngữ [Tr.2] | ✅ Đạt | 40% | 100% | 5 | `165.21` | **PASS** |
| **Q15** | Nhóm 3 | Trường hợp nào sinh viên được miễn chuẩn đầu ra ngoại ngữ tại Trường Đại học Thủ Dầu Một theo Công văn 432/ĐHTDM-TTNN và Điều 12 Quy chế 1774? | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Mục 3, Điều 12) | Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ [Tr.1]<br>Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023) - Mục 3. Thống nhất cách hiểu và thang điểm chuẩn đầu ra ngoại ngữ (IELTS, TOEIC, EPT/FPT/CPT) [Tr.3] | ✅ Đạt | 50% | 100% | 2 | `198.63` | **PASS** |
| **Q16** | Nhóm 4 | Học phí một tín chỉ ngành Kỹ thuật phần mềm năm nay ở TDMU là bao nhiêu tiền? | Từ chối trả lời (Out-of-Domain) (Không trích dẫn (citations = [])) | `citations = []` (Từ chối an toàn) | ✅ Đạt | 100% | 100% | 0 | `0.03` | **PASS** |
| **Q17** | Nhóm 4 | Trường Đại học Thủ Dầu Một nằm ở đâu và có địa chỉ cụ thể ở đường nào? | Từ chối trả lời (Out-of-Domain) (Không trích dẫn (citations = [])) | `citations = []` (Từ chối an toàn) | ✅ Đạt | 100% | 100% | 0 | `0.02` | **PASS** |
| **Q18** | Nhóm 4 | Hiệu trưởng trường là ai? | Từ chối trả lời (Out-of-Domain) (Không trích dẫn (citations = [])) | `citations = []` (Từ chối an toàn) | ✅ Đạt | 100% | 100% | 0 | `0.04` | **PASS** |
| **Q19** | Nhóm 4 | Lịch nghỉ lễ Tết Nguyên đán năm nay của sinh viên TDMU bắt đầu từ ngày nào? | Từ chối trả lời (Out-of-Domain) (Không trích dẫn (citations = [])) | `citations = []` (Từ chối an toàn) | ✅ Đạt | 100% | 100% | 0 | `0.02` | **PASS** |
| **Q20** | Nhóm 4 | Căn tin và bãi giữ xe của Trường Đại học Thủ Dầu Một nằm ở tòa nhà nào? | Từ chối trả lời (Out-of-Domain) (Không trích dẫn (citations = [])) | `citations = []` (Từ chối an toàn) | ✅ Đạt | 100% | 100% | 0 | `0.02` | **PASS** |

---

## 5. Nhật ký Truy vấn Mở rộng (Multi-Query Expansion) & Trích xuất Câu trả lời Mẫu

### [Q01] Sinh viên Trường Đại học Thủ Dầu Một cần đáp ứng đầy đủ những điều kiện gì để được xét và công nhận tốt nghiệp đại học?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 27 Điều kiện xét và công nhận tốt nghiệp đại học tại Trường Đại học Thủ Dầu Một` ; `Quy định tích lũy đủ học phần điểm trung bình tích lũy từ 5,0 trở lên chứng chỉ GDQP-AN GDTC và chuẩn đầu ra Điều 27`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `3` | **Thời gian xử lý:** `146.43 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Điều kiện xét và công nhận tốt nghiệp đại học tại TDMU (Điều 27 - Trang 13...

### [Q02] Trong trường hợp nào sinh viên đạt điểm trung bình tích lũy loại Xuất sắc hoặc Giỏi bị giảm đi một mức (hạ bậc) khi xếp hạng tốt nghiệp?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 28 Cấp bằng tốt nghiệp xếp hạng tốt nghiệp Xuất sắc Giỏi Khá Trung bình` ; `Trường hợp hạng tốt nghiệp Xuất sắc và Giỏi bị giảm đi một mức do khối lượng học phần phải thi lại vượt quá 5% tổng số tín chỉ Điều 28 Khoản 2`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `158.17 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Xếp hạng tốt nghiệp và các trường hợp bị giảm hạng tốt nghiệp (Điều 28 - T...

### [Q03] Khi nào sinh viên TDMU bị cảnh báo kết quả học tập (cảnh báo học vụ) hoặc bị buộc thôi học?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 23 Xử lý kết quả học tập cảnh báo học vụ và buộc thôi học sinh viên TDMU` ; `Điều kiện cảnh báo học vụ và buộc thôi học do tổng số tín chỉ không đạt trong học kỳ vượt quá 50% hoặc tổng nợ đọng vượt quá 24 tín chỉ hoặc cảnh báo 2 lần liên tiếp Điều 23`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `2` | **Thời gian xử lý:** `107.59 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Cảnh báo kết quả học tập và Buộc thôi học (Điều 23 - Trang 10 & Trang 11):...

### [Q04] Sinh viên đang học muốn xin nghỉ học tạm thời (bảo lưu kết quả học tập) vì lý do cá nhân thì cần điều kiện gì và thời hạn nộp đơn như thế nào?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 21 Nghỉ học tạm thời xin thôi học và bảo lưu kết quả đã học tại Trường Đại học Thủ Dầu Một` ; `Thủ tục điều kiện nộp đơn xin nghỉ học tạm thời vì lý do cá nhân điểm trung bình tích lũy không dưới 5,0 và thời hạn nộp đơn Điều 21`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `131.97 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Nghỉ học tạm thời (Bảo lưu kết quả học tập) và Xin thôi học (Điều 21 - Tra...

### [Q05] Quy định về việc rút bớt học phần đã đăng ký, thời hạn hoàn trả học phí và nhận điểm RT tại TDMU được thực hiện ra sao?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 22 Rút bớt học phần đã đăng ký hoàn trả học phí và điểm RT` ; `Điều kiện rút các học phần đã đăng ký sau 2 tuần kể từ đầu học kỳ Điều 22`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `2` | **Thời gian xử lý:** `94.30 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Rút bớt học phần đã đăng ký (Điều 22 - Trang 10):** - **Thời hạn và quyền ...

### [Q06] Thời gian đào tạo theo kế hoạch học tập chuẩn toàn khóa và thời gian tối đa được phép hoàn thành khóa học đối với bậc Cử nhân, Kỹ sư là bao nhiêu năm?
- **Nhóm:** Nhóm 1: Quy chế Đào tạo 1774/QĐ-ĐHTDM (2021)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 15 Thời gian khóa học theo kế hoạch học tập chuẩn toàn khóa và thời gian tối đa hoàn thành khóa học` ; `Bảng thời gian đào tạo chuẩn 4 năm cử nhân 4,5-5 năm kỹ sư và cộng tối đa 2 năm Điều 15`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `2` | **Thời gian xử lý:** `94.21 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Quy chế Đào tạo 1774/QĐ-ĐHTDM (Ban hành năm 2021)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Về Thời gian khóa học chuẩn và tối đa (Điều 15 - Trang 7):** - **Đào tạo chín...

### [Q07] Theo Hướng dẫn 03/HD-ĐHTDM và Quyết định 56/QĐ-HĐTr, số tín chỉ tích lũy tối thiểu trong học kỳ để được hưởng 100% mức học bổng khuyến khích học tập (hệ số 1,00) là bao nhiêu tín chỉ?
- **Nhóm:** Nhóm 2: Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 03/HD-ĐHTDM quy đổi số tín chỉ tích lũy trong học kỳ tối thiểu 12 tín chỉ để xét học bổng khuyến khích học tập` ; `Bảng quy đổi hệ số hưởng học bổng tương ứng số tín chỉ tích lũy từ 5 đến 12 tín chỉ theo Quyết định 56/QĐ-HĐTr và Hướng dẫn 03/HD-ĐHTDM`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `124.17 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ ...

### [Q08] Nếu trong học kỳ sinh viên tích lũy được 11 tín chỉ hoặc 10 tín chỉ thì hệ số hưởng học bổng khuyến khích học tập tương ứng là bao nhiêu?
- **Nhóm:** Nhóm 2: Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 03/HD-ĐHTDM quy đổi số tín chỉ tích lũy trong học kỳ tối thiểu 12 tín chỉ để xét học bổng khuyến khích học tập` ; `Bảng quy đổi hệ số hưởng học bổng tương ứng số tín chỉ tích lũy từ 5 đến 12 tín chỉ theo Quyết định 56/QĐ-HĐTr và Hướng dẫn 03/HD-ĐHTDM`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `114.57 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ ...

### [Q09] Sinh viên tích lũy được 09 tín chỉ hoặc 08 tín chỉ trong học kỳ xét học bổng thì được quy đổi hệ số hưởng học bổng là bao nhiêu?
- **Nhóm:** Nhóm 2: Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Điều 19 Đăng ký khối lượng học tập tối thiểu 12 tín chỉ học lực bình thường và 8 tín chỉ học lực yếu` ; `Quy định bắt buộc đăng ký học lại học phần bị điểm dưới 5,0 và học cải thiện điểm trung bình tích lũy Điều 19` ; `Hướng dẫn 03/HD-ĐHTDM quy đổi số tín chỉ tích lũy trong học kỳ tối thiểu 12 tín chỉ để xét học bổng khuyến khích học tập`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `166.25 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ ...

### [Q10] Sinh viên năm cuối học kỳ cuối chỉ còn 05 tín chỉ tích lũy theo chương trình đào tạo và đủ điều kiện học bổng thì nhận hệ số hưởng học bổng là bao nhiêu?
- **Nhóm:** Nhóm 2: Hướng dẫn Xét học bổng 03/HD-ĐHTDM (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 03/HD-ĐHTDM quy đổi số tín chỉ tích lũy trong học kỳ tối thiểu 12 tín chỉ để xét học bổng khuyến khích học tập` ; `Bảng quy đổi hệ số hưởng học bổng tương ứng số tín chỉ tích lũy từ 5 đến 12 tín chỉ theo Quyết định 56/QĐ-HĐTr và Hướng dẫn 03/HD-ĐHTDM`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `4` | **Thời gian xử lý:** `139.80 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Xét học bổng 03/HD-ĐHTDM (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Quy định về điều kiện tín chỉ tối thiểu và nguyên tắc quy đổi hệ ...

### [Q11] Theo Công văn 432/ĐHTDM-TTNN, sinh viên TDMU có thể lựa chọn những hình thức nào để hoàn thành chuẩn đầu ra ngoại ngữ và quy định khác nhau giữa khóa 2020 trở về trước với khóa 2021 trở về sau là gì?
- **Nhóm:** Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế` ; `Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN` ; `Điều 11 và Điều 12 Chuẩn đầu ra của chương trình đào tạo và thiết kế chương trình đào tạo 120 tín chỉ cử nhân 150 tín chỉ kỹ sư`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `5` | **Thời gian xử lý:** `176.19 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ — Tiểu mụ...

### [Q12] Điểm chuẩn đạt chứng chỉ năng lực ngoại ngữ nội bộ EPT-TDMU, FPT-TDMU, CPT-TDMU đối với hệ chính quy và hệ thường xuyên là bao nhiêu điểm?
- **Nhóm:** Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế` ; `Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN` ; `Điều 11 và Điều 12 Chuẩn đầu ra của chương trình đào tạo và thiết kế chương trình đào tạo 120 tín chỉ cử nhân 150 tín chỉ kỹ sư`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `5` | **Thời gian xử lý:** `195.15 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ — Tiểu mụ...

### [Q13] Đối với sinh viên hệ chính quy khóa 2017 đến 2022 đã hoàn thành NNKC cấp độ 3 hoặc cấp độ 4 trở lên khi chuyển sang thi chứng chỉ EPT/FPT/CPT thì quy định học ôn tập tại Trung tâm Ngoại ngữ như thế nào?
- **Nhóm:** Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế` ; `Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN` ; `Điều 11 và Điều 12 Chuẩn đầu ra của chương trình đào tạo và thiết kế chương trình đào tạo 120 tín chỉ cử nhân 150 tín chỉ kỹ sư`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `5` | **Thời gian xử lý:** `206.46 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 2. Hướng dẫn lựa chọn các hình thức hoàn thành chuẩn đầ...

### [Q14] Quy định về chứng chỉ quốc tế IELTS (đơn vị cấp hợp lệ, loại hình Academic/General) và mức điểm chuẩn TOEIC 4 kỹ năng tại TDMU như thế nào?
- **Nhóm:** Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế` ; `Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `5` | **Thời gian xử lý:** `165.21 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ — Tiểu mụ...

### [Q15] Trường hợp nào sinh viên được miễn chuẩn đầu ra ngoại ngữ tại Trường Đại học Thủ Dầu Một theo Công văn 432/ĐHTDM-TTNN và Điều 12 Quy chế 1774?
- **Nhóm:** Nhóm 3: Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (2023)
- **Truy vấn mở rộng (Multi-Query Expansion):** `Hướng dẫn 432/ĐHTDM-TTNN thực hiện chuẩn đầu ra ngoại ngữ gồm 3 hình thức: hoàn thành 6 học phần NNKC, thi chứng chỉ EPT/FPT/CPT hoặc nộp chứng chỉ quốc tế` ; `Quy định điểm chuẩn IELTS TOEIC 450 Listening Reading 200 Speaking Writing và EPT FPT CPT 45 điểm chính quy 40 điểm thường xuyên Công văn 432/ĐHTDM-TTNN` ; `Điều 11 và Điều 12 Chuẩn đầu ra của chương trình đào tạo và thiết kế chương trình đào tạo 120 tín chỉ cử nhân 150 tín chỉ kỹ sư`
- **Trạng thái:** `PASS` | **Số trích dẫn:** `2` | **Thời gian xử lý:** `198.63 ms`
- **Trích đoạn phản hồi:** Căn cứ theo **Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN (Ban hành năm 2023)** của **Trường Đại học Thủ Dầu Một (TDMU)**, nội dung bạn tra cứu được quy định cụ thể như sau:  **Mục 1. Nguyên tắc chung về Chuẩn đầu ra Ngoại ngữ — Tiểu mụ...

### [Q16] Học phí một tín chỉ ngành Kỹ thuật phần mềm năm nay ở TDMU là bao nhiêu tiền?
- **Nhóm:** Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)
- **Truy vấn mở rộng:** *(Chặn trực tiếp tại tầng Relevance / Out-of-Domain Gate)*
- **Trạng thái:** `PASS` | **Số trích dẫn:** `0` | **Thời gian xử lý:** `0.03 ms`
- **Trích đoạn phản hồi:** Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ.

### [Q17] Trường Đại học Thủ Dầu Một nằm ở đâu và có địa chỉ cụ thể ở đường nào?
- **Nhóm:** Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)
- **Truy vấn mở rộng:** *(Chặn trực tiếp tại tầng Relevance / Out-of-Domain Gate)*
- **Trạng thái:** `PASS` | **Số trích dẫn:** `0` | **Thời gian xử lý:** `0.02 ms`
- **Trích đoạn phản hồi:** Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ.

### [Q18] Hiệu trưởng trường là ai?
- **Nhóm:** Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)
- **Truy vấn mở rộng:** *(Chặn trực tiếp tại tầng Relevance / Out-of-Domain Gate)*
- **Trạng thái:** `PASS` | **Số trích dẫn:** `0` | **Thời gian xử lý:** `0.04 ms`
- **Trích đoạn phản hồi:** Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ.

### [Q19] Lịch nghỉ lễ Tết Nguyên đán năm nay của sinh viên TDMU bắt đầu từ ngày nào?
- **Nhóm:** Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)
- **Truy vấn mở rộng:** *(Chặn trực tiếp tại tầng Relevance / Out-of-Domain Gate)*
- **Trạng thái:** `PASS` | **Số trích dẫn:** `0` | **Thời gian xử lý:** `0.02 ms`
- **Trích đoạn phản hồi:** Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ.

### [Q20] Căn tin và bãi giữ xe của Trường Đại học Thủ Dầu Một nằm ở tòa nhà nào?
- **Nhóm:** Nhóm 4: Câu hỏi bẫy ngoài phạm vi dữ liệu (Out-of-Domain / Unanswerable)
- **Truy vấn mở rộng:** *(Chặn trực tiếp tại tầng Relevance / Out-of-Domain Gate)*
- **Trạng thái:** `PASS` | **Số trích dẫn:** `0` | **Thời gian xử lý:** `0.02 ms`
- **Trích đoạn phản hồi:** Xin lỗi, thông tin bạn đang hỏi hiện không nằm trong phạm vi dữ liệu kho văn bản học vụ hiện hành của Trường Đại học Thủ Dầu Một (gồm Quy chế Đào tạo 1774/QĐ-ĐHTDM năm 2021, Hướng dẫn Xét học bổng 03/HD-ĐHTDM năm 2023 và Hướng dẫn Chuẩn đầu ra Ngoại ngữ 432/ĐHTDM-TTNN năm 2023). Bạn vui lòng đặt câu hỏi về các quy định học vụ (đăng ký học phần, tính điểm, cảnh báo học vụ, bảo lưu, xét tốt nghiệp, xét học bổng, chuẩn đầu ra ngoại ngữ...) hoặc liên hệ trực tiếp các phòng ban chức năng của Trường để được hỗ trợ.
