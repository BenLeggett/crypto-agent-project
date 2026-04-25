"""Market data library package."""

from libs.market_data.ccxt_client import (
    CCXTReadClient,
    MarketDataClientError,
    MarketMetadata,
    OHLCV,
    create_public_ccxt_exchange,
)
from libs.market_data.collectors import (
    CommandResult,
    MarketDataCollectorError,
    OHLCVCollectionRequest,
    OHLCVCollectionResult,
    SubprocessCommandRunner,
    build_freqtrade_download_command,
    run_freqtrade_ohlcv_download,
)
from libs.market_data.normalization import (
    MarketDataNormalizationError,
    normalize_ohlcv_record,
    normalize_ohlcv_records,
)
from libs.market_data.quality_checks import (
    MarketDataQualityError,
    QualityIssue,
    QualityReport,
    assert_ohlcv_quality,
    timeframe_to_milliseconds,
    validate_ohlcv_quality,
)
from libs.market_data.storage import (
    DuckDBAnalyticsBackend,
    MarketDataStorage,
    MarketDataStorageError,
    MarketDataStoragePaths,
    OHLCVDatasetRow,
    PyArrowParquetBackend,
    StoredDataset,
    default_table_name,
    rows_from_ohlcv,
)

__all__ = [
    "CCXTReadClient",
    "CommandResult",
    "DuckDBAnalyticsBackend",
    "MarketDataCollectorError",
    "MarketDataClientError",
    "MarketDataNormalizationError",
    "MarketDataStorage",
    "MarketDataStorageError",
    "MarketDataQualityError",
    "MarketDataStoragePaths",
    "MarketMetadata",
    "OHLCV",
    "OHLCVCollectionRequest",
    "OHLCVCollectionResult",
    "OHLCVDatasetRow",
    "PyArrowParquetBackend",
    "QualityIssue",
    "QualityReport",
    "StoredDataset",
    "SubprocessCommandRunner",
    "assert_ohlcv_quality",
    "build_freqtrade_download_command",
    "create_public_ccxt_exchange",
    "default_table_name",
    "normalize_ohlcv_record",
    "normalize_ohlcv_records",
    "run_freqtrade_ohlcv_download",
    "rows_from_ohlcv",
    "timeframe_to_milliseconds",
    "validate_ohlcv_quality",
]
