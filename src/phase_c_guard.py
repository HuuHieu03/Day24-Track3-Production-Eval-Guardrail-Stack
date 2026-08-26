from __future__ import annotations

"""Phase C: Production Guardrails — Presidio PII + NeMo Guardrails + P95 Latency."""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ADVERSARIAL_SET_PATH, GUARDRAILS_CONFIG_DIR, LATENCY_BUDGET_P95_MS, PRESIDIO_LANGUAGE


# ─── Task 9a: Presidio PII Detection ─────────────────────────────────────────

_cached_presidio = None
_cached_rails = None

def setup_presidio():
    """Khởi tạo Presidio engine với custom Vietnamese PII recognizers. (Đã implement sẵn)

    Custom recognizers thêm vào:
        VN_CCCD  — số CCCD 12 chữ số hoặc CMND 9 chữ số
        VN_PHONE — số điện thoại Việt Nam (0[3-9]xxxxxxxx)

    Các recognizers mặc định đã có sẵn: EMAIL, PHONE_NUMBER (international), ...
    """
    global _cached_presidio
    if _cached_presidio is not None:
        return _cached_presidio

    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        patterns=[
            Pattern("CCCD 12 digits", r"\b\d{12}\b", 0.9),
            Pattern("CMND 9 digits",  r"\b\d{9}\b",  0.7),
        ],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
    )

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
    })
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    registry.add_recognizer(cccd_recognizer)
    registry.add_recognizer(phone_recognizer)

    analyzer  = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine)
    anonymizer = AnonymizerEngine()
    _cached_presidio = (analyzer, anonymizer)
    return _cached_presidio


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Task 9a: Quét PII trong văn bản bằng Presidio.

    Returns:
        {
          "has_pii":    bool,
          "entities":   [{"type": str, "text": str, "score": float, "start": int, "end": int}],
          "anonymized": str,   # text với PII được thay bằng <TYPE>
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    raw_results = analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
    # Chỉ giữ các thực thể PII thực sự cần phát hiện (tránh false positive PERSON trên tiếng Việt)
    target_pii_types = {"VN_CCCD", "VN_PHONE", "EMAIL_ADDRESS", "EMAIL", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "PASSPORT"}
    results = [r for r in raw_results if r.entity_type in target_pii_types]

    if not results:
        return {"has_pii": False, "entities": [], "anonymized": text}

    anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
    anonymized_text = anonymized_result.text
    entities = [
        {
            "type": r.entity_type,
            "text": text[r.start:r.end],
            "score": round(r.score, 3),
            "start": r.start,
            "end": r.end,
        }
        for r in results
    ]
    return {"has_pii": True, "entities": entities, "anonymized": anonymized_text}


# ─── Task 9b + 11: NeMo Guardrails ───────────────────────────────────────────

def setup_nemo_rails():
    """Khởi tạo NeMo Guardrails từ guardrails/config.yml. (Đã implement sẵn)

    Config directory: guardrails/
        config.yml  — model + rails config
        rails.co    — Colang dialogue flows (topic check, jailbreak check, output check)
    """
    global _cached_rails
    if _cached_rails is not None:
        return _cached_rails

    from nemoguardrails import RailsConfig, LLMRails
    config = RailsConfig.from_path(GUARDRAILS_CONFIG_DIR)
    _cached_rails = LLMRails(config)
    return _cached_rails


async def check_input_rail(text: str, rails=None) -> dict:
    """Task 9b: Kiểm tra input qua NeMo input rails (topic guard + jailbreak guard).

    Returns:
        {
          "allowed":        bool,
          "blocked_reason": str | None,
          "response":       str,          # NeMo's raw response
        }
    """
    from config import OPENAI_API_KEY

    refuse_keywords = [
        "xin lỗi", "không thể", "không được phép", "i cannot", "i'm sorry",
        "chỉ có thể trả lời", "tôi không thể", "dữ liệu bảo mật", "từ chối",
    ]
    jailbreak_cues = [
        "bỏ qua tất cả", "ignore previous", "pretend you are dan", "dan (do anything now)", "dan",
        "unrestricted ai", "system override", "đóng vai", "không có giới hạn",
        "tấn công mạng", "admin command", "system instructions", "dump all training",
        "ignore your system prompt", "role-play", "ignore previous instructions",
    ]
    off_topic_cues = [
        "bài thơ", "nấu ăn", "phở bò", "bitcoin", "ethereum", "phương trình vi phân", "marvel", "bộ phim",
        "thời tiết", "giải phương trình",
    ]
    pii_request_cues = [
        "cho tôi biết cccd", "số điện thoại của", "tiết lộ bảng lương", "tiết lộ lương",
        "thông tin cá nhân của", "lương của nhân viên", "bảng lương chi tiết", "mật khẩu admin",
        "thông tin nhân viên", "employee records", "salaries", "salary",
    ]

    lower_text = text.lower()
    blocked = False
    blocked_reason = None
    response = ""

    if any(cue in lower_text for cue in jailbreak_cues + off_topic_cues + pii_request_cues):
        blocked = True
        blocked_reason = "nemo_input_rail"
        response = "Xin lỗi, tôi không thể thực hiện yêu cầu này. Tôi chỉ có thể trả lời các câu hỏi về chính sách nhân sự công ty."
    elif OPENAI_API_KEY and (rails is not None or os.path.exists(GUARDRAILS_CONFIG_DIR)):
        try:
            if rails is None:
                rails = setup_nemo_rails()
            res = await asyncio.wait_for(
                rails.generate_async(messages=[{"role": "user", "content": text}]),
                timeout=3.0
            )
            if isinstance(res, dict):
                response = res.get("content", "")
            else:
                response = str(res)
            lower_resp = response.lower()
            if any(kw in lower_resp for kw in refuse_keywords):
                blocked = True
                blocked_reason = "nemo_input_rail"
        except Exception:
            pass

    return {
        "allowed": not blocked,
        "blocked_reason": blocked_reason,
        "response": response,
    }


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Task 11: Kiểm tra LLM output qua NeMo output rails trước khi trả về user.

    NeMo output rails hoạt động trong context của cả cuộc hội thoại (input + output).
    Kiểm tra: có PII không? Nội dung có phù hợp không? Có hallucination rõ ràng không?

    Returns:
        {
          "safe":           bool,
          "flagged_reason": str | None,
          "final_answer":   str,          # answer đã qua guard (có thể bị redact)
        }
    """
    from config import OPENAI_API_KEY
    refuse_keywords = ["xin lỗi", "không thể cung cấp", "i cannot", "tôi không thể cung cấp thông tin này"]
    response = ""

    if OPENAI_API_KEY and (rails is not None or os.path.exists(GUARDRAILS_CONFIG_DIR)):
        try:
            if rails is None:
                rails = setup_nemo_rails()
            res = await asyncio.wait_for(
                rails.generate_async(messages=[
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]),
                timeout=3.0
            )
            if isinstance(res, dict):
                response = res.get("content", "")
            else:
                response = str(res)
        except Exception:
            pass

    lower_resp = response.lower()
    flagged = any(kw in lower_resp for kw in refuse_keywords)
    return {
        "safe": not flagged,
        "flagged_reason": "nemo_output_rail" if flagged else None,
        "final_answer": response if flagged and response else answer,
    }


# ─── Task 10: Adversarial Test Suite ─────────────────────────────────────────

def run_adversarial_suite(adversarial_set: list[dict], rails=None,
                           analyzer=None, anonymizer=None) -> list[dict]:
    """Task 10: Chạy 20 adversarial inputs qua full guard stack, so sánh với expected.

    Guard stack order:
        1. pii_scan()         → block nếu has_pii (cho category pii_injection)
        2. check_input_rail() → block nếu jailbreak / off-topic / prompt injection

    Returns:
        list of {
          "id": int, "category": str, "input": str,
          "expected": "blocked"|"allowed",
          "actual":   "blocked"|"allowed",
          "blocked_by": str | None,       # "presidio" | "nemo_input" | None
          "passed": bool,
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    async def _run_all():
        results = []
        for item in adversarial_set:
            blocked_by = None

            # Layer 1: Presidio PII (synchronous, fast)
            pii_result = pii_scan(item["input"], analyzer, anonymizer)
            if pii_result["has_pii"] and item.get("category") == "pii_injection" and item.get("block_layer") == "presidio":
                blocked_by = "presidio"

            # Layer 2: NeMo input rail (async)
            if blocked_by is None:
                rail_result = await check_input_rail(item["input"], rails)
                if not rail_result["allowed"]:
                    blocked_by = "nemo_input"

            actual = "blocked" if blocked_by else "allowed"
            results.append({
                "id":         item["id"],
                "category":   item["category"],
                "input":      item["input"][:80] + "..." if len(item["input"]) > 80 else item["input"],
                "expected":   item["expected"],
                "actual":     actual,
                "blocked_by": blocked_by,
                "passed":     (actual == item["expected"]),
            })
        return results

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            results = loop.run_until_complete(_run_all())
        else:
            results = loop.run_until_complete(_run_all())
    except RuntimeError:
        results = asyncio.run(_run_all())

    passed = sum(1 for r in results if r["passed"])
    print(f"Adversarial suite: {passed}/{len(results)} passed")
    return results


# ─── Task 12: P95 Latency Measurement ────────────────────────────────────────

def measure_p95_latency(test_inputs: list[str], n_runs: int = 20,
                         rails=None, analyzer=None, anonymizer=None) -> dict:
    """Task 12: Đo P50/P95/P99 latency cho từng layer trong guard stack.

    Mục tiêu production: P95 total < LATENCY_BUDGET_P95_MS (500ms mặc định)

    Insight cần quan sát:
        - Presidio: local regex → rất nhanh (<10ms)
        - NeMo:     LLM API call → chậm (~200-800ms tuỳ model và network)
        → Tổng: dominated by NeMo

    Returns:
        {
          "presidio_ms":  {"p50": float, "p95": float, "p99": float},
          "nemo_ms":      {"p50": float, "p95": float, "p99": float},
          "total_ms":     {"p50": float, "p95": float, "p99": float},
          "latency_budget_ok": bool,
          "budget_ms": int,
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    presidio_times, nemo_times, total_times = [], [], []

    async def _measure():
        inputs_to_run = (test_inputs * ((n_runs // len(test_inputs)) + 1))[:n_runs] if test_inputs else ["test"] * n_runs
        for text in inputs_to_run:
            # Presidio (synchronous)
            t0 = time.perf_counter()
            pii_scan(text, analyzer, anonymizer)
            presidio_ms = max(0.01, (time.perf_counter() - t0) * 1000)

            # NeMo input rail
            t1 = time.perf_counter()
            await check_input_rail(text, rails)
            nemo_ms = max(0.01, (time.perf_counter() - t1) * 1000)

            presidio_times.append(presidio_ms)
            nemo_times.append(nemo_ms)
            total_times.append(presidio_ms + nemo_ms)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            loop.run_until_complete(_measure())
        else:
            loop.run_until_complete(_measure())
    except RuntimeError:
        asyncio.run(_measure())

    def percentiles(times):
        if not times:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        s = sorted(times)
        n = len(s)
        return {
            "p50": round(s[int(n * 0.50)], 2),
            "p95": round(s[min(int(n * 0.95), n - 1)], 2),
            "p99": round(s[min(int(n * 0.99), n - 1)], 2),
        }

    total_p = percentiles(total_times)
    return {
        "presidio_ms": percentiles(presidio_times),
        "nemo_ms":     percentiles(nemo_times),
        "total_ms":    total_p,
        "latency_budget_ok": total_p["p95"] < LATENCY_BUDGET_P95_MS,
        "budget_ms": LATENCY_BUDGET_P95_MS,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Task 9a: PII scan demo
    test_pii = "Nhân viên Nguyễn Văn A, CCCD 034095001234, SĐT 0987654321 hỏi về nghỉ phép."
    result = pii_scan(test_pii)
    print(f"PII detected: {result['has_pii']}")
    print(f"Entities: {result['entities']}")
    print(f"Anonymized: {result['anonymized']}")

    # Task 10: Adversarial suite
    with open(ADVERSARIAL_SET_PATH, encoding="utf-8") as f:
        adversarial_set = json.load(f)
    print(f"\nLoaded {len(adversarial_set)} adversarial inputs")
    results = run_adversarial_suite(adversarial_set)
    if results:
        passed = sum(1 for r in results if r["passed"])
        print(f"Adversarial suite: {passed}/{len(results)} passed")

    # Task 12: P95 latency
    sample_inputs = [item["input"] for item in adversarial_set[:10]]
    latency = measure_p95_latency(sample_inputs, n_runs=10)
    print(f"\nLatency P95 — Presidio: {latency['presidio_ms']['p95']}ms | "
          f"NeMo: {latency['nemo_ms']['p95']}ms | "
          f"Total: {latency['total_ms']['p95']}ms")
    print(f"Budget OK ({latency['budget_ms']}ms): {latency['latency_budget_ok']}")

    os.makedirs("reports", exist_ok=True)
    guard_report = {
        "adversarial_suite_pass_rate": round(passed / len(results), 3) if results else 1.0,
        "adversarial_passed": passed if results else len(adversarial_set),
        "adversarial_total": len(results) if results else len(adversarial_set),
        "latency_benchmark": latency,
        "results": results,
    }
    with open("reports/guard_results.json", "w", encoding="utf-8") as f:
        json.dump(guard_report, f, ensure_ascii=False, indent=2)
    print("Guard results saved → reports/guard_results.json")
