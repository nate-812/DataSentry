"""知识路由和血缘使用的不可变模型。"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeModel(BaseModel):
    """知识层严格不可变模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QuestionType(StrEnum):
    """M1 支持的确定性问题类型。"""

    DATA_STALE = "data_stale"
    COMPONENT_DOWN = "component_down"
    LATENCY_BACKPRESSURE = "latency_backpressure"
    CONFIGURATION = "configuration"


class KnowledgeTopic(KnowledgeModel):
    """由 INDEX 文档地图声明的主题。"""

    topic_id: str = Field(pattern=r"^\d{2}$")
    path: Path
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    typical_questions: tuple[str, ...] = ()
    historical: bool = False


class KnowledgeReference(KnowledgeModel):
    """诊断结果中安全暴露的知识引用。"""

    topic_id: str
    path: str
    title: str
    historical: bool


class KnowledgeRoute(KnowledgeModel):
    """INDEX 快速路由中的原始主题组合。"""

    intent: str
    required_topic_ids: tuple[str, ...]
    optional_topic_ids: tuple[str, ...] = ()


class RouteMatch(KnowledgeModel):
    """问题分类与本次实际加载的主题。"""

    question_type: QuestionType
    required_topic_ids: tuple[str, ...]
    optional_topic_ids: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...]


class LineageNodeKind(StrEnum):
    """血缘节点类别。"""

    EXTERNAL = "external"
    SERVICE = "service"
    TOPIC = "topic"
    JOB = "job"
    TABLE = "table"
    KEY_PATTERN = "key_pattern"
    API = "api"


class LineageNode(KnowledgeModel):
    """StreamLake 稳定血缘节点。"""

    node_id: str
    kind: LineageNodeKind
    component: str
    label: str


class LineageEdge(KnowledgeModel):
    """两个稳定节点之间的有向关系。"""

    source_id: str
    target_id: str
    relation: str
