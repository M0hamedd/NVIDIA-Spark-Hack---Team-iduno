from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from contract_radar import config
from contract_radar.data import ProcurementDataUnavailable, load_procurement_data
from contract_radar.models import parse_date
from contract_radar.profiles import SUPPORTED_PROFILE_IDS, get_supported_profile
from contract_radar.ranker import (
    FEATURE_NAMES,
    MARKET_FEATURE_NAMES,
    VALUE_FEATURE_NAMES,
    MarketExample,
    RankerExample,
    build_historical_award_examples,
    build_market_award_examples,
    build_ranker_examples,
    feature_matrix,
    market_feature_matrix,
    market_sample_weights,
    market_target_vector,
    require_sklearn,
    sample_weights,
    target_vector,
    train_award_value_model,
)
from scripts.evaluate_bid_engine import evaluate_bid_engine


DEFAULT_AS_OF = date(2026, 5, 30)


def train_bid_ranker(
    profile_selector: str = "all",
    offline: bool = False,
    as_of: date | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    require_sklearn()
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    today = as_of or DEFAULT_AS_OF
    solicitations, awards, data_mode, warnings = _load_training_data(offline=offline)
    profile_ids = _resolve_profile_ids(profile_selector)
    examples: list[RankerExample] = []
    market_examples: list[MarketExample] = []
    current_example_count = 0
    historical_example_count = 0
    for profile_id in profile_ids:
        profile = get_supported_profile(profile_id)
        current_examples = build_ranker_examples(
            profile=profile,
            solicitations=solicitations,
            awards=awards,
            today=today,
        )
        historical_examples = build_historical_award_examples(profile=profile, awards=awards)
        current_example_count += len(current_examples)
        historical_example_count += len(historical_examples)
        examples.extend(
            current_examples + historical_examples
        )
        market_examples.extend(build_market_award_examples(profile=profile, awards=awards))

    if len({example.target for example in examples}) < 2:
        raise ValueError("Ranker training needs at least one positive and one negative example.")

    train_examples, test_examples = _train_test_split(examples, train_test_split)
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
    )
    model.fit(
        feature_matrix(train_examples),
        target_vector(train_examples),
        logisticregression__sample_weight=sample_weights(train_examples),
    )
    test_scores = [
        float(score)
        for score in model.predict_proba(feature_matrix(test_examples))[:, 1]
    ]
    all_scores = [
        float(score)
        for score in model.predict_proba(feature_matrix(examples))[:, 1]
    ]
    market_summary, market_model, value_model = _train_award_history_model(
        examples=market_examples,
        make_pipeline=make_pipeline,
        logistic_regression_cls=LogisticRegression,
        scaler_cls=StandardScaler,
    )
    baseline = evaluate_bid_engine(profile_selector, offline=offline, as_of=today)
    summary = _evaluation_summary(
        examples=examples,
        train_examples=train_examples,
        test_examples=test_examples,
        test_scores=test_scores,
        all_scores=all_scores,
        baseline=baseline,
        data_mode=data_mode,
        warnings=warnings,
        model=model,
        as_of=today,
        current_example_count=current_example_count,
        historical_example_count=historical_example_count,
    )
    summary["award_history_model"] = market_summary
    if output_path is not None:
        _write_model_artifact(output_path, summary, model, market_model, value_model)
    return summary


def _load_training_data(offline: bool) -> tuple[list[Any], list[Any], str, list[str]]:
    previous_offline = os.environ.get(config.OFFLINE_ENV)
    if offline:
        os.environ[config.OFFLINE_ENV] = "1"
    try:
        bundle = load_procurement_data(refresh=False)
    finally:
        if offline:
            if previous_offline is None:
                os.environ.pop(config.OFFLINE_ENV, None)
            else:
                os.environ[config.OFFLINE_ENV] = previous_offline

    data_sources = "; ".join(f"{name}={status}" for name, status in bundle.source_status.items())
    return bundle.solicitations, bundle.awards, data_sources or "Toronto Open Data", bundle.warnings


