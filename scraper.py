import os
import sys
import json
import csv
import logging
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import base64
import time
import threading
import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("   Selenium não instalado. Screenshots desabilitados.")
    print("   Para habilitar: pip install selenium")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("   Pandas não instalado. Análise avançada desabilitada.")
    print("   Para habilitar: pip install pandas")

# ============== CONFIGURAÇÕES ==============

@dataclass
class Quote:
    """Modelo de dados para uma citação"""
    text: str
    author: str
    tags: List[str]
    scraped_at: str


class ScraperConfig:
    """Configurações centralizadas"""
    BASE_URL = "http://quotes.toscrape.com"
    OUTPUT_DIR = Path("./data")
    LOGS_DIR = Path("./logs")
    SCREENSHOTS_DIR = Path("./screenshots")
    DB_PATH = Path("./data/quotes.db")
    TIMEOUT = 10
    RETRY_ATTEMPTS = 3
    MAX_PAGES = 100  # Limite de páginas a serem extraídas
    
    @classmethod
    def setup_dirs(cls):
        """Cria diretórios necessários"""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)
        cls.SCREENSHOTS_DIR.mkdir(exist_ok=True)


# ============== LOGGING ==============

def setup_logger(name: str) -> logging.Logger:
    """Configura logger com múltiplos handlers"""
    ScraperConfig.setup_dirs()
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    fh = logging.FileHandler(
        ScraperConfig.LOGS_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        encoding='utf-8'
    )
    fh.setLevel(logging.DEBUG)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


logger = setup_logger("QuotesScraper")

class ScreenshotManager:
    """Gerencia screenshots REAIS em PNG usando Selenium"""
    
    def __init__(self):
        self.driver = None
    
    def setup_driver(self):
        """Configura Chrome em modo headless"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless') 
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--log-level=3') 
            chrome_options.add_argument('--silent')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
                logger.info("Chrome WebDriver inicializado")
                return True
            except Exception as e:
                logger.warning(f"Chrome não disponível: {e}")
                
                try:
                    from selenium.webdriver.edge.options import Options as EdgeOptions
                    from selenium.webdriver.edge.service import Service as EdgeService
                    
                    edge_options = EdgeOptions()
                    edge_options.add_argument('--headless')
                    edge_options.add_argument('--window-size=1920,1080')
                    
                    self.driver = webdriver.Edge(options=edge_options)
                    logger.info("Edge WebDriver inicializado")
                    return True
                except Exception as edge_error:
                    logger.error(f"Nenhum driver disponível: {edge_error}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao configurar WebDriver: {e}")
            return False
    
    def take_screenshot(self, url: str, quotes_count: int) -> Optional[str]:
        """Captura screenshot REAL da página em PNG"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{timestamp}.png"
        filepath = ScraperConfig.SCREENSHOTS_DIR / filename
        
        try:
            self.setup_driver()
            
            logger.info(f"Capturando screenshot de: {url}")
            self.driver.get(url)
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "quote"))
            )
            self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot salvo: {filepath}")
            metadata_file = filepath.with_suffix('.json')
            metadata = {
                'timestamp': datetime.now().isoformat(),
                'url': url,
                'quotes_count': quotes_count,
                'screenshot_file': filename,
                'resolution': '1920x1080',
                'status': 'success'
            }
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Erro ao capturar screenshot: {e}")
            return None
    
    def close(self):
        """Fecha WebDriver"""
        try:
            self.driver.quit()
            logger.info("WebDriver fechado")
        except Exception as e:
            logger.warning(f"Erro ao fechar WebDriver: {e}")
    
    def __del__(self):
        """Destrutor - fecha driver automaticamente"""
        self.close()

# ============== DATABASE ==============

