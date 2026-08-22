"""Model routing policy, PRD section 13.4.

Routing is configuration held in the gateway and mirrored in the platform. A
change to routing is an audited administrative event requiring approval from
Legal. Failover between providers is permitted only between routes of equal or
stricter class.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.domain.enums import CLASS_RANK, DataClass


class RouteRefused(PermissionError):
    """Raised when no permitted route exists for the data class in question."""

@dataclass(frozen=True)
class ModelRoute:
    name: str
    provider: str
    model: str
    max_data_class: DataClass
    no_training: bool
    zero_retention: bool
    redaction_required: bool
    self_hosted: bool = False
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0

ROUTES: dict[str, ModelRoute] = {
    "enterprise-lg": ModelRoute(
        name="enterprise-lg",
        provider="openai",
        model=settings.dsnlai_ai_default_model,
        max_data_class=DataClass.CONFIDENTIAL,
        no_training=True,
        zero_retention=True,
        redaction_required=True,
        input_cost_per_mtok=settings.dsnlai_ai_input_cost_per_mtok,
        output_cost_per_mtok=settings.dsnlai_ai_output_cost_per_mtok,
    ),
    "local-open-weights": ModelRoute(
        name="local-open-weights",
        provider="self_hosted",
        model=settings.dsnlai_ai_local_model,
        max_data_class=DataClass.RESTRICTED,
        no_training=True,
        zero_retention=True,
        redaction_required=False,
        self_hosted=True,
    ),
    "offline-deterministic": ModelRoute(
        name="offline-deterministic",
        provider="offline",
        model="offline-deterministic",
        max_data_class=DataClass.RESTRICTED,
        no_training=True,
        zero_retention=True,
        redaction_required=False,
        self_hosted=True,
    ),
}

POLICY: dict[DataClass, list[str]] = {
    DataClass.PUBLIC: ["enterprise-lg", "local-open-weights", "offline-deterministic"],
    DataClass.INTERNAL: ["enterprise-lg", "local-open-weights", "offline-deterministic"],
    DataClass.CONFIDENTIAL: ["enterprise-lg", "local-open-weights", "offline-deterministic"],
    DataClass.RESTRICTED: ["local-open-weights", "offline-deterministic"],
}

def permitted(route: ModelRoute, data_class: DataClass) -> bool:
    return CLASS_RANK[data_class] <= CLASS_RANK[route.max_data_class]

def select_route(
    data_class: DataClass,
    available: set[str],
    preferred: str | None = None,
) -> ModelRoute:
    """Choose the route for a call.

    ``available`` is the set of route names whose provider is configured and
    reachable. A preferred route is honoured only if it is permitted for the
    class, so a capability cannot widen its own reach.
    """
    order = POLICY[data_class]
    if preferred and preferred in order:
        order = [preferred] + [name for name in order if name != preferred]

    for name in order:
        route = ROUTES[name]
        if name in available and permitted(route, data_class):
            return route

    raise RouteRefused(
        f"No permitted route is available for {data_class.value} content. "
        "Restricted content requires a self-hosted model or a documented exception "
        "approved by Legal."
    )

def failover_candidates(current: ModelRoute, data_class: DataClass, available: set[str]
                        ) -> list[ModelRoute]:
    """Failover is permitted only to a route of equal or stricter class."""
    return [
        ROUTES[name]
        for name in POLICY[data_class]
        if name in available
        and name != current.name
        and CLASS_RANK[ROUTES[name].max_data_class] <= CLASS_RANK[current.max_data_class]
    ]
