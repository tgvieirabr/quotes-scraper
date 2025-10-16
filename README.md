#  Quotes Scraper

Web scraper de citações com screenshots, banco de dados SQLite e análise de dados.

---

##  Como Executar

### **1. Instalar Dependências**

```bash
pip install -r requirements.txt
```

---

### **2. Executar o Scraper**

```bash
python scraper.py
```

---

### **3. Executar os Testes**

```bash
pytest test_scraper.py --cov=scraper --cov-report=html --cov-report=term
```

---

##  Pré-requisitos

- Python 3.11 ou superior
- pip

 Possíveis melhorias : 
   Uso de um orm como  sqlachemy
   Melhoria no cli com typer
   Uso da lib scrapy
   executar o projeto no docker usando grid para não ter necessidade de instalar drive na maquina.

