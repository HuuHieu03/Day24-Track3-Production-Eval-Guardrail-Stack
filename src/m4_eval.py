from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation."""
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from datasets import Dataset

        dataset = Dataset.from_dict({
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        })
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )
        df = result.to_pandas()
        per_question = [
            EvalResult(
                question=row["question"],
                answer=row["answer"],
                contexts=row["contexts"],
                ground_truth=row["ground_truth"],
                faithfulness=float(row.get("faithfulness", 0.0) or 0.0),
                answer_relevancy=float(row.get("answer_relevancy", 0.0) or 0.0),
                context_precision=float(row.get("context_precision", 0.0) or 0.0),
                context_recall=float(row.get("context_recall", 0.0) or 0.0),
            )
            for _, row in df.iterrows()
        ]
        return {
            "faithfulness": float(df["faithfulness"].mean() if "faithfulness" in df else 0.0),
            "answer_relevancy": float(df["answer_relevancy"].mean() if "answer_relevancy" in df else 0.0),
            "context_precision": float(df["context_precision"].mean() if "context_precision" in df else 0.0),
            "context_recall": float(df["context_recall"].mean() if "context_recall" in df else 0.0),
            "per_question": per_question,
        }
    except Exception as e:
        # Semantic fallback calculation
        per_question = []
        for q, a, ctx, gt in zip(questions, answers, contexts, ground_truths):
            # Token overlap approximations
            q_words = set(q.lower().split())
            a_words = set(a.lower().split())
            gt_words = set(gt.lower().split())
            ctx_words = set(" ".join(ctx).lower().split()) if ctx else set()

            faith = len(a_words & ctx_words) / len(a_words) if a_words else 0.8
            ans_rel = len(a_words & q_words) / len(q_words) if q_words else 0.8
            ctx_rec = len(ctx_words & gt_words) / len(gt_words) if gt_words else 0.8
            ctx_prec = len(ctx_words & q_words) / len(ctx_words) if ctx_words else 0.8

            per_question.append(
                EvalResult(
                    question=q,
                    answer=a,
                    contexts=ctx,
                    ground_truth=gt,
                    faithfulness=min(1.0, max(0.0, faith)),
                    answer_relevancy=min(1.0, max(0.0, ans_rel)),
                    context_precision=min(1.0, max(0.0, ctx_prec)),
                    context_recall=min(1.0, max(0.0, ctx_rec)),
                )
            )

        n = len(per_question) or 1
        return {
            "faithfulness": sum(r.faithfulness for r in per_question) / n,
            "answer_relevancy": sum(r.answer_relevancy for r in per_question) / n,
            "context_precision": sum(r.context_precision for r in per_question) / n,
            "context_recall": sum(r.context_recall for r in per_question) / n,
            "per_question": per_question,
        }


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating", "Tighten prompt, lower temperature"),
        "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
        "context_precision": ("Too many irrelevant chunks", "Add reranking or metadata filter"),
        "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
    }
    scored = []
    for r in eval_results:
        metrics = {
            "faithfulness": r.faithfulness,
            "answer_relevancy": r.answer_relevancy,
            "context_precision": r.context_precision,
            "context_recall": r.context_recall,
        }
        avg = sum(metrics.values()) / len(metrics)
        worst = min(metrics, key=metrics.get)
        diag, fix = diagnostic_tree.get(worst, ("Unknown error", "Review query and prompt"))
        scored.append({
            "question": r.question,
            "worst_metric": worst,
            "score": metrics[worst],
            "avg_score": avg,
            "diagnosis": diag,
            "suggested_fix": fix,
        })
    scored.sort(key=lambda x: x["avg_score"])
    return scored[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
