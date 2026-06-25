"""显式有向血缘图及确定性遍历。"""

from collections import deque

from datasentry.errors import LineageError
from datasentry.knowledge.models import LineageEdge, LineageNode


class LineageGraph:
    """经过完整性校验的 StreamLake 有向图。"""

    def __init__(
        self,
        nodes: tuple[LineageNode, ...],
        edges: tuple[LineageEdge, ...],
    ) -> None:
        self._nodes: dict[str, LineageNode] = {}
        for node in nodes:
            if node.node_id in self._nodes:
                raise LineageError(
                    code="lineage.duplicate_node",
                    message="血缘目录包含重复节点",
                )
            self._nodes[node.node_id] = node
        self._adjacency: dict[str, list[str]] = {node_id: [] for node_id in self._nodes}
        for edge in edges:
            if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
                raise LineageError(
                    code="lineage.unknown_node",
                    message="血缘边引用了未知节点",
                )
            self._adjacency[edge.source_id].append(edge.target_id)

    def node(self, node_id: str) -> LineageNode:
        try:
            return self._nodes[node_id]
        except KeyError as error:
            raise LineageError(
                code="lineage.unknown_node",
                message="未找到指定血缘节点",
            ) from error

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
    ) -> tuple[LineageNode, ...]:
        self.node(source_id)
        self.node(target_id)
        queue: deque[tuple[str, ...]] = deque([(source_id,)])
        visited = {source_id}
        while queue:
            path = queue.popleft()
            current = path[-1]
            if current == target_id:
                return tuple(self._nodes[node_id] for node_id in path)
            for next_id in self._adjacency[current]:
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((*path, next_id))
        raise LineageError(
            code="lineage.path_not_found",
            message="指定节点之间不存在血缘路径",
        )
