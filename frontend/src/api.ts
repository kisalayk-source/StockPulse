export type TradingMode = 'paper' | 'live'
export type OrderStatus = 'accepted' | 'rejected' | 'pending' | 'filled' | 'canceled'
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit'
export type OptionPositionIntent = 'buy_to_open' | 'buy_to_close' | 'sell_to_open' | 'sell_to_close'

export interface SearchResult {
  symbol: string
  name: string
  exchange?: string
  assetClass?: string
}

export type SentimentLabel = 'bullish' | 'bearish' | 'neutral'

export interface PublicSentiment {
  label: SentimentLabel
  bullishPercent: number | null
  bearishPercent: number | null
  score: number | null
}

export interface Quote {
  symbol: string
  name: string
  price: number | null
  change: number | null
  changePercent: number | null
  previousClose?: number | null
  afterHoursPrice?: number | null
  afterHoursChangePercent?: number | null
  session: 'regular' | 'pre_market' | 'after_hours' | 'closed' | string
  timestamp: string
  isStale?: boolean
  open?: number | null
  high?: number | null
  low?: number | null
  volume?: number | null
  marketCap?: number | null
  peRatio?: number | null
  dividendYield?: number | null
  eps?: number | null
}

export interface Candle {
  time: string | number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface ForecastPoint {
  time: string | number
  value: number
  lower?: number
  upper?: number
}

export interface ChartResponse {
  symbol: string
  interval: string
  candles: Candle[]
  asOf?: string
}

export interface ForecastResponse {
  symbol: string
  horizon: 'short' | 'long'
  points: ForecastPoint[]
  model?: string
  generatedAt?: string
  predictionStart?: string
  predictionEnd?: string
  confidence?: string
  sentiment?: SentimentLabel
  forecastChange?: number | null
  netForecastChange?: number | null
  roundTripBps?: number | null
  regime?: string
  edgeReliable?: boolean
  evaluation?: {
    folds: number
    hitRate: number | null
    meanNetReturn: number | null
    ic: number | null
  }
}

export interface NewsItem {
  id?: string
  headline: string
  summary?: string
  source: string
  url: string
  publishedAt: string
  sentiment?: 'positive' | 'negative' | 'neutral'
}

export interface Account {
  accountNumber?: string
  status?: string
  equity: number
  cash: number
  buyingPower: number
  dayTradingBuyingPower?: number
  currency?: string
  dailyPnlPercent?: number | null
  newBuysHalted?: boolean
}

export interface Position {
  symbol: string
  quantity: number
  marketValue: number
  averageEntryPrice: number
  currentPrice: number
  unrealizedPl: number
  unrealizedPlPercent?: number
  assetClass?: string
}

export interface Order {
  id: string
  symbol: string
  side: OrderSide
  quantity?: number
  notional?: number
  type: OrderType
  limitPrice?: number
  status: OrderStatus
  submittedAt: string
  filledAt?: string
  filledAveragePrice?: number
  contract?: string
}

export interface OptionContract {
  symbol: string
  underlying: string
  expiration: string
  type: 'call' | 'put'
  strike: number
  bid: number | null
  ask: number | null
  last?: number | null
  volume?: number | null
  openInterest?: number | null
}

export interface OptionChain {
  underlying: string
  expirations: string[]
  contracts: OptionContract[]
  timestamp?: string
}

export interface OrderPreview {
  ok: boolean
  estimatedCost: number | null
  positionPct: number | null
  spreadBps: number | null
  dailyPnlPct: number | null
  warnings: string[]
  newBuysHalted?: boolean
}

export interface EquityOrderRequest {
  mode: TradingMode
  symbol: string
  side: OrderSide
  quantity?: number
  notional?: number
  type: OrderType
  limitPrice?: number
  timeInForce: 'day' | 'gtc'
}

export interface OptionOrderRequest {
  mode: TradingMode
  contractSymbol: string
  side: OrderSide
  quantity: number
  type: OrderType
  limitPrice?: number
  timeInForce: 'day' | 'gtc'
  positionIntent: OptionPositionIntent
}

export interface AppConfig {
  environment?: string
  alpacaConnected?: boolean
  dataFeed?: string
  liveTradingEnabled?: boolean
}

export interface MarketClock {
  isOpen: boolean
  session: string
  timestamp?: string
  nextOpen?: string
  nextClose?: string
}

export interface Mover {
  symbol: string
  lastPrice: number | null
  predictedPrice: number | null
  forecastChange: number | null
  netForecastChange?: number | null
  direction: 'up' | 'down' | 'flat' | string
  dayChange: number | null
  volume: number | null
  asOf?: string
  regime?: string
  edgeReliable?: boolean
}

export interface MoversResponse {
  status?: 'idle' | 'pending' | 'ready' | 'error'
  error?: string
  asOf?: string
  session?: string
  marketOpen: boolean
  preset?: string
  timeframe?: string
  scanned: number
  total?: number
  cached: boolean
  movers: Mover[]
  gainers?: Mover[]
  losers?: Mover[]
  skipped?: Array<{ symbol: string; message: string }>
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_API_KEY || ''
const inflight = new Map<string, Promise<unknown>>()

export class ApiError extends Error {
  status: number
  retryAfterMs: number

