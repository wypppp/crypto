import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class CollectorConfig:
    output_dir: str = "crypto/prediction_market_research/data/shadow"
    gamma_url: str = "https://gamma-api.polymarket.com"
    clob_url: str = "https://clob.polymarket.com"
    coinbase_url: str = "https://api.exchange.coinbase.com"
    clob_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    rtds_ws_url: str = "wss://ws-live-data.polymarket.com"
    coinbase_ws_url: str = "wss://ws-feed.exchange.coinbase.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    symbols: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    intervals_minutes: List[int] = field(default_factory=lambda: [5, 15])
    poll_seconds: float = 2.0
    discovery_seconds: float = 60.0
    clock_poll_seconds: float = 60.0
    resolution_poll_seconds: float = 30.0
    request_timeout_seconds: float = 8.0
    max_markets: int = 24
    past_markets_per_series: int = 1
    future_markets_per_series: int = 1
    max_workers: int = 12
    discovery_pages: int = 2
    discovery_page_size: int = 100
    fsync_every: int = 5000
    writer_queue_max_events: int = 100000
    gzip_compresslevel: int = 1
    ws_connect_timeout_seconds: float = 10.0
    market_discovery_startup_timeout_seconds: float = 30.0
    ws_read_timeout_seconds: float = 1.0
    clob_heartbeat_seconds: float = 10.0
    clob_shard_by_series: bool = True
    # CLOB price-change messages are market-scoped and can contain both
    # outcomes. Splitting Up/Down across sockets therefore duplicates most of
    # the firehose and can also exceed the server's practical connection cap.
    clob_token_shards_per_series: int = 1
    # The replay only posts BUY orders. Full snapshots retain the deep book;
    # incremental changes farther than this from their side's BBO are omitted.
    clob_price_change_depth_ticks: int = 5
    enable_message_hashes: bool = False
    rtds_heartbeat_seconds: float = 5.0
    spot_heartbeat_seconds: float = 20.0
    reconnect_max_seconds: float = 30.0
    market_end_grace_seconds: float = 120.0
    resolution_start_grace_seconds: float = 5.0
    rtds_topics: List[str] = field(
        default_factory=lambda: [
            "crypto_prices_chainlink",
            "crypto_prices_twap_thirty",
            "crypto_prices_twap_sixty",
        ]
    )
    enable_coinbase_ws: bool = True
    enable_kraken_ws: bool = True
    # This endpoint returned HTTP 451 from the current research environment.
    # Keep the implementation opt-in for locations where it is lawfully available.
    enable_binance_ws: bool = False

    @classmethod
    def from_path(cls, path: Path) -> "CollectorConfig":
        data: Dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
