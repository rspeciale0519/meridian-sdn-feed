"""Official sources, schema, and sanity thresholds."""

SCHEMA_VERSION = "1.0"

# Official OFAC Sanctions List Service exports (User-Agent required).
OFAC_SDN_XML_URL = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML"
)
# SDN.CSV remarks are truncated (~1000 chars); not used as a live source.
OFAC_SDN_CSV_URL = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
)

# Official ITA Consolidated Screening List (fallback). HEAD is 404; GET works.
CSL_JSON_URL = (
    "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
)

USER_AGENT = (
    "meridian-sdn-feed/1.0 "
    "(+https://github.com/rspeciale0519/meridian-sdn-feed; corp@miodiollc.com)"
)

CRYPTO_ID_PREFIX = "Digital Currency Address"
MIN_UNIQUE_COUNT = 900
MAX_DROP_RATIO = 0.10
MAX_INVALID_RATIO = 0.02
FETCH_TIMEOUT_S = 120
FETCH_RETRIES = 3
MAX_RESPONSE_BYTES = 80 * 1024 * 1024  # SDN.XML ~28MB, CSL ~34MB

# HTTPS hosts we will follow. OFAC SLS 302s to this exact GovCloud S3 host
# (the same bucket name is not reserved in commercial AWS).
ALLOWED_FETCH_HOSTS = frozenset(
    {
        "sanctionslistservice.ofac.treas.gov",
        "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
        "data.trade.gov",
        "api.trade.gov",
    }
)

SOURCE_OFAC_XML = "ofac_sdn_xml"
SOURCE_OFAC_CSV = "ofac_sdn_csv"
SOURCE_CSL = "ita_csl_json"

SDN_SOURCE_MARKERS = (
    "specially designated nationals",
    "sdn - treasury",
    "(sdn)",
)

ADDRESSES_FILENAME = "sdn-addresses.json"
SHA256_FILENAME = "sdn-addresses.json.sha256"
HEARTBEAT_FILENAME = "last-run.json"
