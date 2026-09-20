<?php
namespace App\Controller;

use App\Entity\Offer;
use App\Entity\PriceHistory;
use App\Entity\PriceDrop;
use App\Entity\Product;
use App\Entity\Store;
use App\Service\LandedCostCalculator;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

final class IngestController extends AbstractController
{
    #[Route('/api/ingest', name:'api_ingest', methods:['POST'])]
    public function ingest(Request $request, EntityManagerInterface $em, LandedCostCalculator $cost): JsonResponse
    {
        $expected = $_ENV['INGEST_TOKEN'] ?? 'dev-change-me';
        if (!hash_equals($expected, (string)$request->headers->get('X-Ingest-Token'))) {
            return $this->json(['error'=>'unauthorized'], 401);
        }
        $payload = json_decode($request->getContent(), true);
        if (!is_array($payload) || !is_array($payload['items'] ?? null) || count($payload['items']) > 50000) {
            return $this->json(['error'=>'Expected items array (maximum 50000)'], 400);
        }
        $em->getConnection()->beginTransaction();
        // Serialize catalogue upserts across simultaneous collectors.
        $em->getConnection()->executeStatement('SELECT pg_advisory_xact_lock(52005)');
        try {
        $stores=[]; $products=[]; $offers=[];
        $items = is_array($payload['items'] ?? null) ? $payload['items'] : [];
        $stats=['received'=>count($items),'accepted'=>0,'skipped'=>0,'created'=>0,'updated'=>0];
        foreach (($payload['catalog'] ?? []) as $entry) {
            if (!is_array($entry) || empty($entry['game']) || empty($entry['code']) || empty($entry['language']) || empty($entry['name'])) continue;
            $key=$entry['game'].'|'.$entry['code'].'|'.$entry['language'].'|display';
            $product=$products[$key] ?? $em->getRepository(Product::class)->findOneBy(['game'=>$entry['game'],'setCode'=>$entry['code'],'language'=>$entry['language'],'kind'=>'display']);
            if (!$product) { $product=new Product(); $product->game=$entry['game']; $product->setCode=$entry['code']; $product->language=$entry['language']; $em->persist($product); }
            $product->setName=mb_substr($entry['name'],0,180); $product->canonical=true; $product->catalogSource=$entry['source'] ?? null;
            $products[$key]=$product;
        }
        foreach ($items as $row) {
            if (!is_array($row)) { $stats['skipped']++; continue; }
            $m=$row['meta'] ?? [];
            if (!is_array($m) || empty($row['store']) || !isset($row['price_eur']) || !is_numeric($row['price_eur']) || !is_finite((float)$row['price_eur']) || (float)$row['price_eur'] <= 0 || !is_numeric($row['price'] ?? null) || (float)$row['price'] <= 0 || !filter_var($row['url'] ?? '', FILTER_VALIDATE_URL) || !in_array(parse_url($row['url'], PHP_URL_SCHEME), ['https','http'], true)) { $stats['skipped']++; continue; }
            if (!in_array($m['kind'] ?? '', ['display','case'], true)) { $stats['skipped']++; continue; }
            if (empty($m['game']) || empty($m['kind']) || empty($row['url']) || !isset($row['price'])) { $stats['skipped']++; continue; }
            $store=$stores[$row['store']] ?? $em->getRepository(Store::class)->findOneBy(['name'=>(string)$row['store']]);
            if (!$store) { $store=new Store(); $store->name=(string)$row['store']; $store->baseUrl=(string)($row['store_url'] ?? parse_url($row['url'],PHP_URL_SCHEME).'://'.parse_url($row['url'],PHP_URL_HOST)); $store->country=strtoupper((string)($row['store_country'] ?? 'FR')); $store->currency=strtoupper((string)($row['currency'] ?? 'EUR')); $store->strategy=(string)($row['source'] ?? 'universal'); $em->persist($store); }
            $stores[$row['store']]=$store;
            $lang=strtoupper((string)($m['language'] ?? 'UNK')); $code=strtoupper((string)($m['set_code'] ?? 'UNMATCHED-'.substr(hash('sha256',$row['url']),0,24)));
            $key=$m['game'].'|'.$code.'|'.$lang.'|display';
            $product=$products[$key] ?? $em->getRepository(Product::class)->findOneBy(['game'=>$m['game'],'setCode'=>$code,'language'=>$lang,'kind'=>'display']);
            if (!$product) { $product=new Product(); $product->game=(string)$m['game']; $product->setCode=$code; $product->setName=mb_substr((string)($m['set_name'] ?? $m['title'] ?? $row['title']),0,180); $product->language=$lang; $product->kind='display'; $product->boosters=isset($m['boosters'])?(int)$m['boosters']:null; $em->persist($product); }
            $products[$key]=$product;
            $product->canonical=(bool)($m['canonical'] ?? false);
            $product->catalogSource=$m['catalog_source'] ?? null;
            if ($product->canonical) $product->setName=mb_substr((string)$m['set_name'],0,180);
            $offer=$offers[$row['url']] ?? $em->getRepository(Offer::class)->findOneBy(['url'=>(string)$row['url']]); $new=!$offer;
            if (!$offer) { $offer=new Offer(); $offer->url=(string)$row['url']; $em->persist($offer); }
            $previous=$offer->unitCost; $wasAvailable=$offer->inStock;
            $sameProduct=$offer->getId() !== null && $offer->product === $product;
            $known=isset($row['shipping_eur']);
            $sameShipping=$offer->shippingKnown === $known;
            $units=array_key_exists('display_count',$m) ? $m['display_count'] : ($m['kind']==='display' ? 1 : null);
            $sameQuantity=$offer->displayCount === $units;
            $offer->displayCount=is_int($units) && $units>0 && $units<=100 ? $units : null;
            $offer->shippingKnown=$known;
            $offers[$row['url']]=$offer;
            $offer->product=$product; $offer->store=$store; $offer->title=mb_substr((string)$row['title'],0,220); $offer->price=(float)$row['price']; $offer->currency=strtoupper((string)($row['currency'] ?? $store->currency)); $offer->shipping=(float)($row['shipping_eur'] ?? 0); $offer->inStock=(bool)($row['in_stock'] ?? false); $offer->costConfidence=(string)($row['landed_cost_confidence'] ?? 'low'); $offer->matchConfidence=(int)($m['confidence'] ?? 0); $offer->checkedAt=new \DateTimeImmutable();
            $priceEur=(float)($row['price_eur'] ?? $row['price']);
            $origin=is_array($row['shipping_origin'] ?? null) ? $row['shipping_origin'] : null;
            $sameOrigin=($offer->shippingOrigin['country'] ?? null)===($origin['country'] ?? null)
                && ($offer->shippingOrigin['tax_status'] ?? null)===($origin['tax_status'] ?? null);
            $offer->shippingOrigin=$origin;
            $taxStatus=$origin['tax_status'] ?? 'unknown';
            // Only estimate import VAT when the source says it remains payable.
            $calc=$cost->calculate($priceEur,$offer->shipping,$origin['country'] ?? 'UNK',$taxStatus!=='extra',
                (float)($row['carrier_fee'] ?? 0),(float)($row['customs'] ?? 0));
            $offer->landedCost=round($calc['total'],2);
            $offer->unitCost=$offer->displayCount ? round($offer->landedCost/$offer->displayCount,2) : null;
            if ($sameProduct && $sameShipping && $sameQuantity && $sameOrigin && $wasAvailable && $offer->inStock && $previous !== null && $offer->unitCost !== null && $offer->unitCost < $previous-0.005) {
                $drop=new PriceDrop(); $drop->offer=$offer; $drop->previousCost=$previous; $drop->newCost=$offer->unitCost; $em->persist($drop);
            }
            $history=new PriceHistory(); $history->offer=$offer; $history->product=$product; $history->price=$offer->price; $history->landedCost=$offer->landedCost; $history->unitCost=$offer->unitCost; $history->inStock=$offer->inStock; $history->shippingKnown=$offer->shippingKnown; $em->persist($history);
            $stats[$new?'created':'updated']++; $stats['accepted']++;
        }
        $em->flush(); $em->getConnection()->commit(); return $this->json($stats);
        } catch (\Throwable $error) { $em->getConnection()->rollBack(); throw $error; }
    }
}
