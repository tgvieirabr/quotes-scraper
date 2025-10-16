from setuptools import setup, find_packages
from pathlib import Path

readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = requirements_file.read_text(encoding="utf-8").strip().split('\n') if requirements_file.exists() else []

setup(
    name="quotes-scraper",
    version="1.0.0",
    author="Tiago",
    author_email="tgvieirabr@gmail.com",
    description="Scraper para quotes.toscrape.com com persistência em BD",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/t/quotes-scraper",
    project_urls={
        "Bug Tracker": "https://github.com/tgvieirabr/quotes-scraper/issues",
        "Documentation": "https://github.com/tgvieirabr/quotes-scraper/blob/main/README.md",
        "Source Code": "https://github.com/tgvieirabr/quotes-scraper",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-cov>=5.0",
            "pytest-mock>=3.0",
            "black>=24.0",
            "flake8>=7.0",
            "mypy>=1.0",
        ],
        "test": [
            "pytest>=8.0",
            "pytest-cov>=5.0",
            "pytest-mock>=3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "quotes-scraper=scraper:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="scraper web-scraping quotes beautifulsoup selenium pandas",
)