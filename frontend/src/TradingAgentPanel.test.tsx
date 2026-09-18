import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  maxUniverseSize: 50,
  cycleIntervalSeconds: 300,
  lastCycleAt: null,
  lastUniverseScan: [],
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
    tradesToday: 2,
    maxTradesPerDay: 10,
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
          id: 3,
          symbol: 'NVDA',
          assetType: 'equity',
          strategy: 'intraday_exit',
          status: 'approved',
          forecastSnapshot: { signal: 'EXIT', confidence: 1, exit_reason: 'stop_loss' },
          riskDecision: { approved: true },
          exitReason: 'stop_loss',
          createdAt: '2026-09-10T00:05:00Z',
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
      getTradingAgentDayTrades: vi.fn(async () => ({
        date: '2026-09-10',
        timezone: 'America/Los_Angeles',
        trades: [],
        summary: {
          count: 0,
          wins: 0,
          losses: 0,
          open: 0,
          netRealizedPnl: 0,
          netUnrealizedPnl: 0,
        },
      })),
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
      listFavorites: vi.fn(async () => []),
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
    expect(screen.getByTestId('day-trades-today')).toHaveTextContent('2 / 10')
    expect(screen.getByTestId('rejected-queue')).toBeInTheDocument()
    expect(screen.getByTestId('trade-history')).toBeInTheDocument()
    expect(screen.getByTestId('daily-trades')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Generate$/i })).toBeInTheDocument()
    expect(screen.getByTestId('risk-auto-adjust-log')).toBeInTheDocument()
    expect((await screen.findAllByText('NVDA')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/stop loss/i)).toBeInTheDocument()
    expect(screen.getByText(/Forecast confidence 0.40 below minimum/i)).toBeInTheDocument()
    expect(screen.getByText(/Risk loosened/i)).toBeInTheDocument()
    expect(await screen.findByTestId('performance-summary')).toBeInTheDocument()
    expect(screen.getByText(/Invested now \(cost basis\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Taken out \(sell proceeds\)/i)).toBeInTheDocument()
  })

  it('shows invested cost basis per open position', async () => {
    const { api } = await import('./api')
    vi.mocked(api.getTradingAgentPositions).mockResolvedValueOnce([
      {
        id: 1,
        symbol: 'NVDA',
        assetType: 'equity',
        quantity: 10,
        averageEntryPrice: 180,
        currentPrice: 190,
        unrealizedPnl: 100,
        realizedPnl: 0,
      },
    ])
    render(<TradingAgentPanel />)
    const section = await screen.findByTestId('active-positions')
    expect(section).toHaveTextContent('Invested')
    expect(section).toHaveTextContent('$1,800.00')
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

  it('adds a ticker to the risk portfolio', async () => {
    const user = userEvent.setup()
    const { api } = await import('./api')
    render(<TradingAgentPanel />)
    await screen.findByTestId('risk-portfolio')
    await user.type(screen.getByLabelText(/add tickers to risk portfolio/i), 'msft, goog')
    await user.click(screen.getByRole('button', { name: /^Add$/i }))
    await waitFor(() =>
      expect(api.updateTradingAgentConfig).toHaveBeenCalledWith({
        universe: ['NVDA', 'MSFT', 'GOOG'],
      }),
    )
  })

  it('imports favorites into the risk portfolio', async () => {
    const user = userEvent.setup()
    const { api } = await import('./api')
    vi.mocked(api.listFavorites).mockResolvedValueOnce([
      { ticker: 'AAPL' },
      { ticker: 'NVDA' },
    ])
    render(<TradingAgentPanel />)
    await screen.findByTestId('risk-portfolio')
    await user.click(screen.getByRole('button', { name: /Sync favorites/i }))
    await waitFor(() =>
      expect(api.updateTradingAgentConfig).toHaveBeenCalledWith({
        universe: ['NVDA', 'AAPL'],
      }),
    )
  })

  it('shows last cycle universe scan rows', async () => {
    const { api } = await import('./api')
    vi.mocked(api.getTradingAgentConfig).mockResolvedValueOnce({
      ...config,
      lastUniverseScan: [
        {
          symbol: 'NVDA',
          outcome: 'approved',
          signal: 'BUY',
          confidence: 0.8,
          reason: 'Candidate approved',
          price: 100,
          sizingCapital: 25000,
        },
        {
          symbol: 'MU',
          outcome: 'hold',
          signal: 'HOLD',
          confidence: 0.4,
          reason: 'Signal HOLD is not actionable',
          price: 90,
          sizingCapital: 25000,
        },
      ],
    })
    render(<TradingAgentPanel />)
    await screen.findByTestId('universe-scan')
    expect(screen.getByText('Approved')).toBeInTheDocument()
    expect(screen.getByText('Hold')).toBeInTheDocument()
    expect(screen.getByText('Signal HOLD is not actionable')).toBeInTheDocument()
  })

  it('generates a daily profit and loss report', async () => {
    const user = userEvent.setup()
    const { api } = await import('./api')
    vi.mocked(api.getTradingAgentDayTrades).mockResolvedValueOnce({
      date: '2026-09-10',
      timezone: 'America/Los_Angeles',
      latestDate: '2026-09-10',
      trades: [
        {
          id: 11,
          symbol: 'NVDA',
          assetType: 'equity',
          side: 'sell',
          status: 'closed',
          quantity: 5,
          entryPrice: 100,
          exitPrice: 110,
          pnl: 50,
          result: 'Profit',
          strategy: 'intraday_exit',
          filledAt: '2026-09-10T18:00:00Z',
        },
      ],
      summary: {
        count: 1,
        wins: 1,
        losses: 0,
        open: 0,
        netRealizedPnl: 50,
        netUnrealizedPnl: 0,
      },
    })
    render(<TradingAgentPanel />)
    await screen.findByTestId('daily-trades')
    fireEvent.change(screen.getByLabelText(/session day/i), { target: { value: '2026-09-10' } })
    await user.click(screen.getByRole('button', { name: /^Generate$/i }))
    await waitFor(() => expect(api.getTradingAgentDayTrades).toHaveBeenCalledWith('2026-09-10'))
    expect(await screen.findByTestId('daily-trades-summary')).toHaveTextContent('1 wins')
    expect(screen.getByText('Profit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Download CSV/i })).toBeEnabled()
  })

  it('falls back to the latest session day when the selected day is empty', async () => {
    const user = userEvent.setup()
    const { api } = await import('./api')
    vi.mocked(api.getTradingAgentDayTrades)
      .mockResolvedValueOnce({
        date: '2026-09-17',
        timezone: 'America/Los_Angeles',
        latestDate: '2026-09-16',
        trades: [],
        summary: {
          count: 0,
          wins: 0,
          losses: 0,
          open: 0,
          netRealizedPnl: 0,
          netUnrealizedPnl: 0,
        },
      })
      .mockResolvedValueOnce({
        date: '2026-09-16',
        timezone: 'America/Los_Angeles',
        latestDate: '2026-09-16',
        trades: [
          {
            id: 12,
            symbol: 'AAPL',
            assetType: 'equity',
            side: 'sell',
            status: 'closed',
            quantity: 5,
            entryPrice: 100,
            exitPrice: 105,
            pnl: 25,
            result: 'Profit',
            strategy: 'intraday_exit',
            filledAt: '2026-09-16T18:00:00Z',
          },
        ],
        summary: {
          count: 1,
          wins: 1,
          losses: 0,
          open: 0,
          netRealizedPnl: 25,
          netUnrealizedPnl: 0,
        },
      })
    render(<TradingAgentPanel />)
    await screen.findByTestId('daily-trades')
    fireEvent.change(screen.getByLabelText(/session day/i), { target: { value: '2026-09-17' } })
    await user.click(screen.getByRole('button', { name: /^Generate$/i }))
    await waitFor(() => expect(api.getTradingAgentDayTrades).toHaveBeenCalledWith('2026-09-16'))
    expect(await screen.findByTestId('daily-trades-summary')).toHaveTextContent('1 wins')
    expect(screen.getByText(/No fills on 2026-09-17; showing latest session 2026-09-16/i)).toBeInTheDocument()
  })
})
