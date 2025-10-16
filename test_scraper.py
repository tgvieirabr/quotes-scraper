import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import (
    Quote,
    ScraperConfig,
    DatabaseManager,
    QuotesScraper,
    DataFrameAnalyzer,
    ScreenshotManager,
    TaskScheduler
)
from bs4 import BeautifulSoup
import requests


@pytest.fixture
def temp_db():
    """Cria banco de dados temporário para testes"""
    import gc
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_quotes.db"
    
    yield db_path
    
    gc.collect()
    
    try:
        import time
        time.sleep(0.1)
        
        try:
            temp_dir.cleanup()
        except PermissionError:
            pass
    except Exception:
        pass


@pytest.fixture
def sample_quote():
    """Cria uma Quote de exemplo"""
    return Quote(
        text="The world as we have created it is a process of our thinking.",
        author="Albert Einstein",
        tags=["change", "deep-thoughts", "thinking"],
        scraped_at=datetime.now().isoformat()
    )


@pytest.fixture
def sample_html():
    """HTML real do site quotes.toscrape.com"""
    return """
    <div class="quote" itemscope itemtype="http://schema.org/CreativeWork">
        <span class="text" itemprop="text">"The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking."</span>
        <span>by <small class="author" itemprop="author">Albert Einstein</small>
        <a href="/author/Albert-Einstein">(about)</a>
        </span>
        <div class="tags">
            Tags:
            <meta class="keywords" itemprop="keywords" content="change,deep-thoughts,thinking" />
            <a class="tag" href="/tag/change/page/1/">change</a>
            <a class="tag" href="/tag/deep-thoughts/page/1/">deep-thoughts</a>
            <a class="tag" href="/tag/thinking/page/1/">thinking</a>
        </div>
    </div>
    """


@pytest.fixture
def sample_html_multiple():
    """HTML com múltiplas quotes"""
    return """
    <div class="quote">
        <span class="text">"Quote 1"</span>
        <small class="author">Author 1</small>
        <div class="tags">
            <a class="tag">tag1</a>
        </div>
    </div>
    <div class="quote">
        <span class="text">"Quote 2"</span>
        <small class="author">Author 2</small>
        <div class="tags">
            <a class="tag">tag2</a>
            <a class="tag">tag3</a>
        </div>
    </div>
    """


class TestQuoteModel:
    """Testa a classe Quote real"""
    
    def test_quote_creation(self, sample_quote):
        """Testa criação de Quote"""
        assert sample_quote.text == "The world as we have created it is a process of our thinking."
        assert sample_quote.author == "Albert Einstein"
        assert len(sample_quote.tags) == 3
        assert "change" in sample_quote.tags
    
    def test_quote_dataclass_fields(self, sample_quote):
        """Testa que Quote tem todos os campos necessários"""
        assert hasattr(sample_quote, 'text')
        assert hasattr(sample_quote, 'author')
        assert hasattr(sample_quote, 'tags')
        assert hasattr(sample_quote, 'scraped_at')
    
    def test_quote_serialization(self, sample_quote):
        """Testa conversão para dict"""
        from dataclasses import asdict
        quote_dict = asdict(sample_quote)
        
        assert 'text' in quote_dict
        assert 'author' in quote_dict
        assert 'tags' in quote_dict
        assert quote_dict['author'] == "Albert Einstein"


