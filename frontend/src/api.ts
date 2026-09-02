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

export interface ForecastPathSegment {
  direction: 'up' | 'down' | 'flat'
  startIndex: number
  endIndex: number
  startClose: number
  endClose: number
  change: number
  startTimestamp?: string
  endTimestamp?: string
}

export type ChartInterval = '1Min' | '5Min' | '15Min' | '1Hour' | '1Day'

export interface ForecastResponse {
  symbol: string
  horizon: 'short' | 'long'
  bars: number
  timeframe?: ChartInterval
  engine?: 'kronos' | 'ensemble'
  points: ForecastPoint[]
  model?: string
  modelsUsed?: string[]
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
  pathSegments?: ForecastPathSegment[]
  evaluation?: {
    folds: number
    hitRate: number | null
    meanNetReturn: number | null
    ic: number | null
    evalHorizon?: number | null
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
  paperConfigured?: boolean
  liveConfigured?: boolean
  paperKeyPreview?: string | null
  liveKeyPreview?: string | null
  dataFeed?: string
  liveTradingEnabled?: boolean
  userEmail?: string
  researchLlmAvailable?: boolean
  researchLlmEnabled?: boolean
}

export interface AuthUser {
  id: number
  email: string
  alpaca: {
    paper: { configured: boolean; keyPreview: string | null }
    live: { configured: boolean; keyPreview: string | null }
  }
  researchLlmEnabled?: boolean
  researchLlmAvailable?: boolean
}

export interface AuthResponse {
  accessToken: string
  user: AuthUser
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
  predictionEnd?: string
  horizon?: number
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

export interface AccumulationComponents {
  institutional?: number
  insider?: number
  major_holder?: number
  price_volume?: number
  fundamentals?: number
}

export interface AccumulationHistoryPoint {
  date: string
  score: number
  classification: string
}

export interface AccumulationResponse {
  ticker: string
  score: number
  signal: string
  classification: string
  components: AccumulationComponents
  events: Array<Record<string, unknown>>
  history: AccumulationHistoryPoint[]
  as_of: string
  provider_errors?: Array<{ provider: string; message: string }>
}

export interface SecIntelligenceResponse {
  ticker: string
  accumulation: AccumulationResponse
  institutional_changes: Array<Record<string, unknown>>
  insider_transactions: Array<Record<string, unknown>>
  major_holder_changes: Array<Record<string, unknown>>
  caveats: string[]
  provider_errors?: Array<{ provider: string; message: string }>
}

export interface SectorAccumulationResponse {
  sector: string
  avg_score: number
  pct_increasing: number
  pct_decreasing: number
  ticker_count?: number
  stocks: Array<{ ticker: string; score: number; components: AccumulationComponents }>
}

export interface SectorListResponse {
  sectors: Array<{ sector: string; ticker_count: number }>
}

export interface AccumulationScanStatus {
  status: string
  scanned: number
  total: number
  errors?: Array<{ ticker?: string; message?: string }>
  started_at?: string | null
  finished_at?: string | null
  error?: string
}

export interface SecFilingDetail {
  type: 'insider' | 'institutional' | 'ownership' | 'holding'
  entity: string
  action: string
  action_tone?: 'positive' | 'negative' | 'neutral'
  title?: string | null
  transaction_code?: string
  normalized_type?: string
  transaction_date?: string | null
  shares?: number | null
  price?: number | null
  value?: number | null
  shares_owned_after?: number | null
  ownership_type?: string | null
  is_derivative?: boolean
  classification?: string
  previous_shares?: number | null
  current_shares?: number | null
  change_shares?: number | null
  change_pct?: number | null
  report_period?: string | null
  issuer_name?: string | null
  event_type?: string | null
  ownership_pct?: number | null
  purpose?: string | null
  passive?: boolean
  form_type?: string
  market_value?: number | null
  issuer_cusip?: string | null
  security_type?: string | null
  put_call?: string | null
}

export interface SecFilingRecord {
  accession_number: string
  form_type: string
  form_family: string
  filing_date: string | null
  report_period: string | null
  description: string
  is_amendment: boolean
  edgar_url: string | null
  filer_name?: string | null
  action?: string | null
  action_tone?: 'positive' | 'negative' | 'neutral'
  details?: SecFilingDetail[]
}

export interface SecFilingsResponse {
  ticker: string
  months: number
  cutoff_date: string
  summary: Record<string, number>
  filings: SecFilingRecord[]
  insider_transactions: Array<Record<string, unknown>>
  beneficial_ownership: Array<Record<string, unknown>>
  provider_errors?: Array<{ provider: string; message: string }>
}

export interface SecFilingsAnalysisHighlight {
  category: string
  text: string
  tone: 'positive' | 'negative' | 'neutral'
}

export interface SecFilingsAnalysisResponse {
  ticker: string
  months: number
  headline: string
  gist: string[]
  sentiment: 'good' | 'bad' | 'mixed' | 'neutral'
  sentiment_label: string
  highlights: SecFilingsAnalysisHighlight[]
  source: 'llm' | 'rules'
  llm_available?: boolean
  llm_enabled?: boolean
  disclaimer: string
}

export interface ResearchCandidate {
  ticker: string
  accumulation_score: number
  signal?: string
  why?: string
  components?: AccumulationComponents
}

export interface TopAccumulationResponse {
  results: Array<{
    ticker: string
    score: number
    classification: string
    sector?: string | null
    components: AccumulationComponents
  }>
  sector?: string | null
  min_score: number
}

export interface ResearchQueryResponse {
  query: string
  filters: Record<string, unknown>
  candidates: ResearchCandidate[]
  narrative: string
  disclaimer: string
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_API_KEY || ''
const TOKEN_KEY = 'stockpulse_access_token'
const inflight = new Map<string, Promise<unknown>>()

type AuthListener = (token: string | null) => void
const authListeners = new Set<AuthListener>()

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore storage failures */
  }
  authListeners.forEach((listener) => listener(token))
}

export function onAuthChange(listener: AuthListener): () => void {
  authListeners.add(listener)
  return () => { authListeners.delete(listener) }
}

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
  const token = getAccessToken()
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
      setAccessToken(null)
    }
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
    predictionEnd: text(item.prediction_end) || undefined,
    horizon: number(item.horizon) ?? undefined,
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

