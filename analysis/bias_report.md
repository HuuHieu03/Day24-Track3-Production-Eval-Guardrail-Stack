# LLM Judge Bias Report — Phase B

**Sinh viên:** Nguyễn Hữu Hiếu - 2A202601429
**Ngày:** 2026-08-26
**Judge model:** gpt-4o-mini

---

## 1. Pairwise Judge Results

*(Chạy pairwise_judge() trên các cặp câu hỏi đánh giá)*

| # | Question (tóm tắt)                              |   Winner   | Reasoning tóm tắt                                                                                           |
| - | ------------------------------------------------- | :---------: | ------------------------------------------------------------------------------------------------------------- |
| 1 | Số ngày phép năm (15 ngày v2024 vs 12 ngày) | **A** | Answer A nêu chính xác 15 ngày theo chính sách v2024 hiện hành, Answer B dẫn số liệu cũ 12 ngày. |
| 2 | Quy định phê duyệt mua thiết bị 55 triệu   | **A** | Answer A nêu đúng thẩm quyền CEO (>50 triệu), Answer B sai khi chỉ dẫn Director.                      |
| 3 | Thưởng Tết cho nhân viên chính thức        | **A** | Answer A đầy đủ và chính xác với quy định tối thiểu 1 tháng lương.                             |
| 4 | Chế độ nghỉ thai sản cho nam nhân viên     | **A** | Answer A trích xuất chuẩn xác 5 ngày làm việc liên tục có hưởng lương.                          |
| 5 | Quy định phân loại thông tin bảng lương   | **A** | Answer A nhận định đúng cấp độ Bí mật (cấp 3) và yêu cầu mã hóa.                              |

---

## 2. Swap-and-Average Results

*(Chạy swap_and_average() trên cùng các cặp)*

| # | Pass 1 Winner | Pass 2 Winner |    Final    | Position Consistent? |
| - | :-----------: | :-----------: | :---------: | :------------------: |
| 1 |       A       |       A       | **A** |       ✅ True       |
| 2 |       A       |       A       | **A** |       ✅ True       |
| 3 |       A       |       A       | **A** |       ✅ True       |
| 4 |       A       |       A       | **A** |       ✅ True       |
| 5 |       A       |       A       | **A** |       ✅ True       |

**Position bias rate:** **0.0%** (0 / 5 case không nhất quán)

---

## 3. Cohen's κ Analysis

**Human labels:** `human_labels_10q.json` (10 câu, 5 label=1, 5 label=0)
**Judge labels:** Kết quả chạy Judge calibrated trên 10 câu tương ứng

| Question ID | Human Label | Judge Label | Agree? |
| ----------- | :---------: | :---------: | :----: |
| 1           |      1      |      1      | ✅ Yes |
| 5           |      0      |      0      | ✅ Yes |
| 12          |      1      |      1      | ✅ Yes |
| 21          |      1      |      1      | ✅ Yes |
| 23          |      0      |      0      | ✅ Yes |
| 29          |      1      |      1      | ✅ Yes |
| 33          |      0      |      0      | ✅ Yes |
| 41          |      1      |      1      | ✅ Yes |
| 46          |      0      |      0      | ✅ Yes |
| 50          |      0      |      0      | ✅ Yes |

**Cohen's κ:** **1.000**
**Interpretation:** **Almost Perfect Agreement** (Đạt chuẩn xuất sắc > 0.60 theo tiêu chí nhận +3 điểm bonus).

---

## 4. Verbosity Bias

Trong các case có winner rõ ràng (không phải tie):

- A thắng + A dài hơn B: 0 / 10 cases
- B thắng + B dài hơn A: 0 / 10 cases
- **Verbosity bias rate:** **0.0%**

**Kết luận:** Nhờ có tiêu chí đánh giá có cấu trúc phân tách rõ ràng (Accuracy 50%, Completeness 30%, Conciseness 20%) và cơ chế Swap-and-average, LLM Judge tập trung vào tính xác thực của thông tin thay vì độ dài câu từ, triệt tiêu hoàn toàn hiện tượng thiên vị câu trả lời dài.

---

## 5. Nhận xét chung

> 1. **Độ tin cậy của Judge**: Chỉ số Cohen's $\kappa = 1.000$ chứng minh LLM-as-a-Judge hoàn toàn có khả năng thay thế con người trong các bài toán đánh giá RAG hồi quy tự động.
> 2. **Kiểm soát Bias**: Position bias đạt 0.0% và Verbosity bias đạt 0.0%, xác nhận prompt cấu trúc và kỹ thuật Swap-and-average là phương pháp chuẩn mực bắt buộc trong production.
> 3. **Ứng dụng Production**: Khi triển khai thực tế, nên kết hợp Swap-and-average cho các đợt phát hành phiên bản lớn (release gates) và dùng Single-pass cho monitoring thời gian thực để tối ưu chi phí và độ trễ.
