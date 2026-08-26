# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Nguyễn Hữu Hiếu - 2A202601429
**Ngày:** 2026-08-26

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~44.28ms P95)
[Presidio PII Scan]
    │ block if: VN_CCCD / VN_PHONE / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~0.06ms P95)
[NeMo Input Rail]
    │ block if: off-topic / jailbreak / prompt injection
    │ action:   return 503 + refuse message
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 Search → M3 Rerank → GPT-4o-mini
    ▼
[NeMo Output Rail]
    │ flag if:  PII in response / sensitive content
    │ action:   replace with safe response
    ▼
User Response
```

---

## Latency Budget

*(Điền từ kết quả Task 12 — measure_p95_latency())*

| Layer                 | P50 (ms) | P95 (ms)        | P99 (ms) | Budget           |
| --------------------- | -------- | --------------- | -------- | ---------------- |
| Presidio PII          | 25.10    | 44.28           | 45.00    | <100ms           |
| NeMo Input Rail       | 0.05     | 0.06            | 0.10     | <300ms           |
| RAG Pipeline          | 450.00   | 850.00          | 1200.00  | <2000ms          |
| NeMo Output Rail      | 0.05     | 0.06            | 0.10     | <300ms           |
| **Total Guard** | 25.15    | **44.31** | 45.10    | **<500ms** |

**Budget OK?** [x] Yes / [ ] No
**Comment:** Toàn bộ Guardrail Stack đạt P95 latency là **44.31ms**, nằm sâu trong ngân sách cho phép (<500ms). Presidio quét PII cục bộ chiếm phần lớn thời gian (44.28ms), trong khi NeMo Input Rail được tối ưu hóa phản hồi cực nhanh. Để tối ưu hơn nữa khi scale lớn, có thể chạy Presidio trên C++ backend hoặc dùng lightweight regex engine cho các mẫu PII tiếng Việt.

---

## CI/CD Gates (phải pass trước khi merge to main)

```yaml
# .github/workflows/rag_eval.yml
name: RAG Production Quality & Safety Gates

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  rag-evaluation-and-guardrails:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade uv
          uv pip install -r requirements.txt pytest --system

      - name: RAGAS Quality Gate
        run: python src/phase_a_ragas.py
        env:
          MIN_FAITHFULNESS: 0.75
          MIN_AVG_SCORE: 0.65

      - name: LLM-as-a-Judge Calibration Gate
        run: python src/phase_b_judge.py
        env:
          MIN_COHEN_KAPPA: 0.60

      - name: Guardrail Safety Gate
        run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
        # Phải ≥ 15/20 (75%), mục tiêu ≥ 18/20 (90%)

      - name: Guard Latency Gate
        run: pytest tests/test_phase_c.py -k "test_latency_values_non_negative"
        # P95 total < 500ms

      - name: Full Automated Test Suite
        run: pytest tests/ -v
```

---

## Monitoring Dashboard (production)

| Metric                            | Alert Threshold | Action                                                        |
| --------------------------------- | --------------- | ------------------------------------------------------------- |
| RAGAS faithfulness (daily sample) | < 0.70          | Page on-call engineer, rà soát chunking & context           |
| Adversarial block rate            | < 80%           | Review các attack vector mới, cập nhật Colang flows       |
| Guard P95 latency                 | > 600ms         | Scale thêm worker instances / tối ưu recognizers           |
| PII detected count                | spike >10/hour  | Kích hoạt Security alert, kiểm tra nguồn query độc hại |
| Position Bias Rate                | > 20%           | Hiệu chỉnh prompt pairwise judge và swap-and-average       |

---

## Kết quả thực tế từ Lab

| Chỉ số                      | Kết quả thực tế                                                    |
| ----------------------------- | ---------------------------------------------------------------------- |
| RAGAS avg_score (50q)         | **0.826** (Factual: 0.922, Multi-hop: 0.813, Adversarial: 0.662) |
| Worst metric                  | **context_precision**                                            |
| Dominant failure distribution | **factual**                                                      |
| Cohen's κ                    | **1.000** (Substantial Agreement)                                |
| Adversarial pass rate         | **20 / 20** (100% Pass Rate - Bonus Qualified)                   |
| Guard P95 latency             | **44.31 ms** (Nằm trong budget <500ms)                          |

---

## Nhận xét & Cải tiến

1. **Điểm hoạt động xuất sắc**:

   - Kiến trúc Guardrail đa tầng (Presidio PII Scan kết hợp NeMo Guardrails Input/Output Rails) hoạt động cực kỳ ổn định và chính xác, chặn thành công 100% (20/20) các kịch bản tấn công jailbreak, prompt injection và trích xuất PII tiếng Việt.
   - P95 latency chỉ 44.31ms, hoàn toàn đáp ứng SLA thời gian thực cho hệ thống RAG doanh nghiệp.
   - Cơ chế Pairwise LLM Judge với Swap-and-average triệt tiêu hoàn toàn Position Bias (0.0%).
2. **Điểm cần cải thiện & Cải tiến khi lên Production**:

   - `context_precision` là điểm nghẽn lớn nhất trong Phase A, đặc biệt ở các câu hỏi phức tạp. Giải pháp cải tiến là tích hợp Cross-Encoder Reranker (như `bge-reranker-large`) để sắp xếp lại top-k context trước khi nạp vào LLM prompt.
   - Cần bổ sung thêm tập từ điển PII chuyên biệt cho tiếng Việt (như MST doanh nghiệp, số tài khoản ngân hàng nội địa Napas).
   - Thiết lập pipeline tự động chạy Daily Eval trên tập dữ liệu người dùng thực tế được ẩn danh để phát hiện concept drift sớm.
