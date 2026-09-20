<?php
namespace App\Controller;

use App\Entity\Product;
use App\Entity\Offer;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Contracts\HttpClient\HttpClientInterface;

final class CatalogController extends AbstractController
{
    #[Route('/api/catalog', methods:['GET','POST'])]
    public function catalog(Request $request, EntityManagerInterface $em, HttpClientInterface $client): JsonResponse
    {
        $check=$request->isMethod('POST');
        if ($check && $request->headers->get('X-Requested-With')!=='XMLHttpRequest') {
            return $this->json(['error'=>'Requête depuis l’application requise.'],400);
        }
        try {
            $status=$client->request($check?'POST':'GET',rtrim($_ENV['SCRAPER_URL'] ?? 'http://scraper:8000','/')
                .($check?'/catalog/refresh':'/catalog/status'),['timeout'=>3,'max_duration'=>4])->toArray();
        } catch (\Throwable $error) {
            $status=['refreshing'=>false,'last_error'=>'Vérification indisponible ; catalogue en cache conservé.'];
        }
        $sets=$em->createQueryBuilder()
            ->select('p.id AS id,p.game AS game,p.language AS language,p.setCode AS code,p.setName AS name,COUNT(o.id) AS offers')
            ->from(Product::class,'p')->leftJoin(Offer::class,'o','WITH','o.product=p AND o.inStock=true AND o.checkedAt>=:since')
            ->setParameter('since',new \DateTimeImmutable('-48 hours'))
            ->groupBy('p.id,p.game,p.language,p.setCode,p.setName')->orderBy('p.game','ASC')->addOrderBy('p.setCode','ASC')
            ->getQuery()->getArrayResult();
        return $this->json(['sets'=>$sets,'status'=>$status]);
    }
}
