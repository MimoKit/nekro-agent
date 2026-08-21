"""OneBot V11 多账号接入 —— 账号作用域与人设解析链测试"""

import importlib.util
import pathlib
from typing import Optional

import pytest

_SC_PATH = pathlib.Path(__file__).resolve().parents[1] / "nekro_agent/adapters/onebot_v11/core/scoped_channel.py"
_spec = importlib.util.spec_from_file_location("_scoped_channel", _SC_PATH)
assert _spec and _spec.loader
scoped_channel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scoped_channel)


class TestScopedChannelId:
    """channel_id 的账号作用域编解码"""

    def test_build_and_parse_group(self):
        cid = scoped_channel.build_channel_id("2249382149", "group_798949533")
        assert cid == "2249382149:group_798949533"

        parsed = scoped_channel.parse_channel_id(cid)
        assert parsed.self_id == "2249382149"
        assert parsed.raw_channel_id == "group_798949533"
        assert parsed.target_id_int == 798949533
        assert parsed.is_scoped is True

    def test_build_and_parse_private(self):
        cid = scoped_channel.build_channel_id("111", "private_222")
        assert scoped_channel.strip_scope(cid) == "private_222"
        assert scoped_channel.extract_target_id(cid) == 222

    @pytest.mark.parametrize("old_id", ["group_798949533", "private_222"])
    def test_legacy_format_still_parses(self, old_id: str):
        """旧格式（单账号时期数据）必须继续可用，否则既有会话/人设/工作区全部失效"""
        parsed = scoped_channel.parse_channel_id(old_id)
        assert parsed.self_id is None
        assert parsed.is_scoped is False
        assert parsed.raw_channel_id == old_id
        assert scoped_channel.strip_scope(old_id) == old_id
        assert scoped_channel.extract_self_id(old_id) is None

    def test_strip_scope_is_idempotent(self):
        cid = scoped_channel.build_channel_id("111", "group_222")
        once = scoped_channel.strip_scope(cid)
        assert scoped_channel.strip_scope(once) == once

    def test_two_accounts_same_group_are_isolated(self):
        """同一个群、两个账号 -> 必须得到不同的 channel_id"""
        a = scoped_channel.build_channel_id("1001", "group_500")
        b = scoped_channel.build_channel_id("1002", "group_500")
        assert a != b
        assert scoped_channel.strip_scope(a) == scoped_channel.strip_scope(b) == "group_500"

    def test_chat_key_within_length_limit(self):
        """chat_key 字段上限 256，作用域格式不得越界"""
        cid = scoped_channel.build_channel_id("2249382149", "group_798949533")
        chat_key = f"onebot_v11-{cid}"
        assert len(chat_key) <= 256


class _FakePreset:
    def __init__(self, preset_id: int, name: str):
        self.id = preset_id
        self.name = name


class _PresetChain:
    """复刻 DBChatChannel.get_preset 的解析顺序，避免依赖数据库"""

    BUILTIN = "builtin"

    def __init__(
        self,
        *,
        channel_preset: Optional[int],
        account_preset: Optional[int],
        global_preset: Optional[int],
        existing: dict[int, str],
    ):
        self.channel_preset = channel_preset
        self.account_preset = account_preset
        self.global_preset = global_preset
        self.existing = existing

    def resolve(self) -> str:
        for candidate in (self.channel_preset, self.account_preset, self.global_preset):
            if candidate is not None and candidate in self.existing:
                return self.existing[candidate]
        return self.BUILTIN


class TestPresetResolutionOrder:
    """人设优先级: 频道 > 账号 > 全局 > 内置"""

    EXISTING = {1: "channel-persona", 2: "account-persona", 3: "global-persona"}

    def test_channel_wins_over_account_and_global(self):
        chain = _PresetChain(channel_preset=1, account_preset=2, global_preset=3, existing=self.EXISTING)
        assert chain.resolve() == "channel-persona"

    def test_account_wins_over_global(self):
        chain = _PresetChain(channel_preset=None, account_preset=2, global_preset=3, existing=self.EXISTING)
        assert chain.resolve() == "account-persona"

    def test_global_used_when_no_account_preset(self):
        chain = _PresetChain(channel_preset=None, account_preset=None, global_preset=3, existing=self.EXISTING)
        assert chain.resolve() == "global-persona"

    def test_builtin_fallback(self):
        chain = _PresetChain(channel_preset=None, account_preset=None, global_preset=None, existing=self.EXISTING)
        assert chain.resolve() == "builtin"

    def test_missing_preset_id_falls_through(self):
        """指向已删除人设的 ID 应继续往下回退，而不是报错或返回空"""
        chain = _PresetChain(channel_preset=999, account_preset=2, global_preset=3, existing=self.EXISTING)
        assert chain.resolve() == "account-persona"

    def test_two_accounts_resolve_different_personas(self):
        """多账号核心诉求：同一群、不同账号 -> 不同人设"""
        a = _PresetChain(channel_preset=None, account_preset=2, global_preset=3, existing=self.EXISTING)
        b = _PresetChain(channel_preset=None, account_preset=None, global_preset=3, existing=self.EXISTING)
        assert a.resolve() != b.resolve()


def _select_default(
    online: list[str],
    *,
    marked: Optional[str] = None,
    configured: Optional[str] = None,
) -> Optional[str]:
    """复刻 bot._get_default_bot 的选取顺序: WebUI 标记 > BOT_QQ 配置 > 任意在线"""
    if not online:
        return None
    if marked and marked in online:
        return marked
    if configured and configured in online:
        return configured
    return online[0]


class TestDefaultAccountSelection:
    """默认账号选取顺序（无法从 chat_key 判定账号时使用）"""

    ONLINE = ["1001", "1002", "1003"]

    def test_marked_account_wins(self):
        """WebUI 星标账号优先于配置"""
        assert _select_default(self.ONLINE, marked="1002", configured="1003") == "1002"

    def test_falls_back_to_configured_bot_qq(self):
        assert _select_default(self.ONLINE, marked=None, configured="1003") == "1003"

    def test_falls_back_to_any_online(self):
        assert _select_default(self.ONLINE) == "1001"

    def test_offline_marked_account_is_skipped(self):
        """星标账号掉线时不应导致发送失败，应回退"""
        assert _select_default(self.ONLINE, marked="9999", configured="1003") == "1003"

    def test_offline_configured_account_is_skipped(self):
        assert _select_default(self.ONLINE, marked=None, configured="9999") == "1001"

    def test_no_online_account(self):
        assert _select_default([], marked="1001") is None
