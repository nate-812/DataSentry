"""按显式关键词执行可重复的问题路由。"""

from dataclasses import dataclass

from datasentry.errors import KnowledgeError
from datasentry.knowledge.index import KnowledgeIndex
from datasentry.knowledge.models import QuestionType, RouteMatch


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    question_type: QuestionType
    keywords: tuple[str, ...]
    required_topic_ids: tuple[str, ...]
    optional_topic_ids: tuple[str, ...] = ()


ROUTE_POLICIES = (
    RoutePolicy(
        QuestionType.CONFIGURATION,
        ("配置", "参数", "环境变量", "没生效", "阈值"),
        ("04", "03"),
        ("02",),
    ),
    RoutePolicy(
        QuestionType.LATENCY_BACKPRESSURE,
        ("延迟", "反压", "backpressure", "checkpoint", "积压", "lag"),
        ("03", "04"),
        ("08",),
    ),
    RoutePolicy(
        QuestionType.COMPONENT_DOWN,
        ("宕机", "挂了", "没启动", "未运行", "连接不上", "不可用"),
        ("02", "06"),
        ("08",),
    ),
    RoutePolicy(
        QuestionType.DATA_STALE,
        ("不更新", "没数据", "断流", "新鲜度", "停止推进"),
        ("03", "04"),
        ("02",),
    ),
)


class KnowledgeRouter:
    """将用户问题映射为 M1 支持的问题类型和知识主题。"""

    def __init__(self, index: KnowledgeIndex) -> None:
        self._index = index

    def route(self, question: str) -> RouteMatch:
        normalized = question.casefold()
        for policy in ROUTE_POLICIES:
            matched = tuple(
                keyword for keyword in policy.keywords if keyword.casefold() in normalized
            )
            if not matched:
                continue
            required = list(policy.required_topic_ids)
            if any(keyword in normalized for keyword in ("历史", "上次", "基线")):
                required.append("07")
            selected = tuple(dict.fromkeys(required))[:3]
            for topic_id in selected + policy.optional_topic_ids:
                self._index.topic(topic_id)
            return RouteMatch(
                question_type=policy.question_type,
                required_topic_ids=selected,
                optional_topic_ids=policy.optional_topic_ids,
                matched_keywords=matched,
            )
        raise KnowledgeError(
            code="knowledge.question_unclassified",
            message="当前问题无法映射到 M1 支持的诊断类型",
        )
