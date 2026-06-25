from pathlib import Path

import pytest

from datasentry.errors import KnowledgeError
from datasentry.knowledge import KnowledgeIndex


def _write_knowledge_tree(
    tmp_path: Path,
    *,
    topic_filename: str = "03-jobs-and-lineage.md",
) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    if "/" not in topic_filename and topic_filename != "missing.md":
        (root / topic_filename).write_text("# 任务、Topic与数据血缘\n", encoding="utf-8")
    (root / "07-runtime-baseline-2026-06-25.md").write_text(
        "# 历史运行基线\n",
        encoding="utf-8",
    )
    (root / "INDEX.md").write_text(
        "\n".join(
            [
                "# 知识导航",
                "",
                "## 文档地图",
                "",
                "| 文档 | 内容 | 典型问题 |",
                "|---|---|---|",
                f"| [{topic_filename}]({topic_filename}) | 任务和血缘 | K线为什么不更新? |",
                (
                    "| [07-runtime-baseline-2026-06-25.md]"
                    "(07-runtime-baseline-2026-06-25.md) | 历史快照 | 上次状态? |"
                ),
                "",
                "## 快速路由",
                "",
                "| 用户意图 | 必读 | 按需追加 |",
                "|---|---|---|",
                "| 数据延迟/断流 | 03 | 07 |",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_index_parses_document_map_and_routes(tmp_path: Path) -> None:
    root = _write_knowledge_tree(tmp_path)

    index = KnowledgeIndex.load(root)

    assert index.topic("03").path == root / "03-jobs-and-lineage.md"
    assert index.topic("03").title == "任务、Topic与数据血缘"
    assert index.topic("07").historical is True
    assert index.route("数据延迟/断流").required_topic_ids == ("03",)
    assert index.route("数据延迟/断流").optional_topic_ids == ("07",)


@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("../outside.md", "knowledge.path_outside_root"),
        ("missing.md", "knowledge.topic_missing"),
    ],
)
def test_index_rejects_unsafe_or_missing_topic(
    tmp_path: Path,
    filename: str,
    code: str,
) -> None:
    root = _write_knowledge_tree(tmp_path, topic_filename=filename)

    with pytest.raises(KnowledgeError) as raised:
        KnowledgeIndex.load(root)

    assert raised.value.code == code


def test_index_rejects_duplicate_topic_id(tmp_path: Path) -> None:
    root = _write_knowledge_tree(tmp_path)
    duplicate = root / "03-duplicate.md"
    duplicate.write_text("# 重复主题\n", encoding="utf-8")
    index_path = root / "INDEX.md"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "| [07-runtime",
            "| [03-duplicate.md](03-duplicate.md) | 重复 | 重复? |\n| [07-runtime",
        ),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeError) as raised:
        KnowledgeIndex.load(root)

    assert raised.value.code == "knowledge.duplicate_topic"


def test_index_rejects_route_to_unknown_topic(tmp_path: Path) -> None:
    root = _write_knowledge_tree(tmp_path)
    index_path = root / "INDEX.md"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "| 数据延迟/断流 | 03 | 07 |",
            "| 数据延迟/断流 | 99 | 07 |",
        ),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeError) as raised:
        KnowledgeIndex.load(root)

    assert raised.value.code == "knowledge.route_topic_missing"
