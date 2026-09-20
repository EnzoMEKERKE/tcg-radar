<?php
namespace App\Service;

use App\Entity\Offer;
use Doctrine\ORM\EntityManagerInterface;

/** Recent observations remain useful when an external search engine is unavailable. */
final class CatalogDiscovery
{
    public function candidates(array $query, EntityManagerInterface $em): array
    {
        $qb=$em->createQueryBuilder()->select('o,p,s')->from(Offer::class,'o')
            ->join('o.product','p')->join('o.store','s')
            ->where('p.game=:game AND o.inStock=true AND o.checkedAt>=:since')
            ->setParameter('game',$query['game'])
            ->setParameter('since',new \DateTimeImmutable('-48 hours'));
        $code=$query['code'] ?? '';
        if ($code!=='' && !preg_match('/^(UNKNOWN|UNMATCHED-|YGO-)/',$code)) {
            $compact=str_replace(['-',' '],'',strtoupper($code));
            $codes=array_unique([strtoupper($code),$compact,preg_replace('/^([A-Z]+)([0-9])/','$1-$2',$compact)]);
            $qb->andWhere('UPPER(p.setCode) IN (:codes)')->setParameter('codes',$codes);
        } else {
            $qb->andWhere('LOWER(p.setName)=:name')->setParameter('name',mb_strtolower($query['name']));
        }
        if (in_array($query['language'],['FR','JP','EN'],true)) {
            $qb->andWhere('p.language=:language')->setParameter('language',$query['language']);
        }
        $offers=$qb->orderBy('o.inStock','DESC')->addOrderBy('o.checkedAt','DESC')->setMaxResults(100)->getQuery()->getResult();
        return array_map(static function(Offer $o): array {
            // Stored landedCost includes import/shipping: never mislabel it as the item price.
            $unit=$o->currency==='EUR' && $o->displayCount ? round($o->price/$o->displayCount,2) : null;
            $language=$o->product->language;
            return ['url'=>$o->url,'domain'=>preg_replace('/^www\./','',parse_url($o->url,PHP_URL_HOST) ?? ''),
                'title'=>$o->title,'price_title'=>$o->title,'price_url'=>$o->url,'known_store'=>true,
                'status'=>'collected','source_type'=>'catalog','snippet'=>'Offre issue de la dernière collecte de la boutique.',
                'set_match'=>true,'language_match'=>in_array($language,['FR','JP','EN'],true)?'match':'unknown',
                'detected_languages'=>[$language],'packaging'=>$o->displayCount>1?'case':'display',
                'price_status'=>'read','price'=>$o->price,'currency'=>$o->currency,'unit_price_eur'=>$unit,
                'display_count'=>$o->displayCount,'in_stock'=>$o->inStock,'comparable'=>$unit!==null && $o->inStock,
                'checked_at'=>$o->checkedAt->getTimestamp(),'shipping_origin'=>$o->shippingOrigin];
        },$offers);
    }
}
