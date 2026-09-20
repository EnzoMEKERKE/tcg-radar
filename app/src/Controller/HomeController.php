<?php
namespace App\Controller;
use App\Entity\Offer;
use App\Entity\Product;
use App\Entity\Store;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;
final class HomeController extends AbstractController
{
    #[Route('/', name:'home')]
    public function index(EntityManagerInterface $em): Response
    {
        $sets=[];
        foreach ($em->getRepository(Product::class)->findBy([],['game'=>'ASC','setCode'=>'ASC']) as $product) {
            $sets[$product->getId()]=['product'=>$product,'best'=>null,'count'=>0];
        }
        $offers=$em->createQueryBuilder()->select('o,p,s')->from(Offer::class,'o')->join('o.product','p')->join('o.store','s')
            ->where('o.inStock=true AND o.checkedAt >= :since')->setParameter('since',new \DateTimeImmutable('-48 hours'))->getQuery()->getResult();
        foreach ($offers as $offer) {
            $id=$offer->product->getId();
            $sets[$id]['count']++;
            if ($offer->unitCost !== null && ($sets[$id]['best'] === null || $offer->unitCost < $sets[$id]['best']->unitCost)) $sets[$id]['best']=$offer;
        }
        return $this->render('home.html.twig',['sets'=>$sets,'offerCount'=>count($offers),'storeCount'=>$em->getRepository(Store::class)->count(['enabled'=>true])]);
    }
}
