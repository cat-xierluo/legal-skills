"""技能改名后的历史资产映射。

改名不等于资产消失：旧调用名下的已发布 ZIP 仍然有效，可以作为该技能在
改名后、重新发布前的公开下载入口。但旧名资产只能代表旧版本，绝不能用来
推断当前源码版本已经发布。

规则：
- 只有显式声明的 slug 可以借用旧名资产；
- 旧名资产的版本必须严格低于当前源码版本；
- 使用旧名资产的行必须保留「源码 vX.Y.Z 待发布」标记。

校验器与 README 回写脚本共用本模块，避免两处对同一映射的理解漂移。
"""

from __future__ import annotations


LEGACY_ASSET_IDS: dict[str, tuple[str, ...]] = {
    "judgment-analysis": ("litigation-analysis",),
}


def legacy_asset_ids(skill_id: str) -> tuple[str, ...]:
    """返回该技能被允许借用的旧名 slug；未声明时为空。"""
    return LEGACY_ASSET_IDS.get(skill_id, ())
