"""OneBot V11 多账号注册表

复用通用 `DBAdapterInstance` 表存储每个 QQ 账号的接入记录，
账号级默认人设等扩展信息存放于 `metadata_json`，无需数据库迁移。
"""

import json
from typing import Any, Dict, List, Optional

from nekro_agent.core.logger import get_sub_logger
from nekro_agent.models.db_adapter_instance import DBAdapterInstance
from nekro_agent.models.db_adapter_instance_event import DBAdapterInstanceEvent

from .bot import get_cached_default_self_id, set_cached_default_self_id

logger = get_sub_logger("adapter.onebot_v11.account")

ADAPTER_KEY = "onebot_v11"

STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_PENDING = "pending"

META_DEFAULT_PRESET_ID = "default_preset_id"


def _load_metadata(instance: DBAdapterInstance) -> Dict[str, Any]:
    """解析实例元数据，损坏时返回空字典而非抛错"""
    if not instance.metadata_json:
        return {}
    try:
        data = json.loads(instance.metadata_json)
    except (TypeError, ValueError):
        logger.warning(f"账号 {instance.instance_key} 元数据解析失败，已忽略")
        return {}
    return data if isinstance(data, dict) else {}


async def _save_metadata(instance: DBAdapterInstance, metadata: Dict[str, Any]) -> None:
    instance.metadata_json = json.dumps(metadata, ensure_ascii=False)
    await instance.save()


async def _record_event(
    instance: DBAdapterInstance,
    event_type: str,
    *,
    status_from: str = "",
    status_to: str = "",
    message: str = "",
) -> None:
    """写入实例事件，失败不影响主流程"""
    try:
        await DBAdapterInstanceEvent.create(
            instance_id=instance.id,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            message=message,
        )
    except Exception as e:  # noqa: BLE001 - 审计日志不应阻断账号接入
        logger.debug(f"记录账号事件失败: {e}")


async def get_account(self_id: str) -> Optional[DBAdapterInstance]:
    """按 QQ 号查询账号记录"""
    return await DBAdapterInstance.get_or_none(adapter_key=ADAPTER_KEY, instance_key=str(self_id))


async def list_accounts() -> List[DBAdapterInstance]:
    """列出所有已登记的 QQ 账号"""
    return await DBAdapterInstance.filter(adapter_key=ADAPTER_KEY).order_by("-is_default", "instance_key")


async def register_account(self_id: str, *, display_name: str = "") -> DBAdapterInstance:
    """账号连接时自动登记（已存在则复用并置为在线）

    首个接入的账号自动成为默认账号。
    """
    self_id = str(self_id)
    instance = await get_account(self_id)

    if instance is None:
        has_any = await DBAdapterInstance.filter(adapter_key=ADAPTER_KEY).exists()
        instance = await DBAdapterInstance.create(
            adapter_key=ADAPTER_KEY,
            instance_key=self_id,
            display_name=display_name or self_id,
            status=STATUS_ONLINE,
            enabled=True,
            is_default=not has_any,
            provider="onebot_v11",
            provider_account_id=self_id,
            metadata_json="{}",
        )
        await _record_event(instance, "auto_register", status_to=STATUS_ONLINE, message="账号自动注册")
        logger.info(f"OneBot V11 账号自动注册: {self_id}{'（默认账号）' if instance.is_default else ''}")
        return instance

    previous_status = instance.status
    instance.status = STATUS_ONLINE
    instance.last_error = ""
    if display_name and instance.display_name in ("", self_id):
        instance.display_name = display_name
    await instance.save()

    if previous_status != STATUS_ONLINE:
        await _record_event(instance, "connect", status_from=previous_status, status_to=STATUS_ONLINE)
        logger.info(f"OneBot V11 账号上线: {self_id}")
    return instance


async def mark_offline(self_id: str, *, reason: str = "") -> None:
    """账号断开时置为离线"""
    instance = await get_account(self_id)
    if instance is None:
        return

    previous_status = instance.status
    instance.status = STATUS_OFFLINE
    if reason:
        instance.last_error = reason
    await instance.save()
    await _record_event(instance, "disconnect", status_from=previous_status, status_to=STATUS_OFFLINE, message=reason)
    logger.info(f"OneBot V11 账号离线: {self_id}")


async def is_account_enabled(self_id: str) -> bool:
    """账号是否允许处理消息（未登记的账号默认放行，登记后以 enabled 为准）"""
    instance = await get_account(self_id)
    return True if instance is None else bool(instance.enabled)


async def set_account_enabled(self_id: str, enabled: bool) -> Optional[DBAdapterInstance]:
    """启用/停用账号"""
    instance = await get_account(self_id)
    if instance is None:
        return None
    instance.enabled = enabled
    await instance.save()
    await _record_event(instance, "enable" if enabled else "disable", message=f"enabled={enabled}")
    return instance


def read_default_preset_id(instance: DBAdapterInstance) -> Optional[int]:
    """从已取出的实例记录中读取账号级默认人设 ID（不再查库）"""
    value = _load_metadata(instance).get(META_DEFAULT_PRESET_ID)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def get_default_preset_id(self_id: str) -> Optional[int]:
    """读取账号级默认人设 ID"""
    instance = await get_account(self_id)
    if instance is None:
        return None
    return read_default_preset_id(instance)


async def set_default_preset_id(self_id: str, preset_id: Optional[int]) -> Optional[DBAdapterInstance]:
    """设置账号级默认人设；传 None 清除该账号的独立人设"""
    instance = await get_account(self_id)
    if instance is None:
        return None

    metadata = _load_metadata(instance)
    if preset_id is None or preset_id < 0:
        metadata.pop(META_DEFAULT_PRESET_ID, None)
    else:
        metadata[META_DEFAULT_PRESET_ID] = int(preset_id)
    await _save_metadata(instance, metadata)
    await _record_event(instance, "set_default_preset", message=f"preset_id={preset_id}")
    return instance


async def set_as_default_account(self_id: str) -> Optional[DBAdapterInstance]:
    """设为默认账号（互斥，其余账号取消默认标记）"""
    instance = await get_account(self_id)
    if instance is None:
        return None

    await DBAdapterInstance.filter(adapter_key=ADAPTER_KEY).exclude(id=instance.id).update(is_default=False)
    instance.is_default = True
    await instance.save()
    set_cached_default_self_id(instance.instance_key)
    await _record_event(instance, "set_default_account", message="设为默认账号")
    return instance


async def refresh_default_account_cache() -> Optional[str]:
    """从数据库载入默认账号标记到内存缓存

    `get_bot()` 是同步函数无法查库，故启动时同步一次。
    """
    instance = await DBAdapterInstance.filter(adapter_key=ADAPTER_KEY, is_default=True).first()
    self_id = instance.instance_key if instance else None
    set_cached_default_self_id(self_id)
    return self_id


async def delete_account(self_id: str) -> bool:
    """删除账号登记记录（不影响协议端连接本身）"""
    instance = await get_account(self_id)
    if instance is None:
        return False
    await DBAdapterInstanceEvent.filter(instance_id=instance.id).delete()
    await instance.delete()
    if get_cached_default_self_id() == instance.instance_key:
        set_cached_default_self_id(None)
    logger.info(f"OneBot V11 账号记录已删除: {self_id}")
    return True


async def sync_online_states(online_self_ids: List[str]) -> None:
    """以当前实际连接为准校正账号状态（启动时调用）"""
    online = {str(i) for i in online_self_ids}
    for instance in await list_accounts():
        expected = STATUS_ONLINE if instance.instance_key in online else STATUS_OFFLINE
        if instance.status != expected:
            instance.status = expected
            await instance.save()
