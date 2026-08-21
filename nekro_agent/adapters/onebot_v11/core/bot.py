from typing import Dict, List, Optional

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot


def get_all_bots() -> Dict[str, OneBotV11Bot]:
    """获取当前所有已连接的 OneBot V11 Bot 实例

    Returns:
        Dict[str, OneBotV11Bot]: self_id -> Bot 实例
    """
    return {
        str(bot_instance.self_id): bot_instance
        for bot_instance in get_bots().values()
        if isinstance(bot_instance, OneBotV11Bot)
    }


def get_online_self_ids() -> List[str]:
    """获取当前在线的 QQ 号列表"""
    return sorted(get_all_bots().keys())


def get_bot(self_id: Optional[str] = None) -> OneBotV11Bot:
    """获取 OneBot V11 Bot 实例

    Args:
        self_id: 指定 QQ 号。为空时返回默认账号（优先取配置的 BOT_QQ，
            其次取任意一个在线账号），以兼容单账号场景下的历史调用。

    Raises:
        RuntimeError: 无可用 Bot 实例，或指定的 QQ 号不在线
    """
    all_bots = get_all_bots()
    if not all_bots:
        raise RuntimeError("No OneBot V11 bot instance found.")

    if self_id:
        bot = all_bots.get(str(self_id))
        if bot is None:
            raise RuntimeError(
                f"OneBot V11 bot {self_id} is not connected. "
                f"Online accounts: {', '.join(sorted(all_bots)) or 'none'}",
            )
        return bot

    return _get_default_bot(all_bots)


def _get_default_bot(all_bots: Dict[str, OneBotV11Bot]) -> OneBotV11Bot:
    """选取默认账号

    优先级: WebUI 标记的默认账号 > 配置的 BOT_QQ > 任意在线账号。
    WebUI 的标记在内存中缓存（由 account_manager 写入），避免在同步函数里查库。
    """
    marked = get_cached_default_self_id()
    if marked and marked in all_bots:
        return all_bots[marked]

    preferred = _get_preferred_self_id()
    if preferred and preferred in all_bots:
        return all_bots[preferred]
    return next(iter(all_bots.values()))


_cached_default_self_id: Optional[str] = None
"""WebUI 标记的默认账号 QQ 号缓存

`get_bot()` 是同步函数，无法 await 查库，故由 account_manager 在读写默认账号时
维护此缓存。启动时由 `refresh_default_account_cache()` 从数据库载入。
"""


def get_cached_default_self_id() -> Optional[str]:
    """读取缓存的默认账号 QQ 号"""
    return _cached_default_self_id


def set_cached_default_self_id(self_id: Optional[str]) -> None:
    """更新缓存的默认账号 QQ 号（由 account_manager 调用）"""
    global _cached_default_self_id  # noqa: PLW0603 - 同步函数需要读取的进程级缓存
    _cached_default_self_id = str(self_id) if self_id else None


def _get_preferred_self_id() -> Optional[str]:
    """读取配置中作为默认账号的 QQ 号（读取失败时静默回退）"""
    try:
        from nekro_agent.adapters import get_adapter

        bot_qq = getattr(get_adapter("onebot_v11").config, "BOT_QQ", "")
        return str(bot_qq).strip() or None
    except Exception:  # noqa: BLE001 - 适配器未加载时不应阻断取 Bot
        return None
