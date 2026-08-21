import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Star as StarIcon,
  StarBorder as StarBorderIcon,
  Style as StyleIcon,
} from '@mui/icons-material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CARD_VARIANTS } from '../../../theme/variants'
import { useNotification } from '../../../hooks/useNotification'
import { oneBotV11Api, type QQAccount } from '../../../services/api/adapters/onebot_v11'
import { presetsApi } from '../../../services/api/presets'

const ACCOUNTS_QUERY_KEY = ['onebot-v11-accounts']

/** 无账号级人设时的占位值（Select 不接受 null） */
const NO_PRESET = -1

function StatusChip({ account }: { account: QQAccount }) {
  if (!account.enabled) {
    return <Chip size="small" label="已停用" color="default" variant="outlined" />
  }
  if (account.status === 'online') {
    return <Chip size="small" label="在线" color="success" />
  }
  if (account.status === 'offline') {
    return <Chip size="small" label="离线" color="warning" variant="outlined" />
  }
  return <Chip size="small" label={account.status} color="default" variant="outlined" />
}

export default function OneBotV11AccountsPage() {
  const notification = useNotification()
  const queryClient = useQueryClient()

  const [presetDialogAccount, setPresetDialogAccount] = useState<QQAccount | null>(null)
  const [selectedPresetId, setSelectedPresetId] = useState<number>(NO_PRESET)
  const [deleteTarget, setDeleteTarget] = useState<QQAccount | null>(null)

  const {
    data,
    isLoading,
    error,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ACCOUNTS_QUERY_KEY,
    queryFn: () => oneBotV11Api.getAccounts(),
    refetchInterval: 15_000,
  })

  const { data: presetData } = useQuery({
    queryKey: ['presets-for-account-binding'],
    queryFn: () => presetsApi.getList({ page: 1, page_size: 200 }),
    staleTime: 60_000,
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY })
  }

  const presetMutation = useMutation({
    mutationFn: ({ selfId, presetId }: { selfId: string; presetId: number | null }) =>
      oneBotV11Api.setAccountPreset(selfId, presetId),
    onSuccess: async () => {
      notification.success('账号默认人设已更新')
      setPresetDialogAccount(null)
      await invalidate()
    },
    onError: (err: Error) => notification.error(err.message || '设置人设失败'),
  })

  const enabledMutation = useMutation({
    mutationFn: ({ selfId, enabled }: { selfId: string; enabled: boolean }) =>
      oneBotV11Api.setAccountEnabled(selfId, enabled),
    onSuccess: async () => {
      notification.success('账号状态已更新')
      await invalidate()
    },
    onError: (err: Error) => notification.error(err.message || '更新账号状态失败'),
  })

  const defaultMutation = useMutation({
    mutationFn: (selfId: string) => oneBotV11Api.setDefaultAccount(selfId),
    onSuccess: async () => {
      notification.success('默认账号已切换')
      await invalidate()
    },
    onError: (err: Error) => notification.error(err.message || '设置默认账号失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: (selfId: string) => oneBotV11Api.deleteAccount(selfId),
    onSuccess: async () => {
      notification.success('账号记录已删除')
      setDeleteTarget(null)
      await invalidate()
    },
    onError: (err: Error) => notification.error(err.message || '删除账号失败'),
  })

  const openPresetDialog = (account: QQAccount) => {
    setPresetDialogAccount(account)
    setSelectedPresetId(account.default_preset_id ?? NO_PRESET)
  }

  const accounts = data?.accounts ?? []
  const presets = presetData?.items ?? []

  return (
    <Box sx={{ p: { xs: 1.5, sm: 2, md: 3 }, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card sx={CARD_VARIANTS.default.styles}>
        <CardContent>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Box>
              <Typography variant="h6">QQ 账号管理</Typography>
              <Typography variant="body2" color="text.secondary">
                多个 QQ 账号可同时通过 WebSocket 接入，首次连接时自动注册。
                不同账号在同一群的会话相互隔离，可分别设置默认人设。
              </Typography>
            </Box>
            <Tooltip title="刷新">
              <IconButton onClick={() => refetch()} disabled={isRefetching}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Stack>

          <Alert severity="info" sx={{ mb: 2 }}>
            人设优先级：频道人设 &gt; 账号默认人设 &gt; 全局默认人设 &gt; 内置默认人设
          </Alert>

          {error ? (
            <Alert severity="error">加载账号列表失败：{(error as Error).message}</Alert>
          ) : isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : accounts.length === 0 ? (
            <Alert severity="warning">
              暂无已接入的 QQ 账号。请将协议端（NapCat / LLOneBot 等）以反向 WebSocket 方式连接到本服务，
              账号会在连接成功后自动出现在此列表。
            </Alert>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>QQ 号</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>默认人设</TableCell>
                    <TableCell align="center">启用</TableCell>
                    <TableCell align="center">默认账号</TableCell>
                    <TableCell>最近活跃</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {accounts.map(account => (
                    <TableRow key={account.self_id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={600}>
                          {account.self_id}
                        </Typography>
                        {account.display_name && account.display_name !== account.self_id && (
                          <Typography variant="caption" color="text.secondary">
                            {account.display_name}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusChip account={account} />
                        {account.last_error && (
                          <Tooltip title={account.last_error}>
                            <Typography variant="caption" color="error" sx={{ display: 'block' }}>
                              有错误
                            </Typography>
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell>
                        {account.default_preset_name ? (
                          <Chip size="small" label={account.default_preset_name} variant="outlined" />
                        ) : (
                          <Typography variant="caption" color="text.secondary">
                            跟随全局
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="center">
                        <Switch
                          size="small"
                          checked={account.enabled}
                          onChange={e =>
                            enabledMutation.mutate({
                              selfId: account.self_id,
                              enabled: e.target.checked,
                            })
                          }
                          disabled={enabledMutation.isPending}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title={account.is_default ? '当前默认账号' : '设为默认账号'}>
                          <IconButton
                            size="small"
                            onClick={() => defaultMutation.mutate(account.self_id)}
                            disabled={account.is_default || defaultMutation.isPending}
                          >
                            {account.is_default ? (
                              <StarIcon fontSize="small" color="warning" />
                            ) : (
                              <StarBorderIcon fontSize="small" />
                            )}
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">
                          {account.last_active_at
                            ? new Date(account.last_active_at).toLocaleString()
                            : '—'}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="设置默认人设">
                          <IconButton size="small" onClick={() => openPresetDialog(account)}>
                            <StyleIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="删除账号记录">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => setDeleteTarget(account)}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* 设置账号默认人设 */}
      <Dialog
        open={Boolean(presetDialogAccount)}
        onClose={() => setPresetDialogAccount(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>设置账号默认人设</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            为 QQ {presetDialogAccount?.self_id} 指定默认人设。该账号所有会话在未单独设置频道人设时都会使用它。
          </Typography>
          <FormControl fullWidth size="small">
            <InputLabel id="account-preset-label">默认人设</InputLabel>
            <Select
              labelId="account-preset-label"
              label="默认人设"
              value={selectedPresetId}
              onChange={e => setSelectedPresetId(Number(e.target.value))}
            >
              <MenuItem value={NO_PRESET}>
                <em>跟随全局默认人设</em>
              </MenuItem>
              {presets.map(preset => (
                <MenuItem key={preset.id} value={preset.id}>
                  {preset.title || preset.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPresetDialogAccount(null)}>取消</Button>
          <Button
            variant="contained"
            disabled={presetMutation.isPending}
            onClick={() => {
              if (!presetDialogAccount) return
              presetMutation.mutate({
                selfId: presetDialogAccount.self_id,
                presetId: selectedPresetId === NO_PRESET ? null : selectedPresetId,
              })
            }}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 删除确认 */}
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>删除账号记录</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            确认删除 QQ {deleteTarget?.self_id} 的账号记录？
          </Typography>
          <Alert severity="info" sx={{ mt: 2 }}>
            历史会话数据不会被删除。若该账号协议端仍在连接，重连后会再次自动注册。
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button
            color="error"
            variant="contained"
            disabled={deleteMutation.isPending}
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.self_id)}
          >
            删除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
