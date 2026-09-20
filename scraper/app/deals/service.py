import asyncio
import csv
import hashlib
import io
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from pydantic import ValidationError
from .models import Listing
from .collector import Collector
from .analyzer import analyze


CSV_FIELDS = ['source','title','url','price','currency','shipping','language','condition','card_number','set_code','variant','sold','sold_at','observed_at','available','seller','listing_id','price_exact']


def parse_csv(content):
    try:
        dialect = csv.Sniffer().sniff(content[:10000],delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')),dialect=dialect)
    required = {'source','title','url','price','observed_at'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Colonnes requises : source, title, url, price, observed_at. Utilisez le modèle CSV.')
    rows = []
    for line, data in enumerate(reader,2):
        if line > 2001: raise ValueError('Import limité à 2 000 lignes.')
        values = {key:value.strip() for key,value in data.items() if key in CSV_FIELDS and isinstance(value,str) and value.strip()}
        if not values: continue
        if not values.get('observed_at'): raise ValueError(f'Ligne {line} : date de relevé manquante.')
        values['provenance'] = 'imported'
        for key in ('price','shipping'):
            if key in values: values[key] = values[key].replace(',','.')
        try:
            row = Listing.model_validate(values)
        except ValidationError as error:
            first = error.errors()[0]
            raise ValueError(f"Ligne {line} : champ {first['loc'][0]} invalide ({first['type']}).") from error
        if row.sold and not row.sold_at:
            raise ValueError(f'Ligne {line} : une vente réalisée doit avoir une date sold_at.')
        rows.append(row)
    if not rows: raise ValueError('Le fichier ne contient aucune observation.')
    return rows


class DealsService:
    def __init__(self,path=None,collector_factory=Collector):
        self.path = Path(path or os.getenv('DEALS_CACHE','/tmp/tcg-deals.sqlite'))
        self.collector_factory = collector_factory
        self.tasks = {}

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, updated REAL NOT NULL, payload TEXT NOT NULL)')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self,job):
        with self.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(job['id'],time.time(),json.dumps(job,ensure_ascii=False)))
            conn.execute('DELETE FROM jobs WHERE updated < ?',(time.time()-30*86400,))

    def status(self,key):
        with self.connect() as conn:
            row = conn.execute('SELECT payload FROM jobs WHERE id=?',(key,)).fetchone()
        if not row: return None
        job = json.loads(row[0])
        if job['status']=='running' and key not in self.tasks:
            job.update(status='interrupted',message='Collecte interrompue par un redémarrage. Vous pouvez la relancer.')
            self.save(job)
        return job

    def start(self,settings):
        config = settings.model_dump(exclude={'force'})
        key = hashlib.sha256(json.dumps([3,config],sort_keys=True).encode()).hexdigest()[:32]
        existing = self.status(key)
        if key in self.tasks: return existing
        # Failed reads have a short cooldown, never a successful empty cache.
        if existing and not settings.force and time.time()-existing['started_at'] < (10800 if existing['status']=='complete' else 60):
            return dict(existing,cached=True)
        if self.tasks: raise ValueError('Une analyse est déjà en cours. Attendez sa fin.')
        job = {'id':key,'status':'running','started_at':time.time(),'settings':config,'reports':[],
               'deals':[],'deal_count':0,'listing_count':0,'message':'Lecture par navigateur des ventes eBay et des offres Cardmarket…'}
        if existing and existing.get('deals'):
            job['previous_result'] = {k:existing[k] for k in ('deals','analyzed_at','listing_count','deal_count') if k in existing}
        self.save(job)
        task = asyncio.create_task(self.run(job,settings))
        self.tasks[key] = task
        task.add_done_callback(lambda _:self.tasks.pop(key,None))
        return job

    async def run(self,job,settings):
        collector = self.collector_factory()
        try:
            try:
                async with asyncio.timeout(180):
                    await collector.collect(settings)
            except TimeoutError:
                collector.reports.append({'source':'scan','status':'timeout','message':'Limite de trois minutes atteinte ; résultats partiels conservés.'})
            result = analyze(collector.rows,settings)
            statuses = {r['status'] for r in collector.reports}
            failed = bool(statuses & {'blocked','error','unavailable','timeout','no_verified_rows','login_required','verification_required'})
            job.update(result,status=('partial' if collector.rows else 'unavailable') if failed else 'complete',
                       reports=collector.reports,requests=collector.requests,
                       message='Analyse terminée.' if not failed else 'Collecte incomplète : consultez le statut de chaque source.')
        except Exception:
            job.update(status='error',reports=collector.reports,message='L’analyse a échoué. Les résultats précédents restent conservés.')
        finally:
            close = getattr(collector,'close',None)
            if close:
                try:
                    await close()
                except Exception:
                    pass
            job['finished_at'] = time.time()
            self.save(job)

    def imported(self,request):
        rows = parse_csv(request.csv)
        result = analyze(rows,request.settings)
        key = hashlib.sha256((request.csv+request.settings.model_dump_json()).encode()).hexdigest()[:32]
        job = dict(result,id=key,status='complete',started_at=time.time(),finished_at=time.time(),cached=False,
                   message='Analyse des observations importées ; ces prix n’ont pas été revérifiés en ligne.',
                   reports=[{'source':'import','status':'ok','count':len(rows),'message':f'{len(rows)} observations importées.'}])
        self.save(job)
        return job
