# crawl4md

A Python library for crawling websites and extracting their content as Markdown-formatted text files.

## Installation

```bash
pip install -e ".[dev]"
crawl4ai-setup  # one-time browser setup
```

## Quick Start

```python
from crawl4md import SiteCrawler, CrawlerConfig, PageConfig

config = CrawlerConfig(urls=["https://example.com"])
page_config = PageConfig()

crawler = SiteCrawler(config, page_config)
results = crawler.crawl()

from crawl4md import ContentExtractor, FileWriter

extractor = ContentExtractor(page_config)
pages = extractor.extract(results)

writer = FileWriter()
writer.write(pages, crawler.output_dir, page_config.max_file_size_mb)
```

## Usage

See `notebooks/crawl4md.ipynb` for a guided, step-by-step notebook.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## License

MIT
