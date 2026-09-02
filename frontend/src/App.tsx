import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3,
  BriefcaseBusiness, CheckCircle2, ChevronDown, Clock3, ExternalLink, LoaderCircle,
  LogOut, RefreshCw, Search, Settings, ShieldCheck, WalletCards, XCircle,
} from 'lucide-react'
import {
  ApiError,
  api,
  getAccessToken,
  onAuthChange,
  type Account, type AppConfig, type AuthUser, type ChartInterval, type ChartResponse, type ForecastResponse, type HybridPrediction, type MarketClock, type NewsItem,
  type ResearchQueryResponse, type SecFilingsAnalysisResponse, type SecFilingsResponse, type SecIntelligenceResponse, type SectorAccumulationResponse, type TopAccumulationResponse,
  type AccumulationScanStatus,
  type OptionChain, type OptionContract, type OptionPositionIntent, type Order, type OrderSide, type OrderType,
  type Position, type PublicSentiment, type Quote, type SearchResult, type SentimentLabel,
  type TradingMode,
} from './api'
import {
  formatCurrency, formatDateTime, formatNumber, formatPercent,
  localMarketClock, marketStatusLabel, marketStatusTone,
} from './format'
import { AuthScreen } from './AuthScreen'
import { MarketChart } from './MarketChart'
import { MoversPanel } from './MoversPanel'
import { PortfolioPanel, type HoldSuggestion } from './PortfolioPanel'
import { OrderReview, type ReviewOrder } from './OrderReview'
import { SettingsModal } from './SettingsModal'
import { ResearchPanel, SecIntelligencePanel, SecRecordsPanel, SectorsPanel, TopAccumulationPanel } from './SecIntelligencePanel'
import './App.css'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function unavailableLabel(result: PromiseSettledResult<unknown>, name: string): string {
  if (result.status !== 'rejected') return ''
  const reason = result.reason
  if (reason instanceof ApiError && reason.status === 429) {
    return `${name} is throttled; retry in a few seconds`
  }
  if (reason instanceof ApiError && reason.message && reason.message !== `Request failed (${reason.status})`) {
    return `${name}: ${reason.message}`
  }
  return `${name} data is temporarily unavailable`
}

function SentimentBadge({ kind, label, muted }: { kind: 'Public' | 'Investors'; label?: SentimentLabel | null; muted?: boolean }) {
  const display = label ?? '—'
  const tone = label ?? 'unknown'
  return (
    <span
      className={`sentiment-pill ${tone}${muted ? ' muted' : ''}`}
      aria-label={`${kind} ${label ?? 'unavailable'}${muted ? ' unreliable' : ''}`}
      title={muted ? 'Out-of-sample edge is not reliable in the current regime' : undefined}
    >
      <span className="sentiment-kind">{kind}</span>
      {display}
    </span>
  )
}

function StatusPill({ status }: { status: Order['status'] }) {
  const icon = status === 'filled' || status === 'accepted'
    ? <CheckCircle2 size={13} />
    : status === 'rejected' || status === 'canceled'
      ? <XCircle size={13} /> : <Clock3 size={13} />
  return <span className={`status ${status}`}>{icon}{status}</span>
}

const EmptyState = ({ children }: { children: ReactNode }) =>
  <div className="empty-state">{children}</div>

function MarketLight({ clock }: { clock: MarketClock }) {
  const tone = marketStatusTone(clock.session, clock.isOpen)
  const label = marketStatusLabel(clock.session, clock.isOpen)
  const next = clock.isOpen ? clock.nextClose : clock.nextOpen
  const hint = next ? `${clock.isOpen ? 'Closes' : 'Opens'} ${formatDateTime(next)}` : label
  const lamps = [
    { id: 'red', on: tone === 'closed', off: '#7a2424', lit: '#ff2d2d' },
    { id: 'yellow', on: tone === 'extended', off: '#7a6418', lit: '#ffd000' },
    { id: 'green', on: tone === 'open', off: '#1c6b3a', lit: '#22ff7a' },
  ] as const
  return (
    <div className={`traffic-sign ${tone}`} role="status" aria-label={label} title={hint}>
      <div className="traffic-housing" aria-hidden="true">
        {lamps.map((lamp) => (
          <span
            key={lamp.id}
            className={`traffic-lamp ${lamp.id}${lamp.on ? ' on' : ''}`}
            style={{
              background: lamp.on ? lamp.lit : lamp.off,
              boxShadow: lamp.on ? `0 0 12px 3px ${lamp.lit}` : 'inset 0 2px 3px #0009',
            }}
          />
        ))}
      </div>
      <span className="traffic-label">{label}</span>
    </div>
  )
}

type ForecastPreset = 'short' | 'long'
type ForecastEngine = 'kronos' | 'ensemble'

const CHART_INTERVALS: ChartInterval[] = ['1Min', '5Min', '15Min', '1Hour', '1Day']
const DEFAULT_INTERVAL: Record<ForecastPreset, ChartInterval> = { short: '5Min', long: '1Day' }
const DEFAULT_BARS: Record<ForecastPreset, number> = { short: 12, long: 20 }

const INTERVAL_LABELS: Record<ChartInterval, string> = {
  '1Min': '1m',
  '5Min': '5m',
  '15Min': '15m',
  '1Hour': '1h',
  '1Day': '1D',
}

function barUnitLabel(interval: ChartInterval, bars: number): string {
  const units: Record<ChartInterval, [string, string]> = {
    '1Min': ['1-minute bar', '1-minute bars'],
    '5Min': ['five-minute bar', 'five-minute bars'],
    '15Min': ['15-minute bar', '15-minute bars'],
    '1Hour': ['hourly bar', 'hourly bars'],
    '1Day': ['trading day', 'trading days'],
  }
  const [one, many] = units[interval]
  return bars === 1 ? `1 ${one}` : `${bars} ${many}`
}

function intervalMetaLabel(interval: ChartInterval): string {
  return {
    '1Min': '1-minute bars',
    '5Min': '5-minute bars',
    '15Min': '15-minute bars',
    '1Hour': 'hourly bars',
    '1Day': 'daily bars',
  }[interval]
}

function describePathSegments(segments: NonNullable<ForecastResponse['pathSegments']>): string {
  if (!segments.length) return 'The selected forecast path is flat within the model’s noise band.'
  return segments.map((segment) => {
    const bars = Math.max(1, segment.endIndex - segment.startIndex)
    const move = formatPercent(segment.change, false)
    if (segment.direction === 'up') return `rises ${move} over ${bars} bar${bars === 1 ? '' : 's'}`
    if (segment.direction === 'down') return `falls ${move} over ${bars} bar${bars === 1 ? '' : 's'}`
    return `holds near flat (${move}) over ${bars} bar${bars === 1 ? '' : 's'}`
  }).join(', then ')
}

