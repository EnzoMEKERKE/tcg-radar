"""Slow, resumable Cardmarket offer collection through the dedicated local browser.

One worker. No purchases, login automation, proxies or challenge solving.
Only sanitized listing fragments enter the database. Run --help for controls.
"""
import argparse
from contextlib import contextmanager
import csv
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys
import time
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scraper'))
from app.deals.parsers import parse_cardmarket, product_links, cardmarket_next_page


@contextmanager
def single_worker():
    path=ROOT/'.local-browser/cardmarket-crawl.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise SystemExit('Une collecte Cardmarket est déjà lancée. Un seul processus est autorisé.')
        try:
            yield
        finally:
            if os.name=='nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def next_numbered(url):
    parts=urlsplit(url)
    params=parse_qs(parts.query)
    params['site']=[str(int(params.get('site',['1'])[0])+1)]
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params,doseq=True),''))


class Crawl:
    def __init__(self,path,query,scope='search',delay=20,jitter=15,clock=time.time,sleep=time.sleep,read=None):
        self.clock,self.sleep=clock,sleep
        self.delay,self.jitter=delay,jitter
        self.read=read or self.browser_read
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS queue(url TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',note TEXT);
            CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        ''')
        config=json.dumps({'query':query,'scope':scope},sort_keys=True)
        previous=self.get('config')
        if previous and previous!=config:
            raise ValueError('Ce fichier contient une autre recherche : utilisez un autre --db.')
        with self.db:
            self.set('config',config)
            # An interrupted read is safe to retry after the persisted delay.
            self.db.execute("UPDATE queue SET status='pending' WHERE status='reading'")
            if not previous:
                root='https://www.cardmarket.com/fr/Pokemon/Products/'
                url=root+'Singles' if scope=='pokemon' else root+'Search?'+urlencode({'searchString':query})
                self.enqueue(url,'search')

    def get(self,key,default=None):
        row=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return row[0] if row else default

    def set(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,str(value)))

    def enqueue(self,url,kind):
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.netloc!='www.cardmarket.com' or not parts.path.startswith('/fr/Pokemon/Products/'):
            raise ValueError('URL hors du périmètre Cardmarket Pokémon')
        self.db.execute('INSERT OR IGNORE INTO queue(url,kind) VALUES (?,?)',(url,kind))

    @staticmethod
    def browser_read(url):
        response=requests.post('http://127.0.0.1:8766/read',json={'url':url},headers={'X-TCG-Local':'browser'},timeout=45)
        response.raise_for_status()
        return response.json()

    def step(self):
        # Cooldowns persist through process restarts; no retry loop on a block.
        if self.clock()<float(self.get('cooldown_until','0')):
            return False
        entry=self.db.execute("SELECT * FROM queue WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
        if not entry:
            return False
        wait=max(0,float(self.get('next_read_at','0'))-self.clock())
        if wait:
            self.sleep(wait)
        with self.db:
            self.db.execute("UPDATE queue SET status='reading' WHERE url=?",(entry['url'],))
            self.set('next_read_at',self.clock()+self.delay+random.uniform(0,self.jitter))
        try:
            result=self.read(entry['url'])
        except (requests.RequestException,ValueError):
            result={'status':'unavailable','message':'Erreur de lecture du navigateur local.'}
        if result.get('status')!='ok':
            with self.db:
                self.db.execute("UPDATE queue SET status='pending',note=? WHERE url=?",(result.get('status','unavailable'),entry['url']))
                self.set('cooldown_until',self.clock()+1800)
                self.set('message',result.get('message') or 'Lecture interrompue ; délai de reprise de 30 minutes.')
            return False
        html=result.get('html','')
        soup=BeautifulSoup(html,'html.parser')
        # A successful browser response can still contain an incomplete page.
        # Keep it queued rather than silently losing this search or product.
        parsed=product_links(html,entry['url']) if entry['kind']=='search' else parse_cardmarket(html,entry['url'])
        if not parsed:
            with self.db:
                self.db.execute("UPDATE queue SET status='pending',note=? WHERE url=?",
                                ('no_verified_data',entry['url']))
                self.set('cooldown_until',self.clock()+1800)
                self.set('message','Page Cardmarket sans données vérifiées ; nouvelle tentative après 30 minutes.')
            return False
        target=cardmarket_next_page(html,entry['url'])
        uncertain=False
        with self.db:
            if entry['kind']=='search':
                links=parsed
                fresh_links=0
                if not links:
                    uncertain=True
                for link in links:
                    fresh_links+=not bool(self.db.execute('SELECT 1 FROM queue WHERE url=?',(link,)).fetchone())
                    self.enqueue(link,'product')
                # Without a visible next link, never claim the whole catalogue is covered.
                if not target:
                    uncertain=True
                    if len(links)>=30 and fresh_links:
                        target=next_numbered(entry['url'])
                if not fresh_links:
                    target=None
                    uncertain=True
            else:
                rows=parsed
                fresh=0
                for row in rows:
                    key=json.dumps([urlsplit(row.url).path,row.listing_id or row.seller,row.language,row.condition,row.variant])
                    exists=self.db.execute('SELECT 1 FROM offers WHERE id=?',(key,)).fetchone()
                    fresh+=not bool(exists)
                    self.db.execute('INSERT OR REPLACE INTO offers VALUES (?,?)',(key,row.model_dump_json()))
                if not target and len(soup.select('.article-row'))>=50 and fresh:
                    # Legacy bridge omits query-only pagination. Probe only the next
                    # page, paced normally, then stop on duplicates or access errors.
                    target=next_numbered(entry['url'])
                    uncertain=True
                if not fresh:
                    target=None
                    uncertain=True
            if target:
                self.enqueue(target,entry['kind'])
            self.db.execute('UPDATE queue SET status=?,note=? WHERE url=?',
                ('done', 'pagination_non_confirmee' if uncertain else None,entry['url']))
            self.set('message','Collecte en cours ; progression sauvegardée.')
        return True

    def status(self):
        counts={r[0]:r[1] for r in self.db.execute('SELECT status,count(*) FROM queue GROUP BY status')}
        shipping=self.db.execute("SELECT count(*) FROM offers WHERE json_extract(payload,'$.shipping') IS NOT NULL").fetchone()[0]
        return {'pages':counts,'offers':self.db.execute('SELECT count(*) FROM offers').fetchone()[0],
                'shipping_known':shipping,'pagination_unverified':self.db.execute('SELECT count(*) FROM queue WHERE note=?',('pagination_non_confirmee',)).fetchone()[0],
                'cooldown_until':float(self.get('cooldown_until','0')),'message':self.get('message','Prêt')}

    def export(self,path):
        fields=['source','title','url','price','currency','shipping','language','condition','card_number','set_code','variant','sold','sold_at','observed_at','available','seller','listing_id','price_exact','provenance']
        with open(path,'w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
            writer.writeheader()
            for row in self.db.execute('SELECT payload FROM offers'):
                writer.writerow(json.loads(row[0]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query',default='Pikachu')
    parser.add_argument('--scope',choices=['search','pokemon'],default='search')
    parser.add_argument('--db',default=str(ROOT/'.local-browser/cardmarket-crawl.sqlite'))
    parser.add_argument('--delay',type=float,default=20)
    parser.add_argument('--jitter',type=float,default=15)
    parser.add_argument('--max-requests',type=int,default=100)
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--export')
    args=parser.parse_args()
    if not math.isfinite(args.delay) or not math.isfinite(args.jitter) or args.delay<20 or args.jitter<0 or args.max_requests<1:
        parser.error('Délai minimal : 20 secondes ; jitter positif ; au moins une requête.')
    crawl=Crawl(args.db,args.query,args.scope,args.delay,args.jitter)
    try:
        if not args.status and not args.export:
            for _ in range(args.max_requests):
                if not crawl.step():
                    break
                print(json.dumps(crawl.status(),ensure_ascii=True),flush=True)
        if args.export:
            crawl.export(args.export)
        print(json.dumps(crawl.status(),ensure_ascii=True),flush=True)
    except KeyboardInterrupt:
        print('Arrêt demandé. Relancer la même commande pour reprendre.',flush=True)
    finally:
        crawl.db.close()


if __name__=='__main__':
    with single_worker():
        main()