class TestQuotesScraper:
    """Testa a classe QuotesScraper real"""
    
    def test_scraper_initialization(self):
        """Testa criação do scraper"""
        scraper = QuotesScraper()
        assert scraper is not None
        assert hasattr(scraper, 'session')
        assert hasattr(scraper, 'screenshot_mgr')
    
    def test_extract_quotes_dynamic(self, sample_html):
        """Testa extração REAL de quotes do HTML"""
        scraper = QuotesScraper()
        soup = BeautifulSoup(sample_html, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 1
        assert quotes[0].author == "Albert Einstein"
        assert "change" in quotes[0].tags
    
    def test_extract_multiple_quotes(self, sample_html_multiple):
        """Testa extração de múltiplas quotes"""
        scraper = QuotesScraper()
        soup = BeautifulSoup(sample_html_multiple, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 2
        assert quotes[0].author == "Author 1"
        assert quotes[1].author == "Author 2"
    
    @patch('scraper.requests.Session.get')
    def test_fetch_page_success(self, mock_get):
        """Testa busca de página com sucesso"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<html><body>Test</body></html>'
        mock_get.return_value = mock_response
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        
        assert soup is not None
        assert soup.find('body') is not None
    
    @patch('scraper.requests.Session.get')
    def test_fetch_page_retry_on_failure(self, mock_get):
        """Testa retry automático em caso de falha"""
        mock_get.side_effect = requests.RequestException("Connection error")
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        
        assert soup is None
        assert mock_get.call_count == ScraperConfig.RETRY_ATTEMPTS
    
    def test_save_json(self, sample_quote, tmp_path):
        """Testa salvamento em JSON"""
        scraper = QuotesScraper()
        
        ScraperConfig.OUTPUT_DIR = tmp_path
        
        filepath = scraper.save_json([sample_quote], "test_quotes.json")
        
        assert filepath.exists()
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]['author'] == "Albert Einstein"
    
    def test_save_csv(self, sample_quote, tmp_path):
        """Testa salvamento em CSV"""
        scraper = QuotesScraper()
        
        ScraperConfig.OUTPUT_DIR = tmp_path
        
        filepath = scraper.save_csv([sample_quote], "test_quotes.csv")
        
        assert filepath.exists()
        assert filepath.stat().st_size > 0


class TestDatabaseManager:
    """Testa a classe DatabaseManager real"""
    
    def test_database_initialization(self, temp_db):
        """Testa criação do banco de dados"""
        import gc
        db = DatabaseManager(temp_db)
        
        assert temp_db.exists()
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
        
        assert 'quotes' in tables
        assert 'execution_history' in tables
        
        del db
        gc.collect()
    
    def test_insert_quotes(self, temp_db, sample_quote):
        """Testa inserção de quotes"""
        import gc
        db = DatabaseManager(temp_db)
        
        inserted = db.insert_quotes([sample_quote])
        
        assert inserted == 1
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM quotes")
            count = cursor.fetchone()[0]
        
        assert count == 1
        
        del db
        gc.collect()
    
    def test_duplicate_prevention(self, temp_db, sample_quote):
        """Testa que duplicatas não são inseridas"""
        import gc
        db = DatabaseManager(temp_db)
        
        inserted1 = db.insert_quotes([sample_quote])
        assert inserted1 == 1
        
        inserted2 = db.insert_quotes([sample_quote])
        assert inserted2 == 0
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM quotes")
            count = cursor.fetchone()[0]
        
        assert count == 1
        
        del db
        gc.collect()
    
    def test_get_all_quotes(self, temp_db, sample_quote):
        """Testa recuperação de todas as quotes"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        quotes = db.get_all_quotes()
        
        assert len(quotes) == 1
        assert quotes[0]['author'] == "Albert Einstein"
        
        del db
        gc.collect()
    
    def test_get_statistics(self, temp_db, sample_quote):
        """Testa estatísticas do banco"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        stats = db.get_statistics()
        
        assert stats['total_quotes'] == 1
        assert stats['total_authors'] == 1
        assert 'scraped_at' in stats
        
        del db
        gc.collect()
    
    def test_log_execution(self, temp_db):
        """Testa registro de histórico de execução"""
        import gc
        db = DatabaseManager(temp_db)
        
        db.log_execution(
            scraped=100,
            inserted=95,
            status='success',
            screenshot='test.png'
        )
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT * FROM execution_history")
            row = cursor.fetchone()
        
        assert row is not None
        assert row[2] == 100
        assert row[3] == 95
        
        del db
        gc.collect()


class TestDataFrameAnalyzer:
    """Testa a classe DataFrameAnalyzer real"""
    
    def test_create_dataframe(self, temp_db, sample_quote):
        """Testa criação de DataFrame real"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        quotes_data = db.get_all_quotes()
        df = DataFrameAnalyzer.create_dataframe(quotes_data)
        
        if df is not None:
            assert len(df) == 1
            assert 'author' in df.columns
            assert 'text' in df.columns
            assert 'tag_count' in df.columns
        
        del db
        gc.collect()
    
    def test_dataframe_with_multiple_quotes(self, temp_db):
        """Testa DataFrame com múltiplas quotes"""
        import gc
        db = DatabaseManager(temp_db)
        
        quotes = [
            Quote("Quote 1", "Author A", ["tag1"], datetime.now().isoformat()),
            Quote("Quote 2", "Author B", ["tag1", "tag2"], datetime.now().isoformat()),
            Quote("Quote 3", "Author A", ["tag1"], datetime.now().isoformat()),
        ]
        
        db.insert_quotes(quotes)
        quotes_data = db.get_all_quotes()
        df = DataFrameAnalyzer.create_dataframe(quotes_data)
        
        if df is not None:
            assert len(df) == 3
            assert df[df['author'] == 'Author A'].shape[0] == 2
        
        del db
        gc.collect()


class TestScraperConfig:
    """Testa a classe ScraperConfig"""
    
    def test_config_has_required_attributes(self):
        """Testa que config tem todos os atributos necessários"""
        assert hasattr(ScraperConfig, 'BASE_URL')
        assert hasattr(ScraperConfig, 'OUTPUT_DIR')
        assert hasattr(ScraperConfig, 'LOGS_DIR')
        assert hasattr(ScraperConfig, 'SCREENSHOTS_DIR')
        assert hasattr(ScraperConfig, 'TIMEOUT')
        assert hasattr(ScraperConfig, 'RETRY_ATTEMPTS')
    
    def test_config_values(self):
        """Testa valores da configuração"""
        assert ScraperConfig.BASE_URL == "http://quotes.toscrape.com"
        assert ScraperConfig.RETRY_ATTEMPTS >= 1
        assert ScraperConfig.TIMEOUT > 0
    
    def test_setup_dirs_creates_directories(self, tmp_path):
        """Testa criação de diretórios"""
        original_output = ScraperConfig.OUTPUT_DIR
        original_logs = ScraperConfig.LOGS_DIR
        original_screenshots = ScraperConfig.SCREENSHOTS_DIR
        
        ScraperConfig.OUTPUT_DIR = tmp_path / "data"
        ScraperConfig.LOGS_DIR = tmp_path / "logs"
        ScraperConfig.SCREENSHOTS_DIR = tmp_path / "screenshots"
        
        ScraperConfig.setup_dirs()
        
        assert ScraperConfig.OUTPUT_DIR.exists()
        assert ScraperConfig.LOGS_DIR.exists()
        assert ScraperConfig.SCREENSHOTS_DIR.exists()
        
        ScraperConfig.OUTPUT_DIR = original_output
        ScraperConfig.LOGS_DIR = original_logs
        ScraperConfig.SCREENSHOTS_DIR = original_screenshots


class TestIntegration:
    """Testes de integração - fluxo completo"""
    
    @patch('scraper.requests.Session.get')
    def test_full_scrape_flow(self, mock_get, temp_db, sample_html):
        """Testa fluxo completo: scrape -> database -> export"""
        import gc
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sample_html.encode('utf-8')
        mock_get.return_value = mock_response
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) > 0
        
        db = DatabaseManager(temp_db)
        inserted = db.insert_quotes(quotes)
        
        assert inserted > 0
        
        stats = db.get_statistics()
        
        assert stats['total_quotes'] > 0
        
        del db
        del scraper
        gc.collect()


class TestEdgeCases:
    """Testes de casos extremos e situações incomuns"""
    
    def test_empty_html(self):
        """Testa HTML vazio"""
        scraper = QuotesScraper()
        soup = BeautifulSoup("", 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 0
    
    def test_malformed_html(self):
        """Testa HTML malformado"""
        scraper = QuotesScraper()
        malformed = "<div class='quote'><span class='text'>Quote</div>"
        soup = BeautifulSoup(malformed, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        assert isinstance(quotes, list)
    
    def test_quote_without_tags(self):
        """Testa quote sem tags"""
        scraper = QuotesScraper()
        html = """
        <div class="quote">
            <span class="text">"Quote without tags"</span>
            <small class="author">Author</small>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 1
        assert quotes[0].tags == []


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


@pytest.fixture
def temp_db():
    """Cria banco de dados temporário para testes"""
    import gc
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_quotes.db"
    yield db_path
    gc.collect()  
    try:
        import time
        time.sleep(0.1)
        try:
            temp_dir.cleanup()
        except PermissionError:
            pass
    except Exception:
        pass


@pytest.fixture
def sample_quote():
    """Cria uma Quote de exemplo"""
    return Quote(
        text="The world as we have created it is a process of our thinking.",
        author="Albert Einstein",
        tags=["change", "deep-thoughts", "thinking"],
        scraped_at=datetime.now().isoformat()
    )


@pytest.fixture
def sample_html():
    """HTML real do site quotes.toscrape.com"""
    return """
    <div class="quote" itemscope itemtype="http://schema.org/CreativeWork">
        <span class="text" itemprop="text">"The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking."</span>
        <span>by <small class="author" itemprop="author">Albert Einstein</small>
        <a href="/author/Albert-Einstein">(about)</a>
        </span>
        <div class="tags">
            Tags:
            <meta class="keywords" itemprop="keywords" content="change,deep-thoughts,thinking" />
            <a class="tag" href="/tag/change/page/1/">change</a>
            <a class="tag" href="/tag/deep-thoughts/page/1/">deep-thoughts</a>
            <a class="tag" href="/tag/thinking/page/1/">thinking</a>
        </div>
    </div>
    """


@pytest.fixture
def sample_html_multiple():
    """HTML com múltiplas quotes"""
    return """
    <div class="quote">
        <span class="text">"Quote 1"</span>
        <small class="author">Author 1</small>
        <div class="tags">
            <a class="tag">tag1</a>
        </div>
    </div>
    <div class="quote">
        <span class="text">"Quote 2"</span>
        <small class="author">Author 2</small>
        <div class="tags">
            <a class="tag">tag2</a>
            <a class="tag">tag3</a>
        </div>
    </div>
    """


class TestQuoteModel:
    """Testa a classe Quote real"""
    
    def test_quote_creation(self, sample_quote):
        """Testa criação de Quote"""
        assert sample_quote.text == "The world as we have created it is a process of our thinking."
        assert sample_quote.author == "Albert Einstein"
        assert len(sample_quote.tags) == 3
        assert "change" in sample_quote.tags
    
    def test_quote_dataclass_fields(self, sample_quote):
        """Testa que Quote tem todos os campos necessários"""
        assert hasattr(sample_quote, 'text')
        assert hasattr(sample_quote, 'author')
        assert hasattr(sample_quote, 'tags')
        assert hasattr(sample_quote, 'scraped_at')
    
    def test_quote_serialization(self, sample_quote):
        """Testa conversão para dict"""
        from dataclasses import asdict
        quote_dict = asdict(sample_quote)
        
        assert 'text' in quote_dict
        assert 'author' in quote_dict
        assert 'tags' in quote_dict
        assert quote_dict['author'] == "Albert Einstein"


class TestQuotesScraper:
    """Testa a classe QuotesScraper real"""
    
    def test_scraper_initialization(self):
        """Testa criação do scraper"""
        scraper = QuotesScraper()
        assert scraper is not None
        assert hasattr(scraper, 'session')
        assert hasattr(scraper, 'screenshot_mgr')
    
    def test_extract_quotes_dynamic(self, sample_html):
        """Testa extração REAL de quotes do HTML"""
        scraper = QuotesScraper()
        soup = BeautifulSoup(sample_html, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 1
        assert quotes[0].author == "Albert Einstein"
        assert "change" in quotes[0].tags
    
    def test_extract_multiple_quotes(self, sample_html_multiple):
        """Testa extração de múltiplas quotes"""
        scraper = QuotesScraper()
        soup = BeautifulSoup(sample_html_multiple, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 2
        assert quotes[0].author == "Author 1"
        assert quotes[1].author == "Author 2"
    
    @patch('scraper.requests.Session.get')
    def test_fetch_page_success(self, mock_get):
        """Testa busca de página com sucesso"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<html><body>Test</body></html>'
        mock_get.return_value = mock_response
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        
        assert soup is not None
        assert soup.find('body') is not None
    
    @patch('scraper.requests.Session.get')
    def test_fetch_page_retry_on_failure(self, mock_get):
        """Testa retry automático em caso de falha"""
        mock_get.side_effect = requests.RequestException("Connection error")
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        
        assert soup is None
        assert mock_get.call_count == ScraperConfig.RETRY_ATTEMPTS
    
    def test_save_json(self, sample_quote, tmp_path):
        """Testa salvamento em JSON"""
        scraper = QuotesScraper()
        
        ScraperConfig.OUTPUT_DIR = tmp_path
        
        filepath = scraper.save_json([sample_quote], "test_quotes.json")
        
        assert filepath.exists()
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]['author'] == "Albert Einstein"
    
    def test_save_csv(self, sample_quote, tmp_path):
        """Testa salvamento em CSV"""
        scraper = QuotesScraper()
        
        ScraperConfig.OUTPUT_DIR = tmp_path
        
        filepath = scraper.save_csv([sample_quote], "test_quotes.csv")
        
        assert filepath.exists()
        
        assert filepath.stat().st_size > 0


class TestDatabaseManager:
    """Testa a classe DatabaseManager real"""
    
    def test_database_initialization(self, temp_db):
        """Testa criação do banco de dados"""
        import gc
        db = DatabaseManager(temp_db)
        
        assert temp_db.exists()
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
        
        assert 'quotes' in tables
        assert 'execution_history' in tables
        
        del db
        gc.collect()
    
    def test_insert_quotes(self, temp_db, sample_quote):
        """Testa inserção de quotes"""
        import gc
        db = DatabaseManager(temp_db)
        
        inserted = db.insert_quotes([sample_quote])
        
        assert inserted == 1
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM quotes")
            count = cursor.fetchone()[0]
        
        assert count == 1
   
        del db
        gc.collect()
    
    def test_duplicate_prevention(self, temp_db, sample_quote):
        """Testa que duplicatas não são inseridas"""
        import gc
        db = DatabaseManager(temp_db)
        
        inserted1 = db.insert_quotes([sample_quote])
        assert inserted1 == 1
     
        inserted2 = db.insert_quotes([sample_quote])
        assert inserted2 == 0 
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM quotes")
            count = cursor.fetchone()[0]
        
        assert count == 1
        
        del db
        gc.collect()
    
    def test_get_all_quotes(self, temp_db, sample_quote):
        """Testa recuperação de todas as quotes"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        quotes = db.get_all_quotes()
        
        assert len(quotes) == 1
        assert quotes[0]['author'] == "Albert Einstein"
        
        del db
        gc.collect()
    
    def test_get_statistics(self, temp_db, sample_quote):
        """Testa estatísticas do banco"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        stats = db.get_statistics()
        
        assert stats['total_quotes'] == 1
        assert stats['total_authors'] == 1
        assert 'scraped_at' in stats
        
        del db
        gc.collect()
    
    def test_log_execution(self, temp_db):
        """Testa registro de histórico de execução"""
        import gc
        db = DatabaseManager(temp_db)
        
        db.log_execution(
            scraped=100,
            inserted=95,
            status='success',
            screenshot='test.png'
        )
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT * FROM execution_history")
            row = cursor.fetchone()
        
        assert row is not None
        assert row[2] == 100 
        assert row[3] == 95  
        
        del db
        gc.collect()


class TestDataFrameAnalyzer:
    """Testa a classe DataFrameAnalyzer real"""
    
    def test_create_dataframe(self, temp_db, sample_quote):
        """Testa criação de DataFrame real"""
        import gc
        db = DatabaseManager(temp_db)
        db.insert_quotes([sample_quote])
        
        quotes_data = db.get_all_quotes()
        df = DataFrameAnalyzer.create_dataframe(quotes_data)
        
        if df is not None: 
            assert len(df) == 1
            assert 'author' in df.columns
            assert 'text' in df.columns
            assert 'tag_count' in df.columns
        
        del db
        gc.collect()
    
    def test_dataframe_with_multiple_quotes(self, temp_db):
        """Testa DataFrame com múltiplas quotes"""
        import gc
        db = DatabaseManager(temp_db)
        
        quotes = [
            Quote("Quote 1", "Author A", ["tag1"], datetime.now().isoformat()),
            Quote("Quote 2", "Author B", ["tag1", "tag2"], datetime.now().isoformat()),
            Quote("Quote 3", "Author A", ["tag1"], datetime.now().isoformat()),
        ]
        
        db.insert_quotes(quotes)
        quotes_data = db.get_all_quotes()
        df = DataFrameAnalyzer.create_dataframe(quotes_data)
        
        if df is not None:
            assert len(df) == 3
            assert df[df['author'] == 'Author A'].shape[0] == 2
        
        del db
        gc.collect()


class TestScraperConfig:
    """Testa a classe ScraperConfig"""
    
    def test_config_has_required_attributes(self):
        """Testa que config tem todos os atributos necessários"""
        assert hasattr(ScraperConfig, 'BASE_URL')
        assert hasattr(ScraperConfig, 'OUTPUT_DIR')
        assert hasattr(ScraperConfig, 'LOGS_DIR')
        assert hasattr(ScraperConfig, 'SCREENSHOTS_DIR')
        assert hasattr(ScraperConfig, 'TIMEOUT')
        assert hasattr(ScraperConfig, 'RETRY_ATTEMPTS')
    
    def test_config_values(self):
        """Testa valores da configuração"""
        assert ScraperConfig.BASE_URL == "http://quotes.toscrape.com"
        assert ScraperConfig.RETRY_ATTEMPTS >= 1
        assert ScraperConfig.TIMEOUT > 0
    
    def test_setup_dirs_creates_directories(self, tmp_path):
        """Testa criação de diretórios"""
        original_output = ScraperConfig.OUTPUT_DIR
        original_logs = ScraperConfig.LOGS_DIR
        original_screenshots = ScraperConfig.SCREENSHOTS_DIR
        
        ScraperConfig.OUTPUT_DIR = tmp_path / "data"
        ScraperConfig.LOGS_DIR = tmp_path / "logs"
        ScraperConfig.SCREENSHOTS_DIR = tmp_path / "screenshots"
        
        ScraperConfig.setup_dirs()
        
        assert ScraperConfig.OUTPUT_DIR.exists()
        assert ScraperConfig.LOGS_DIR.exists()
        assert ScraperConfig.SCREENSHOTS_DIR.exists()
        
        ScraperConfig.OUTPUT_DIR = original_output
        ScraperConfig.LOGS_DIR = original_logs
        ScraperConfig.SCREENSHOTS_DIR = original_screenshots


class TestIntegration:
    """Testes de integração - fluxo completo"""
    
    @patch('scraper.requests.Session.get')
    def test_full_scrape_flow(self, mock_get, temp_db, sample_html):
        """Testa fluxo completo: scrape -> database -> export"""
        import gc
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sample_html.encode('utf-8')
        mock_get.return_value = mock_response
        
        scraper = QuotesScraper()
        soup = scraper.fetch_page("http://test.com")
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) > 0
        
        db = DatabaseManager(temp_db)
        inserted = db.insert_quotes(quotes)
        
        assert inserted > 0
        
        stats = db.get_statistics()
        
        assert stats['total_quotes'] > 0
        
        del db
        del scraper
        gc.collect()



class TestEdgeCases:
    """Testes de casos extremos e situações incomuns"""
    
    def test_empty_html(self):
        """Testa HTML vazio"""
        scraper = QuotesScraper()
        soup = BeautifulSoup("", 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 0
    
    def test_malformed_html(self):
        """Testa HTML malformado"""
        scraper = QuotesScraper()
        malformed = "<div class='quote'><span class='text'>Quote</div>"
        soup = BeautifulSoup(malformed, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        assert isinstance(quotes, list)
    
    def test_quote_without_tags(self):
        """Testa quote sem tags"""
        scraper = QuotesScraper()
        html = """
        <div class="quote">
            <span class="text">"Quote without tags"</span>
            <small class="author">Author</small>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        quotes = scraper.extract_quotes_dynamic(soup)
        
        assert len(quotes) == 1
        assert quotes[0].tags == []  


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