function DecisionPanel({
  forecast,
  prediction,
  news,
  publicSentiment,
  interval,
}: {
  forecast: ForecastResponse | null
  prediction: HybridPrediction | null
  news: NewsItem[]
  publicSentiment: PublicSentiment | null
  interval: ChartInterval
}) {
  if (!forecast && !prediction) {
    return (
      <div className="decision-panel">
        <EmptyState>Load a forecast to see chart-path turns and model-stance context.</EmptyState>
      </div>
    )
  }
  const target = forecast?.points.at(-1)
  const bullishNews = news.filter((item) => item.sentiment === 'positive').slice(0, 3)
  const bearishNews = news.filter((item) => item.sentiment === 'negative').slice(0, 3)
  const regime = forecast?.regime || prediction?.marketRegime || ''
  const regimeUp = regime.includes('_up') || regime === 'BULL'
  const regimeDown = regime.includes('_down') || regime.includes('high_vol') || regime === 'BEAR' || regime === 'HIGH_VOLATILITY'
  const publicUp = publicSentiment?.label === 'bullish'
  const publicDown = publicSentiment?.label === 'bearish'
  const signal = prediction?.signal || '—'
  const signalTone = signal.includes('BUY') ? 'positive' : signal.includes('SELL') ? 'negative' : undefined
  const upDrivers = [
    ...(publicUp ? [`Public news sentiment is ${publicSentiment?.label}`] : []),
    ...(regimeUp ? [`Price regime looks supportive (${regime.replaceAll('_', ' ')})`] : []),
    ...bullishNews.map((item) => item.headline),
  ]
  const downDrivers = [
    ...(publicDown ? [`Public news sentiment is ${publicSentiment?.label}`] : []),
    ...(regimeDown ? [`Regime caution (${regime.replaceAll('_', ' ')})`] : []),
    ...(forecast?.edgeReliable === false ? ['Out-of-sample edge is not reliable in the current regime'] : []),
    ...bearishNews.map((item) => item.headline),
  ]
  const resolvedInterval = forecast?.timeframe || interval

  return (
    <div className="decision-panel">
      <p className="decision-lens-note">
        Two separate research views: <strong>chart path</strong> (where the forecast line goes) and{' '}
        <strong>model stance</strong> (probability call for a holding window). Disagreement is normal.
      </p>
      <div className="decision-summary">
        <div>
          <span>Chart path target</span>
          <strong>{formatCurrency(target?.value)}</strong>
        </div>
        <div>
          <span>Chart path move</span>
          <strong className={(forecast?.netForecastChange ?? forecast?.forecastChange ?? 0) >= 0 ? 'positive' : 'negative'}>
            {formatPercent(forecast?.netForecastChange ?? forecast?.forecastChange, false)}
          </strong>
        </div>
        <div>
          <span>Chart path window</span>
          <strong>{forecast ? barUnitLabel(resolvedInterval, forecast.bars) : '—'}</strong>
        </div>
        <div>
          <span>Chart path bias</span>
          <strong className={forecast?.sentiment === 'bullish' ? 'positive' : forecast?.sentiment === 'bearish' ? 'negative' : undefined}>
            {forecast?.sentiment ?? '—'}
          </strong>
        </div>
        <div>
          <span>Model stance</span>
          <strong className={signalTone}>{signal}</strong>
        </div>
        <div>
          <span>Model P(up)</span>
          <strong>{prediction?.probability == null ? '—' : formatPercent(prediction.probability, false)}</strong>
        </div>
        <div>
          <span>Model risk</span>
          <strong>{prediction?.riskScore == null ? '—' : prediction.riskScore.toFixed(2)}</strong>
        </div>
        <div>
          <span>Model window</span>
          <strong>{prediction?.horizon ?? '—'}</strong>
        </div>
      </div>
      {forecast ? (
        <p className="decision-path">
          <strong>Chart path:</strong> Forecast {describePathSegments(forecast.pathSegments || [])}.
        </p>
      ) : null}
      {prediction?.explanationText ? (
        <p className="decision-path">
          <strong>Model stance:</strong> {prediction.explanationText.split('\n')[0]}
        </p>
      ) : null}
      <div className="decision-columns">
        <div>
          <h3>Why it may go up</h3>
          {upDrivers.length
            ? <ul>{upDrivers.map((item) => <li key={item}>{item}</li>)}</ul>
            : <p>No strong bullish news or regime cue right now — lean on the chart path and model probability.</p>}
        </div>
        <div>
          <h3>Why it may go down</h3>
          {downDrivers.length
            ? <ul>{downDrivers.map((item) => <li key={item}>{item}</li>)}</ul>
            : <p>No strong bearish news or regime cue right now — lean on the chart path and model probability.</p>}
        </div>
      </div>
      <p className="decision-note">
        Chart path bias comes from the Kronos/ensemble close path. Model stance is a separate probability call
        (technical features → XGBoost in MVP-1). Neither places orders.
      </p>
    </div>
  )
}

type DashboardView = 'market' | 'sectors' | 'top' | 'research' | 'records'

const FALLBACK_SECTORS = ['Energy', 'Technology', 'Healthcare', 'Financials', 'Industrials']

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => { window.setTimeout(resolve, ms) })
}

