"""解析受控 Markdown 知识索引。"""

import re
from pathlib import Path

from datasentry.errors import KnowledgeError
from datasentry.knowledge.models import KnowledgeRoute, KnowledgeTopic

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TOPIC_ID_PATTERN = re.compile(r"(?<!\d)(\d{2})(?!\d)")


def _error(code: str, message: str) -> KnowledgeError:
    return KnowledgeError(code=code, message=message)


def _table_rows(text: str, heading: str) -> list[list[str]]:
    lines = text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as error:
        raise _error("knowledge.invalid_index", f"知识索引缺少 {heading} 章节") from error
    rows: list[list[str]] = []
    in_table = False
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if not line.strip().startswith("|"):
            if in_table and rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(cell.replace("-", "").replace(":", "") == "" for cell in cells):
            in_table = True
            continue
        if not in_table:
            in_table = True
            continue
        rows.append(cells)
    if not rows:
        raise _error("knowledge.invalid_index", f"{heading} 表格没有数据")
    return rows


def _topic_ids(value: str) -> tuple[str, ...]:
    return tuple(TOPIC_ID_PATTERN.findall(value))


def _first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    raise _error("knowledge.invalid_index", "主题文档缺少一级标题")


class KnowledgeIndex:
    """经过路径和引用校验的知识主题索引。"""

    def __init__(
        self,
        root: Path,
        topics: dict[str, KnowledgeTopic],
        routes: dict[str, KnowledgeRoute],
    ) -> None:
        self.root = root
        self._topics = topics
        self._routes = routes

    @classmethod
    def load(cls, root: Path) -> "KnowledgeIndex":
        resolved_root = root.resolve()
        index_path = resolved_root / "INDEX.md"
        if not index_path.is_file():
            raise _error("knowledge.index_missing", "知识库根目录缺少 INDEX.md")
        text = index_path.read_text(encoding="utf-8")
        topics: dict[str, KnowledgeTopic] = {}
        for row in _table_rows(text, "## 文档地图"):
            if len(row) < 3:
                raise _error("knowledge.invalid_index", "文档地图表格列数无效")
            match = LINK_PATTERN.search(row[0])
            if match is None:
                raise _error("knowledge.invalid_index", "文档地图包含无效链接")
            filename = match.group(2)
            candidate = (resolved_root / filename).resolve()
            if not candidate.is_relative_to(resolved_root):
                raise _error("knowledge.path_outside_root", "知识主题路径超出知识库根目录")
            if not candidate.is_file():
                raise _error("knowledge.topic_missing", "知识索引引用的主题文档不存在")
            topic_match = re.match(r"^(\d{2})-", candidate.name)
            if topic_match is None:
                raise _error("knowledge.invalid_index", "知识主题文件名缺少两位编号")
            topic_id = topic_match.group(1)
            if topic_id in topics:
                raise _error("knowledge.duplicate_topic", "知识索引包含重复主题编号")
            question = row[2].strip('“”" ')
            topics[topic_id] = KnowledgeTopic(
                topic_id=topic_id,
                path=candidate,
                title=_first_heading(candidate),
                summary=row[1],
                typical_questions=(question,) if question else (),
                historical=candidate.name.startswith("07-runtime-baseline-"),
            )
        routes: dict[str, KnowledgeRoute] = {}
        for row in _table_rows(text, "## 快速路由"):
            if len(row) < 3:
                raise _error("knowledge.invalid_index", "快速路由表格列数无效")
            required = _topic_ids(row[1])
            optional = _topic_ids(row[2])
            for topic_id in required + optional:
                if topic_id not in topics:
                    raise _error(
                        "knowledge.route_topic_missing",
                        "快速路由引用了不存在的知识主题",
                    )
            routes[row[0]] = KnowledgeRoute(
                intent=row[0],
                required_topic_ids=required,
                optional_topic_ids=optional,
            )
        return cls(resolved_root, topics, routes)

    def topic(self, topic_id: str) -> KnowledgeTopic:
        try:
            return self._topics[topic_id]
        except KeyError as error:
            raise _error("knowledge.topic_missing", "未找到指定知识主题") from error

    def topic_ids(self) -> tuple[str, ...]:
        return tuple(self._topics)

    def route(self, intent: str) -> KnowledgeRoute:
        try:
            return self._routes[intent]
        except KeyError as error:
            raise _error("knowledge.route_missing", "未找到指定知识路由") from error

    def routes(self) -> tuple[KnowledgeRoute, ...]:
        return tuple(self._routes.values())

    def load_topic_text(self, topic_id: str) -> str:
        return self.topic(topic_id).path.read_text(encoding="utf-8")
