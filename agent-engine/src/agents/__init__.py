"""
Agent registry — maps agent class names (as stored in agent_definitions.class_name)
to their concrete Python classes.

The orchestrator uses this registry to instantiate agents dynamically
from their DB definitions without hard-coding imports in the pipeline.
"""
from __future__ import annotations

from typing import Type

from src.agents.base import BaseAgent
from src.agents.data import DataQualityAgent, MarketDataAgent
from src.agents.analysis import MomentumAgent, PriceActionAgent, TechnicalAnalysisAgent
from src.agents.critique import ContrarianAgent, ManipulationDetectionAgent
from src.agents.risk import ChiefRiskOfficerAgent, RewardPlanAgent, RiskAuditorAgent
from src.agents.security import PromptInjectionDefenseAgent, SecurityGuardianAgent
from src.agents.system_evolution import SystemEvolutionAgent

AGENT_REGISTRY: dict[str, Type[BaseAgent]] = {
    "MarketDataAgent": MarketDataAgent,
    "DataQualityAgent": DataQualityAgent,
    "TechnicalAnalysisAgent": TechnicalAnalysisAgent,
    "PriceActionAgent": PriceActionAgent,
    "MomentumAgent": MomentumAgent,
    "ContrarianAgent": ContrarianAgent,
    "ManipulationDetectionAgent": ManipulationDetectionAgent,
    "RiskAuditorAgent": RiskAuditorAgent,
    "RewardPlanAgent": RewardPlanAgent,
    "ChiefRiskOfficerAgent": ChiefRiskOfficerAgent,
    "SecurityGuardianAgent": SecurityGuardianAgent,
    "PromptInjectionDefenseAgent": PromptInjectionDefenseAgent,
    "SystemEvolutionAgent": SystemEvolutionAgent,
}


def get_agent_class(class_name: str) -> Type[BaseAgent]:
    """
    Returns the agent class for a given class_name string.
    Raises KeyError with a helpful message if unknown.
    """
    if class_name not in AGENT_REGISTRY:
        raise KeyError(
            f"Unknown agent class '{class_name}'. "
            f"Available: {sorted(AGENT_REGISTRY.keys())}"
        )
    return AGENT_REGISTRY[class_name]


__all__ = [
    "AGENT_REGISTRY",
    "get_agent_class",
    "BaseAgent",
    "MarketDataAgent",
    "DataQualityAgent",
    "TechnicalAnalysisAgent",
    "PriceActionAgent",
    "MomentumAgent",
    "ContrarianAgent",
    "ManipulationDetectionAgent",
    "RiskAuditorAgent",
    "RewardPlanAgent",
    "ChiefRiskOfficerAgent",
    "SecurityGuardianAgent",
    "PromptInjectionDefenseAgent",
    "SystemEvolutionAgent",
]