  constructor(message: string, status: number, retryAfterMs = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfterMs = retryAfterMs
  }
}

type JsonObject = Record<string, unknown>

const object = (value: unknown): JsonObject =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {}
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : []
const text = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : value == null ? fallback : String(value)
const number = (value: unknown): number | null => {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeError(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const value = payload as Record<string, unknown>
    if (typeof value.detail === 'string') return value.detail
    if (Array.isArray(value.detail)) {
      const messages = value.detail
        .map((entry) => text(object(entry).msg))
        .filter(Boolean)
      if (messages.length) return messages.join(' ')
    }
    if (value.detail && typeof value.detail === 'object') {
      const detail = value.detail as Record<string, unknown>
      if (typeof detail.message === 'string') return detail.message
    }
    if (typeof value.message === 'string') return value.message
  }
  return `Request failed (${status})`
}

function retryAfterMs(response: Response): number {
  const raw = response.headers.get('Retry-After')
  const seconds = raw ? Number(raw) : NaN
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000
  return 1500
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...init?.headers,
    },
  })
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(normalizeError(payload, response.status), response.status, retryAfterMs(response))
  }
  return payload as T
}

async function requestWithRetry<T>(path: string, init?: RequestInit, attempts = 3): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await request<T>(path, init)
    } catch (error) {
      lastError = error
      if (!(error instanceof ApiError) || error.status !== 429 || attempt === attempts - 1) {
        throw error
      }
      await sleep(Math.min(error.retryAfterMs || 1500, 5_000))
    }
  }
  throw lastError
}

function coalesced<T>(key: string, run: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key)
  if (existing) return existing as Promise<T>
  const pending = run().finally(() => {
    if (inflight.get(key) === pending) inflight.delete(key)
  })
  inflight.set(key, pending)
  return pending
}

const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => value !== undefined && params.set(key, String(value)))
  return params.toString()
}

function mapSentiment(value: unknown): SentimentLabel | undefined {
  const label = text(value).toLowerCase()
  if (label === 'bullish' || label === 'up') return 'bullish'
  if (label === 'bearish' || label === 'down') return 'bearish'
  if (label === 'neutral' || label === 'flat') return 'neutral'
  return undefined
}

function mapPublicSentiment(value: unknown): PublicSentiment | null {
  const item = object(value)
  if (!item.label && item.bullish_percent == null && item.bearish_percent == null) return null
  return {
    label: mapSentiment(item.label) || 'neutral',
    bullishPercent: number(item.bullish_percent),
    bearishPercent: number(item.bearish_percent),
    score: number(item.score),
  }
}

function mapNewsSentiment(value: unknown): NewsItem['sentiment'] | undefined {
  const label = text(value).toLowerCase()
  if (label === 'positive' || label === 'bullish') return 'positive'
  if (label === 'negative' || label === 'bearish') return 'negative'
  if (label === 'neutral') return 'neutral'
  return undefined
}

function mapNews(value: unknown): NewsItem {
  const item = object(value)
  const published = item.created_at ?? item.updated_at ?? item.datetime
  return {
    id: text(item.id),
    headline: text(item.headline, 'Untitled article'),
    summary: text(item.summary),
    source: text(item.source, 'Unknown source'),
    url: text(item.url, '#'),
    publishedAt: typeof published === 'number'
      ? new Date(published * 1000).toISOString()
      : text(published),
    sentiment: mapNewsSentiment(item.sentiment),
  }
}

