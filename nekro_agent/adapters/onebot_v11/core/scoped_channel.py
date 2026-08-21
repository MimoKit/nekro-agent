"""OneBot V11 账号作用域 channel_id 编解码

多账号接入后，同一个群可能同时被多个 QQ 账号接入，因此 channel_id 需要携带账号信息，
否则不同账号在同一群的会话会互相串扰。

新格式（带账号作用域）:
    {self_id}:group_{group_id}
    {self_id}:private_{user_id}

旧格式（无账号作用域，单账号时期产生的历史数据）:
    group_{group_id}
    private_{user_id}

两种格式都必须能解析，避免既有会话数据（含历史消息、人设绑定、工作区）失效。
"""

from dataclasses import dataclass
from typing import Optional

SCOPE_SEP = ":"


@dataclass(slots=True)
class ScopedChannel:
    """解析后的频道信息"""

    self_id: Optional[str]
    """账号 QQ 号；旧格式数据为 None"""

    raw_channel_id: str
    """不含账号作用域的频道标识，如 `group_123456`"""

    @property
    def target_id(self) -> str:
        """会话对端的数字 ID（群号或用户 QQ 号）"""
        return self.raw_channel_id.split("_", 1)[1]

    @property
    def target_id_int(self) -> int:
        return int(self.target_id)

    @property
    def is_scoped(self) -> bool:
        return self.self_id is not None


def build_channel_id(self_id: str, raw_channel_id: str) -> str:
    """构造带账号作用域的 channel_id"""
    return f"{self_id}{SCOPE_SEP}{raw_channel_id}"


def parse_channel_id(channel_id: str) -> ScopedChannel:
    """解析 channel_id，自动兼容新旧两种格式"""
    if SCOPE_SEP in channel_id:
        self_id, _, raw = channel_id.partition(SCOPE_SEP)
        if self_id and raw:
            return ScopedChannel(self_id=self_id, raw_channel_id=raw)
    return ScopedChannel(self_id=None, raw_channel_id=channel_id)


def strip_scope(channel_id: str) -> str:
    """去掉账号作用域，得到 `group_xxx` / `private_xxx`

    供需要原始频道标识的既有逻辑使用（如按频道类型判断）。
    """
    return parse_channel_id(channel_id).raw_channel_id


def extract_self_id(channel_id: str) -> Optional[str]:
    """从 channel_id 提取账号 QQ 号；旧格式返回 None"""
    return parse_channel_id(channel_id).self_id


def extract_target_id(channel_id: str) -> int:
    """从 channel_id 提取群号或用户 QQ 号"""
    return parse_channel_id(channel_id).target_id_int
