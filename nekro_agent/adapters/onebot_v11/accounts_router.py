"""OneBot V11 多 QQ 账号管理 API

账号记录复用通用的 `DBAdapterInstance` 表，账号在 WS 首次连接时自动注册，
因此这里只提供查询与调整能力，不提供「手动创建账号」端点。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from nekro_agent.core.logger import get_sub_logger
from nekro_agent.models.db_adapter_instance import DBAdapterInstance
from nekro_agent.models.db_preset import DBPreset
from nekro_agent.models.db_user import DBUser
from nekro_agent.schemas.errors import NotFoundError
from nekro_agent.services.user.deps import get_current_active_user
from nekro_agent.services.user.perm import Role, require_role

from .core import account_manager

logger = get_sub_logger("adapter.onebot_v11.accounts")

router = APIRouter(prefix="/accounts", tags=["OneBot V11 Accounts"])


class AccountResponse(BaseModel):
    """QQ 账号信息"""

    self_id: str = Field(description="QQ 号")
    display_name: str = Field(default="", description="显示名称")
    status: str = Field(description="连接状态: online / offline / pending")
    enabled: bool = Field(description="是否启用；关闭后不再处理该账号的消息")
    is_default: bool = Field(description="是否为默认账号")
    default_preset_id: Optional[int] = Field(default=None, description="账号级默认人设 ID")
    default_preset_name: Optional[str] = Field(default=None, description="账号级默认人设名称")
    last_active_at: Optional[str] = Field(default=None, description="最近活跃时间")
    last_error: str = Field(default="", description="最近错误信息")


class AccountListResponse(BaseModel):
    accounts: List[AccountResponse]
    total: int


class SetPresetRequest(BaseModel):
    preset_id: Optional[int] = Field(default=None, description="人设 ID；传 null 或 -1 清除账号级人设")


class SetEnabledRequest(BaseModel):
    enabled: bool


class ActionResponse(BaseModel):
    ok: bool = True


async def _to_response(instance: DBAdapterInstance) -> AccountResponse:
    preset_id = account_manager.read_default_preset_id(instance)
    preset_name: Optional[str] = None
    if preset_id is not None:
        preset = await DBPreset.get_or_none(id=preset_id)
        preset_name = preset.name if preset else None

    return AccountResponse(
        self_id=instance.instance_key,
        display_name=instance.display_name,
        status=instance.status,
        enabled=instance.enabled,
        is_default=instance.is_default,
        default_preset_id=preset_id,
        default_preset_name=preset_name,
        last_active_at=instance.last_active_at.isoformat() if instance.last_active_at else None,
        last_error=instance.last_error,
    )


@router.get("", response_model=AccountListResponse, summary="获取 QQ 账号列表")
@require_role(Role.Admin)
async def list_accounts(_current_user: DBUser = Depends(get_current_active_user)) -> AccountListResponse:
    """列出所有已接入的 QQ 账号（含离线账号）"""
    instances = await account_manager.list_accounts()
    accounts = [await _to_response(item) for item in instances]
    return AccountListResponse(accounts=accounts, total=len(accounts))


@router.get("/{self_id}", response_model=AccountResponse, summary="获取指定账号详情")
@require_role(Role.Admin)
async def get_account(self_id: str, _current_user: DBUser = Depends(get_current_active_user)) -> AccountResponse:
    instance = await account_manager.get_account(self_id)
    if instance is None:
        raise NotFoundError(resource=f"QQ 账号 {self_id}")
    return await _to_response(instance)


@router.patch("/{self_id}/preset", response_model=AccountResponse, summary="设置账号级默认人设")
@require_role(Role.Admin)
async def set_account_preset(
    self_id: str,
    body: SetPresetRequest,
    _current_user: DBUser = Depends(get_current_active_user),
) -> AccountResponse:
    """设置该账号的默认人设

    优先级: 频道人设 > 账号默认人设 > 全局默认人设 > 内置默认人设
    """
    if body.preset_id is not None and body.preset_id >= 0 and not await DBPreset.get_or_none(id=body.preset_id):
        raise NotFoundError(resource=f"人设 {body.preset_id}")

    instance = await account_manager.set_default_preset_id(self_id, body.preset_id)
    if instance is None:
        raise NotFoundError(resource=f"QQ 账号 {self_id}")
    logger.info(f"账号 {self_id} 默认人设已更新: preset_id={body.preset_id}")
    return await _to_response(instance)


@router.patch("/{self_id}/enabled", response_model=AccountResponse, summary="启用/停用账号")
@require_role(Role.Admin)
async def set_account_enabled(
    self_id: str,
    body: SetEnabledRequest,
    _current_user: DBUser = Depends(get_current_active_user),
) -> AccountResponse:
    """停用后该账号的消息不再被处理，但连接与历史数据保留"""
    instance = await account_manager.set_account_enabled(self_id, body.enabled)
    if instance is None:
        raise NotFoundError(resource=f"QQ 账号 {self_id}")
    logger.info(f"账号 {self_id} 启用状态已更新: enabled={body.enabled}")
    return await _to_response(instance)


@router.post("/{self_id}/set-default", response_model=AccountResponse, summary="设为默认账号")
@require_role(Role.Admin)
async def set_default_account(
    self_id: str,
    _current_user: DBUser = Depends(get_current_active_user),
) -> AccountResponse:
    """默认账号用于无法从 chat_key 判定账号的场景（如旧格式会话、主动推送）"""
    instance = await account_manager.set_as_default_account(self_id)
    if instance is None:
        raise NotFoundError(resource=f"QQ 账号 {self_id}")
    logger.info(f"默认账号已切换: {self_id}")
    return await _to_response(instance)


@router.delete("/{self_id}", response_model=ActionResponse, summary="删除账号记录")
@require_role(Role.Admin)
async def delete_account(self_id: str, _current_user: DBUser = Depends(get_current_active_user)) -> ActionResponse:
    """删除账号记录（不影响历史会话数据）；若该账号仍在线，重连后会再次自动注册"""
    if not await account_manager.delete_account(self_id):
        raise NotFoundError(resource=f"QQ 账号 {self_id}")
    logger.info(f"账号记录已删除: {self_id}")
    return ActionResponse(ok=True)
