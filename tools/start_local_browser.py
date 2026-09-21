"""Start the local browser service from the user's Windows desktop."""
from pathlib import Path
import subprocess
import sys
import time

import requests


def ready():
    try:
        return requests.get('http://127.0.0.1:8766/status', timeout=2).json().get('available', False)
    except (requests.RequestException, ValueError):
        return False


def main():
    if ready():
        print('Le service Chrome local est disponible.')
        return 0
    root = Path(__file__).resolve().parents[1]
    logs = root / '.local-browser'
    logs.mkdir(exist_ok=True)
    with (logs / 'service.log').open('a') as out, (logs / 'service-error.log').open('a') as err:
        child = subprocess.Popen([sys.executable, str(root / 'tools/local_deals_browser.py')],
                                 cwd=root, stdout=out, stderr=err,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for _ in range(15):
        if ready():
            print('Service pret. Ouvrez http://localhost:8080/deals et cliquez sur Ouvrir Chrome pour Cardmarket.')
            return 0
        if child.poll() is not None:
            break
        time.sleep(0.5)
    print('Le service Chrome n’a pas demarre. Consultez .local-browser/service-error.log.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
