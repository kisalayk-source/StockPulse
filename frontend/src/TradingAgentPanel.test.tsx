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
  cycleIntervalSeconds: 300,
  lastCycleAt: null,
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
          createdAt: '2026-09-10T00:00:00Z',
        },
        {
          id: 2,
          symbol: 'AAPL',
          assetType: 'equity',
          strategy: 'intraday_momentum',
          status: 'rejected',
          forecastSnapshot: { signal: 'BUY', confidence: 0.4 },
          riskDecision: { approved: false, reason: 'Forecast confidence 0.40 below minimum 0.55' },
          createdAt: '2026-09-10T00:05:00Z',
        },
      ]),
      getTradingAgentPositions: vi.fn(async () => []),
      getTradingAgentOrders: vi.fn(async () => [
        {
          id: 10,
          status: 'filled',
          symbol: 'NVDA',
          side: 'buy',
          filledQuantity: 2,
          averageFillPrice: 180,
          requestedQuantity: 2,
          submittedAt: '2026-09-10T00:00:00Z',
          filledAt: '2026-09-10T00:00:00Z',
        },
      ]),
      getTradingAgentEvents: vi.fn(async () => [
        { id: 1, eventType: 'AGENT_STARTED', message: 'started', severity: 'info', createdAt: '2026-09-10T00:00:00Z' },
        {
          id: 2,
          eventType: 'RISK_AUTO_ADJUSTED',
          message: 'Loosened min forecast confidence 0.55 → 0.50 because all 3 opportunities were rejected.',
          severity: 'warning',
          createdAt: '2026-09-10T01:00:00Z',
        },
      ]),
      getTradingAgentPerformance: vi.fn(async () => ({
        totalPnl: 0,
        realizedPnl: 0,
        unrealizedPnl: 0,
        capitalInvested: 6100,
        marketValueOpen: 6100,
        proceedsFromExits: 16000,
        startingCapital: 25000,
        accountEquity: 25000,
        equityChange: 0,
        numberOfTrades: 1,
        maxDailyLossReachedCount: 0,
        tradesBlockedByDailyLoss: 0,
        positionsOpen: 1,
        ordersFilled: 1,
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
    expect(await screen.findByTestId('accepted-queue')).toBeInTheDocument()
    expect(screen.getByTestId('rejected-queue')).toBeInTheDocument()
    expect(screen.getByTestId('trade-history')).toBeInTheDocument()
    expect(screen.getByTestId('risk-auto-adjust-log')).toBeInTheDocument()
    expect((await screen.findAllByText('NVDA')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Forecast confidence 0.40 below minimum/i)).toBeInTheDocument()
    expect(screen.getByText(/Risk loosened/i)).toBeInTheDocument()
    expect(await screen.findByTestId('performance-summary')).toBeInTheDocument()
    expect(screen.getByText(/Invested now \(cost basis\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Taken out \(sell proceeds\)/i)).toBeInTheDocument()
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