def _resolve_profile_ids(profile_selector: str) -> list[str]:
    selector = str(profile_selector or "all").strip().lower()
    if selector == "all":
        return list(SUPPORTED_PROFILE_IDS)
    requested = [item.strip().lower() for item in selector.split(",") if item.strip()]
    invalid = [item for item in requested if item not in SUPPORTED_PROFILE_IDS]
    if invalid:
        supported = ", ".join(SUPPORTED_PROFILE_IDS)
        raise ValueError(f"Unsupported profile id(s): {', '.join(invalid)}. Use all or one of: {supported}")
    return requested


def _train_test_split(examples: list[RankerExample], split_fn: Any) -> tuple[list[RankerExample], list[RankerExample]]:
    targets = target_vector(examples)
    positive_count = sum(targets)
    negative_count = len(targets) - positive_count
    if positive_count >= 2 and negative_count >= 2:
        train, test = split_fn(
            examples,
            test_size=0.35,
            random_state=42,
            stratify=targets,
        )
        return list(train), list(test)

    train: list[RankerExample] = []
    test: list[RankerExample] = []
    for example in examples:
        bucket = _stable_bucket(f"{example.profile_id}:{example.document_number}", 10)
        (test if bucket < 3 else train).append(example)
    if not train or not test:
        midpoint = max(1, len(examples) // 2)
        return examples[:midpoint], examples[midpoint:]
    return train, test


def _train_award_history_model(
    examples: list[MarketExample],
    make_pipeline: Any,
    logistic_regression_cls: Any,
    scaler_cls: Any,
) -> tuple[dict[str, Any], Any | None, Any | None]:
    if len({example.target for example in examples}) < 2:
        raise RuntimeError("Award-history model needs at least one positive and one negative example.")

    train_examples, test_examples = _temporal_market_split(examples)
    if len({example.target for example in train_examples}) < 2:
        raise RuntimeError("Temporal award-history training split has only one class.")

    model = make_pipeline(
        scaler_cls(),
        logistic_regression_cls(max_iter=1000, class_weight="balanced", random_state=42),
    )
    model.fit(
        market_feature_matrix(train_examples),
        market_target_vector(train_examples),
        logisticregression__sample_weight=market_sample_weights(train_examples),
    )
    test_scores = [
        float(score)
        for score in model.predict_proba(market_feature_matrix(test_examples))[:, 1]
    ]
    summary = _market_evaluation_summary(examples, train_examples, test_examples, test_scores, model)
    value_model, value_summary = train_award_value_model(examples)
    summary["value_model"] = value_summary
    return summary, model, value_model


def _temporal_market_split(examples: list[MarketExample]) -> tuple[list[MarketExample], list[MarketExample]]:
    dated = [
        example
        for example in examples
        if parse_date(example.award_date) is not None
    ]
    if dated:
        train = [example for example in dated if str(example.award_date) < "2024-01-01"]
        test = [example for example in dated if str(example.award_date) >= "2024-01-01"]
        if train and test and len({example.target for example in train}) >= 2:
            return train, test

    ordered = sorted(
        examples,
        key=lambda item: (
            item.award_date or "",
            item.profile_id,
            item.document_number,
            item.supplier,
        ),
    )
    split_at = max(1, int(len(ordered) * 0.75))
    return ordered[:split_at], ordered[split_at:]


def _evaluation_summary(
    examples: list[RankerExample],
    train_examples: list[RankerExample],
    test_examples: list[RankerExample],
    test_scores: list[float],
    all_scores: list[float],
    baseline: dict[str, Any],
    data_mode: str,
    warnings: list[str],
    model: Any,
    as_of: date,
    current_example_count: int,
    historical_example_count: int,
) -> dict[str, Any]:
    test_targets = target_vector(test_examples)
    profile_metrics = _profile_metrics(test_examples, test_scores)
    top_features = _top_weighted_features(model)
    average_precision = _safe_average_precision(test_targets, test_scores)
    roc_auc = _safe_roc_auc(test_targets, test_scores)
    naive_keyword_candidates = sum(item["naive_keyword_candidate_count"] for item in baseline["profiles"])
    bid_engine_actionable = sum(item["bid_engine_actionable_count"] for item in baseline["profiles"])
    skipped_false_positives = sum(item["skipped_false_positives"] for item in baseline["profiles"])
    hard_negative_count = sum(1 for example in examples if example.hard_negative)
    positive_count = sum(example.target for example in examples)

    return {
        "as_of": as_of.isoformat(),
        "data_mode": data_mode,
        "profiles": [item["profile_id"] for item in baseline["profiles"]],
        "examples": len(examples),
        "current_open_bid_examples": current_example_count,
        "historical_award_examples": historical_example_count,
        "training_examples": len(train_examples),
        "test_examples": len(test_examples),
        "positive_examples": positive_count,
        "negative_examples": len(examples) - positive_count,
        "hard_negative_examples": hard_negative_count,
        "average_precision": round(average_precision, 4),
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "precision_at_3": round(_weighted_metric(profile_metrics, "precision_at_3"), 4),
        "recall_at_5": round(_weighted_metric(profile_metrics, "recall_at_5"), 4),
        "false_positive_rate_top_5": round(_weighted_metric(profile_metrics, "false_positive_rate_top_5"), 4),
        "naive_baseline": {
            "naive_keyword_candidates": naive_keyword_candidates,
            "bid_engine_actionable": bid_engine_actionable,
            "skipped_false_positives": skipped_false_positives,
            "shortlist_reduction_percent": _shortlist_reduction_percent(
                naive_keyword_candidates,
                bid_engine_actionable,
            ),
        },
        "top_weighted_features": top_features,
        "profile_metrics": profile_metrics,
        "warnings": warnings,
    }


def _profile_metrics(examples: list[RankerExample], scores: list[float]) -> list[dict[str, Any]]:
    by_profile: dict[str, list[tuple[RankerExample, float]]] = {}
    for example, score in zip(examples, scores):
        by_profile.setdefault(example.profile_id, []).append((example, score))

    metrics = []
    for profile_id, rows in sorted(by_profile.items()):
        rows.sort(key=lambda row: row[1], reverse=True)
        positives = sum(row[0].target for row in rows)
        top3 = rows[:3]
        top5 = rows[:5]
        precision_at_3 = sum(row[0].target for row in top3) / max(1, len(top3))
        recall_at_5 = sum(row[0].target for row in top5) / max(1, positives)
        false_positive_rate_top_5 = sum(1 for row in top5 if row[0].hard_negative) / max(1, len(top5))
        metrics.append(
            {
                "profile_id": profile_id,
                "test_examples": len(rows),
                "test_positives": positives,
                "precision_at_3": round(precision_at_3, 4),
                "recall_at_5": round(recall_at_5, 4),
                "false_positive_rate_top_5": round(false_positive_rate_top_5, 4),
                "top_documents": [
                    {
                        "document_number": row[0].document_number,
                        "label": row[0].label,
                        "target": row[0].target,
                        "hard_negative": row[0].hard_negative,
                        "score": round(row[1], 4),
                    }
                    for row in top5
                ],
            }
        )
    return metrics


def _market_evaluation_summary(
    examples: list[MarketExample],
    train_examples: list[MarketExample],
    test_examples: list[MarketExample],
    test_scores: list[float],
    model: Any,
) -> dict[str, Any]:
    test_targets = market_target_vector(test_examples)
    positive_count = sum(example.target for example in examples)
    test_positive_count = sum(test_targets)
    base_positive_rate = _safe_ratio(test_positive_count, len(test_examples))
    top_decile_size = max(1, int(len(test_examples) * 0.1))
    top_decile_precision = _precision_at_k(test_examples, test_scores, top_decile_size)
    roc_auc = _safe_roc_auc(test_targets, test_scores)
    return {
        "status": "trained",
        "purpose": "Temporal award-history market-fit model trained on older awards and tested on recent awards.",
        "examples": len(examples),
        "training_examples": len(train_examples),
        "test_examples": len(test_examples),
        "positive_examples": positive_count,
        "negative_examples": len(examples) - positive_count,
        "hard_negative_examples": sum(1 for example in examples if example.hard_negative),
        "training_award_date_range": _market_date_range(train_examples),
        "test_award_date_range": _market_date_range(test_examples),
        "test_positive_rate": round(base_positive_rate, 4),
        "average_precision": round(_safe_average_precision(test_targets, test_scores), 4),
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "precision_at_10": round(_precision_at_k(test_examples, test_scores, 10), 4),
        "recall_at_10": round(_recall_at_k(test_examples, test_scores, 10), 4),
        "precision_at_20": round(_precision_at_k(test_examples, test_scores, 20), 4),
        "hard_negative_rate_top_20": round(_hard_negative_rate_at_k(test_examples, test_scores, 20), 4),
        "top_decile_precision": round(top_decile_precision, 4),
        "top_decile_lift": round(top_decile_precision / base_positive_rate, 2) if base_positive_rate else None,
        "top_weighted_features": _top_weighted_features(model, MARKET_FEATURE_NAMES),
        "profile_metrics": _market_profile_metrics(test_examples, test_scores),
        "supplier_intelligence": _supplier_intelligence(examples),
    }


def _market_profile_metrics(examples: list[MarketExample], scores: list[float]) -> list[dict[str, Any]]:
    by_profile: dict[str, list[tuple[MarketExample, float]]] = {}
    for example, score in zip(examples, scores):
        by_profile.setdefault(example.profile_id, []).append((example, score))

    metrics = []
    for profile_id, rows in sorted(by_profile.items()):
        rows.sort(key=lambda row: row[1], reverse=True)
        targets = [row[0].target for row in rows]
        profile_scores = [row[1] for row in rows]
        positives = sum(targets)
        metrics.append(
            {
                "profile_id": profile_id,
                "test_examples": len(rows),
                "test_positives": positives,
                "precision_at_10": round(_precision_at_k([row[0] for row in rows], profile_scores, 10), 4),
                "recall_at_10": round(_recall_at_k([row[0] for row in rows], profile_scores, 10), 4),
                "average_precision": round(_safe_average_precision(targets, profile_scores), 4),
                "top_documents": [
                    {
                        "document_number": row[0].document_number,
                        "supplier": row[0].supplier,
                        "award_date": row[0].award_date,
                        "target": row[0].target,
                        "hard_negative": row[0].hard_negative,
                        "score": round(row[1], 4),
                    }
                    for row in rows[:5]
                ],
            }
        )
    return metrics


def _supplier_intelligence(examples: list[MarketExample]) -> list[dict[str, Any]]:
    by_profile: dict[str, list[MarketExample]] = {}
    for example in examples:
        if example.target:
            by_profile.setdefault(example.profile_id, []).append(example)

    summaries = []
    for profile_id, rows in sorted(by_profile.items()):
        supplier_counts = {}
        for example in rows:
            supplier = example.supplier.strip() or "Unknown supplier"
            supplier_counts[supplier] = supplier_counts.get(supplier, 0) + 1
        top_suppliers = sorted(supplier_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        total = len(rows)
        summaries.append(
            {
                "profile_id": profile_id,
                "fit_awards": total,
                "distinct_fit_suppliers": len(supplier_counts),
                "repeat_supplier_count": sum(1 for count in supplier_counts.values() if count > 1),
                "top_supplier_share": round(top_suppliers[0][1] / total, 4) if total and top_suppliers else 0.0,
                "top_suppliers": [
                    {"supplier": supplier, "fit_awards": count}
                    for supplier, count in top_suppliers
                ],
            }
        )
    return summaries


def _precision_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    if not rows:
        return 0.0
    return sum(row[0].target for row in rows) / len(rows)


def _recall_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    positives = sum(example.target for example in examples)
    if positives <= 0:
        return 0.0
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    return sum(row[0].target for row in rows) / positives


def _hard_negative_rate_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    if not rows:
        return 0.0
    return sum(1 for row in rows if row[0].hard_negative) / len(rows)


def _market_date_range(examples: list[MarketExample]) -> dict[str, str | None]:
    dates = sorted(example.award_date for example in examples if example.award_date)
    if not dates:
        return {"start": None, "end": None}
    return {"start": dates[0], "end": dates[-1]}


def _top_weighted_features(
    model: Any,
    feature_names: list[str] = FEATURE_NAMES,
    limit: int = 8,
) -> list[dict[str, Any]]:
    classifier = model.named_steps["logisticregression"]
    weights = classifier.coef_[0]
    ranked = sorted(
        zip(feature_names, weights),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )
    return [
        {"feature": name, "weight": round(float(weight), 4)}
        for name, weight in ranked[:limit]
    ]


def _safe_average_precision(targets: list[int], scores: list[float]) -> float:
    from sklearn.metrics import average_precision_score

    if not targets or len(set(targets)) < 2:
        return 0.0
    return float(average_precision_score(targets, scores))


def _safe_roc_auc(targets: list[int], scores: list[float]) -> float | None:
    from sklearn.metrics import roc_auc_score

    if not targets or len(set(targets)) < 2:
        return None
    return float(roc_auc_score(targets, scores))


def _weighted_metric(profile_metrics: list[dict[str, Any]], key: str) -> float:
    total_weight = sum(max(1, int(item["test_examples"])) for item in profile_metrics)
    if total_weight <= 0:
        return 0.0
    return sum(float(item[key]) * max(1, int(item["test_examples"])) for item in profile_metrics) / total_weight


def _shortlist_reduction_percent(naive_count: int, actionable_count: int) -> float:
    if naive_count <= 0:
        return 0.0
    return round(max(0.0, 1.0 - actionable_count / naive_count) * 100, 1)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _write_model_artifact(
    output_path: Path,
    summary: dict[str, Any],
    model: Any,
    market_model: Any | None,
    value_model: Any | None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "models": {
            "shadow_fit_ranker": _model_artifact(model, FEATURE_NAMES),
            "award_history_market_model": _model_artifact(market_model, MARKET_FEATURE_NAMES)
            if market_model is not None else None,
            "award_value_model": _model_artifact(value_model, VALUE_FEATURE_NAMES)
            if value_model is not None else None,
        },
        "evaluation": summary,
    }
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def _model_artifact(model: Any, feature_names: list[str]) -> dict[str, Any]:
    if hasattr(model, "named_steps") and "logisticregression" in model.named_steps:
        classifier = model.named_steps["logisticregression"]
        return {
            "model_type": "sklearn.pipeline.StandardScaler+LogisticRegression",
            "feature_names": feature_names,
            "intercept": [float(value) for value in classifier.intercept_],
            "coefficients": [float(value) for value in classifier.coef_[0]],
        }
    feature_importances = getattr(model, "feature_importances_", None)
    return {
        "model_type": f"{model.__class__.__module__}.{model.__class__.__name__}",
        "feature_names": feature_names,
        "feature_importances": [float(value) for value in feature_importances]
        if feature_importances is not None else [],
    }


def _stable_bucket(value: str, modulo: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % max(1, modulo)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train and evaluate a shadow local bid-fit ranker over structured procurement features."
    )
    parser.add_argument("--offline", action="store_true", help="Use cached Toronto Open Data without live refresh.")
    parser.add_argument("--profiles", default="all", help="all or comma-separated supported profile ids.")
    parser.add_argument("--as-of", default=DEFAULT_AS_OF.isoformat(), help="Evaluation date. Default: 2026-05-30")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    parser.add_argument("--output", default="", help="Optional path to write a JSON model artifact.")
    args = parser.parse_args()

    as_of = parse_date(args.as_of)
    if as_of is None:
        print(f"FAIL: invalid --as-of date: {args.as_of}", file=sys.stderr)
        return 2

    output_path = Path(args.output) if args.output else None
    try:
        summary = train_bid_ranker(
            profile_selector=args.profiles,
            offline=args.offline,
            as_of=as_of,
            output_path=output_path,
        )
    except (RuntimeError, ValueError, ProcurementDataUnavailable) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_human_summary(summary, output_path)
    return 0


def _print_human_summary(summary: dict[str, Any], output_path: Path | None) -> None:
    print("Local Bid-Fit Ranker Evaluation")
    print(
        f"Data: {summary['data_mode']} | as of {summary['as_of']} | "
        f"profiles={', '.join(summary['profiles'])}"
    )
    for warning in summary.get("warnings") or []:
        print(f"Warning: {warning}")
    print(
        "Examples: "
        f"{summary['examples']} total "
        f"({summary['current_open_bid_examples']} current + {summary['historical_award_examples']} historical), "
        f"{summary['positive_examples']} positive, "
        f"{summary['hard_negative_examples']} hard negative"
    )
    print(
        "Metrics: "
        f"precision@3={summary['precision_at_3']:.3f}, "
        f"recall@5={summary['recall_at_5']:.3f}, "
        f"top-5 false-positive rate={summary['false_positive_rate_top_5']:.3f}, "
        f"average precision={summary['average_precision']:.3f}"
    )
    baseline = summary["naive_baseline"]
    print(
        "Naive baseline: "
        f"{baseline['naive_keyword_candidates']} keyword candidates -> "
        f"{baseline['bid_engine_actionable']} bid-engine actionable, "
        f"{baseline['skipped_false_positives']} false positives skipped, "
        f"{baseline['shortlist_reduction_percent']:.1f}% reduction"
    )
    print("Top feature weights:")
    for item in summary["top_weighted_features"]:
        print(f"  {item['feature']}: {item['weight']}")
    market = summary.get("award_history_model") or {}
    if market.get("status") == "trained":
        train_range = market.get("training_award_date_range") or {}
        test_range = market.get("test_award_date_range") or {}
        print("")
        print("Award-history market model:")
        print(
            "  Temporal holdout: "
            f"train {train_range.get('start')} to {train_range.get('end')}, "
            f"test {test_range.get('start')} to {test_range.get('end')}"
        )
        print(
            "  Examples: "
            f"{market['examples']} total, {market['positive_examples']} positive, "
            f"{market['hard_negative_examples']} hard negative"
        )
        lift = market.get("top_decile_lift")
        lift_text = f"{lift:.2f}x" if lift is not None else "n/a"
        print(
            "  Metrics: "
            f"precision@10={market['precision_at_10']:.3f}, "
            f"recall@10={market['recall_at_10']:.3f}, "
            f"top-decile lift={lift_text}, "
            f"average precision={market['average_precision']:.3f}"
        )
        value_model = market.get("value_model") or {}
        if value_model.get("status") == "trained":
            print(
                "  Award value model: "
                f"{value_model.get('mode')} | MAE ${float(value_model.get('mae') or 0):,.0f} | "
                f"MAPE {float(value_model.get('mape') or 0):.1%}"
            )
        print("  Market feature weights:")
        for item in market["top_weighted_features"][:6]:
            print(f"    {item['feature']}: {item['weight']}")
        print("  Supplier concentration:")
        for item in market["supplier_intelligence"][:3]:
            top_supplier = item["top_suppliers"][0] if item["top_suppliers"] else {}
            print(
                f"    {item['profile_id']}: {item['fit_awards']} fit awards, "
                f"{item['distinct_fit_suppliers']} suppliers, "
                f"top supplier share {item['top_supplier_share']:.1%} "
                f"({top_supplier.get('supplier', 'none')})"
            )
    if output_path is not None:
        print(f"Model artifact written: {output_path}")


if __name__ == "__main__":
    raise SystemExit(main())
