import axios from '../axios'
import { createEventStream } from '../utils/stream'

export interface ContainerStatus {
  running: boolean
  started_at: string
}

export interface TokenResponse {
  token: string | null
}

export interface ActionResponse {
  ok: boolean
}

/** QQ 账号（多账号接入） */
export interface QQAccount {
  self_id: string
  display_name: string
  status: string
  enabled: boolean
  is_default: boolean
  default_preset_id: number | null
  default_preset_name: string | null
  last_active_at: string | null
  last_error: string
}

export interface QQAccountListResponse {
  accounts: QQAccount[]
  total: number
}

export const oneBotV11Api = {
  /**
   * 获取容器状态
   */
  getContainerStatus: async () => {
    const { data } = await axios.get<ContainerStatus>('/adapters/onebot_v11/container/status')
    return data
  },

  /**
   * 获取历史日志
   */
  getContainerLogs: async (tail = 500) => {
    const { data } = await axios.get<string[]>('/adapters/onebot_v11/container/logs', {
      params: { tail },
    })
    return data
  },

  /**
   * 获取实时日志流
   */
  streamContainerLogs: (onMessage: (data: string) => void, onError?: (error: Error) => void) => {
    return createEventStream({
      endpoint: '/adapters/onebot_v11/container/logs/stream',
      onMessage,
      onError,
    })
  },

  /**
   * 重启容器
   */
  restartContainer: async () => {
    const { data } = await axios.post<ActionResponse>('/adapters/onebot_v11/container/restart')
    return data.ok
  },

  /**
   * 获取OneBot访问令牌
   */
  getOneBotToken: async () => {
    const { data } = await axios.get<TokenResponse>('/adapters/onebot_v11/container/onebot-token')
    return data.token
  },

  /**
   * 获取NapCat WebUI访问令牌
   */
  getNapcatToken: async () => {
    const { data } = await axios.get<TokenResponse>('/adapters/onebot_v11/container/napcat-token')
    return data.token
  },

  /**
   * 获取已接入的 QQ 账号列表
   */
  getAccounts: async () => {
    const { data } = await axios.get<QQAccountListResponse>('/adapters/onebot_v11/accounts')
    return data
  },

  /**
   * 设置账号级默认人设（传 null 清除）
   */
  setAccountPreset: async (selfId: string, presetId: number | null) => {
    const { data } = await axios.patch<QQAccount>(
      `/adapters/onebot_v11/accounts/${selfId}/preset`,
      { preset_id: presetId }
    )
    return data
  },

  /**
   * 启用 / 停用账号
   */
  setAccountEnabled: async (selfId: string, enabled: boolean) => {
    const { data } = await axios.patch<QQAccount>(
      `/adapters/onebot_v11/accounts/${selfId}/enabled`,
      { enabled }
    )
    return data
  },

  /**
   * 设为默认账号
   */
  setDefaultAccount: async (selfId: string) => {
    const { data } = await axios.post<QQAccount>(
      `/adapters/onebot_v11/accounts/${selfId}/set-default`
    )
    return data
  },

  /**
   * 删除账号记录
   */
  deleteAccount: async (selfId: string) => {
    const { data } = await axios.delete<ActionResponse>(
      `/adapters/onebot_v11/accounts/${selfId}`
    )
    return data.ok
  },
}