function App() {
  const [accessToken, setAccessTokenState] = useState<string | null>(() => getAccessToken())
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [authChecking, setAuthChecking] = useState(() => Boolean(getAccessToken()))
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [mode, setMode] = useState<TradingMode>('paper')
  const [modeConfirm, setModeConfirm] = useState(false)
  const [livePhrase, setLivePhrase] = useState('')
  const [symbol, setSymbol] = useState('SPY')
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [quote, setQuote] = useState<Quote | null>(null)
  const [publicSentiment, setPublicSentiment] = useState<PublicSentiment | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [chart, setChart] = useState<ChartResponse | null>(null)
  const [forecast, setForecast] = useState<ForecastResponse | null>(null)
  const [prediction, setPrediction] = useState<HybridPrediction | null>(null)
  const [horizon, setHorizon] = useState<ForecastPreset>('short')
  const [chartInterval, setChartInterval] = useState<ChartInterval>(DEFAULT_INTERVAL.short)
  const [forecastEngine, setForecastEngine] = useState<ForecastEngine>('kronos')
  const [marketState, setMarketState] = useState<LoadState>('idle')
  const [marketError, setMarketError] = useState('')
  const [marketWarning, setMarketWarning] = useState('')
  const [account, setAccount] = useState<Account | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [portfolioState, setPortfolioState] = useState<LoadState>('idle')
  const [portfolioError, setPortfolioError] = useState('')
  const [realizedPl, setRealizedPl] = useState<number | null>(null)
  const [realizedPlState, setRealizedPlState] = useState<LoadState>('idle')
  const [holdSuggestions, setHoldSuggestions] = useState<HoldSuggestion[]>([])
  const [activePanel, setActivePanel] = useState<'trade' | 'portfolio'>('trade')
  const [assetType, setAssetType] = useState<'equity' | 'option'>('equity')
  const [side, setSide] = useState<OrderSide>('buy')
  const [orderType, setOrderType] = useState<OrderType>('market')
  const [quantity, setQuantity] = useState('1')
  const [notional, setNotional] = useState('')
  const [limitPrice, setLimitPrice] = useState('')
  const [chain, setChain] = useState<OptionChain | null>(null)
  const [optionType, setOptionType] = useState<'call' | 'put'>('call')
  const [positionIntent, setPositionIntent] = useState<OptionPositionIntent>('buy_to_open')
  const [expiration, setExpiration] = useState('')
  const [selectedContract, setSelectedContract] = useState<OptionContract | null>(null)
  const [chainState, setChainState] = useState<LoadState>('idle')
  const [chainError, setChainError] = useState('')
  const [review, setReview] = useState<ReviewOrder | null>(null)
  const [orderBusy, setOrderBusy] = useState(false)
  const [orderError, setOrderError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Order | null>(null)
  const [cancelCandidate, setCancelCandidate] = useState<Order | null>(null)
  const [cancelBusy, setCancelBusy] = useState(false)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const marketRequest = useRef(0)
  const [clock, setClock] = useState<MarketClock>(() => {
    const local = localMarketClock()
    return { isOpen: local.isOpen, session: local.session }
  })
  const [dashboardView, setDashboardView] = useState<DashboardView>('market')
  const [secData, setSecData] = useState<SecIntelligenceResponse | null>(null)
  const [secState, setSecState] = useState<LoadState>('idle')
  const [secError, setSecError] = useState('')
  const [sectorRows, setSectorRows] = useState<SectorAccumulationResponse[]>([])
  const [sectorsState, setSectorsState] = useState<LoadState>('idle')
  const [topAccumulation, setTopAccumulation] = useState<TopAccumulationResponse | null>(null)
  const [topState, setTopState] = useState<LoadState>('idle')
  const [researchResponse, setResearchResponse] = useState<ResearchQueryResponse | null>(null)
  const [researchState, setResearchState] = useState<LoadState>('idle')
  const [researchError, setResearchError] = useState('')
  const [scanProgress, setScanProgress] = useState<AccumulationScanStatus | null>(null)
  const [recordsData, setRecordsData] = useState<SecFilingsResponse | null>(null)
  const [recordsState, setRecordsState] = useState<LoadState>('idle')
  const [recordsError, setRecordsError] = useState('')
  const [recordsAnalysis, setRecordsAnalysis] = useState<SecFilingsAnalysisResponse | null>(null)
  const [recordsAnalysisState, setRecordsAnalysisState] = useState<LoadState>('idle')
  const [recordsAnalysisError, setRecordsAnalysisError] = useState('')

  const loadSec = useCallback(async () => {
    setSecState('loading')
    setSecError('')
    try {
      const payload = await api.secIntelligence(symbol)
      setSecData(payload)
      setSecState('ready')
    } catch (error) {
      setSecData(null)
      setSecError(error instanceof Error ? error.message : 'SEC data unavailable')
      setSecState('error')
    }
  }, [symbol])

  const reloadMarketSecData = useCallback(async () => {
    setSectorsState('loading')
    setTopState('loading')
    try {
      const sectorList = await api.listSectors()
      const names = sectorList.sectors.map((row) => row.sector).filter(Boolean)
      const sectors = names.length ? names : FALLBACK_SECTORS
      const rows = await Promise.all(sectors.map((sector) => api.sectorAccumulation(sector)))
      setSectorRows(rows)
      setSectorsState('ready')
      const top = await api.topAccumulation({ minScore: 0, limit: 50 })
      setTopAccumulation(top)
      setTopState('ready')
    } catch (error) {
      setSectorsState('error')
      setTopState('error')
      setSectorRows([])
      setTopAccumulation(null)
      if (error instanceof Error && !scanProgress?.error) {
        /* keep silent; panels show error state */
      }
    }
  }, [])

  const pollAccumulationScan = useCallback(async () => {
    try {
      await api.startAccumulationScan()
    } catch {
      /* scan may already be running */
    }
    for (let attempt = 0; attempt < 90; attempt += 1) {
      try {
        const status = await api.accumulationScanStatus()
        setScanProgress(status)
        if (status.status === 'ready' || status.status === 'error' || status.status === 'disabled') {
          await reloadMarketSecData()
          return
        }
        if (status.status === 'running' && attempt > 0 && attempt % 3 === 0) {
          await reloadMarketSecData()
        }
      } catch {
        break
      }
      await sleep(2000)
    }
    await reloadMarketSecData()
  }, [reloadMarketSecData])

  const loadSectorPanels = useCallback(async () => {
    void pollAccumulationScan()
  }, [pollAccumulationScan])

  const refreshMarketScan = useCallback(async () => {
    try {
      await api.startAccumulationScan(true)
      await pollAccumulationScan()
    } catch {
      await reloadMarketSecData()
    }
  }, [pollAccumulationScan, reloadMarketSecData])

  const loadRecords = useCallback(async (ticker: string) => {
    setRecordsState('loading')
    setRecordsError('')
    setRecordsAnalysis(null)
    setRecordsAnalysisState('loading')
    setRecordsAnalysisError('')
    try {
      const payload = await api.secFilings(ticker, { months: 6, limit: 100 })
      setRecordsData(payload)
      setRecordsState('ready')
      try {
        const analysis = await api.secFilingsAnalysis(ticker, { months: 6 })
        setRecordsAnalysis(analysis)
        setRecordsAnalysisState('ready')
      } catch (error) {
        setRecordsAnalysis(null)
        setRecordsAnalysisError(error instanceof Error ? error.message : 'SEC analysis unavailable')
        setRecordsAnalysisState('error')
      }
    } catch (error) {
      setRecordsData(null)
      setRecordsAnalysis(null)
      setRecordsError(error instanceof Error ? error.message : 'SEC records unavailable')
      setRecordsState('error')
      setRecordsAnalysisState('idle')
    }
  }, [])

  const runResearch = useCallback(async (query: string) => {
    setResearchState('loading')
    setResearchError('')
    try {
      const payload = await api.researchQuery(query)
      setResearchResponse(payload)
      setResearchState('ready')
    } catch (error) {
      setResearchResponse(null)
      setResearchError(error instanceof Error ? error.message : 'Research query failed')
      setResearchState('error')
    }
  }, [])

  const loadMarket = useCallback(async () => {
    const requestId = ++marketRequest.current
    setMarketState('loading')
    setMarketError('')
    setMarketWarning('')
    setQuote(null)
    setChart(null)
    setForecast(null)
    setPrediction(null)
    setNews([])
    setPublicSentiment(null)
    try {
      const overviewPromise = api.overview(symbol).then((overview) => {
        if (requestId !== marketRequest.current) return overview
        setQuote(overview.quote)
        setPublicSentiment(overview.publicSentiment)
        setNews(overview.news || [])
        setMarketState('ready')
        return overview
      })
      const forecastBars = DEFAULT_BARS[horizon]
      const predictionHorizon = chartInterval === '1Day' && horizon === 'long' ? '20d' : '5d'
      const [overviewResult, chartResult, forecastResult, predictionResult] = await Promise.allSettled([
        overviewPromise,
        api.chart(symbol, chartInterval),
        api.forecast(symbol, horizon, forecastBars, forecastEngine, chartInterval),
        api.prediction(symbol, predictionHorizon),
      ])
      if (requestId !== marketRequest.current) return
      if (overviewResult.status === 'rejected') throw overviewResult.reason
      setChart(chartResult.status === 'fulfilled' ? chartResult.value : null)
      setForecast(forecastResult.status === 'fulfilled' ? forecastResult.value : null)
      setPrediction(predictionResult.status === 'fulfilled' ? predictionResult.value : null)
      const unavailable = [
        unavailableLabel(chartResult, 'chart'),
        unavailableLabel(forecastResult, 'forecast'),
        unavailableLabel(predictionResult, 'hybrid prediction'),
      ].filter(Boolean)
      if (unavailable.length) {
        setMarketWarning(`${unavailable.join('. ')}.`)
      }
      setMarketState('ready')
    } catch (error) {
      if (requestId !== marketRequest.current) return
      setQuote(null)
      setChart(null)
      setForecast(null)
      setPrediction(null)
      setMarketError(error instanceof Error ? error.message : 'Unable to load market data')
      setMarketState('error')
    }
  }, [symbol, horizon, chartInterval, forecastEngine])

  const loadPortfolio = useCallback(async () => {
    setPortfolioState('loading')
    setPortfolioError('')
    setAccount(null)
    setPositions([])
    setOrders([])
    setRealizedPl(null)
    setRealizedPlState('loading')
    try {
      const [accountData, positionData, orderData, realizedResult] = await Promise.all([
        api.account(mode),
        api.positions(mode),
        api.orders(mode),
        api.realizedPl(mode).then(
          (data) => ({ ok: true as const, data }),
          (reason) => ({ ok: false as const, reason }),
        ),
      ])
      setAccount(accountData)
      setPositions(positionData)
      setOrders(orderData)
      setPortfolioState('ready')
      if (realizedResult.ok) {
        setRealizedPl(realizedResult.data.realizedPl)
        setRealizedPlState('ready')
      } else {
        setRealizedPl(null)
        setRealizedPlState('error')
      }
    } catch (error) {
      setPortfolioError(error instanceof Error ? error.message : 'Unable to load account')
      setPortfolioState('error')
      setRealizedPlState('error')
    }
  }, [mode])

  const loadClock = useCallback(async () => {
    try {
      setClock(await api.clock())
    } catch {
      const local = localMarketClock()
      setClock({ isOpen: local.isOpen, session: local.session })
    }
  }, [])

  useEffect(() => onAuthChange((token) => {
    setAccessTokenState(token)
    if (!token) setAuthUser(null)
  }), [])

  useEffect(() => {
    if (!accessToken) {
      setAuthUser(null)
      setAuthChecking(false)
      return
    }
    let active = true
    setAuthChecking(true)
    api.me()
      .then((user) => {
        if (active) {
          setAuthUser(user)
          setAuthChecking(false)
        }
      })
      .catch(() => {
        if (active) {
          setAuthUser(null)
          setAuthChecking(false)
        }
      })
    return () => { active = false }
  }, [accessToken])

  useEffect(() => {
    if (!authUser) return
    void loadMarket()
  }, [loadMarket, authUser])
  useEffect(() => {
    if (!authUser) return
    void loadSec()
  }, [loadSec, authUser])
  useEffect(() => {
    if (!authUser) return
    void loadSectorPanels()
  }, [loadSectorPanels, authUser])
  useEffect(() => {
    if (!authUser || dashboardView !== 'records') return
    void loadRecords(symbol)
  }, [authUser, dashboardView, loadRecords, symbol])
  useEffect(() => {
    if (!authUser) return
    void loadPortfolio()
  }, [loadPortfolio, authUser])
  useEffect(() => {
    if (!authUser) return
    api.config().then(setConfig).catch(() => setConfig(null))
  }, [authUser])
  useEffect(() => {
    if (!authUser) return
    void loadClock()
    const timer = window.setInterval(() => void loadClock(), 60_000)
    return () => window.clearInterval(timer)
  }, [loadClock, authUser])

  useEffect(() => {
    if (!authUser) return
    if (searchTerm.trim().length < 2) {
      setResults([])
      setSearchError('')
      return
    }
    let active = true
    const timer = window.setTimeout(async () => {
      setSearching(true)
      setSearchError('')
      try {
        const data = await api.search(searchTerm.trim())
        if (active) setResults(data)
      } catch {
        if (active) {
          setResults([])
          setSearchError('Search is temporarily unavailable.')
        }
      } finally {
        if (active) setSearching(false)
      }
    }, 250)
    return () => { active = false; window.clearTimeout(timer) }
  }, [searchTerm, authUser])

  useEffect(() => {
    if (!authUser || assetType !== 'option') return
    let active = true
    setChainState('loading')
    setChainError('')
    api.optionChain(symbol, mode, expiration || undefined, optionType)
      .then((data) => {
        if (!active) return
        setChain(data)
        if (!expiration && data.expirations[0]) setExpiration(data.expirations[0])
        setSelectedContract(null)
        setChainState('ready')
      })
      .catch((error) => {
        if (!active) return
        setChain(null)
        setSelectedContract(null)
        setChainError(error instanceof Error ? error.message : 'Unable to load the option chain.')
        setChainState('error')
      })
    return () => { active = false }
  }, [assetType, symbol, mode, expiration, optionType, authUser])

  useEffect(() => {
    setPositionIntent((current) => {
      if (side === 'buy' && current.startsWith('sell_')) return 'buy_to_open'
      if (side === 'sell' && current.startsWith('buy_')) return 'sell_to_close'
      return current
    })
  }, [side])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 8_000)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    if (!modeConfirm && !cancelCandidate) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (modeConfirm) {
          setModeConfirm(false)
          setLivePhrase('')
        }
        if (cancelCandidate && !cancelBusy) {
          setCancelCandidate(null)
          setOrderError(null)
        }
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [modeConfirm, cancelCandidate, cancelBusy])

  const contracts = useMemo(() => chain?.contracts
    .filter((item) => item.type === optionType && (!expiration || item.expiration === expiration))
    .sort((a, b) => a.strike - b.strike) || [], [chain, optionType, expiration])

  const selectSymbol = (result: SearchResult) => {
    setSymbol(result.symbol.toUpperCase())
    setSearchTerm('')
    setResults([])
    setSelectedContract(null)
  }

  const prepareOrder = async () => {
    const qty = Number(quantity)
    const notionalValue = Number(notional)
    const limit = Number(limitPrice)
    const hasQuantity = Number.isFinite(qty) && qty > 0
    const hasNotional = assetType === 'equity' && Number.isFinite(notionalValue) && notionalValue > 0
    if (assetType === 'option' && !selectedContract) {
      setOrderError('Select an option contract first.')
      return
    }
    if (!hasQuantity && !hasNotional) {
      setOrderError('Enter a valid quantity or notional amount.')
      return
    }
    if (assetType === 'option' && (!Number.isInteger(qty) || qty <= 0)) {
      setOrderError('Option quantity must be a positive whole number.')
      return
    }
    if (orderType === 'limit' && (!Number.isFinite(limit) || limit <= 0)) {
      setOrderError('Enter a valid limit price.')
      return
    }
    setOrderError(null)
    const draft: ReviewOrder = {
      kind: assetType, symbol, contract: selectedContract?.symbol, side,
      quantity: hasNotional ? undefined : hasQuantity ? qty : undefined,
      notional: hasNotional ? notionalValue : undefined,
      type: orderType, limitPrice: orderType === 'limit' ? limit : undefined, mode,
      positionIntent: assetType === 'option' ? positionIntent : undefined,
    }
    try {
      const preview = await api.previewOrder({
        kind: assetType,
        mode,
        symbol,
        contractSymbol: selectedContract?.symbol,
        side,
        quantity: draft.quantity,
        notional: draft.notional,
        type: orderType,
        limitPrice: draft.limitPrice,
        positionIntent: draft.positionIntent,
      })
      if (!preview.ok || preview.newBuysHalted) {
        setOrderError(preview.warnings.join(' ') || 'Order blocked by configured risk limits.')
        return
      }
      setReview({ ...draft, preview })
    } catch (error) {
      setOrderError(error instanceof Error ? error.message : 'Order blocked by risk limits')
    }
  }

  const submitOrder = async () => {
    if (!review) return
    setOrderBusy(true)
    setOrderError(null)
    try {
      const result = review.kind === 'equity'
        ? await api.placeEquityOrder({
          mode: review.mode, symbol: review.symbol, side: review.side,
          quantity: review.quantity, notional: review.notional, type: review.type,
          limitPrice: review.limitPrice, timeInForce: 'day',
        })
        : await api.placeOptionOrder({
          mode: review.mode, contractSymbol: review.contract || '', side: review.side,
          quantity: review.quantity || 1, type: review.type, limitPrice: review.limitPrice,
          timeInForce: 'day', positionIntent: review.positionIntent || 'buy_to_open',
        })
      setNotice(result)
      setReview(null)
      await loadPortfolio()
    } catch (error) {
      setOrderError(error instanceof Error ? error.message : 'Order was not submitted')
    } finally {
      setOrderBusy(false)
    }
  }

  const cancelSelectedOrder = async () => {
    if (!cancelCandidate) return
    setCancelBusy(true)
    setOrderError(null)
    try {
      await api.cancelOrder(cancelCandidate.id, mode)
      setNotice({ ...cancelCandidate, status: 'canceled' })
      setCancelCandidate(null)
      await loadPortfolio()
    } catch (error) {
      setOrderError(error instanceof Error ? error.message : 'Order cancellation failed')
    } finally {
      setCancelBusy(false)
    }
  }

  const direction = (quote?.change || 0) >= 0 ? 'positive' : 'negative'

  if (authChecking) {
    return (
      <div className="auth-shell">
        <div className="auth-card auth-loading"><LoaderCircle className="spin" size={22} /><span>Checking session…</span></div>
      </div>
    )
  }

  if (!accessToken || !authUser) {
    return <AuthScreen onAuthenticated={(user) => { setAuthUser(user); setAccessTokenState(getAccessToken()) }} />
  }

  const paperReady = authUser.alpaca.paper.configured
  const liveReady = authUser.alpaca.live.configured
  const modeReady = mode === 'paper' ? paperReady : liveReady
  const alpacaLabel = modeReady ? 'ALPACA CONNECTED' : 'ADD ALPACA KEYS'

  return (
    <div className="app-shell">
      {mode === 'live' && <div className="live-banner"><AlertTriangle size={16} /> LIVE TRADING — REAL FUNDS AT RISK</div>}
      <header className="topbar">
        <a className="brand" href="/" aria-label="StockPulse home">
          <span className="brand-mark"><BarChart3 size={20} /></span>
          <span>StockPulse<small>{alpacaLabel}</small></span>
        </a>
        <div className="search-wrap">
          <Search size={18} />
          <input
            aria-label="Search stocks"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={results.length > 0}
            aria-controls="symbol-search-results"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search symbol or company"
          />
          {searching && <LoaderCircle className="spin" size={16} />}
          {results.length > 0 && (
            <div className="search-results" id="symbol-search-results" role="listbox">
              {results.map((result) => (
                <button key={result.symbol} role="option" aria-selected={false} onClick={() => selectSymbol(result)}>
                  <strong>{result.symbol}</strong><span>{result.name}</span><small>{result.exchange}</small>
                </button>
              ))}
            </div>
          )}
          {searchError && <span className="sr-only" role="alert">{searchError}</span>}
        </div>
        <MarketLight clock={clock} />
        <div className="mode-switch" aria-label="Trading mode">
          <ShieldCheck size={16} />
          <button aria-pressed={mode === 'paper'} className={mode === 'paper' ? 'active' : ''} onClick={() => setMode('paper')}>Paper</button>
          <button
            aria-pressed={mode === 'live'}
            className={mode === 'live' ? 'active live' : ''}
            disabled={config?.liveTradingEnabled === false}
            title={config?.liveTradingEnabled === false ? 'Live trading is disabled by the server' : undefined}
            onClick={() => setModeConfirm(true)}
          >Live</button>
        </div>
        <div className="account-actions">
          <button type="button" className="icon-button" aria-label="Account settings" title="Account settings" onClick={() => setSettingsOpen(true)}>
            <Settings size={18} />
          </button>
          <button type="button" className="icon-button" aria-label="Sign out" title="Sign out" onClick={() => api.logout()}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {!modeReady && (
        <div className="warning-banner" role="status">
          <AlertTriangle size={18} />
          <span>
            <strong>Alpaca {mode} keys required.</strong> Add your API key and secret to trade with your own account.
          </span>
          <button type="button" onClick={() => setSettingsOpen(true)}>Open settings</button>
        </div>
      )}

      <main>
        <section className="market-heading">
          <div>
            <span className="eyebrow">US EQUITY</span>
            <div className="symbol-line">
              <h1>{symbol}</h1><span>{quote?.name || 'Loading security…'}</span>
              <div className="sentiment-pills">
                <SentimentBadge kind="Public" label={publicSentiment?.label} />
                <SentimentBadge kind="Investors" label={forecast?.sentiment} muted={forecast != null && forecast.edgeReliable === false} />
              </div>
              {quote?.isStale && <span className="stale"><Clock3 size={13} /> Stale data</span>}
            </div>
          </div>
          <button className="icon-button" aria-label="Refresh dashboard" onClick={() => { void loadMarket(); void loadPortfolio(); void loadClock(); void loadSec(); void refreshMarketScan() }}><RefreshCw size={18} /></button>
        </section>

        <div className="dashboard-tabs" role="tablist" aria-label="Dashboard views">
          <button role="tab" aria-selected={dashboardView === 'market'} className={dashboardView === 'market' ? 'active' : ''} onClick={() => setDashboardView('market')}>Market</button>
          <button role="tab" aria-selected={dashboardView === 'sectors'} className={dashboardView === 'sectors' ? 'active' : ''} onClick={() => setDashboardView('sectors')}>Sectors</button>
          <button role="tab" aria-selected={dashboardView === 'top'} className={dashboardView === 'top' ? 'active' : ''} onClick={() => setDashboardView('top')}>Top Accumulation</button>
          <button role="tab" aria-selected={dashboardView === 'records'} className={dashboardView === 'records' ? 'active' : ''} onClick={() => setDashboardView('records')}>SEC Records</button>
          <button role="tab" aria-selected={dashboardView === 'research'} className={dashboardView === 'research' ? 'active' : ''} onClick={() => setDashboardView('research')}>AI Research</button>
        </div>

        {dashboardView === 'market' && <>
        {marketState === 'error' && (
          <div className="error-banner"><AlertCircle size={18} /><span><strong>Market data unavailable.</strong> {marketError}</span><button onClick={() => void loadMarket()}>Retry</button></div>
        )}
        {marketWarning && (
          <div className="warning-banner" role="status"><AlertTriangle size={18} /><span><strong>Partial data.</strong> {marketWarning}</span></div>
        )}

        <section className="dashboard-grid">
          <div className="main-column">
            <section className="card quote-card">
              <div className="price-block">
                <span className="label">Last price</span>
                <div className="price">{formatCurrency(quote?.price)}</div>
                <div className={`price-change ${direction}`}>
                  {direction === 'positive' ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}
                  {formatCurrency(quote?.change)} ({formatPercent(quote?.changePercent)})
                </div>
                <small>{quote?.session?.replaceAll('_', ' ') || 'unavailable'} · {formatDateTime(quote?.timestamp)}</small>
                {quote?.afterHoursPrice != null && <div className="after-hours">After hours <strong>{formatCurrency(quote.afterHoursPrice)}</strong> <span className={(quote.afterHoursChangePercent || 0) >= 0 ? 'positive' : 'negative'}>{formatPercent(quote.afterHoursChangePercent)}</span></div>}
              </div>
              <div className="metric-grid">
                <div><span>Open</span><strong>{formatCurrency(quote?.open)}</strong></div>
                <div><span>Day high</span><strong>{formatCurrency(quote?.high)}</strong></div>
                <div><span>Day low</span><strong>{formatCurrency(quote?.low)}</strong></div>
                <div><span>Volume</span><strong>{formatNumber(quote?.volume, true)}</strong></div>
                <div><span>Market cap</span><strong>{formatCurrency(quote?.marketCap, true)}</strong></div>
                <div><span>P / E</span><strong>{formatNumber(quote?.peRatio)}</strong></div>
                <div><span>EPS</span><strong>{formatCurrency(quote?.eps)}</strong></div>
                <div><span>Dividend yield</span><strong>{formatPercent(quote?.dividendYield, false)}</strong></div>
              </div>
            </section>

            <section className="card chart-card">
              <div className="card-heading">
                <div><span className="eyebrow">PRICE & PREDICTION</span><h2>Market trajectory</h2></div>
                <div className="forecast-controls">
                  <div className="segmented" aria-label="Forecast engine">
                    <button
                      aria-pressed={forecastEngine === 'kronos'}
                      className={forecastEngine === 'kronos' ? 'active' : ''}
                      onClick={() => setForecastEngine('kronos')}
                    >
                      Kronos
                    </button>
                    <button
                      aria-pressed={forecastEngine === 'ensemble'}
                      className={forecastEngine === 'ensemble' ? 'active' : ''}
                      onClick={() => setForecastEngine('ensemble')}
                    >
                      Forecast
                    </button>
                  </div>
                  <div className="segmented" aria-label="Forecast preset">
                    <button
                      aria-pressed={horizon === 'short'}
                      className={horizon === 'short' ? 'active' : ''}
                      onClick={() => {
                        setHorizon('short')
                        setChartInterval(DEFAULT_INTERVAL.short)
                      }}
                    >
                      Short horizon
                    </button>
                    <button
                      aria-pressed={horizon === 'long'}
                      className={horizon === 'long' ? 'active' : ''}
                      onClick={() => {
                        setHorizon('long')
                        setChartInterval(DEFAULT_INTERVAL.long)
                      }}
                    >
                      Long horizon
                    </button>
                  </div>
                  <div className="segmented interval-chips" aria-label="Chart interval">
                    {CHART_INTERVALS.map((interval) => (
                      <button
                        key={interval}
                        aria-pressed={chartInterval === interval}
                        className={chartInterval === interval ? 'active' : ''}
                        onClick={() => setChartInterval(interval)}
                        title={intervalMetaLabel(interval)}
                      >
                        {INTERVAL_LABELS[interval]}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {marketState === 'loading' && !chart ? <div className="chart-loading"><LoaderCircle className="spin" /> Loading candles and forecast…</div>
                : chart?.candles?.length ? <MarketChart candles={chart.candles} forecast={forecast?.points || []} />
                  : <EmptyState>No chart data available for {symbol}.</EmptyState>}
              <div className="chart-meta">
                <span><i className="legend candle" /> Historical OHLC</span>
                <span>
                  <i className="legend forecast" />{' '}
                  {forecastEngine === 'ensemble' || forecast?.engine === 'ensemble'
                    ? 'Ensemble forecast'
                    : 'Kronos forecast'}
                </span>
                <span className="meta-right">
                  {intervalMetaLabel(chartInterval)} · {barUnitLabel(chartInterval, DEFAULT_BARS[horizon])} ·{' '}
                  {forecast?.regime ? `${forecast.regime.replaceAll('_', ' ')} · ` : ''}
                  {forecast?.netForecastChange != null
                    ? `net ${formatPercent(forecast.netForecastChange, false)} after ${forecast.roundTripBps?.toFixed(1) ?? '—'} bps cost · `
                    : ''}
                  {forecast?.evaluation?.folds
                    ? `OOS ${forecast.evaluation.folds} folds hit ${formatPercent(forecast.evaluation.hitRate, false)}${forecast.evaluation.evalHorizon ? ` @ ${forecast.evaluation.evalHorizon} bars` : ''} · `
                    : ''}
                  {forecast?.modelsUsed?.length
                    ? `${forecast.modelsUsed.join(' + ')} · `
                    : ''}
                  {forecast?.model || (forecastEngine === 'ensemble' ? 'ensemble' : 'Kronos')} · prediction {formatDateTime(forecast?.predictionStart)}
                  {' → '}{formatDateTime(forecast?.predictionEnd)} · data through {formatDateTime(forecast?.generatedAt)}
                </span>
              </div>
              <DecisionPanel forecast={forecast} prediction={prediction} news={news} publicSentiment={publicSentiment} interval={chartInterval} />
              <p className="disclaimer">Chart-path forecasts and model-stance calls are probabilistic research outputs, not investment advice. They never trigger orders.</p>
            </section>

            <section className="card">
              <div className="card-heading"><div><span className="eyebrow">LATEST COVERAGE</span><h2>{symbol} news</h2></div></div>
              <div className="news-grid">
                {marketState === 'loading' ? <EmptyState>Loading news for {symbol}…</EmptyState>
                  : news.length ? news.slice(0, 6).map((item) => (
                  <a className={`news-card ${item.sentiment || 'neutral'}`} key={item.id || item.url} href={item.url} target="_blank" rel="noreferrer">
                    <span>{item.source} · {formatDateTime(item.publishedAt)}</span><h3>{item.headline}</h3>
                    {item.summary && <p>{item.summary}</p>}<ExternalLink size={15} />
                  </a>
                )) : <EmptyState>No recent news is available for {symbol}.</EmptyState>}
              </div>
            </section>

            <SecIntelligencePanel data={secData} loading={secState === 'loading'} error={secState === 'error' ? secError : undefined} />
          </div>

          <aside className="side-column">
            <section className="card account-card">
              <div className="card-heading compact"><div><span className="eyebrow">{mode} ACCOUNT</span><h2>Portfolio</h2></div><WalletCards size={20} /></div>
              {portfolioState === 'loading' ? <div className="loading-state"><LoaderCircle className="spin" size={16} /> Loading portfolio…</div> : portfolioState === 'error' ? <div className="inline-error">{portfolioError}</div> : <>
                <span className="label">Total equity</span><div className="account-value">{formatCurrency(account?.equity)}</div>
                {account?.newBuysHalted && <div className="inline-error">New buys halted: daily loss limit reached.</div>}
                <div className="account-metrics"><div><span>Buying power</span><strong>{formatCurrency(account?.buyingPower)}</strong></div><div><span>Cash</span><strong>{formatCurrency(account?.cash)}</strong></div></div>
              </>}
            </section>

            <section className="card ticket-card">
              <div className="tabs" role="tablist"><button role="tab" aria-selected={activePanel === 'trade'} className={activePanel === 'trade' ? 'active' : ''} onClick={() => setActivePanel('trade')}>Trade</button><button role="tab" aria-selected={activePanel === 'portfolio'} className={activePanel === 'portfolio' ? 'active' : ''} onClick={() => setActivePanel('portfolio')}>Activity</button></div>
              {activePanel === 'trade' ? <>
                <div className="asset-toggle" aria-label="Asset type"><button aria-pressed={assetType === 'equity'} className={assetType === 'equity' ? 'active' : ''} onClick={() => setAssetType('equity')}>Equity</button><button aria-pressed={assetType === 'option'} className={assetType === 'option' ? 'active' : ''} onClick={() => setAssetType('option')}>Single-leg option</button></div>
                <div className="ticket-symbol"><div><span>Instrument</span><strong>{selectedContract?.symbol || symbol}</strong></div><span className="quote-mini">{formatCurrency(selectedContract?.ask ?? quote?.price)}</span></div>
                <div className="side-toggle" aria-label="Order side"><button aria-pressed={side === 'buy'} className={side === 'buy' ? 'buy active' : 'buy'} onClick={() => setSide('buy')}>Buy</button><button aria-pressed={side === 'sell'} className={side === 'sell' ? 'sell active' : 'sell'} onClick={() => setSide('sell')}>Sell</button></div>
                {assetType === 'option' && <div className="option-builder">
                  <label>Expiration<select value={expiration} onChange={(event) => setExpiration(event.target.value)}><option value="">Nearest</option>{chain?.expirations.map((date) => <option key={date}>{date}</option>)}</select><ChevronDown size={15} /></label>
                  <div className="side-toggle small"><button className={optionType === 'call' ? 'active buy' : 'buy'} onClick={() => setOptionType('call')}>Calls</button><button className={optionType === 'put' ? 'active sell' : 'sell'} onClick={() => setOptionType('put')}>Puts</button></div>
                  <label>Position intent<select value={positionIntent} onChange={(event) => setPositionIntent(event.target.value as OptionPositionIntent)}>
                    {side === 'buy' ? <><option value="buy_to_open">Buy to open</option><option value="buy_to_close">Buy to close</option></>
                      : <><option value="sell_to_close">Sell to close</option><option value="sell_to_open">Sell to open</option></>}
                  </select><ChevronDown size={15} /></label>
                  <label>Strike / contract<select value={selectedContract?.symbol || ''} onChange={(event) => setSelectedContract(contracts.find((item) => item.symbol === event.target.value) || null)}><option value="">{chainState === 'loading' ? 'Loading chain…' : 'Select strike'}</option>{contracts.map((item) => <option key={item.symbol} value={item.symbol}>${item.strike} · bid {formatCurrency(item.bid)} / ask {formatCurrency(item.ask)}</option>)}</select><ChevronDown size={15} /></label>
                  {chainState === 'error' && <div className="inline-error" role="alert">{chainError}</div>}
                  {selectedContract && <div className="bid-ask"><div><span>Bid</span><strong>{formatCurrency(selectedContract.bid)}</strong></div><div><span>Ask</span><strong>{formatCurrency(selectedContract.ask)}</strong></div><div><span>Open interest</span><strong>{formatNumber(selectedContract.openInterest, true)}</strong></div></div>}
                </div>}
                <div className="form-grid">
                  <label>Order type<select value={orderType} onChange={(event) => setOrderType(event.target.value as OrderType)}><option value="market">Market</option><option value="limit">Limit</option></select><ChevronDown size={15} /></label>
                  <label>Quantity<input aria-label="Quantity" value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" /></label>
                  {assetType === 'equity' && <label>Notional (optional)<input aria-label="Notional (optional)" value={notional} onChange={(event) => setNotional(event.target.value)} inputMode="decimal" placeholder="$0.00" /></label>}
                  {orderType === 'limit' && <label>Limit price<input aria-label="Limit price" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} inputMode="decimal" placeholder="$0.00" /></label>}
                </div>
                {orderError && !review && <div className="inline-error">{orderError}</div>}
                <button className={`button ticket-submit ${side}`} onClick={() => void prepareOrder()}>Review {side} order</button>
                <p className="ticket-note"><Activity size={13} /> Manual orders only. Forecast data is isolated from execution.</p>
              </> : <div className="activity-list">
                <div className="activity-section"><h3><BriefcaseBusiness size={15} /> Positions</h3>{positions.length ? positions.map((position) => <div className="activity-row" key={position.symbol}><div><strong>{position.symbol}</strong><span>{formatNumber(position.quantity)} shares</span></div><div><strong>{formatCurrency(position.marketValue)}</strong><span className={position.unrealizedPl >= 0 ? 'positive' : 'negative'}>{formatCurrency(position.unrealizedPl)}</span></div></div>) : <EmptyState>No open positions.</EmptyState>}</div>
                <div className="activity-section"><h3><Clock3 size={15} /> Recent orders</h3>{orders.length ? orders.slice(0, 8).map((order) => <div className="activity-row" key={order.id}><div><strong>{order.symbol}</strong><span>{order.side} · {order.quantity || formatCurrency(order.notional)}</span></div><div className="activity-actions"><StatusPill status={order.status} />{(order.status === 'accepted' || order.status === 'pending') && <button type="button" className="text-button danger-text" onClick={() => { setOrderError(null); setCancelCandidate(order) }}>Cancel</button>}</div></div>) : <EmptyState>No recent orders.</EmptyState>}</div>
              </div>}
            </section>
          </aside>
        </section>

        </>}

        {dashboardView === 'sectors' && (
          <SectorsPanel
            sectors={sectorRows}
            loading={sectorsState === 'loading'}
            error={sectorsState === 'error' ? 'Sector data unavailable. Try refresh.' : undefined}
            scanProgress={scanProgress}
            onSelectSector={(sector) => {
              setDashboardView('top')
              void api.topAccumulation({ sector, minScore: 0, limit: 50 }).then(setTopAccumulation).catch(() => undefined)
            }}
            onSelectTicker={(ticker) => { setSymbol(ticker); setDashboardView('market'); void loadSec() }}
          />
        )}
        {dashboardView === 'top' && (
          <TopAccumulationPanel
            data={topAccumulation}
            loading={topState === 'loading'}
            error={topState === 'error' ? 'Top accumulation data unavailable. Try refresh.' : undefined}
            scanProgress={scanProgress}
            onSelectTicker={(ticker) => { setSymbol(ticker); setDashboardView('market'); void loadSec() }}
          />
        )}
        {dashboardView === 'records' && (
          <SecRecordsPanel
            symbol={symbol}
            data={recordsData}
            loading={recordsState === 'loading'}
            error={recordsState === 'error' ? recordsError : undefined}
            analysis={recordsAnalysis}
            analysisLoading={recordsAnalysisState === 'loading'}
            analysisError={recordsAnalysisState === 'error' ? recordsAnalysisError : undefined}
            onSearch={(ticker) => { setSymbol(ticker); void loadRecords(ticker) }}
          />
        )}
        {dashboardView === 'research' && (
          <ResearchPanel
            response={researchResponse}
            loading={researchState === 'loading'}
            error={researchState === 'error' ? researchError : undefined}
            scanProgress={scanProgress}
            onSubmit={(query) => void runResearch(query)}
          />
        )}

        {dashboardView === 'market' && <>
        <MoversPanel
          onSelectSymbol={(ticker) => { setSymbol(ticker.toUpperCase()); setSelectedContract(null) }}
          onHoldSuggestions={setHoldSuggestions}
        />
        <PortfolioPanel
          account={account}
          positions={positions}
          state={portfolioState}
          error={portfolioError}
          realizedPl={realizedPl}
          realizedPlState={realizedPlState}
          holdSuggestions={holdSuggestions}
          onSelectSymbol={(ticker) => { setSymbol(ticker.toUpperCase()); setSelectedContract(null) }}
        />
        </>}
      </main>

      {modeConfirm && <div
        className="modal-backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) {
            setModeConfirm(false)
            setLivePhrase('')
          }
        }}
      ><section className="modal mode-modal" role="dialog" aria-modal="true" aria-labelledby="live-title" aria-describedby="live-description">
        <AlertTriangle className="danger-icon" size={28} /><span className="eyebrow">HIGH RISK ACTION</span><h2 id="live-title">Enable live trading?</h2>
        <p id="live-description">Live mode submits real orders to your Alpaca brokerage account. Losses are real and orders may fill immediately.</p>
        <label>Type <strong>LIVE</strong> to continue<input aria-label="Type LIVE to continue" autoFocus value={livePhrase} onChange={(event) => setLivePhrase(event.target.value)} /></label>
        <div className="modal-actions"><button className="button secondary" onClick={() => { setModeConfirm(false); setLivePhrase('') }}>Cancel</button><button className="button danger" disabled={livePhrase !== 'LIVE'} onClick={() => { setMode('live'); setModeConfirm(false); setLivePhrase('') }}>Enable live mode</button></div>
      </section></div>}
      {review && <OrderReview order={review} busy={orderBusy} error={orderError} onCancel={() => { setReview(null); setOrderError(null) }} onConfirm={() => void submitOrder()} />}
      {cancelCandidate && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !cancelBusy) setCancelCandidate(null) }}>
        <section className="modal" role="dialog" aria-modal="true" aria-labelledby="cancel-title" aria-describedby="cancel-description">
          <AlertTriangle className="danger-icon" size={28} />
          <span className="eyebrow">ORDER MANAGEMENT</span>
          <h2 id="cancel-title">Cancel this order?</h2>
          <p id="cancel-description">{cancelCandidate.symbol} · {cancelCandidate.side} {cancelCandidate.quantity || formatCurrency(cancelCandidate.notional)}. Cancellation is not guaranteed if the order is already filling.</p>
          {orderError && <div className="inline-error" role="alert">{orderError}</div>}
          <div className="modal-actions"><button className="button secondary" disabled={cancelBusy} onClick={() => { setCancelCandidate(null); setOrderError(null) }}>Keep order</button><button className="button danger" disabled={cancelBusy} onClick={() => void cancelSelectedOrder()}>{cancelBusy ? 'Canceling…' : 'Request cancellation'}</button></div>
        </section>
      </div>}
      {notice && <div className={`toast ${notice.status}`} role="status" aria-live="polite"><StatusPill status={notice.status} /><div><strong>Order {notice.status}</strong><span>{notice.symbol} · {notice.side} {notice.quantity || formatCurrency(notice.notional)}</span></div><button className="icon-button" aria-label="Dismiss order status" onClick={() => setNotice(null)}><XCircle size={17} /></button></div>}
      {settingsOpen && (
        <SettingsModal
          user={authUser}
          liveTradingEnabled={config?.liveTradingEnabled !== false}
          onClose={() => setSettingsOpen(false)}
          onUpdated={(user) => {
            setAuthUser(user)
            api.config().then(setConfig).catch(() => undefined)
            if (dashboardView === 'records' && symbol) {
              void loadRecords(symbol)
            }
          }}
        />
      )}
    </div>
  )
}

export default App
