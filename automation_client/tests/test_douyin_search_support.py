from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.douyin_search_support import collect_matched_author_elements


class FakeDriver:
    def __init__(self, page_source: str) -> None:
        self.page_source = page_source
        self.capabilities = {}


class FakeActions:
    def __init__(self, page_source: str) -> None:
        self.driver = FakeDriver(page_source)


def test_collect_matched_author_elements_matches_like_in_same_column() -> None:
    page_source = """
    <hierarchy width="1080" height="2400">
      <node resource-id="com.ss.android.ugc.aweme:id/+j" text="left doctor"
        content-desc="" bounds="[120,1000][360,1040]" />
      <node resource-id="like-left" text=""
        content-desc="已点赞，喜欢11，按钮" bounds="[414,1000][510,1080]" />
      <node resource-id="com.ss.android.ugc.aweme:id/+j" text="target doctor"
        content-desc="" bounds="[654,1000][900,1040]" />
      <node resource-id="like-right" text=""
        content-desc="未点赞，喜欢281，按钮" bounds="[927,1000][1044,1080]" />
    </hierarchy>
    """

    items = collect_matched_author_elements(FakeActions(page_source), target_author="target")

    assert len(items) == 1
    assert items[0][0] == "target doctor"
    assert items[0][1] is False
    assert items[0][2] == "未点赞，喜欢281，按钮"
