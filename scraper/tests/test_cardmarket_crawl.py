import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('cm_crawl',Path(__file__).resolve().parents[2]/'tools/cardmarket_crawl.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PRODUCT='https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu-V1-BS58'


def test_crawl_persists_queue_offers_and_delay_across_restart(tmp_path):
    now=[1000.0]
    waits=[]
    def sleep(seconds):waits.append(seconds);now[0]+=seconds
    def read(url):
        if '/Search?' in url:return {'status':'ok','html':f'<a href="{PRODUCT}">Pikachu</a>'}
        return {'status':'ok','html':'<h1>Pikachu</h1><div class="article-row" id="1"><a href="/fr/Pokemon/Users/Seller">Seller</a><div class="product-attributes">Japanese NM</div><span class="col-price">10 EUR</span></div>'}
    path=tmp_path/'crawl.sqlite'
    crawl=module.Crawl(path,'Pikachu',jitter=0,clock=lambda:now[0],sleep=sleep,read=read)
    assert crawl.step()
    crawl.db.close()
    resumed=module.Crawl(path,'Pikachu',jitter=0,clock=lambda:now[0],sleep=sleep,read=read)
    assert resumed.step()
    assert waits==[20]
    assert resumed.status()['offers']==1 and resumed.status()['shipping_known']==0
    assert not resumed.step()
    assert resumed.status()['pagination_unverified']==1
    resumed.db.close()


def test_block_stops_and_cooldown_survives_restart(tmp_path):
    calls=[]
    def read(url):calls.append(url);return {'status':'verification_required','message':'Vérification requise'}
    path=tmp_path/'crawl.sqlite'
    crawl=module.Crawl(path,'Pikachu',clock=lambda:1000,read=read)
    assert not crawl.step()
    assert crawl.status()['cooldown_until']==2800
    crawl.db.close()
    resumed=module.Crawl(path,'Pikachu',clock=lambda:1100,read=read)
    assert not resumed.step() and len(calls)==1
    assert resumed.status()['pages']['pending']==1
    resumed.db.close()


def test_full_search_queues_next_page_but_repeat_does_not_loop(tmp_path):
    html=''.join(f'<a href="{PRODUCT}-{i}">Card</a>' for i in range(30))
    crawl=module.Crawl(tmp_path/'crawl.sqlite','Pikachu',delay=0,jitter=0,
                       read=lambda url:{'status':'ok','html':html})
    assert crawl.step()
    assert crawl.db.execute("SELECT count(*) FROM queue WHERE kind='search'").fetchone()[0]==2
    # Isolate the search progression without visiting the 30 product fixtures.
    with crawl.db:
        crawl.db.execute("UPDATE queue SET status='done' WHERE kind='product'")
    assert crawl.step()
    assert not crawl.step()
    assert crawl.status()['pagination_unverified']==2
    crawl.db.close()


def test_empty_successful_page_remains_pending_for_retry(tmp_path):
    now=[1000.0]
    calls=[]
    def read(url):
        calls.append(url)
        return {'status':'ok','html':'<html><h1>Cardmarket</h1></html>'}
    path=tmp_path/'crawl.sqlite'
    crawl=module.Crawl(path,'Pikachu',clock=lambda:now[0],read=read)
    assert not crawl.step()
    assert crawl.status()['pages']['pending']==1
    assert crawl.status()['cooldown_until']==2800
    crawl.db.close()
    resumed=module.Crawl(path,'Pikachu',clock=lambda:now[0],read=read)
    assert not resumed.step()
    assert len(calls)==1
    resumed.db.close()


def test_unparseable_product_page_is_not_marked_done(tmp_path):
    now=[1000.0]
    def read(url):
        if '/Search?' in url:
            return {'status':'ok','html':f'<a href="{PRODUCT}">Pikachu</a>'}
        return {'status':'ok','html':'<h1>Pikachu</h1><div class="article-row"></div>'}
    crawl=module.Crawl(tmp_path/'crawl.sqlite','Pikachu',delay=0,jitter=0,
                       clock=lambda:now[0],read=read)
    assert crawl.step()
    assert not crawl.step()
    assert crawl.status()['offers']==0
    assert tuple(crawl.db.execute("SELECT status,note FROM queue WHERE url=?",(PRODUCT,)).fetchone())==('pending','no_verified_data')
    crawl.db.close()