class DatabaseManager:
    """Gerenciador de banco de dados SQLite"""
    
    def __init__(self, db_path: Path = ScraperConfig.DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa banco de dados"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL UNIQUE,
                    author TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quotes_scraped INTEGER,
                    quotes_inserted INTEGER,
                    status TEXT,
                    screenshot_path TEXT
                )
            """)
            conn.commit()
        logger.info(f"Banco de dados inicializado: {self.db_path}")
    
    def insert_quotes(self, quotes: List[Quote]) -> int:
        """Insere citações, evitando duplicatas"""
        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            for quote in quotes:
                try:
                    conn.execute("""
                        INSERT INTO quotes (text, author, tags, scraped_at)
                        VALUES (?, ?, ?, ?)
                    """, (quote.text, quote.author, json.dumps(quote.tags), quote.scraped_at))
                    inserted += 1
                except sqlite3.IntegrityError:
                    logger.debug(f"Citação duplicada: {quote.text[:50]}...")
            conn.commit()
        return inserted
    
    def log_execution(self, scraped: int, inserted: int, status: str, screenshot: str):
        """Registra histórico de execução"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO execution_history 
                (quotes_scraped, quotes_inserted, status, screenshot_path)
                VALUES (?, ?, ?, ?)
            """, (scraped, inserted, status, screenshot))
            conn.commit()
    
    def get_all_quotes(self) -> List[Dict]:
        """Retorna todas as citações"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM quotes ORDER BY scraped_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do banco"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT author) as authors
                FROM quotes
            """)
            row = cursor.fetchone()
            
            cursor = conn.execute("""
                SELECT COUNT(*) as executions 
                FROM execution_history
            """)
            exec_count = cursor.fetchone()[0]
            return {
                'total_quotes': row[0],
                'total_authors': row[1],
                'total_executions': exec_count,
                'scraped_at': datetime.now().isoformat()
            }

class QuotesScraper:
    """Scraper principal com extração dinâmica"""
    
    def __init__(self):
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.screenshot_mgr = ScreenshotManager()
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Busca página com retry automático"""
        for attempt in range(ScraperConfig.RETRY_ATTEMPTS):
            try:
                response = self.session.get(url, timeout=ScraperConfig.TIMEOUT)
                response.raise_for_status()
                self.logger.info(f"✓ Página carregada: {url}")
                return BeautifulSoup(response.content, 'html.parser')
            except requests.RequestException as e:
                self.logger.warning(f"Tentativa {attempt + 1}/{ScraperConfig.RETRY_ATTEMPTS} falhou: {e}")
                time.sleep(2 ** attempt)
        
        self.logger.error(f"Falha ao carregar {url}")
        return None
    
    def extract_quotes_dynamic(self, soup: BeautifulSoup) -> List[Quote]:
        """Extrai citações sem fixar XPath"""
        quotes = []
        quote_containers = soup.select('[class*="quote"]')
        
        for container in quote_containers:
            text_elem = container.select_one('[class*="text"]')
            author_elem = container.select_one('[class*="author"]')
            tags_elem = container.select('[class*="tag"]')
            
            try:
                text = text_elem.get_text(strip=True).replace('"', '').replace('"', '')
                author = author_elem.get_text(strip=True).replace('by ', '')
                tags = [tag.get_text(strip=True) for tag in tags_elem] if tags_elem else []
                
                quote = Quote(
                    text=text,
                    author=author,
                    tags=tags,
                    scraped_at=datetime.now().isoformat()
                )
                quotes.append(quote)
            except AttributeError:
                continue
        
        self.logger.info(f"Extraídas {len(quotes)} citações da página")
        return quotes
    
    def scrape_all_pages(self, take_screenshot: bool = True, max_pages: int = None) -> tuple:
        """Scraping de todas as páginas e retorna (quotes, screenshot_path)
        
        Args:
            take_screenshot: Se deve capturar screenshot da primeira página
            max_pages: Número máximo de páginas a serem extraídas (None = usa ScraperConfig.MAX_PAGES)
        """
        if max_pages is None:
            max_pages = ScraperConfig.MAX_PAGES
            
        all_quotes = []
        page_num = 1
        screenshot_path = None
        
        try:
            first_url = f"{ScraperConfig.BASE_URL}/page/1/"
            screenshot_path = self.screenshot_mgr.take_screenshot(first_url, 0) if take_screenshot else None
        except Exception as e:
            self.logger.warning(f"Erro ao capturar screenshot: {e}")
        
        while page_num <= max_pages:
            url = f"{ScraperConfig.BASE_URL}/page/{page_num}/"
            soup = self.fetch_page(url)
            
            try:
                quotes = self.extract_quotes_dynamic(soup)
                all_quotes.extend(quotes)
                
                next_btn = soup.select_one('li.next')
                page_num += 1
                
                if page_num > max_pages:
                    self.logger.info(f"Limite de {max_pages} páginas atingido")
                    break
            except (AttributeError, TypeError):
                self.logger.info("Fim da paginação alcançado")
                break
        
        self.logger.info(f"Total de {len(all_quotes)} citações extraídas de {page_num - 1} páginas")
        return all_quotes, screenshot_path
    
    def save_json(self, quotes: List[Quote], filename: str = "quotes.json"):
        """Salva em JSON"""
        filepath = ScraperConfig.OUTPUT_DIR / filename
        data = [asdict(q) for q in quotes]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Salvo: {filepath}")
        return filepath
    
    def save_csv(self, quotes: List[Quote], filename: str = "quotes.csv"):
        """Salva em CSV"""
        filepath = ScraperConfig.OUTPUT_DIR / filename
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['text', 'author', 'tags', 'scraped_at'])
            writer.writeheader()
            for quote in quotes:
                row = asdict(quote)
                row['tags'] = '|'.join(row['tags'])
                writer.writerow(row)
        
        self.logger.info(f"Salvo: {filepath}")
        return filepath
    
    def __del__(self):
        """Fecha screenshot manager"""
        try:
            self.screenshot_mgr.close()
        except (AttributeError, Exception):
            pass