function mapAuthUser(value: unknown): AuthUser {
  const payload = object(value)
  const alpaca = object(payload.alpaca)
  const paper = object(alpaca.paper)
  const live = object(alpaca.live)
  return {
    id: Number(payload.id) || 0,
    email: text(payload.email),
    alpaca: {
      paper: {
        configured: Boolean(paper.configured),
        keyPreview: text(paper.key_preview) || null,
      },
      live: {
        configured: Boolean(live.configured),
        keyPreview: text(live.key_preview) || null,
      },
    },
    researchLlmEnabled: Boolean(payload.research_llm_enabled),
    researchLlmAvailable: Boolean(payload.research_llm_available),
  }
}

function mapAuthResponse(value: unknown): AuthResponse {
  const payload = object(value)
  const token = text(payload.access_token)
  const user = mapAuthUser(payload.user)
  if (token) setAccessToken(token)
  return { accessToken: token, user }
}

function mapAccumulationResponse(payload: JsonObject): AccumulationResponse {
  const components = object(payload.components)
  return {
    ticker: text(payload.ticker),
    score: number(payload.score) ?? 50,
    signal: text(payload.signal, 'NEUTRAL'),
    classification: text(payload.classification, 'NEUTRAL'),
    components: {
      institutional: number(components.institutional) ?? undefined,
      insider: number(components.insider) ?? undefined,
      major_holder: number(components.major_holder) ?? undefined,
      price_volume: number(components.price_volume) ?? undefined,
      fundamentals: number(components.fundamentals) ?? undefined,
    },
    events: list(payload.events) as Array<Record<string, unknown>>,
    history: list(payload.history).map((row) => {
      const item = object(row)
      return {
        date: text(item.date),
        score: number(item.score) ?? 0,
        classification: text(item.classification),
      }
    }),
    as_of: text(payload.as_of),
    provider_errors: payload.provider_errors as AccumulationResponse['provider_errors'],
  }
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  register: async (email: string, password: string): Promise<AuthResponse> => mapAuthResponse(
    await request<unknown>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  ),
  login: async (email: string, password: string): Promise<AuthResponse> => mapAuthResponse(
    await request<unknown>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  ),
  me: async (): Promise<AuthUser> => mapAuthUser(await request<unknown>('/auth/me')),
  saveAlpacaCredentials: async (
    mode: TradingMode,
    keyId: string,
    secret: string,
  ): Promise<AuthUser> => mapAuthUser(
    await request<unknown>('/auth/alpaca', {
      method: 'PUT',
      body: JSON.stringify({ mode, key_id: keyId, secret }),
    }),
  ),
  deleteAlpacaCredentials: async (mode: TradingMode): Promise<AuthUser> => mapAuthUser(
    await request<unknown>(`/auth/alpaca?${query({ mode })}`, { method: 'DELETE' }),
  ),
  savePreferences: async (preferences: { researchLlmEnabled: boolean }): Promise<AuthUser> => mapAuthUser(
    await request<unknown>('/auth/preferences', {
      method: 'PUT',
      body: JSON.stringify({ research_llm_enabled: preferences.researchLlmEnabled }),
    }),
  ),
  logout: () => { setAccessToken(null) },
  config: async (): Promise<AppConfig> => {
    const payload = object(await request<unknown>('/config/status'))
    const alpaca = object(payload.alpaca)
    const user = object(payload.user)
    return {
      alpacaConnected: Boolean(alpaca.paper_configured),
      paperConfigured: Boolean(alpaca.paper_configured),
      liveConfigured: Boolean(alpaca.live_configured),
      paperKeyPreview: text(alpaca.paper_key_preview) || null,
      liveKeyPreview: text(alpaca.live_key_preview) || null,
      liveTradingEnabled: Boolean(payload.live_trading_allowed),
      dataFeed: text(payload.data_feed),
      userEmail: text(user.email) || undefined,
      researchLlmAvailable: Boolean(payload.research_llm_available),
      researchLlmEnabled: Boolean(payload.research_llm_enabled),
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
  chart: async (symbol: string, timeframe: ChartInterval = '1Day'): Promise<ChartResponse> => {
    const limits: Record<ChartInterval, number> = {
      '1Min': 390,
      '5Min': 256,
      '15Min': 256,
      '1Hour': 240,
      '1Day': 180,
    }
    const payload = object(await request<unknown>(
      `/stocks/${encodeURIComponent(symbol)}/bars?${query({ timeframe, limit: limits[timeframe] })}`,
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
  forecast: async (
    symbol: string,
    horizon: 'short' | 'long',
    bars: number = horizon === 'long' ? 20 : 12,
    engine: 'kronos' | 'ensemble' = 'kronos',
    timeframe?: ChartInterval,
  ): Promise<ForecastResponse> => {
    const cacheKey = `forecast:${symbol}:${horizon}:${bars}:${engine}:${timeframe || 'default'}`
    const payload = object(await coalesced(cacheKey, () => requestWithRetry<unknown>('/forecast', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        preset: horizon,
        horizon: bars,
        engine,
        ...(timeframe ? { timeframe } : {}),
      }),
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
    const pathSegments = list(payload.path_segments).map((value) => {
      const item = object(value)
      const directionRaw = text(item.direction)
      const direction = directionRaw === 'up' || directionRaw === 'down' || directionRaw === 'flat'
        ? directionRaw
        : 'flat'
      return {
        direction,
        startIndex: number(item.start_index) ?? 0,
        endIndex: number(item.end_index) ?? 0,
        startClose: number(item.start_close) ?? 0,
        endClose: number(item.end_close) ?? 0,
        change: number(item.change) ?? 0,
        startTimestamp: text(item.start_timestamp) || undefined,
        endTimestamp: text(item.end_timestamp) || undefined,
      } satisfies ForecastPathSegment
    })
    const modelsUsed = list(model.models_used).map((value) => text(value)).filter(Boolean)
    const engineRaw = text(model.engine) || engine
    const resolvedEngine = engineRaw === 'ensemble' ? 'ensemble' : 'kronos'
    const timeframeRaw = text(payload.timeframe) || timeframe || ''
    const resolvedTimeframe = (
      timeframeRaw === '1Min'
      || timeframeRaw === '5Min'
      || timeframeRaw === '15Min'
      || timeframeRaw === '1Hour'
      || timeframeRaw === '1Day'
    ) ? timeframeRaw : undefined
    return {
      symbol: text(payload.symbol, symbol),
      horizon,
      bars,
      timeframe: resolvedTimeframe,
      engine: resolvedEngine,
      points,
      model: text(model.id, resolvedEngine === 'ensemble' ? 'ensemble' : 'Kronos'),
      modelsUsed: modelsUsed.length ? modelsUsed : undefined,
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
      pathSegments,
      evaluation: {
        folds: number(object(payload.evaluation).folds) ?? 0,
        hitRate: number(object(payload.evaluation).hit_rate),
        meanNetReturn: number(object(payload.evaluation).mean_net_return),
        ic: number(object(payload.evaluation).ic),
        evalHorizon: number(object(payload.evaluation).eval_horizon),
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
  realizedPl: async (mode: TradingMode): Promise<{ realizedPl: number; fillCount: number; asOf?: string }> => {
    const item = object(await request<unknown>(`/account/realized-pl?${query({ mode })}`))
    return {
      realizedPl: number(item.realized_pl) ?? 0,
      fillCount: number(item.fill_count) ?? 0,
      asOf: text(item.as_of) || undefined,
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
  secIntelligence: async (symbol: string): Promise<SecIntelligenceResponse> => {
    const payload = object(await request<unknown>(`/stocks/${encodeURIComponent(symbol)}/sec`))
    return {
      ticker: text(payload.ticker, symbol.toUpperCase()),
      accumulation: mapAccumulationResponse(object(payload.accumulation)),
      institutional_changes: list(payload.institutional_changes) as Array<Record<string, unknown>>,
      insider_transactions: list(payload.insider_transactions) as Array<Record<string, unknown>>,
      major_holder_changes: list(payload.major_holder_changes) as Array<Record<string, unknown>>,
      caveats: list(payload.caveats).map((value) => text(value)),
      provider_errors: payload.provider_errors as SecIntelligenceResponse['provider_errors'],
    }
  },
  accumulation: async (symbol: string): Promise<AccumulationResponse> =>
    mapAccumulationResponse(object(await request<unknown>(`/stocks/${encodeURIComponent(symbol)}/accumulation`))),
  sectorAccumulation: async (sector: string): Promise<SectorAccumulationResponse> => {
    const payload = object(await request<unknown>(`/sectors/${encodeURIComponent(sector)}/accumulation`))
    return {
      sector: text(payload.sector, sector),
      avg_score: number(payload.avg_score) ?? 50,
      pct_increasing: number(payload.pct_increasing) ?? 0,
      pct_decreasing: number(payload.pct_decreasing) ?? 0,
      ticker_count: number(payload.ticker_count) ?? undefined,
      stocks: list(payload.stocks).map((row) => {
        const item = object(row)
        const components = object(item.components)
        return {
          ticker: text(item.ticker),
          score: number(item.score) ?? 0,
          components: {
            institutional: number(components.institutional) ?? undefined,
            insider: number(components.insider) ?? undefined,
            major_holder: number(components.major_holder) ?? undefined,
            price_volume: number(components.price_volume) ?? undefined,
            fundamentals: number(components.fundamentals) ?? undefined,
          },
        }
      }),
    }
  },
  listSectors: async (): Promise<SectorListResponse> => {
    const payload = object(await request<unknown>('/sectors'))
    return {
      sectors: list(payload.sectors).map((row) => {
        const item = object(row)
        return {
          sector: text(item.sector),
          ticker_count: number(item.ticker_count) ?? 0,
        }
      }),
    }
  },
  startAccumulationScan: async (refresh = false): Promise<AccumulationScanStatus> => {
    const suffix = refresh ? '?refresh=true' : ''
    const payload = object(await request<unknown>(`/accumulation/scan${suffix}`, { method: 'POST' }))
    return {
      status: text(payload.status, 'pending'),
      scanned: number(payload.scanned) ?? 0,
      total: number(payload.total) ?? 0,
      errors: list(payload.errors) as AccumulationScanStatus['errors'],
      started_at: payload.started_at as string | null,
      finished_at: payload.finished_at as string | null,
      error: payload.error as string | undefined,
    }
  },
  accumulationScanStatus: async (): Promise<AccumulationScanStatus> => {
    const payload = object(await request<unknown>('/accumulation/scan/status'))
    return {
      status: text(payload.status, 'idle'),
      scanned: number(payload.scanned) ?? 0,
      total: number(payload.total) ?? 0,
      errors: list(payload.errors) as AccumulationScanStatus['errors'],
      started_at: payload.started_at as string | null,
      finished_at: payload.finished_at as string | null,
      error: payload.error as string | undefined,
    }
  },
  secFilings: async (symbol: string, params?: { months?: number; limit?: number }): Promise<SecFilingsResponse> => {
    const query = new URLSearchParams()
    if (params?.months != null) query.set('months', String(params.months))
    if (params?.limit != null) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    const payload = object(await request<unknown>(`/stocks/${encodeURIComponent(symbol)}/filings${suffix}`))
    return {
      ticker: text(payload.ticker, symbol.toUpperCase()),
      months: number(payload.months) ?? 6,
      cutoff_date: text(payload.cutoff_date),
      summary: object(payload.summary) as Record<string, number>,
      filings: list(payload.filings).map((row) => {
        const item = object(row)
        const actionTone = text(item.action_tone) as SecFilingRecord['action_tone']
        return {
          accession_number: text(item.accession_number),
          form_type: text(item.form_type),
          form_family: text(item.form_family),
          filing_date: item.filing_date as string | null,
          report_period: item.report_period as string | null,
          description: text(item.description),
          is_amendment: Boolean(item.is_amendment),
          edgar_url: item.edgar_url as string | null,
          filer_name: item.filer_name as string | null | undefined,
          action: item.action as string | null | undefined,
          action_tone: ['positive', 'negative', 'neutral'].includes(actionTone || '') ? actionTone : 'neutral',
          details: list(item.details).map((detailRow) => {
            const detail = object(detailRow)
            const detailTone = text(detail.action_tone) as SecFilingDetail['action_tone']
            return {
              type: text(detail.type) as SecFilingDetail['type'],
              entity: text(detail.entity),
              action: text(detail.action),
              action_tone: ['positive', 'negative', 'neutral'].includes(detailTone || '') ? detailTone : 'neutral',
              title: detail.title as string | null | undefined,
              transaction_code: detail.transaction_code as string | undefined,
              normalized_type: detail.normalized_type as string | undefined,
              transaction_date: detail.transaction_date as string | null | undefined,
              shares: number(detail.shares) ?? undefined,
              price: number(detail.price) ?? undefined,
              value: number(detail.value) ?? undefined,
              shares_owned_after: number(detail.shares_owned_after) ?? undefined,
              ownership_type: detail.ownership_type as string | null | undefined,
              is_derivative: detail.is_derivative as boolean | undefined,
              classification: detail.classification as string | undefined,
              previous_shares: number(detail.previous_shares) ?? undefined,
              current_shares: number(detail.current_shares) ?? undefined,
              change_shares: number(detail.change_shares) ?? undefined,
              change_pct: number(detail.change_pct) ?? undefined,
              report_period: detail.report_period as string | null | undefined,
              issuer_name: detail.issuer_name as string | null | undefined,
              event_type: detail.event_type as string | null | undefined,
              ownership_pct: number(detail.ownership_pct) ?? undefined,
              purpose: detail.purpose as string | null | undefined,
              passive: detail.passive as boolean | undefined,
              form_type: detail.form_type as string | undefined,
              market_value: number(detail.market_value) ?? undefined,
              issuer_cusip: detail.issuer_cusip as string | null | undefined,
              security_type: detail.security_type as string | null | undefined,
              put_call: detail.put_call as string | null | undefined,
            }
          }),
        }
      }),
      insider_transactions: list(payload.insider_transactions) as Array<Record<string, unknown>>,
      beneficial_ownership: list(payload.beneficial_ownership) as Array<Record<string, unknown>>,
      provider_errors: payload.provider_errors as SecFilingsResponse['provider_errors'],
    }
  },
  secFilingsAnalysis: async (symbol: string, params?: { months?: number }): Promise<SecFilingsAnalysisResponse> => {
    const query = new URLSearchParams()
    if (params?.months != null) query.set('months', String(params.months))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    const payload = object(await request<unknown>(`/stocks/${encodeURIComponent(symbol)}/filings/analysis${suffix}`))
    const sentiment = text(payload.sentiment) as SecFilingsAnalysisResponse['sentiment']
    const source = text(payload.source) as SecFilingsAnalysisResponse['source']
    return {
      ticker: text(payload.ticker, symbol.toUpperCase()),
      months: number(payload.months) ?? 6,
      headline: text(payload.headline),
      gist: list(payload.gist).map((item) => String(item)),
      sentiment: ['good', 'bad', 'mixed', 'neutral'].includes(sentiment) ? sentiment : 'neutral',
      sentiment_label: text(payload.sentiment_label, 'Neutral'),
      highlights: list(payload.highlights).map((row) => {
        const item = object(row)
        const tone = text(item.tone) as SecFilingsAnalysisHighlight['tone']
        return {
          category: text(item.category),
          text: text(item.text),
          tone: ['positive', 'negative', 'neutral'].includes(tone) ? tone : 'neutral',
        }
      }),
      source: source === 'llm' ? 'llm' : 'rules',
      llm_available: Boolean(payload.llm_available),
      llm_enabled: Boolean(payload.llm_enabled),
      disclaimer: text(payload.disclaimer),
    }
  },
  topAccumulation: async (params?: { sector?: string; minScore?: number; limit?: number }): Promise<TopAccumulationResponse> => {
    const query = new URLSearchParams()
    if (params?.sector) query.set('sector', params.sector)
    if (params?.minScore != null) query.set('min_score', String(params.minScore))
    if (params?.limit != null) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    const payload = object(await request<unknown>(`/accumulation/top${suffix}`))
    return {
      sector: payload.sector as string | null,
      min_score: number(payload.min_score) ?? 0,
      results: list(payload.results).map((row) => {
        const item = object(row)
        const components = object(item.components)
        return {
          ticker: text(item.ticker),
          score: number(item.score) ?? 0,
          classification: text(item.classification),
          sector: item.sector as string | null,
          components: {
            institutional: number(components.institutional) ?? undefined,
            insider: number(components.insider) ?? undefined,
            major_holder: number(components.major_holder) ?? undefined,
            price_volume: number(components.price_volume) ?? undefined,
            fundamentals: number(components.fundamentals) ?? undefined,
          },
        }
      }),
    }
  },
  researchQuery: async (query: string): Promise<ResearchQueryResponse> => {
    const payload = object(await request<unknown>('/research/query', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }))
    return {
      query: text(payload.query, query),
      filters: object(payload.filters) as Record<string, unknown>,
      candidates: list(payload.candidates).map((row) => {
        const item = object(row)
        const components = object(item.components)
        return {
          ticker: text(item.ticker),
          accumulation_score: number(item.accumulation_score) ?? 0,
          signal: item.signal as string | undefined,
          why: item.why as string | undefined,
          components: {
            institutional: number(components.institutional) ?? undefined,
            insider: number(components.insider) ?? undefined,
            major_holder: number(components.major_holder) ?? undefined,
            price_volume: number(components.price_volume) ?? undefined,
            fundamentals: number(components.fundamentals) ?? undefined,
          },
        }
      }),
      narrative: text(payload.narrative),
      disclaimer: text(payload.disclaimer),
    }
  },
}
