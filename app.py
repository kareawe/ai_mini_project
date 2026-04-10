import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from dotenv import load_dotenv

# ─────────────────────────────────────────────
# .env 먼저 로드
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(env_path)

# .env 로드 이후에 import
from graph import build_graph
from agents.formatting_node import markdown_to_pdf

# ─────────────────────────────────────────────
# 출력 디렉토리 보장
# ─────────────────────────────────────────────
(BASE_DIR / "outputs").mkdir(exist_ok=True)
(BASE_DIR / "data").mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "outputs" / "run.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def save_evaluation(evaluation, timestamp: str) -> str:
    """평가 결과를 JSON으로 outputs/ 에 저장"""
    output_path = BASE_DIR / "outputs" / f"evaluation_{timestamp}.json"
    try:
        eval_dict = asdict(evaluation) if evaluation else {"error": "평가 결과 없음"}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(eval_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"평가 결과 저장: {output_path}")
    except Exception as e:
        logger.error(f"평가 결과 저장 실패: {e}")
    return str(output_path)


def print_summary(state: dict) -> None:
    """실행 결과 요약 출력"""
    print("\n" + "═" * 60)
    print("  반도체 기술 전략 분석 — 실행 결과 요약")
    print("═" * 60)
    print(f"  상태        : {state.get('status', 'unknown')}")
    print(f"  수집 문서   : {len(state.get('retrieved_documents', []))}개")
    print(f"  검증 팩트   : {len(state.get('validated_facts', []))}개")
    print(f"  경쟁사 프로파일: {len(state.get('company_profiles', []))}개")

    ev = state.get("evaluation_result")
    if ev:
        print(f"\n  ── 보고서 품질 평가 ──")
        print(f"  정확성      : {ev.accuracy_score:.2f}  (기준 ≥ 0.80)")
        print(f"  최신성      : {ev.recency_score:.2f}  (기준 ≥ 0.75)")
        print(f"  일관성      : {ev.consistency_score:.2f}  (기준 ≥ 0.80)")
        print(f"  편향 통제   : {'✓' if ev.bias_check_passed else '✗'}")
        print(f"  교차 검증   : {'✓' if ev.cross_validation_passed else '✗'}")
        print(f"  최종 통과   : {'✓ PASS' if ev.overall_passed else '✗ FAIL'}")
        if ev.feedback != "모든 기준 통과":
            print(f"  피드백      : {ev.feedback}")

    retry = state.get("retry_count", {})
    if any(v > 0 for v in retry.values()):
        print(f"\n  재시도 횟수 : {retry}")

    print("═" * 60 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="반도체 핵심 기술(HBM4, PIM, CXL) 경쟁사 기술 전략 분석 시스템"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default="HBM4, PIM, CXL 핵심 기술에 대한 경쟁사 기술 성숙도와 전략 변화를 분석하라",
        help="분석 요청 쿼리",
    )
    parser.add_argument(
        "--techs", "-t",
        nargs="+",
        default=["HBM4", "PIM", "CXL"],
        choices=["HBM4", "PIM", "CXL"],
        help="분석 대상 기술 (복수 선택 가능)",
    )
    parser.add_argument(
        "--max-retry", "-r",
        type=int,
        default=3,
        help="에이전트별 최대 재시도 횟수 (기본값: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "═" * 60)
    print("  반도체 기술 전략 분석 시스템 시작")
    print("═" * 60)
    print(f"  분석 기술 : {', '.join(args.techs)}")
    print(f"  쿼리      : {args.query}")
    print(f"  최대 재시도: {args.max_retry}회")
    print("═" * 60 + "\n")

    initial_state = {
        "user_query": args.query,
        "target_technologies": args.techs,
        "max_retry": args.max_retry,
        "retry_count": {"rag": 0, "web_search": 0, "competitor": 0, "report": 0},
    }

    graph = build_graph()

    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"워크플로우 실행 오류: {e}", exc_info=True)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_path = save_evaluation(final_state.get("evaluation_result"), timestamp)

    draft = final_state.get("draft_report", "")
    if draft:
        # ── formatting_node가 이미 PDF 생성했으면 해당 경로 사용 ──
        report_path = final_state.get("output_path")

        if report_path and Path(report_path).exists():
            logger.info(f"[app] formatting_node PDF 사용: {report_path}")
        else:
            # ── fallback: app.py에서 직접 PDF 변환 ──────────────
            logger.warning("[app] output_path 없음 — 직접 PDF 변환 실행")
            report_path = str(
                BASE_DIR / "outputs" / f"semiconductor_strategy_report_{timestamp}.pdf"
            )

            success = markdown_to_pdf(draft, report_path)
            if not success:
                # PDF 변환도 실패하면 md로 fallback
                report_path = str(
                    BASE_DIR / "outputs" / f"semiconductor_strategy_report_{timestamp}.md"
                )
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(draft)
                logger.error(f"[app] PDF 변환 실패 — MD로 저장: {report_path}")

        print(f"\n  ✓ 보고서 저장: {report_path}")
        print(f"  ✓ 평가 결과  : {eval_path}\n")
    else:
        print("\n  ✗ 보고서 생성 실패 — outputs/run.log 확인\n")

    print_summary(final_state)

    return 0 if final_state.get("status") in ("done",) else 1


if __name__ == "__main__":
    sys.exit(main())