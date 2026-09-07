"""
Application Constants
All magic numbers and configuration values in one place
"""

# Database Configuration
DEFAULT_DB_HOST = 'localhost'
DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = 'analysis'
DEFAULT_DB_USER = 'postgres'
DEFAULT_DB_PASSWORD = 'eggarf123'

# Connection Pool Settings
MIN_POOL_CONNECTIONS = 5
MAX_POOL_CONNECTIONS = 20
CONNECTION_TIMEOUT = 10

# Word Processing Limits
MAX_REGULAR_WORD_LENGTH = 100
MAX_EMAIL_LENGTH = 320
MAX_URL_LENGTH = 2000
MAX_DOMAIN_LENGTH = 255
MAX_DATE_LENGTH = 50

# Cache Settings
WORD_CACHE_MAX_SIZE = 50000
CACHE_TTL_SECONDS = 3600

# Batch Processing
BATCH_SIZE = 2000
LARGE_BATCH_THRESHOLD = 1000

# Data File Settings
SUPPORTED_FORMATS = ['.xlsx', '.csv', '.json']
DEFAULT_DATA_FILE = 'domain_data.xlsx'
DATA_FILE_SEARCH_PATHS = [
    'classification/',
    './',
]

# Logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Database Tables
TABLE_WORDS = 'words'
TABLE_CATEGORIES = 'categorys'
TABLE_KEYWORDS = 'keywords'
TABLE_WORDS_CATEGORIES = 'words_categorys'
TABLE_KEYWORDS_PATHS = 'keywords_paths'
TABLE_WORDS_PATHS = 'words_paths'

