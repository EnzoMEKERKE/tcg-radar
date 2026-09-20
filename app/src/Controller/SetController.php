<?php
namespace App\Controller;

use App\Entity\Offer;
use App\Entity\Product;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

final class SetController extends AbstractController
{
    #[Route('/api/sets/{id}/best', requirements: ['id'=>'\d+'], methods:['GET'])]
    public function best(int $id, EntityManagerInterface $em): JsonResponse
    {
        if (!$em->find(Product::class,$id)) throw $this->createNotFoundException();
        $offer=$em->createQueryBuilder()->select('o')->from(Offer::class,'o')
            ->where('IDENTITY(o.product)=:id AND o.inStock=true AND o.unitCost IS NOT NULL AND o.checkedAt>=:since')
            ->setParameter('id',$id)->setParameter('since',new \DateTimeImmutable('-48 hours'))
            ->orderBy('o.unitCost','ASC')->setMaxResults(1)->getQuery()->getOneOrNullResult();
        return $this->json(['price'=>$offer?->unitCost,'shippingKnown'=>$offer?->shippingKnown]);
    }
    #[Route('/sets/{id}', name: 'set_detail', requirements: ['id'=>'\d+'])]
    public function page(int $id, EntityManagerInterface $em): Response
    {
        $product=$em->find(Product::class,$id);
        if (!$product) throw $this->createNotFoundException();
        $offers=$em->getRepository(Offer::class)->findBy(['product'=>$product,'inStock'=>true],['unitCost'=>'ASC']);
        return $this->render('set.html.twig',['product'=>$product,'offers'=>$offers]);
    }

    #[Route('/api/sets/{id}/history', requirements: ['id'=>'\d+'], methods:['GET'])]
    public function history(int $id, Request $request, EntityManagerInterface $em): JsonResponse
    {
        $days=$request->query->getInt('days',30);
        if (!in_array($days,[7,30,90],true)) return $this->json(['error'=>'days must be 7, 30 or 90'],400);
        if (!$em->find(Product::class,$id)) throw $this->createNotFoundException();
        $rows=$em->getConnection()->fetchAllAssociative(
            'SELECT DATE(h.recorded_at) AS day, MIN(h.unit_cost) AS price, h.shipping_known
             FROM price_history h JOIN offer o ON o.id=h.offer_id
             WHERE h.product_id=:id AND h.recorded_at>=:since AND h.in_stock=true AND h.unit_cost IS NOT NULL
             GROUP BY DATE(h.recorded_at), h.shipping_known ORDER BY day',
            ['id'=>$id,'since'=>(new \DateTimeImmutable('today'))->modify('-'.($days-1).' days')->format('Y-m-d')]
        );
        return $this->json(['days'=>$days,'points'=>array_map(fn($r)=>['day'=>$r['day'],'price'=>(float)$r['price'],'shippingKnown'=>in_array($r['shipping_known'],[true,1,'1','t'],true)],$rows)]);
    }

    #[Route('/api/alerts', methods:['GET'])]
    public function alerts(EntityManagerInterface $em): JsonResponse
    {
        return $this->json($em->getConnection()->fetchAllAssociative(
            'SELECT d.id, o.product_id, p.set_name, p.language, s.name AS store, d.previous_cost, d.new_cost,
                    ROUND(CAST(100*(d.previous_cost-d.new_cost)/NULLIF(d.previous_cost,0) AS numeric),1) AS percent, d.created_at
             FROM price_drop d JOIN offer o ON o.id=d.offer_id JOIN product p ON p.id=o.product_id JOIN store s ON s.id=o.store_id
             ORDER BY d.created_at DESC, d.id DESC LIMIT 100'
        ));
    }
}
