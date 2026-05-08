"""Composite health scoring for v2 dashboard."""

from __future__ import annotations

from typing import Dict


class HealthScorer:
    def score(self, conversion: Dict, cost: Dict, cashflow: Dict) -> Dict[str, object]:
        scores = {
            "conversion": self._conversion_score(conversion),
            "cost": self._cost_score(cost),
            "cashflow": self._cashflow_score(cashflow),
        }
        overall = round(scores["conversion"] * 0.35 + scores["cost"] * 0.30 + scores["cashflow"] * 0.35, 1)
        return {
            "overall_score": overall,
            "overall_status": self._status(overall),
            "scores": scores,
            "top_risks": self._top_risks(conversion, cost, cashflow),
        }

    @staticmethod
    def _conversion_score(result: Dict) -> float:
        rates = result.get("stage_rates", {})
        targets = {
            "referral_to_interview": 0.40,
            "interview_to_offer": 0.50,
            "offer_to_onboard": 0.90,
            "onboard_to_paid": 0.90,
            "referral_to_offer": 0.08,
        }
        if not rates:
            return 0.0
        parts = [min(rates.get(k, 0) / target, 1.0) for k, target in targets.items()]
        return round(sum(parts) / len(parts) * 100, 1)

    @staticmethod
    def _cost_score(result: Dict) -> float:
        ratio = result.get("summary", {}).get("cost_revenue_ratio")
        if ratio is None:
            return 30.0
        if ratio <= 0.40:
            return 100.0
        if ratio <= 0.60:
            return 80.0
        if ratio <= 1.0:
            return 55.0
        return 30.0

    @staticmethod
    def _cashflow_score(result: Dict) -> float:
        summary = result.get("summary", {})
        overdue = summary.get("overdue_rate", 0)
        runway = summary.get("cash_runway_months")
        score = 100.0
        if overdue > 0.20:
            score -= min((overdue - 0.20) * 150, 45)
        if runway is not None and runway < 3:
            score -= min((3 - runway) * 15, 45)
        return round(max(score, 0), 1)

    @staticmethod
    def _status(score: float) -> str:
        if score >= 80:
            return "healthy"
        if score >= 60:
            return "warning"
        return "critical"

    @staticmethod
    def _top_risks(conversion: Dict, cost: Dict, cashflow: Dict):
        risks = []
        metric_map = {
            "referral_to_interview": {
                "title": "推荐到一面转化偏低",
                "meaning": "候选人质量、岗位匹配或客户筛选口径存在问题。",
                "suggestion": "复盘最近未进面候选人，校准岗位画像、必备条件和推荐标准。",
            },
            "interview_to_offer": {
                "title": "一面到Offer转化偏低",
                "meaning": "候选人面试后推进不足，可能存在能力不匹配、薪酬不匹配或客户岗位吸引力不足。",
                "suggestion": "建立面试后24小时复盘机制，区分能力不匹配、薪酬不匹配、客户反馈慢和候选人意愿弱。",
            },
            "offer_to_onboard": {
                "title": "Offer到入职转化偏低",
                "meaning": "候选人接受Offer后仍存在反悔、竞品截留、背调/薪酬/入职时间风险。",
                "suggestion": "对已Offer候选人建立入职护航清单，重点跟踪反Offer、离职交接和入职日期。",
            },
            "onboard_to_paid": {
                "title": "入职到回款转化偏低",
                "meaning": "已入职项目没有及时形成回款，可能卡在开票、试用期、客户付款或坏账风险。",
                "suggestion": "按客户和项目拆分未回款原因，优先推动已入职未开票、已开票未回款和逾期应收。",
            },
            "overall": {
                "title": "整体推荐到回款转化偏低",
                "meaning": "从推荐到最终收款的整体效率不足，过程效率、交付质量和回款管理需要联动改善。",
                "suggestion": "优先找出转化最低的顾问、客户和岗位类型，做30天改善目标。",
            },
        }
        for item in conversion.get("health", {}).get("bottlenecks", []):
            meta = metric_map.get(item["metric"], {})
            risks.append(
                {
                    "area": "项目推进效率",
                    "problem": meta.get("title", item["metric"]),
                    "priority": "High",
                    "evidence": f"当前 {item.get('actual', 0) * 100:.1f}% / 健康线 {item.get('threshold', 0) * 100:.1f}%",
                    "meaning": meta.get("meaning", ""),
                    "suggestion": meta.get("suggestion", ""),
                }
            )
        if cost.get("summary", {}).get("cost_revenue_ratio") and cost["summary"]["cost_revenue_ratio"] > 0.60:
            risks.append(
                {
                    "area": "顾问成本",
                    "problem": "成本收入比高于健康线",
                    "priority": "Medium",
                    "evidence": f"当前 {cost['summary']['cost_revenue_ratio'] * 100:.1f}% / 健康线 60.0%",
                    "meaning": "本财年累计顾问成本相对回款偏高，利润率承压。",
                    "suggestion": "结合顾问360画像，区分高潜待兑现、过程改善和PIP/产能调整对象。",
                }
            )
        if cashflow.get("summary", {}).get("risk_level") in ("High", "Medium"):
            risks.append(
                {
                    "area": "现金流压力",
                    "problem": "现金流压力升高",
                    "priority": cashflow["summary"]["risk_level"],
                    "evidence": f"现金跑道 {cashflow.get('summary', {}).get('cash_runway_months', 0):.1f} 个月",
                    "meaning": "当前现金余额相对月成本偏紧，或应收回款压力较高。",
                    "suggestion": "优先处理逾期应收、30天到期应收和大额客户付款节点。",
                }
            )
        return risks[:5]