function mapOrder(value: unknown): Order {
  const item = object(value)
  const rawStatus = text(item.status, 'pending')
  const status: OrderStatus =
    rawStatus === 'filled' ? 'filled'
      : ['canceled', 'expired', 'replaced'].includes(rawStatus) ? 'canceled'
        : rawStatus === 'rejected' ? 'rejected'
          : ['accepted', 'new'].includes(rawStatus) ? 'accepted' : 'pending'
  return {
    id: text(item.id),
    symbol: text(item.symbol),
    side: text(item.side, 'buy') as OrderSide,
    quantity: number(item.qty) ?? undefined,
    notional: number(item.notional) ?? undefined,
    type: text(item.type, 'market') as OrderType,
    limitPrice: number(item.limit_price) ?? undefined,
    status,
    submittedAt: text(item.submitted_at),
    filledAt: text(item.filled_at) || undefined,
    filledAveragePrice: number(item.filled_avg_price) ?? undefined,
  }
}

function mapMover(value: unknown): Mover {
  const item = object(value)
  return {
    symbol: text(item.symbol),
    lastPrice: number(item.last_price),
    predictedPrice: number(item.predicted_price),
    forecastChange: number(item.forecast_change),
    netForecastChange: number(item.net_forecast_change),
    direction: text(item.direction, 'flat'),
    dayChange: number(item.day_change),
    volume: number(item.volume),
    asOf: text(item.as_of) || undefined,
    regime: text(item.regime) || undefined,
    edgeReliable: item.edge_reliable == null ? undefined : Boolean(item.edge_reliable),
  }
}

