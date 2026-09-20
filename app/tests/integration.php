<?php
/** Isolated SQLite integration test; PostgreSQL migrations remain a deployment check. */
require dirname(__DIR__).'/vendor/autoload.php';
use App\Kernel;
use App\Entity\Offer;
use App\Entity\Product;
use App\Entity\Store;
use App\Entity\PriceHistory;
use App\Entity\PriceDrop;
use Symfony\Component\HttpFoundation\Request;
use Doctrine\ORM\Tools\SchemaTool;

$_ENV['DATABASE_URL']='sqlite:///:memory:';
$_ENV['APP_SECRET']='integration-only';
$_ENV['INGEST_TOKEN']='test-token';
$_ENV['SHELL_VERBOSITY']='-1';
$kernel=new Kernel('test',true);
$kernel->boot();
$em=$kernel->getContainer()->get('doctrine')->getManager();
$pdo=$em->getConnection()->getNativeConnection();
if (method_exists($pdo,'createFunction')) $pdo->createFunction('pg_advisory_xact_lock',fn()=>1);
else $pdo->sqliteCreateFunction('pg_advisory_xact_lock',fn()=>1);
(new SchemaTool($em))->createSchema($em->getMetadataFactory()->getAllMetadata());
$checks=0;
function check(bool $condition,string $message):void { global $checks; if (!$condition) throw new RuntimeException($message); ++$checks; }
function request(string $url,string $method='GET',?array $data=null,string $token='test-token') {
    global $kernel;
    $r=Request::create($url,$method,[],[],[],['HTTP_X_INGEST_TOKEN'=>$token,'CONTENT_TYPE'=>'application/json'], $data===null?null:json_encode($data));
    return $kernel->handle($r);
}
$row=['store'=>'Fixture shop','store_country'=>'FR','store_url'=>'https://shop.example','title'=>'One Piece OP-08 FR case 6 displays','url'=>'https://shop.example/case','price'=>600,'price_eur'=>600,'shipping_eur'=>12,'in_stock'=>true,'currency'=>'EUR','meta'=>['game'=>'One Piece','set_code'=>'OP-08','language'=>'FR','kind'=>'case','display_count'=>6]];
check(request('/api/ingest','POST',['items'=>[$row]],'wrong')->getStatusCode()===401,'Authentication');
check(request('/api/ingest','POST',[])->getStatusCode()===400,'Payload validation');
$response=request('/api/ingest','POST',['items'=>[$row,$row]]);
check($response->getStatusCode()===200,'Ingestion: '.$response->getContent());
check($em->getRepository(Store::class)->count([])===1,'Duplicate store within batch');
check($em->getRepository(Product::class)->count([])===1,'Duplicate product within batch');
check($em->getRepository(Offer::class)->count([])===1,'Duplicate offer within batch');
$offer=$em->getRepository(Offer::class)->findOneBy([]);
check(abs($offer->unitCost-102)<0.001,'Case unit price includes shipping once');
$id=$offer->product->getId();
check(request('/')->getStatusCode()===200,'Catalogue render');
check(request('/deals')->getStatusCode()===200,'Integrated PokeDeals page');
check(str_contains(request('/')->getContent(),'/deals'),'Deals reachable from main application');
check(request('/api/deals/search','POST',[])->getStatusCode()===400,'Deals mutation requires application header');
$dealsController=new \App\Controller\DealsController();
$dealsController->setContainer($kernel->getContainer());
$dealsClient=new \Symfony\Component\HttpClient\MockHttpClient(function($method,$url,$options) {
    check($method==='POST' && str_ends_with($url,'/deals/search'),'Deals use existing collector');
    return new \Symfony\Component\HttpClient\Response\MockResponse('{"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"running","deals":[]}');
});
$dealRequest=Request::create('/api/deals/search','POST',[],[],[],['HTTP_X_REQUESTED_WITH'=>'XMLHttpRequest','CONTENT_TYPE'=>'application/json'],'{"language":"FR"}');
check(json_decode($dealsController->submit('search',$dealRequest,$dealsClient)->getContent(),true)['status']==='running','Async deals proxy');
$dealsOffline=new \Symfony\Component\HttpClient\MockHttpClient(new \Symfony\Component\HttpClient\Response\MockResponse('{"detail":"Invalid CSV"}',['http_code'=>422]));
check($dealsController->submit('import',$dealRequest,$dealsOffline)->getStatusCode()===422,'Deals import validation preserved');
$catalogController=new \App\Controller\CatalogController();
$catalogController->setContainer($kernel->getContainer());
$catalogClient=new \Symfony\Component\HttpClient\MockHttpClient(function($method,$url) {
    check($method==='POST' && str_ends_with($url,'/catalog/refresh'),'Weekly update endpoint');
    return new \Symfony\Component\HttpClient\Response\MockResponse('{"refreshing":true,"last_checked":123}');
});
$catalogRequest=Request::create('/api/catalog','POST',[],[],[],['HTTP_X_REQUESTED_WITH'=>'XMLHttpRequest']);
$catalogData=json_decode($catalogController->catalog($catalogRequest,$em,$catalogClient)->getContent(),true);
check(count($catalogData['sets'])===1 && $catalogData['sets'][0]['code']==='OP-08','Cached selector catalogue returned during refresh');
check($catalogData['status']['refreshing']===true,'Background refresh status exposed');
$offlineCatalog=new \Symfony\Component\HttpClient\MockHttpClient(new \Symfony\Component\HttpClient\Response\MockResponse('', ['http_code'=>503]));
$cachedCatalog=json_decode($catalogController->catalog(Request::create('/api/catalog'),$em,$offlineCatalog)->getContent(),true);
check(count($cachedCatalog['sets'])===1 && isset($cachedCatalog['status']['last_error']),'Source failure keeps cached catalogue visible');
check($catalogController->catalog(Request::create('/api/catalog','POST'),$em,$catalogClient)->getStatusCode()===400,'Catalogue update origin header required');
if (getenv('EXPORT_PREVIEW')) {
    @mkdir(dirname(__DIR__,2).'/.validation/preview',0777,true);
    file_put_contents(dirname(__DIR__,2).'/.validation/preview/index.html',request('/')->getContent());
    file_put_contents(dirname(__DIR__,2).'/.validation/preview/set.html',request('/sets/'.$id)->getContent());
    file_put_contents(dirname(__DIR__,2).'/.validation/preview/deals.html',request('/deals')->getContent());
}
check(request('/sets/'.$id)->getStatusCode()===200,'Set render');
check(request('/sets/99999')->getStatusCode()===404,'Missing set');
check(request('/api/sets/'.$id.'/discover','POST',[])->getStatusCode()===400,'Discovery origin header required');
$discoveryController=new \App\Controller\DiscoveryController();
$discoveryController->setContainer($kernel->getContainer());
$discoveryRequest=Request::create('/','POST',[],[],[],['HTTP_X_REQUESTED_WITH'=>'XMLHttpRequest'],json_encode(['keywords'=>'livraison France']));
$mockClient=new \Symfony\Component\HttpClient\MockHttpClient(function($method,$url,$options) use (&$checks) {
    check($method==='POST' && str_ends_with($url,'/discover'),'Fixed collector endpoint');
    $body=json_decode($options['body'],true);
    check($body['code']==='OP-08' && $body['keywords']==='livraison France','Search uses canonical product identity');
    check($body['include_prices']===true,'Search requests merchant prices');
    return new \Symfony\Component\HttpClient\Response\MockResponse(json_encode(['status'=>'ok','candidates'=>[['url'=>'https://niche.example/display','status'=>'unverified']]]));
});
$discovered=$discoveryController->search($id,$discoveryRequest,$em,$mockClient);
check($discovered->getStatusCode()===200,'Discovery proxy response');
check($em->getRepository(Offer::class)->count([])===1,'Search results are not inserted as verified offers');
$unavailable=new \Symfony\Component\HttpClient\MockHttpClient(new \Symfony\Component\HttpClient\Response\MockResponse('', ['http_code'=>503]));
$fallback=$discoveryController->search($id,$discoveryRequest,$em,$unavailable);
$fallbackData=json_decode($fallback->getContent(),true);
check($fallback->getStatusCode()===200 && $fallbackData['catalog_count']===1,'Unavailable search retains local offers');
check($fallbackData['candidates'][0]['source_type']==='catalog' && $fallbackData['candidates'][0]['unit_price_eur']===100,'Fallback item price excludes shipping');
check($fallbackData['candidates'][0]['checked_at']===$offer->checkedAt->getTimestamp(),'Fallback preserves actual observation time');
$catalogDiscovery=new \App\Service\CatalogDiscovery();
check($catalogDiscovery->candidates(['game'=>'One Piece','name'=>'OP08','code'=>'OP08','language'=>'JP'],$em)===[],'Fallback does not substitute another language');
check($catalogDiscovery->candidates(['game'=>'Gundam','name'=>'OP08','code'=>'OP08','language'=>'FR'],$em)===[],'Fallback does not substitute another game');
$duplicateClient=new \Symfony\Component\HttpClient\MockHttpClient(new \Symfony\Component\HttpClient\Response\MockResponse(json_encode(['status'=>'ok','candidates'=>[['url'=>$row['url'],'price_status'=>'read']]])));
$deduplicated=json_decode($discoveryController->search($id,$discoveryRequest,$em,$duplicateClient)->getContent(),true);
check(count($deduplicated['candidates'])===1 && $deduplicated['catalog_count']===0,'Fallback deduplicates web URLs');
check(request('/api/discover','POST',[])->getStatusCode()===400,'Free search origin header required');
$explorePayload=['game'=>'One Piece','name'=>' OP-09 ','code'=>'OP-09','language'=>'FR','keywords'=>'livraison France'];
$exploreClient=new \Symfony\Component\HttpClient\MockHttpClient(function($method,$url,$options) {
    $body=json_decode($options['body'],true);
    check($body['name']==='OP-09' && $body['language']==='FR','Free search trims and forwards identity');
    return new \Symfony\Component\HttpClient\Response\MockResponse('{"status":"ok","candidates":[]}');
});
$exploreRequest=fn($body)=>Request::create('/api/discover','POST',[],[],[],['HTTP_X_REQUESTED_WITH'=>'XMLHttpRequest'],json_encode($body));
check($discoveryController->explore($exploreRequest($explorePayload),$exploreClient)->getStatusCode()===200,'Free search without stored set');
foreach ([['name'=>'   '],['game'=>'invalid'],['language'=>'XX'],['keywords'=>['array']],['name'=>str_repeat('a',181)]] as $invalid) {
    check($discoveryController->explore($exploreRequest(array_replace($explorePayload,$invalid)),$exploreClient)->getStatusCode()===400,'Invalid free search rejected');
}
check($discoveryController->explore($exploreRequest(null),$exploreClient)->getStatusCode()===400,'Invalid JSON shape rejected');
$busyClient=new \Symfony\Component\HttpClient\MockHttpClient(new \Symfony\Component\HttpClient\Response\MockResponse('', ['http_code'=>409]));
check($discoveryController->explore($exploreRequest($explorePayload),$busyClient)->getStatusCode()===409,'Busy search reported');
check(request('/api/sets/'.$id.'/history?days=8')->getStatusCode()===400,'Period validation');
foreach ([7,30,90] as $days) {
    $history=json_decode(request('/api/sets/'.$id.'/history?days='.$days)->getContent(),true);
    check(count($history['points'])===1 && $history['points'][0]['price']===102,'History '.$days);
}
$row['price']=480;$row['price_eur']=480;
check(request('/api/ingest','POST',['items'=>[$row]])->getStatusCode()===200,'Price reduction ingest');
check($em->getRepository(PriceDrop::class)->count([])===1,'Persistent price drop');
request('/api/ingest','POST',['items'=>[$row]]);
check($em->getRepository(PriceDrop::class)->count([])===1,'No repeated event at unchanged price');
$alerts=json_decode(request('/api/alerts')->getContent(),true);
check((float)$alerts[0]['new_cost']===82.0,'Alert amount per display');
$row['shipping_eur']=null;
request('/api/ingest','POST',['items'=>[$row]]);
check($em->getRepository(PriceDrop::class)->count([])===1,'Unknown shipping must not cause a drop');
$row['meta']['display_count']=12;
request('/api/ingest','POST',['items'=>[$row]]);
check($em->getRepository(PriceDrop::class)->count([])===1,'Quantity change must not cause a drop');
$row['meta']['display_count']=null;
request('/api/ingest','POST',['items'=>[$row]]);
check($em->getConnection()->fetchOne('SELECT unit_cost FROM offer WHERE id=?',[$offer->getId()])===null,'Unknown case excluded from unit comparison');
$best=json_decode(request('/api/sets/'.$id.'/best')->getContent(),true);
check($best['price']===null,'No comparable offer');
foreach (['unknown-a','unknown-b'] as $slug) {
    $row['url']='https://shop.example/'.$slug; $row['meta']['set_code']=null;
    request('/api/ingest','POST',['items'=>[$row]]);
}
check($em->getRepository(Product::class)->count([])===3,'Unknown references stay separate');
$row['url']='https://shop.example/import';
$row['meta']['set_code']='OP-08'; $row['meta']['display_count']=1;
$row['price']=100; $row['price_eur']=100; $row['shipping_eur']=10;
$row['shipping_origin']=['country'=>'JP','country_label'=>'Japon','region'=>'outside_eu','tax_status'=>'extra',
    'tax_message'=>'TVA à prévoir','sources'=>[['url'=>'https://shop.example/shipping','evidence'=>'Ships from Japan.','checked_at'=>'2026-09-19']]];
