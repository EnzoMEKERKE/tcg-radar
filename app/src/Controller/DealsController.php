<?php
namespace App\Controller;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Contracts\HttpClient\HttpClientInterface;

final class DealsController extends AbstractController
{
    #[Route('/deals', methods:['GET'])]
    public function page(): Response
    {
        return $this->render('deals/index.html.twig');
    }

    #[Route('/api/deals/{action}', requirements:['action'=>'search|import|browser'], methods:['POST'])]
    public function submit(string $action, Request $request, HttpClientInterface $client): JsonResponse
    {
        if ($request->headers->get('X-Requested-With') !== 'XMLHttpRequest') {
            return $this->json(['error'=>'Requête depuis l’application requise.'],400);
        }
        if (strlen($request->getContent())>2100000) return $this->json(['error'=>'Fichier trop volumineux (2 Mo maximum).'],413);
        $data=json_decode($request->getContent(),true);
        if (!is_array($data) || array_is_list($data) && $data!==[]) return $this->json(['error'=>'Données invalides.'],400);
        return $this->proxy($client,'POST','/deals/'.$action,$data);
    }

    #[Route('/api/deals/status/{id}', requirements:['id'=>'[a-f0-9]{32}'], methods:['GET'])]
    public function status(string $id, HttpClientInterface $client): JsonResponse
    {
        return $this->proxy($client,'GET','/deals/status/'.$id);
    }

    #[Route('/api/deals/browser', methods:['GET'])]
    public function browser(HttpClientInterface $client): JsonResponse
    {
        return $this->proxy($client,'GET','/deals/browser');
    }

    private function proxy(HttpClientInterface $client,string $method,string $path,?array $data=null): JsonResponse
    {
        try {
            $options=['timeout'=>15,'max_duration'=>20];
            if ($data!==null) $options['json']=$data ?: new \stdClass();
            $response=$client->request($method,rtrim($_ENV['SCRAPER_URL'] ?? 'http://scraper:8000','/').$path,$options);
            $result=$response->toArray(false);
            if ($response->getStatusCode()>=400) {
                $detail=$result['detail'] ?? 'Analyse indisponible.';
                return $this->json(['error'=>is_string($detail)?$detail:'Paramètres invalides. Vérifiez les valeurs du formulaire.'],$response->getStatusCode());
            }
            return $this->json($result);
        } catch (\Throwable) {
            return $this->json(['error'=>'Le service d’analyse est temporairement indisponible. Réessayez dans un instant.'],503);
        }
    }
}