function mapMoversResponse(value: unknown): MoversResponse {
  const payload = object(value)
  return {
    status: text(payload.status, 'ready') as MoversResponse['status'],
    error: text(payload.error) || undefined,
    asOf: text(payload.as_of) || undefined,
    session: text(payload.session) || undefined,
    marketOpen: Boolean(payload.market_open),
    preset: text(payload.preset) || undefined,
    timeframe: text(payload.timeframe) || undefined,
    scanned: number(payload.scanned) ?? 0,
    total: number(payload.total) ?? undefined,
    cached: Boolean(payload.cached),
    movers: list(payload.movers).map(mapMover),
    gainers: list(payload.gainers).map(mapMover),
    losers: list(payload.losers).map(mapMover),
    skipped: list(payload.skipped).map((value) => {
      const item = object(value)
      return { symbol: text(item.symbol), message: text(item.message) }
    }),
  }
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  config: async (): Promise<AppConfig> => {
    const payload = object(await request<unknown>('/config/status'))
    const alpaca = object(payload.alpaca)
    return {
      alpacaConnected: Boolean(alpaca.paper_configured),
      liveTradingEnabled: Boolean(payload.live_trading_allowed),
      dataFeed: text(payload.data_feed),
    }
  },
  clock: async (): Promise<MarketClock> => {
    const payload = object(await request<unknown>('/market/clock'))
    return {
      isOpen: Boolean(payload.is_open),
      session: text(payload.session, 'unknown'),
      timestamp: text(payload.timestamp) || undefined,
      nextOpen: text(payload.next_open) || undefined,
      nextClose: text(payload.next_close) || undefined,
    }
  },
  search: async (term: string): Promise<SearchResult[]> => {
    const payload = object(await request<unknown>(`/symbols/search?${query({ q: term })}`))
    return list(payload.results).map((value) => {
      const item = object(value)
      return {
        symbol: text(item.symbol),
        name: text(item.name),
        exchange: text(item.exchange),
      }
    })
  },
  overview: async (symbol: string): Promise<{ quote: Quote; news: NewsItem[]; publicSentiment: PublicSentiment | null }> => {
    const payload = object(await request<unknown>(
      `/stocks/${encodeURIComponent(symbol)}/overview?${query({ news_limit: 8 })}`,
    ))
    const daily = object(payload.daily)
    const previous = object(payload.previous_daily)
    const fundamentals = object(payload.fundamentals)
    const price = number(payload.current_price)
    const previousClose = number(previous.close)
    const change = price != null && previousClose != null ? price - previousClose : null
    const rawNews = payload.news
    const articles = Array.isArray(rawNews) ? rawNews : list(object(rawNews).news)
    return {
      quote: {
        symbol: text(payload.symbol, symbol.toUpperCase()),
        name: text(payload.name, symbol.toUpperCase()),
        price,
        change,
        changePercent: change != null && previousClose ? change / previousClose : null,
        previousClose,
        session: text(payload.session, 'unknown'),
        timestamp: text(payload.timestamp),
        open: number(daily.open),
        high: number(daily.high),
        low: number(daily.low),
        volume: number(daily.volume),
        marketCap: number(fundamentals.market_cap),
        peRatio: number(fundamentals.pe_ratio),
        dividendYield: number(fundamentals.dividend_yield),
        eps: number(fundamentals.eps),
      },
      news: articles.map(mapNews),
      publicSentiment: mapPublicSentiment(payload.public_sentiment),
    }
  },
  chart: async (symbol: string, range = '6M'): Promise<ChartResponse> => {
    const limit = range === '1M' ? 30 : range === '1Y' ? 365 : 180
    const payload = object(await request<unknown>(
      `/stocks/${encodeURIComponent(symbol)}/bars?${query({ timeframe: '1Day', limit })}`,
    ))
    const candles = list(payload.bars).map((value) => {
      const item = object(value)
      return {
        time: text(item.timestamp),
        open: number(item.open) ?? 0,
        high: number(item.high) ?? 0,
        low: number(item.low) ?? 0,
        close: number(item.close) ?? 0,
        volume: number(item.volume) ?? undefined,
      }
    })
    return { symbol: text(payload.symbol, symbol), interval: text(payload.timeframe), candles }
  },
  forecast: async (symbol: string, horizon: 'short' | 'long'): Promise<ForecastResponse> => {
    const payload = object(await coalesced(`forecast:${symbol}:${horizon}`, () => requestWithRetry<unknown>('/forecast', {
      method: 'POST',
      body: JSON.stringify({ symbol, preset: horizon }),
    })))
    const model = object(payload.model)
    const trend = object(payload.trend)
    const points = list(payload.forecast).map((value) => {
      const item = object(value)
      return {
        time: text(item.timestamp),
        value: number(item.close) ?? 0,
        lower: number(item.lower) ?? undefined,
        upper: number(item.upper) ?? undefined,
      }
    })
    return {
      symbol: text(payload.symbol, symbol),
      horizon,
      points,
      model: text(model.id, 'Kronos'),
      generatedAt: text(payload.as_of),
      predictionStart: text(points[0]?.time),
      predictionEnd: text(points.at(-1)?.time),
      sentiment: mapSentiment(trend.direction),
      forecastChange: number(trend.forecast_change),
      netForecastChange: number(trend.net_forecast_change),
      roundTripBps: number(object(payload.costs).round_trip_bps),
      regime: text(object(payload.regime).label) || undefined,
      edgeReliable: object(payload.evaluation).edge_reliable == null
        ? undefined
        : Boolean(object(payload.evaluation).edge_reliable),
      evaluation: {
        folds: number(object(payload.evaluation).folds) ?? 0,
        hitRate: number(object(payload.evaluation).hit_rate),
        meanNetReturn: number(object(payload.evaluation).mean_net_return),
        ic: number(object(payload.evaluation).ic),
      },
    }
  },
  movers: async (refresh = false): Promise<MoversResponse> => {
    return mapMoversResponse(await request<unknown>('/forecast/movers', {
      method: 'POST',
      body: JSON.stringify({ refresh, limit: 50 }),
    }))
  },
  moversStatus: async (): Promise<MoversResponse> =>
    mapMoversResponse(await request<unknown>('/forecast/movers/status')),
  account: async (mode: TradingMode): Promise<Account> => {
    const item = object(await request<unknown>(`/account?${query({ mode })}`))
    const risk = object(item.risk)
    return {
      accountNumber: text(item.account_number),
      status: text(item.status),
      equity: number(item.equity) ?? 0,
      cash: number(item.cash) ?? 0,
      buyingPower: number(item.buying_power) ?? 0,
      dayTradingBuyingPower: number(item.daytrading_buying_power) ?? undefined,
      currency: text(item.currency, 'USD'),
      dailyPnlPercent: number(risk.daily_pnl_pct),
      newBuysHalted: Boolean(risk.new_buys_halted),
    }
  },
  positions: async (mode: TradingMode): Promise<Position[]> => {
    const payload = object(await request<unknown>(`/positions?${query({ mode })}`))
    return list(payload.positions).map((value) => {
      const item = object(value)
      return {
        symbol: text(item.symbol),
        quantity: number(item.qty) ?? 0,
        marketValue: number(item.market_value) ?? 0,
        averageEntryPrice: number(item.avg_entry_price) ?? 0,
        currentPrice: number(item.current_price) ?? 0,
        unrealizedPl: number(item.unrealized_pl) ?? 0,
        unrealizedPlPercent: number(item.unrealized_plpc) ?? undefined,
        assetClass: text(item.asset_class),
      }
    })
  },
  orders: async (mode: TradingMode): Promise<Order[]> => {
    const payload = object(await request<unknown>(`/orders?${query({ mode, order_status: 'all' })}`))
    return list(payload.orders).map(mapOrder)
  },
  cancelOrder: async (orderId: string, mode: TradingMode): Promise<void> => {
    await request<unknown>(`/orders/${encodeURIComponent(orderId)}`, {
      method: 'DELETE',
      body: JSON.stringify({
        mode,
        live_confirmation_token: mode === 'live' ? 'LIVE' : undefined,
      }),
    })
  },
  optionChain: async (
    symbol: string,
    mode: TradingMode,
    expiration?: string,
    type?: 'call' | 'put',
  ): Promise<OptionChain> => {
    const contractPayload = await request<unknown>(`/options/contracts?${query({
      underlying: symbol,
      mode,
      type,
      limit: 1000,
    })}`)
    const contracts = list(object(contractPayload).contracts)
    const expirations = [...new Set(contracts.map((value) => text(object(value).expiration_date)).filter(Boolean))].sort()
    const selectedExpiration = expiration && expirations.includes(expiration)
      ? expiration
      : expirations[0]
    const chainPayload = selectedExpiration
      ? await request<unknown>(`/options/chain?${query({
        underlying: symbol,
        expiration: selectedExpiration,
        type,
      })}`)
      : {}
    const snapshots = object(object(chainPayload).chain)
    const mapped = contracts.map((value): OptionContract => {
      const item = object(value)
      const contractSymbol = text(item.symbol)
      const snapshot = object(snapshots[contractSymbol])
      const quote = object(snapshot.latest_quote)
      const trade = object(snapshot.latest_trade)
      const contractType = text(item.type, 'call').toLowerCase()
      return {
        symbol: contractSymbol,
        underlying: text(item.underlying_symbol, symbol.toUpperCase()),
        expiration: text(item.expiration_date),
        type: contractType === 'put' ? 'put' : 'call',
        strike: number(item.strike_price) ?? 0,
        bid: number(quote.bid_price),
        ask: number(quote.ask_price),
        last: number(trade.price),
        volume: number(snapshot.daily_bar && object(snapshot.daily_bar).volume),
        openInterest: number(item.open_interest),
      }
    }).filter((item) => !type || item.type === type)
    return {
      underlying: symbol.toUpperCase(),
      expirations,
      contracts: mapped,
    }
  },
  previewOrder: async (order: {
    kind: 'equity' | 'option'
    mode: TradingMode
    symbol: string
    contractSymbol?: string
    side: OrderSide
    quantity?: number
    notional?: number
    type: OrderType
    limitPrice?: number
    positionIntent?: OptionPositionIntent
  }): Promise<OrderPreview> => {
    const payload = object(await request<unknown>('/orders/preview', {
      method: 'POST',
      body: JSON.stringify({
        kind: order.kind,
        mode: order.mode,
        symbol: order.symbol,
        contract_symbol: order.contractSymbol,
        side: order.side,
        type: order.type,
        qty: order.quantity,
        notional: order.notional,
        limit_price: order.limitPrice,
        position_intent: order.positionIntent,
      }),
    }))
    const risk = object(payload.risk)
    return {
      ok: payload.ok !== false,
      estimatedCost: number(payload.estimated_cost),
      positionPct: number(payload.position_pct),
      spreadBps: number(payload.spread_bps),
      dailyPnlPct: number(payload.daily_pnl_pct),
      warnings: list(payload.warnings).map((value) => text(value)),
      newBuysHalted: Boolean(risk.new_buys_halted),
    }
  },
  placeEquityOrder: async (order: EquityOrderRequest): Promise<Order> => mapOrder(
    await request<unknown>('/orders/equity', {
      method: 'POST',
      body: JSON.stringify({
        mode: order.mode,
        symbol: order.symbol,
        side: order.side,
        qty: order.quantity,
        notional: order.notional,
        type: order.type,
        limit_price: order.limitPrice,
        time_in_force: order.timeInForce,
        live_confirmation_token: order.mode === 'live' ? 'LIVE' : undefined,
      }),
    }),
  ),
  placeOptionOrder: async (order: OptionOrderRequest): Promise<Order> => mapOrder(
    await request<unknown>('/orders/option', {
      method: 'POST',
      body: JSON.stringify({
        mode: order.mode,
        contract_symbol: order.contractSymbol,
        side: order.side,
        qty: order.quantity,
        type: order.type,
        limit_price: order.limitPrice,
        position_intent: order.positionIntent,
        time_in_force: 'day',
        live_confirmation_token: order.mode === 'live' ? 'LIVE' : undefined,
      }),
    }),
  ),
}