class DataFrameAnalyzer:
    """Análise com Pandas DataFrame"""
    
    @staticmethod
    def create_dataframe(quotes_data: List[Dict]) -> 'pd.DataFrame':
        """Cria DataFrame dos dados"""
        try:
            df = pd.DataFrame(quotes_data)
            
            df['tags'] = df['tags'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
            df['tag_count'] = df['tags'].apply(len)
            df['text_length'] = df['text'].str.len()
            df['scraped_at'] = pd.to_datetime(df['scraped_at'])
            
            logger.info(f"DataFrame criado com {len(df)} linhas")
            return df
        except (NameError, Exception) as e:
            logger.warning(f"Pandas não disponível ou erro: {e}")
            return None
    
    @staticmethod
    def display_dataframe(df: 'pd.DataFrame'):
        """Exibe DataFrame formatado"""
        try:
            print("\n" + "="*80)
            print("DATAFRAME - VISUALIZAÇÃO DOS DADOS")
            print("="*80)
            
            print(f"\nDimensões: {df.shape[0]} linhas x {df.shape[1]} colunas\n")
            
            print("Primeiras 10 citações:")
            print("-"*80)
            display_df = df[['author', 'text', 'tag_count', 'text_length']].head(10)
            print(display_df.to_string(index=True, max_colwidth=50))
            
            print("\n" + "="*80)
            print("ESTATÍSTICAS DESCRITIVAS")
            print("="*80)
            print(df[['text_length', 'tag_count']].describe())
            
            print("\n" + "="*80)
            print("TOP 10 AUTORES")
            print("="*80)
            top_authors = df['author'].value_counts().head(10)
            for i, (author, count) in enumerate(top_authors.items(), 1):
                print(f"{i:2d}. {author:30s} - {count:3d} citações")
            
            print("\n" + "="*80)
        except Exception as e:
            print(f"Erro ao exibir DataFrame: {e}")
    
    @staticmethod
    def save_analysis(df: 'pd.DataFrame', filename: str = "analysis.csv"):
        """Salva análise em CSV"""
        try:
            filepath = ScraperConfig.OUTPUT_DIR / filename
            
            analysis = df.groupby('author').agg({
                'text': 'count',
                'text_length': 'mean',
                'tag_count': 'mean'
            }).rename(columns={
                'text': 'quote_count',
                'text_length': 'avg_text_length',
                'tag_count': 'avg_tags'
            }).sort_values('quote_count', ascending=False).head(20)
            
            analysis.to_csv(filepath, encoding='utf-8')
            logger.info(f"Análise salva: {filepath}")
        except Exception as e:
            logger.error(f"Erro ao salvar análise: {e}")


class TaskScheduler:
    """Agendador de tarefas"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduled_jobs = []
    
    def schedule_scrape(self, date_str: str, time_str: str):
        """Agenda scrape para data/hora específica"""
        try:
            day, month, year = map(int, date_str.split('/'))
            hour, minute = map(int, time_str.split(':'))
            run_date = datetime(year, month, day, hour, minute)
            
            job = self.scheduler.add_job(
                self.run_scrape_job,
                'date',
                run_date=run_date,
                id=f'scrape_{run_date.strftime("%Y%m%d_%H%M%S")}'
            )
            
            self.scheduled_jobs.append({
                'job_id': job.id,
                'run_date': run_date.isoformat(),
                'status': 'scheduled'
            })
            
            logger.info(f"✓ Scrape agendado para {run_date.strftime('%d/%m/%Y às %H:%M')}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao agendar: {e}")
            return False
    
    def run_scrape_job(self):
        """Executa job de scrape agendado"""
        logger.info("Iniciando scrape agendado...")
        
        try:
            scraper = QuotesScraper()
            db = DatabaseManager()
            
            quotes, screenshot = scraper.scrape_all_pages(take_screenshot=True)
            inserted = db.insert_quotes(quotes)
            
            db.log_execution(
                scraped=len(quotes),
                inserted=inserted,
                status='success',
                screenshot=screenshot or 'N/A'
            )
            
            logger.info(f"✓ Scrape agendado concluído: {inserted}/{len(quotes)} citações")
            
        except Exception as e:
            logger.error(f"Erro no scrape agendado: {e}")
    
    def list_scheduled(self):
        """Lista tarefas agendadas"""
        return self.scheduled_jobs
    
    def start(self):
        """Inicia scheduler"""
        try:
            self.scheduler.start()
            logger.info("Scheduler iniciado")
        except Exception as e:
            logger.warning(f"Scheduler já em execução: {e}")
    
    def stop(self):
        """Para scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("Scheduler parado")
        except Exception as e:
            logger.warning(f"Erro ao parar scheduler: {e}")

def main():
    """Interface CLI"""
    print("\n" + "="*60)
    print("QUOTES SCRAPER")
    print("="*60 + "\n")
    
    scraper = QuotesScraper()
    db = DatabaseManager()
    scheduler = TaskScheduler()
    scheduler.start()
    
    try:
        while True:
            print("\nOpções:")
            print("1. Fazer scrape agora (com screenshot PNG)")
            print("2. Ver estatísticas do banco")
            print("3. Exportar para CSV")
            print("4. Exportar para JSON")
            print("5. Visualizar DataFrame (Pandas)")
            print("6. Gerar análise com Pandas")
            print("7. Agendar execução futura")
            print("8. Ver tarefas agendadas")
            print("9. Ver screenshots salvos")
            print("10. Alterar limite de páginas (atual: {})".format(ScraperConfig.MAX_PAGES))
            print("0. Sair")
            
            choice = input("\nEscolha uma opção: ").strip()
            
            if choice == '1':
                logger.info("Iniciando scrape com screenshot PNG...")
                quotes, screenshot = scraper.scrape_all_pages(take_screenshot=True)
                inserted = db.insert_quotes(quotes)
                
                db.log_execution(
                    scraped=len(quotes),
                    inserted=inserted,
                    status='success',
                    screenshot=screenshot or 'N/A'
                )
                
                print(f"\n✓ {inserted}/{len(quotes)} citações adicionadas ao banco!")
                screenshot_msg = f"\n   Screenshot salvo: {screenshot}\n   Abra para visualizar a prova da consulta!" if screenshot else ""
                print(screenshot_msg)
            
            elif choice == '2':
                stats = db.get_statistics()
                print(f"\n Estatísticas:")
                for k, v in stats.items():
                    print(f"  {k}: {v}")
            
            elif choice == '3':
                quotes_data = db.get_all_quotes()
                quotes = [Quote(
                    text=q['text'],
                    author=q['author'],
                    tags=json.loads(q['tags']),
                    scraped_at=q['scraped_at']
                ) for q in quotes_data]
                scraper.save_csv(quotes)
                print("✓ Exportado para CSV!")
            
            elif choice == '4':
                quotes_data = db.get_all_quotes()
                quotes = [Quote(
                    text=q['text'],
                    author=q['author'],
                    tags=json.loads(q['tags']),
                    scraped_at=q['scraped_at']
                ) for q in quotes_data]
                scraper.save_json(quotes)
                print("✓ Exportado para JSON!")
            
            elif choice == '5':
                try:
                    quotes_data = db.get_all_quotes()
                    df = DataFrameAnalyzer.create_dataframe(quotes_data)
                    DataFrameAnalyzer.display_dataframe(df)
                    input("\nPressione ENTER para continuar...")
                except Exception as e:
                    print(f"\n Erro: {e}")
                    print("   Certifique-se de que o Pandas está instalado: pip install pandas")
            
            elif choice == '6':
                try:
                    quotes_data = db.get_all_quotes()
                    df = DataFrameAnalyzer.create_dataframe(quotes_data)
                    DataFrameAnalyzer.save_analysis(df)
                    print("✓ Análise salva em analysis.csv!")
                except Exception as e:
                    print(f"\n Erro: {e}")
            
            elif choice == '7':
                print("\n Agendar Execução")
                print("-" * 40)
                date_str = input("Data (DD/MM/YYYY): ").strip()
                time_str = input("Hora (HH:MM): ").strip()
                
                result = scheduler.schedule_scrape(date_str, time_str)
                print(f"\n✓ Scrape agendado para {date_str} às {time_str}" if result else "\n Erro ao agendar. Verifique data/hora.")
            
            elif choice == '8':
                jobs = scheduler.list_scheduled()
                print("\n Tarefas Agendadas:" if jobs else "\n Nenhuma tarefa agendada")
                for i, job in enumerate(jobs, 1):
                    print(f"{i}. {job['run_date']} - Status: {job['status']}")
            
            elif choice == '9':
                screenshots = list(ScraperConfig.SCREENSHOTS_DIR.glob("screenshot_*.png"))
                print(f"\n Screenshots PNG Salvos ({len(screenshots)}):" if screenshots else "\n Nenhum screenshot salvo ainda")
                for i, screenshot in enumerate(screenshots[-10:], 1):
                    print(f"{i}. {screenshot.name}")
                
                if screenshots:
                    print(f"\nPasta: {ScraperConfig.SCREENSHOTS_DIR}")
                    print("\nAbra os arquivos PNG para ver as capturas de tela!")
            
            elif choice == '10':
                print(f"\n Configurar Limite de Páginas")
                print("-" * 40)
                print(f"Limite atual: {ScraperConfig.MAX_PAGES} páginas")
                try:
                    new_limit = input("\nNovo limite (0 = sem limite): ").strip()
                    new_limit = int(new_limit)
                    
                    if new_limit == 0:
                        ScraperConfig.MAX_PAGES = 999999
                        print("✓ Limite removido - extrairá todas as páginas disponíveis")
                    elif new_limit > 0:
                        ScraperConfig.MAX_PAGES = new_limit
                        print(f"✓ Limite configurado para {new_limit} páginas")
                    else:
                        print("Valor inválido! Deve ser >= 0")
                except ValueError:
                    print("Por favor, digite um número válido")
            
            elif choice == '0':
                print("\nEncerrando...")
                scheduler.stop()
                scraper.screenshot_mgr.close()
                print("Até logo!")
                break
            
            else:
                print("Opção inválida!")
    
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário")
        scheduler.stop()
        scraper.screenshot_mgr.close()
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        scheduler.stop()
        scraper.screenshot_mgr.close()


if __name__ == "__main__":
    main()