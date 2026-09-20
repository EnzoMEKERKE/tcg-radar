<?php
namespace App\Controller;

use App\Entity\Product;
use App\Service\CatalogDiscovery;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Contracts\HttpClient\HttpClientInterface;

final class DiscoveryController extends AbstractController
{
    #[Route('/api/discover', methods:['POST'])]
    public function explore(Request $request, HttpClientInterface $client, ?EntityManagerInterface $em=null): JsonResponse
    {
        if ($request->headers->get('X-Requested-With') !== 'XMLHttpRequest') {
            return $this->json(['error'=>'Requête depuis l’application requise.'],400);
        }
        $data=json_decode($request->getContent(),true);
        if (!is_array($data)) return $this->json(['error'=>'Recherche invalide.'],400);
        $payload=[];
        foreach (['game'=>30,'name'=>180,'code'=>50,'language'=>5,'keywords'=>80] as $field=>$limit) {
            $value=$data[$field] ?? '';
            if (!is_string($value) || mb_strlen($value)>$limit) {
                return $this->json(['error'=>'Un champ de recherche est invalide ou trop long.'],400);
            }
            $payload[$field]=trim($value);
        }
        if ($payload['name']==='' || !in_array($payload['game'],['Pokemon','One Piece','Yu-Gi-Oh!','Gundam'],true)
            || !in_array($payload['language'],['FR','JP','EN','UNK','OTHER'],true)) {
            return $this->json(['error'=>'Indiquez un set, un jeu et une langue valides.'],400);
        }
        return $this->forwardSearch($payload,$client,$em);
    }

    #[Route('/api/sets/{id}/discover', requirements: ['id'=>'\d+'], methods:['POST'])]
    public function search(int $id, Request $request, EntityManagerInterface $em, HttpClientInterface $client): JsonResponse
    {
        if ($request->headers->get('X-Requested-With') !== 'XMLHttpRequest') {
            return $this->json(['error'=>'Requête depuis l’application requise.'],400);
        }
        $product=$em->find(Product::class,$id);
        if (!$product) throw $this->createNotFoundException();
        $data=json_decode($request->getContent(),true);
        if (!is_array($data)) return $this->json(['error'=>'Recherche invalide.'],400);
        $keywords=$data['keywords'] ?? '';
        if (!is_string($keywords) || mb_strlen($keywords)>80) {
            return $this->json(['error'=>'Les mots-clés sont limités à 80 caractères.'],400);
        }
        return $this->forwardSearch(['game'=>$product->game,'name'=>$product->setName,'code'=>$product->setCode,
            'language'=>$product->language,'keywords'=>trim($keywords)],$client,$em);
    }

    private function forwardSearch(array $payload, HttpClientInterface $client, ?EntityManagerInterface $em=null): JsonResponse
    {
        $payload['include_prices']=true;
        $failed=false;
        try {
            $response=$client->request('POST',rtrim($_ENV['SCRAPER_URL'] ?? 'http://scraper:8000','/').'/discover',[
                'json'=>$payload,
                'timeout'=>70,'max_duration'=>70,
            ]);
            if ($response->getStatusCode()===409) return $this->json(['error'=>'Une recherche est déjà en cours. Réessayez dans un instant.'],409);
            $result=$response->toArray();
        } catch (\Throwable $error) {
            $failed=true;
            $result=['status'=>'unavailable','candidates'=>[], 'message'=>'Les moteurs web sont indisponibles. Les offres déjà collectées restent consultables.'];
        }
        $web=$result['candidates'] ?? [];
        $urls=array_fill_keys(array_column($web,'url'),true);
        foreach ($result['excluded_stock_urls'] ?? [] as $url) $urls[$url]=true;
        $local=$em ? (new CatalogDiscovery())->candidates($payload,$em) : [];
        $added=0;
        foreach ($local as $row) {
            if (isset($urls[$row['url']])) continue;
            $web[]=$row; $urls[$row['url']]=true; ++$added;
        }
        $result['candidates']=$web;
        $result['catalog_count']=$added;
        $result['priced_count']=count(array_filter($web,fn($row)=>($row['price_status'] ?? '')==='read'));
        $result['comparable_count']=count(array_filter($web,fn($row)=>($row['comparable'] ?? false)));
        if ($added && in_array($result['status'] ?? '',['unavailable','unconfigured'],true)) {
            $result['status']='partial';
            $result['message']='Recherche web indisponible : affichage des offres déjà collectées, avec leur date de relevé.';
        }
        if ($failed && !$web) {
            $result['error']=$result['message'];
            return $this->json($result,503);
        }
        return $this->json($result);
    }
}
