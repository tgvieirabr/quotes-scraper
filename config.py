from pathlib import Path
from datetime import datetime
import json
import os

class Config:
    """Configurações base"""
    
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    
    BASE_URL = "http://quotes.toscrape.com"
    
    REQUEST_TIMEOUT = 10
    RETRY_ATTEMPTS = 3
    RETRY_BACKOFF = 2 
    
    DB_PATH = DATA_DIR / "quotes.db"
    DB_ECHO = False  
    
    LOG_LEVEL = "INFO"
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    DELAY_BETWEEN_REQUESTS = 1 
    
    SCHEDULER_ENABLED = True
    SCHEDULER_TIME = "14:30" 
    
    EXPORT_FORMATS = ["json", "csv"]
    CSV_ENCODING = "utf-8"
    JSON_INDENT = 2
    
    MAX_PAGES = None  
    MAX_RETRIES_BEFORE_EXIT = 5


class DevelopmentConfig(Config):
    """Configurações para desenvolvimento"""
    LOG_LEVEL = "DEBUG"
    RETRY_ATTEMPTS = 5
    REQUEST_TIMEOUT = 15


class ProductionConfig(Config):
    """Configurações para produção"""
    LOG_LEVEL = "INFO"
    RETRY_ATTEMPTS = 3
    REQUEST_TIMEOUT = 10
    SCHEDULER_ENABLED = True


class TestingConfig(Config):
    """Configurações para testes"""
    DB_PATH = Path("./test_quotes.db")
    LOG_LEVEL = "WARNING"
    RETRY_ATTEMPTS = 1
    REQUEST_TIMEOUT = 5


def get_config(env: str = None) -> Config:
    """
    Factory para retornar configuração apropriada
    
    Args:
        env: 'development', 'production', 'testing'
              Se None, lê de variável de ambiente
    
    Returns:
        Instância de Config apropriada
    """
    if env is None:
        env = os.getenv("APP_ENV", "development").lower()
    
    config_map = {
        "development": DevelopmentConfig(),
        "production": ProductionConfig(),
        "testing": TestingConfig(),
    }
    
    return config_map.get(env, DevelopmentConfig())


class DatabaseConfig:
    """Configurações específicas do banco de dados"""
    
    TABLES = {
        "quotes": {
            "schema": """
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL UNIQUE,
                    author TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source_url TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "indices": [
                "CREATE INDEX IF NOT EXISTS idx_author ON quotes(author)",
                "CREATE INDEX IF NOT EXISTS idx_scraped ON quotes(scraped_at)",
            ]
        },
        "scrape_history": {
            "schema": """
                CREATE TABLE IF NOT EXISTS scrape_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    total_scraped INTEGER,
                    total_inserted INTEGER,
                    status TEXT,
                    error_message TEXT
                );
            """,
            "indices": []
        }
    }
    
    @classmethod
    def get_init_sql(cls) -> list:
        """Retorna todas as queries de inicialização"""
        queries = []
        for table_config in cls.TABLES.values():
            queries.append(table_config["schema"])
            queries.extend(table_config["indices"])
        return queries


class SelectorConfig:
    """Seletores CSS dinâmicos"""
    
    QUOTE_CONTAINER = '[class*="quote"]'
    QUOTE_TEXT = '[class*="text"]'
    QUOTE_AUTHOR = '[class*="author"]'
    QUOTE_TAGS = '[class*="tag"]'
    
    NEXT_PAGE = 'li.next'
    PAGINATION = '.pager'
    
    TEXT_CLEAN = {
        'quotes': ['"', '"', '"'],
        'replacements': ['', '', '']
    }
    
    AUTHOR_CLEAN = {
        'prefixes': ['by ', 'By ', 'BY ']
    }
    
    @classmethod
    def get_selector(cls, selector_name: str) -> str:
        """Retorna seletor pelo nome"""
        return getattr(cls, selector_name, None)


class ExportConfig:
    """Configurações de exportação"""
    
    # Nomes de arquivo
    JSON_FILENAME = "quotes.json"
    CSV_FILENAME = "quotes.csv"
    ANALYSIS_FILENAME = "analysis.csv"
    
    # Formatos de timestamp
    TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
    
    # Versioning
    VERSION = "1.0.0"
    INCLUDE_METADATA = True
    
    # Campos para exportação
    FIELDS = {
        "json": ["text", "author", "tags", "scraped_at"],
        "csv": ["text", "author", "tags", "scraped_at"]
    }


class ScheduleConfig:
    """Configurações de agendamento"""
    
    # Padrão CRON
    DAILY_SCHEDULE = {
        "hour": 14,
        "minute": 30
    }
    
    # Tipos de agenda
    SCHEDULE_TYPES = {
        "daily": "cron",
        "hourly": "interval",
        "custom": "cron"
    }
    
    # Notificações
    ENABLE_NOTIFICATIONS = False
    NOTIFICATION_EMAIL = None


class AppConfig:
    """Configuração centralizada da aplicação"""
    
    def __init__(self, env: str = None):
        self.env = env or os.getenv("APP_ENV", "development")
        self.config = get_config(self.env)
        self.database = DatabaseConfig()
        self.selectors = SelectorConfig()
        self.export = ExportConfig()
        self.schedule = ScheduleConfig()
    
    def to_dict(self) -> dict:
        """Converte config para dicionário"""
        return {
            "environment": self.env,
            "base_url": self.config.BASE_URL,
            "database": str(self.config.DB_PATH),
            "log_level": self.config.LOG_LEVEL,
            "timestamp": datetime.now().isoformat()
        }
    
    def export_json(self, filepath: str = None):
        """Exporta configuração para JSON"""
        if filepath is None:
            filepath = self.config.DATA_DIR / f"config_{self.env}.json"
        
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        return filepath


# Instância global
app_config = AppConfig()


if __name__ == "__main__":
    # Teste de configuração
    config = AppConfig("production")
    print("Configuração Ativa:")
    print(json.dumps(config.to_dict(), indent=2))
    
    print("\nSeletores:")
    for attr in dir(config.selectors):
        if not attr.startswith('_') and attr.isupper():
            print(f"  {attr}: {getattr(config.selectors, attr)}")