check(request('/api/ingest','POST',['items'=>[$row]])->getStatusCode()===200,'Shipping evidence ingestion');
$import=$em->getRepository(Offer::class)->findOneBy(['url'=>$row['url']]);
check($import->shippingOrigin['country']==='JP','Actual shipping country overrides French merchant country');
check(abs($import->landedCost-132)<0.001,'Import VAT estimated once, no invented flat duty');
$page=request('/sets/'.$import->product->getId())->getContent();
check(str_contains($page,'Expédition : Japon') && str_contains($page,'https://shop.example/shipping'),'Origin and evidence rendered');
check(str_contains($page,'TVA estimée incluse'),'Partial cost estimate is labelled');
$drops=$em->getRepository(PriceDrop::class)->count([]);
$row['shipping_origin']['country']='FR'; $row['shipping_origin']['tax_status']='eu';
request('/api/ingest','POST',['items'=>[$row]]);
check($em->getRepository(PriceDrop::class)->count([])===$drops,'Tax basis change must not create a price drop');
check(abs((float)$em->getConnection()->fetchOne('SELECT landed_cost FROM offer WHERE id=?',[$import->getId()])-110)<0.001,'EU shipment adds no import VAT');
$row['shipping_origin']=['country'=>null,'tax_status'=>'unknown'];
request('/api/ingest','POST',['items'=>[$row]]);
check(abs((float)$em->getConnection()->fetchOne('SELECT landed_cost FROM offer WHERE id=?',[$import->getId()])-110)<0.001,'Unknown origin does not invent import charges');
check(str_contains(request('/api/offers')->getContent(),'shippingOrigin'),'API exposes shipping evidence');
echo "PASS: $checks integration checks\n";
$kernel->shutdown();
