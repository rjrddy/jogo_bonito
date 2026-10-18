"""Download only public historical result data. Rebuild with build_catalog.py."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

CACHE = Path(__file__).resolve().parents[1] / '.local/sources'
SOURCES = {
    'football.zip': 'https://codeload.github.com/openfootball/football.json/zip/refs/heads/master',
    'france.zip': 'https://codeload.github.com/footballcsv/cache.soccerverse/zip/refs/heads/master',
    'international.csv': 'https://raw.githubusercontent.com/martj42/international_results/master/results.csv',
}

def download(item):
    name, url = item
    request = Request(url, headers={'User-Agent': 'JogoBonito/0.2 historical-results-import'})
    with urlopen(request, timeout=90) as response:
        body = response.read()
    temporary = CACHE / (name + '.tmp')
    temporary.write_bytes(body)
    temporary.replace(CACHE / name)
    print(f'{name}: {len(body)} bytes')

if __name__ == '__main__':
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, SOURCES.items()))
