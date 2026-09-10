import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TradingAgentConfig } from './api'
import { TradingAgentPanel } from './TradingAgentPanel'

const config: TradingAgentConfig = {
  id: 1,
  name: 'Default Agent',
  enabled: true,
  status: 'paper',
  mode: 'paper',
  tradingType: 'mixed',
  riskProfile: 'medium',
  riskConfig: {
    max_daily_loss_enabled: true,
    max_daily_loss_amount: 500,
    max_daily_loss_percent: 2,
  },
  capitalAllocation: 10000,
  forecastEnabled: true,
  liveTradingEnabled: false,
  universe: ['NVDA'],
  dailyLoss: {
    startingEquity: 25000,
    currentEquity: 24875,
    realizedPnl: -100,
    unrealizedPnl: -25,
    tradingFees: 0,
    todayPnl: -125,
    dailyLoss: 125,
    dailyLossPercent: 0.5,
    maxDailyLossAmount: 500,
    maxDailyLossPercent: 2,
    effectiveLimit: 500,
    remainingDailyLoss: 375,
    status: 'active',
    limitReached: false,
    enabled: true,
    warnings: [],
  },
}

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    api: {
      getTradingAgentConfig: vi.fn(async () => config),
      updateTradingAgentConfig: vi.fn(async () => config),
      startTradingAgent: vi.fn(async () => ({ ...config, status: 'paper' })),
      pauseTradingAgent: vi.fn(async () => ({ ...config, status: 'paused' })),
      resumeTradingAgent: vi.fn(async () => ({ ...config, status: 'paper' })),
      emergencyStopTradingAgent: vi.fn(async () => ({ ...config, status: 'emergency_stop' })),
      runTradingAgentCycle: vi.fn(async () => ({})),
      getTradingAgentCandidates: vi.fn(async () => [
        {
          id: 1,
          symbol: 'NVDA',
          assetType: 'equity',
          strategy: 'buy_and_hold',
          status: 'approved',
          forecastSnapshot: { signal: 'BUY', confidence: 0.82 },
          riskDecision: { approved: true },
        },
      ]),
      getTradingAgentPositions: vi.fn(async () => []),
      getTradingAgentOrders: vi.fn(async () => []),
      getTradingAgentEvents: vi.fn(async () => [
        { id: 1, eventType: 'AGENT_STARTED', message: 'started', severity: 'info', createdAt: '2026-09-10T00:00:00Z' },
      ]),
      getTradingAgentPerformance: vi.fn(async () => ({
        totalPnl: 0,
        realizedPnl: 0,
        unrealizedPnl: 0,
        numberOfTrades: 0,
        maxDailyLossReachedCount: 0,
        tradesBlockedByDailyLoss: 0,
        positionsOpen: 0,
        ordersFilled: 0,
      })),
      getTradingAgentDailyLoss: vi.fn(async () => config.dailyLoss),
      updateTradingAgentDailyLoss: vi.fn(async () => config.dailyLoss),
      resetTradingAgentDailyLoss: vi.fn(async () => config.dailyLoss),
    },
  }
})

describe('TradingAgentPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows max daily loss and agent controls', async () => {
    render(<TradingAgentPanel />)
    expect(await screen.findByTestId('trading-agent-page')).toBeInTheDocument()
    expect(screen.getByTestId('max-daily-loss')).toBeInTheDocument()
    expect(screen.getByText(/Today/)).toBeInTheDocument()
    expect(screen.getByText(/Remaining daily loss/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Emergency Stop/i })).toBeInTheDocument()
    expect(await screen.findByText('NVDA')).toBeInTheDocument()
  })

  it('can pause the agent', async () => {
    const user = userEvent.setup()
    const { api } = await import('./api')
    render(<TradingAgentPanel />)
    await screen.findByTestId('trading-agent-page')
    await user.click(screen.getByRole('button', { name: /^Pause$/i }))
    await waitFor(() => expect(api.pauseTradingAgent).toHaveBeenCalled())
  })

  it('shows blocked state when daily loss limit reached', async () => {
    const { api } = await import('./api')
    vi.mocked(api.getTradingAgentConfig).mockResolvedValueOnce({
      ...config,
      dailyLoss: {
        ...config.dailyLoss,
        status: 'blocked',
        limitReached: true,
        remainingDailyLoss: 0,
        warnings: ['Max daily loss limit reached; new trades are blocked'],
      },
    })
    render(<TradingAgentPanel />)
    expect(await screen.findByTestId('daily-loss-blocked')).toBeInTheDocument()
  })
})
