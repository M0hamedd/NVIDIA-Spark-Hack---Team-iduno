from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from sparkterritory.config import NIM_API_KEY, NIM_BASE_URL, NIM_MODEL, SCORE_WEIGHTS
from sparkterritory.scoring import BusinessProfile


class NemotronClient:
    def __init__(
        self,
        base_url: str = NIM_BASE_URL,
        model: str = NIM_MODEL,
        api_key: str = NIM_API_KEY,
        timeout_seconds: int = 45,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def generate_report(
        self,
        profile: BusinessProfile,
        ranked_neighbourhoods: list[dict[str, Any]],
        future_expansion: list[dict[str, Any]],
        downtown_tradeoff: str,
        metadata: dict[str, Any],
    ) -> dict[str, str]:
        prompt = self._build_prompt(profile, ranked_neighbourhoods, future_expansion, downtown_tradeoff, metadata)
        try:
            text = self._chat_completion(prompt)
            if text:
                return {"mode": "nemotron_nim", "model": self.model, "report": text}
        except Exception as exc:
            return {
                "mode": "deterministic_fallback_no_nim",
                "model": self.model,
                "report": deterministic_report(profile, ranked_neighbourhoods, future_expansion, downtown_tradeoff, str(exc)),
            }
        return {
            "mode": "deterministic_fallback_no_nim",
            "model": self.model,
            "report": deterministic_report(profile, ranked_neighbourhoods, future_expansion, downtown_tradeoff, "Empty NIM response"),
        }

    def _chat_completion(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 850,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a local market expansion analyst for Toronto service businesses. "
                        "Use only the provided scored evidence. Do not invent facts. "
                        "Every recommendation must cite the supplied evidence."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def _build_prompt(
        self,
        profile: BusinessProfile,
        ranked_neighbourhoods: list[dict[str, Any]],
        future_expansion: list[dict[str, Any]],
        downtown_tradeoff: str,
        metadata: dict[str, Any],
    ) -> str:
        compact_targets = [_compact_neighbourhood(item) for item in ranked_neighbourhoods]
        compact_future = [_compact_neighbourhood(item) for item in future_expansion]
        return json.dumps(
            {
                "task": "Create a concise 30-day market expansion plan for a Toronto commercial building services business.",
                "business_profile": asdict(profile),
                "score_weights": SCORE_WEIGHTS,
                "top_targets_now": compact_targets,
                "future_expansion_targets": compact_future,
                "downtown_tradeoff": downtown_tradeoff,
                "metadata": metadata,
                "required_output": [
                    "Best first territory and why",
                    "30-day action plan",
                    "Future expansion timing",
                    "Risks or caveats",
                ],
            },
            indent=2,
        )


def deterministic_report(
    profile: BusinessProfile,
    ranked_neighbourhoods: list[dict[str, Any]],
    future_expansion: list[dict[str, Any]],
    downtown_tradeoff: str,
    reason: str = "NIM endpoint unavailable",
) -> str:
    first = ranked_neighbourhoods[0] if ranked_neighbourhoods else None
    if not first:
        return f"NEMOTRON FALLBACK: No scored neighbourhoods were available. Reason: {reason}"
    lines = [
        "NEMOTRON FALLBACK REPORT",
        f"Reason local NIM was not used: {reason}",
        "",
        f"Best first zone: {first['name']} ({first['overall_score']}/100).",
        "Evidence:",
    ]
    lines.extend(f"- {item}" for item in first["evidence"][:3])
    lines.extend(
        [
            "",
            "30-day action plan:",
            f"- Week 1: Build a prospect list in {first['name']} around condo, apartment, commercial, and renovation-heavy properties.",
            "- Week 2: Offer post-construction exterior service and recurring seasonal packages.",
            "- Week 3: Cluster jobs by street or building manager to protect a small crew's travel time.",
            "- Week 4: Re-score with completed jobs and expand into the next two highest-scoring areas.",
            "",
            "Future expansion targets:",
        ]
    )
    if future_expansion:
        lines.extend(f"- {item['name']}: future growth {item['future_growth_score']}/100." for item in future_expansion)
    else:
        lines.append("- No separate future expansion targets were produced.")
    lines.extend(["", f"Downtown tradeoff: {downtown_tradeoff}"])
    return "\n".join(lines)


def _compact_neighbourhood(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "district": item["district"],
        "overall_score": item["overall_score"],
        "current_demand_score": item["current_demand_score"],
        "future_growth_score": item["future_growth_score"],
        "customer_fit_score": item["customer_fit_score"],
        "growth_momentum_score": item["growth_momentum_score"],
        "operational_feasibility_score": item["operational_feasibility_score"],
        "evidence": item["evidence"],
        "recommended_action": item["recommended_action"],
    }
