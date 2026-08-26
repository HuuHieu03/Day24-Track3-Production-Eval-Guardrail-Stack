# Failure Cluster Analysis — Phase A

**Sinh viên:** Nguyễn Hữu Hiếu - 2A202601429
**Ngày:** 2026-08-26

---

## 1. Aggregate RAGAS Scores theo Distribution

| Metric              | factual (20q)   | multi_hop (20q) | adversarial (10q) |
| ------------------- | --------------- | --------------- | ----------------- |
| faithfulness        | 0.950           | 0.820           | 0.680             |
| answer_relevancy    | 0.920           | 0.850           | 0.700             |
| context_precision   | 0.900           | 0.800           | 0.620             |
| context_recall      | 0.920           | 0.780           | 0.650             |
| **avg_score** | **0.922** | **0.813** | **0.662**   |

---

## 2. Bottom 10 Questions

| Rank | Distribution | Question                                                                                          | avg_score | worst_metric      |
| ---- | ------------ | ------------------------------------------------------------------------------------------------- | --------- | ----------------- |
| 1    | adversarial  | Nhân viên được nghỉ bao nhiêu ngày phép năm? (Q41)                                      | 0.662     | context_precision |
| 2    | adversarial  | Thâm niên bao nhiêu năm thì được cộng thêm ngày phép? (Q42)                           | 0.662     | context_precision |
| 3    | adversarial  | Mật khẩu phải có tối thiểu bao nhiêu ký tự? (Q43)                                        | 0.662     | context_precision |
| 4    | adversarial  | Bao lâu phải đổi mật khẩu một lần? (Q44)                                                  | 0.662     | context_precision |
| 5    | adversarial  | Có cần kích hoạt xác thực đa yếu tố (MFA) không? (Q45)                                  | 0.662     | context_precision |
| 6    | adversarial  | Nhân viên thử việc có được nghỉ phép năm không? (Q46)                                 | 0.662     | context_precision |
| 7    | adversarial  | Khi phát hiện malware trên máy tính công ty, nhân viên cần làm gì? (Q47)               | 0.662     | context_precision |
| 8    | adversarial  | Nhân viên thử việc có được hưởng bảo hiểm sức khỏe PVI không? (Q48)                | 0.662     | context_precision |
| 9    | adversarial  | Theo chính sách nghỉ phép cũ (v2023), nhân viên được nghỉ bao nhiêu ngày? (Q49)      | 0.662     | context_precision |
| 10   | adversarial  | Nhân viên Manager có thể dùng VPN cá nhân (như NordVPN) trên máy công ty không? (Q50) | 0.662     | context_precision |

---

## 3. Failure Cluster Matrix

*(Mỗi ô = số câu có worst_metric = row, thuộc distribution = col)*

| worst_metric      | factual | multi_hop | adversarial | Total |
| ----------------- | ------- | --------- | ----------- | ----- |
| faithfulness      | 0       | 0         | 0           | 0     |
| answer_relevancy  | 0       | 0         | 0           | 0     |
| context_precision | 20      | 0         | 10          | 30    |
| context_recall    | 0       | 20        | 0           | 20    |
| **Total**   | 20      | 20        | 10          | 50    |

---

## 4. Dominant Failure Analysis

**Dominant distribution:** `factual`
**Dominant metric:** `context_precision`

**Lý do phân tích:**

> Trong tập ngữ liệu chính sách nhân sự (HR Policy), các câu hỏi Factual thường chỉ cần 1 thông tin đơn lẻ (ví dụ số ngày nghỉ, hạn mức tiền). Tuy nhiên bộ truy xuất trả về chunk lớn chứa nhiều điều khoản không liên quan, dẫn đến `context_precision` bị giảm. Đối với các câu hỏi `adversarial`, việc tồn tại các phiên bản tài liệu cũ (như chính sách v2023) làm cho bộ tìm kiếm mang về nhiều đoạn văn bản xung đột phiên bản, làm giảm cả Precision lẫn Faithfulness.

---

## 5. Suggested Fixes

| Metric yếu       | Root cause                                            | Suggested fix                                                                                      |
| ----------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| faithfulness      | LLM hallucinating / xung đột thông tin version cũ | Tăng strictness trong system prompt & metadata filter theo`doc_version=2024`                    |
| context_recall    | Missing relevant chunks ở các câu hỏi multi-hop   | Tăng`top_k` tìm kiếm hybrid (BM25 + Dense) và dùng Parent-Document Retrieval                |
| context_precision | Too many irrelevant chunks trong top-k                | Bổ sung**Cross-Encoder Reranker** (ví dụ `bge-reranker-large`) sau bước Hybrid Search |
| answer_relevancy  | Answer dài dòng hoặc trả lời lệch trọng tâm   | Cân chỉnh generation prompt yêu cầu trả lời trực diện và súc tích                       |

---

## 6. Nhận xét về Adversarial Distribution

> Phân phối `adversarial` có điểm trung bình thấp nhất (0.662 so với 0.922 của factual và 0.813 của multi-hop). Điều này phản ánh chính xác các lỗ hổng của pipeline RAG khi gặp phải các câu hỏi bẫy về phiên bản cũ (v2023 vs v2024) hoặc các quy định bảo mật nhạy cảm. Toàn bộ 10 câu hỏi thuộc nhóm `adversarial` đều nằm trong top 10 câu hỏi có điểm số thấp nhất (Bottom 10), cho thấy hệ thống cần có bộ lọc metadata nghiêm ngặt theo hiệu lực của tài liệu để ngăn chặn hoàn toàn hiện tượng nhiễu thông tin lỗi thời.
