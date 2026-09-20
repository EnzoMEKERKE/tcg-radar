# TCG Radar V5

## Collecte eBay locale sans clé API

Le parcours utilise Chrome local via Scrapling et BeautifulSoup pour extraire
les annonces. Le branchement ScrapingBee est désactivé, même si une ancienne
variable de configuration fournisseur existe. Aucun service à clé n'est appelé.
Validation réelle : 78 annonces actives Pikachu, dont 72 avec port renseigné.
Les ventes terminées demandent une connexion eBay dans la fenêtre Chrome dédiée.
Le profil persiste ; les identifiants et cookies ne quittent pas le service local.
Les annonces collectées sont désormais consultables dans la page Bonnes affaires,
avec filtre annonces actives / ventes terminées et liens d'origine.
Guide : [collecte eBay](tools/EBAY-SCRAPING.md).
Validation après déploiement : 68 annonces actives enregistrées dans une analyse,
affichage et filtre des observations vérifiés sur ordinateur/mobile. 56 tests
Python ciblés réussis. Rapport : `.validation/ebay-app-live.json`.

## Prix Cardmarket disponibles dans l'application

Filtres disponibles : extension, budget minimum/maximum, référence de prix
(prix bas, tendance, moyennes 1/7/30 jours), série principale ou « holo », tri
par prix, nom ou identifiant. Le budget et le tri utilisent exactement la série
et la référence sélectionnées. Les filtres sont conservés dans l'URL et peuvent
être réinitialisés ; ils s'appliquent avant la pagination.

Les illustrations anglaises TCGdex sont chargées en arrière-plan et agrandissables.
L'association exige un identifiant produit Cardmarket explicite dans la fiche
TCGdex ; un nom ressemblant ne suffit pas. Les références sans correspondance
ou sans image affichent « Illustration indisponible ». Le cache persistant
`/data/cardmarket-images.json` garde les associations pendant sept jours
(nouvelle tentative après une heure en cas d'échec partiel). Les noms d'extension
vérifiés apparaissent progressivement dans le filtre, sinon son numéro est affiché.
Validation : 40 tests Python ciblés, lint PHP/Twig/JS, filtre de budget, tri,
série holo, chargement réel d'image, zoom, réinitialisation et mobile vérifiés.

La page [Bonnes affaires](http://localhost:8080/deals) affiche désormais les prix
réels du catalogue et du guide public Cardmarket : recherche par nom anglais ou
identifiant, prix bas, tendance et moyennes à 1/7/30 jours, avec variante « holo »
séparée. Aucun compte ni abonnement Apify n'est nécessaire pour cette source.

Validation du 20 septembre 2026 : téléchargement HTTP 200 depuis Cardmarket de
74 130 références et 79 193 lignes de guide, jointes par identifiant en
69 803 références avec prix exploitables. Recherche Pikachu : 917 résultats.
Guide daté du 20 septembre à 02:42:36 +02:00. Interface ordinateur/mobile et
pagination vérifiées, conservation après redémarrage du collecteur vérifiée.

Le guide est quotidien : il ne fournit pas les vendeurs, la langue, l'état ni le
port. Ces références ne deviennent donc pas des offres dans le calcul des marges.
Les pages d'offres restent bloquées par Cloudflare lors des tests directs.

Cache persistant : `/data/cardmarket-prices.json`, actualisé à la première lecture
après 24 h ; une panne conserve l'ancien guide avec un statut explicite.
API : `GET /api/deals/cardmarket-prices?q=Pikachu&page=1` (24 résultats par page).
Tests : 43 contrôles Python ciblés, lint PHP/Twig, parcours Playwright réel.
Rapport : `.validation/cardmarket-prices-live.json`.
Source : [publication officielle Cardmarket](https://news.cardmarket.com/en/Magic/were-making-the-price-guide-and-product-catalogue-available-for-download).

## Cardmarket avec AutoScrape

Un lanceur AutoScrape est disponible pour les fiches Cardmarket, avec export
JSON des statistiques et CSV des offres Pokémon pour Bonnes affaires.
Voir [installation, commande et limites](tools/AUTOSCRAPE.md).
Le test réel du 20 septembre 2026 reste bloqué en HTTP 403 ; l'intégration du
parseur est testée, mais l'accès aux données Cardmarket n'est pas validé.

## PokéDeals intégré : bonnes affaires sur les cartes Pokémon

### Session Chrome locale persistante

Lancer `./start-local-browser.ps1`, puis « Ouvrir la session Chrome locale » dans
la page Bonnes affaires. Le service local est déjà démarré pour cette session.
Connectez-vous vous-même à eBay et terminez les vérifications éventuelles dans
les onglets dédiés. Relancez ensuite l'analyse ; le collecteur utilise cette
session en priorité. Ce mode conserve le profil dans `.local-browser/profile`,
séparé de votre profil Chrome habituel et exclu du dépôt. Il ne transmet pas les
cookies ou mots de passe au collecteur : seulement les fragments de fiches/offres.

Après redémarrage de Windows, relancez le script. Dépendances pour une autre
machine : `python -m pip install -r tools/local-browser-requirements.txt`, plus
Chrome installé. Le pont écoute seulement sur `127.0.0.1:8766` ; Docker Desktop
y accède via `host.docker.internal`. Si ce service ne répond plus, l'analyse
signale son indisponibilité sans changer de session. Le mode navigateur Docker
reste disponible lorsque `DEALS_LOCAL_BROWSER_URL` n'est pas configuré.

Validation locale du 20 septembre 2026 : 80 annonces eBay actives transmises au
collecteur via la session locale, dont 71 avec port lisible. Ventes eBay en attente
de connexion utilisateur ; Cardmarket n'affiche pas encore d'offres. La collecte
complète des deux sources n'est donc pas encore validée.

Ouvrir [Bonnes affaires](http://localhost:8080/deals). Le module compare Cardmarket →
eBay et eBay → Cardmarket, avec identité stricte, ventes datées, frais modifiables,
liens justificatifs, scans en arrière-plan, cache persistant et import CSV.

La collecte utilise désormais Chromium via Playwright. Lors du test réel du 19
septembre 2026 : 71 annonces eBay actives extraites, mais ventes terminées eBay
et Cardmarket encore en HTTP 403. Les résultats restent explicitement partiels ;
l'analyse de relevés CSV est disponible. Aucun résultat fictif n'est injecté.

Voir [la documentation du module](scraper/app/deals/README.md) pour le calcul,
les limites de comparaison, le format d'import et les tests.

## Catalogue persistant et découverte hebdomadaire des sets

Le changement de jeu sélectionne une langue présente dans le catalogue si la langue précédente
ne contient aucun set : Gundam passe ainsi de FR à EN (JP reste sélectionnable). La langue choisie
reste visible ; aucune édition française n’est créée à partir d’une édition anglaise.
Les sets sans offres sont affichés par défaut dans le catalogue, et la liste des sets se met à jour
sans rechargement après une synchronisation. Une sélection en cours est conservée.

Le catalogue demeure dans le volume Docker `catalog` et les fiches dans PostgreSQL. Les anciennes
références sont conservées même si elles disparaissent d’une page éditeur. Lors de l’ouverture du
formulaire ou d’une recherche, une vérification de plus de sept jours déclenche une mise à jour
en arrière-plan auprès des sources du catalogue. Les recherches utilisent le cache pendant ce temps.
Une seule tâche de synchronisation est exécutée à la fois. Les nouveaux sets sont envoyés à la base
sans créer de relevés de prix fictifs, puis apparaissent dans le sélecteur ouvert.

L’état et la date sont sauvegardés dans `/data/catalog-refresh.json` et `/data/catalog.json` :
un redémarrage ne remet pas le délai hebdomadaire à zéro. Une panne conserve le cache et laisse
une heure avant une nouvelle tentative déclenchée par une recherche. Si seule la transmission
vers l’application échoue, le catalogue sauvegardé est retransmis sans relire les sources.
Les sources partiellement indisponibles conservent leurs références précédentes.

API locale : `GET /catalog/status`, `POST /catalog/refresh` (vérifie si la mise à jour est due).
`POST /catalog/refresh?force=true` permet une vérification immédiate manuelle. L’interface utilise
`/api/catalog` pour lire les sets de la base et suivre la progression.
Validation : 100 tests Python, 59 contrôles PHP, lint Symfony/Twig et tests navigateur.
Validation réelle après déploiement : 7 références Gundam EN, 8 JP (dont une référence marchande),
15 fiches visibles sans imposer un stock. Une vérification des sources a conservé les 423 entrées
du cache ; les sources Yu-Gi-Oh! restent indisponibles. Après redémarrage du collecteur, le nombre
d’entrées et la date de contrôle sont identiques et aucune nouvelle mise à jour n’est déclenchée
avant l’échéance. Rapports dans `.validation/catalog-weekly-*-restart.json`.

## Correction des recherches vides (19 septembre 2026)

Les moteurs précédemment actifs renvoyaient des CAPTCHA et des limitations de requêtes.
Le moteur local utilise désormais Bing et Yahoo, vérifiés au déploiement. La recherche est
bornée à six appels, deux simultanés, et ne pagine plus les requêtes vides ou répétitives.
Le plafond de 120 liens demeure ; trois pages est une profondeur maximale, pas une exploration
systématique. Une requête courte par code de set évite les noms de catalogue trop restrictifs.

Une réponse HTTP 200 sans résultat et avec des erreurs de moteur est signalée indisponible ;
elle n’est plus conservée comme une recherche vide pendant cinq minutes. La version du cache
a été renouvelée pour ignorer les anciennes réponses. L’application complète les liens web avec
les offres du même set, jeu et langue collectées depuis moins de 48 heures, sans dupliquer les URL.
Ces offres gardent leur date de relevé et leur origine « dernière collecte ». Les coûts avec port
ou import ne sont jamais présentés comme des prix produit hors frais.

Un bouton réinitialise les filtres de source, langue et expédition lorsque des résultats sont masqués.
Validation : 95 tests Python, 54 contrôles PHP, lint Symfony/Twig et parcours navigateur.
Recherche réelle Gundam GD-02 JP : 47 pistes, 25 correspondant au set, 13 prix lus ; affichage
des 47 pistes vérifié dans Chromium. Les moteurs externes restent susceptibles d’indisponibilité.

## Pays d’expédition et frais d’import

Les recherches web et fiches de set affichent désormais le pays de départ annoncé, la zone
UE / hors UE, le statut des frais pour la France métropolitaine et les sources datées.
Un filtre permet de limiter les résultats à la France, à l’UE, au hors UE ou aux origines inconnues.
La langue de la display, la devise, le domaine internet et le siège du vendeur ne prouvent jamais
le pays d’expédition. Le Royaume-Uni et la Suisse sont classés hors UE.

Le collecteur recherche des déclarations explicites sur la page et jusqu’à deux pages de livraison
ou FAQ du même site. Les recherches web partagent ces lectures entre offres d’un même domaine.
Les déclarations contradictoires ou les entrepôts multiples restent à confirmer. Les mentions DDP
destinées aux États-Unis ne sont pas extrapolées à la France.

Sources marchandes examinées le 19 septembre 2026 : [Nippon TCG](https://www.nippontcg.fr/)
annonce un départ de France ; [Japan TCG Direct](https://japantcgdirect.com/policies/shipping-policy)
annonce un départ du Japon et une TVA d’import à la charge du destinataire européen ;
[Japanese-TCG.com](https://japanese-tcg.com/) utilise des stocks japonais et américains, sans
promesse de taxes incluses vérifiée pour la France. Ces annotations expirent après 90 jours
dans le collecteur ; les offres enregistrées montrent la date de leur source.

Le calcul ne déduit plus l’origine du siège de la boutique. La TVA française de 20 % n’est estimée
que lorsque la source indique qu’elle reste due à l’import ; les droits et frais transporteur non
connus restent non chiffrés. Le forfait automatique de 3 € a été supprimé : il ne s’applique pas
indistinctement à tous les envois. Un changement d’origine ou de traitement fiscal ne crée pas
une fausse alerte de baisse. Les anciennes offres sont conservées et indiquées sans origine
confirmée jusqu’à une nouvelle collecte. Les recherches restent classées hors frais d’import.
Référence : [Douane française — achats sur internet](https://www.douane.gouv.fr/demarche/vous-achetez-sur-internet).

Migration : `php bin/console doctrine:migrations:migrate --no-interaction`.
Validation : 93 tests Python, 49 contrôles d’intégration PHP, lint Twig/conteneur et parcours
navigateur des filtres d’origine et liens de source, sur ordinateur et mobile.
Déploiement local effectué avec migration PostgreSQL. Collecte réelle persistée : 44 offres
Nippon TCG (France / UE) et 32 Japan TCG Direct (Japon / TVA d’import à prévoir).
Fiches réelles vérifiées dans Chromium ; rapport dans `.validation/origin-live.json`.

## Collecte élargie (19 septembre 2026)

La recherche explore désormais trois pages par requête, ajoute des variantes par code de set
et conserve jusqu'à 120 liens (six par domaine). Ce sont des plafonds, pas un nombre garanti
d'offres disponibles. Les prix sont lus avec 12 tâches concurrentes, dont deux maximum par domaine.
Le délai global de lecture des prix est de 42 secondes ; certaines pistes peuvent rester sans prix.

Le collecteur utilise Playwright/Chromium sur les pages JavaScript sans données exploitables,
avec dix rendus maximum par boutique. Les appels passent par le client HTTP soumis à robots.txt
et au budget de requêtes. Les ressources hors domaine ne sont pas chargées ; les boutiques qui
dépendent d'un CDN externe peuvent donc rester incomplètes. Aucun CAPTCHA n'est contourné.
Le navigateur est déjà inclus dans l'image Docker. Sans Chromium local, la collecte HTTP continue
et les erreurs de rendu sont comptabilisées dans `/status`.

Autres extensions : sitemaps déclarés dans robots.txt et compressés en gzip, produits imbriqués
dans les listes JSON-LD, grilles WooCommerce au-delà de Ludotrotter, variantes Shopify conservées
avec arrêt sur page répétée, et une nouvelle tentative bornée sur erreur HTTP temporaire.
Le budget par défaut de `/crawl` et du planificateur passe à 1 000 requêtes par boutique.

Réglages Docker : `DISCOVERY_PAGES` (1–5, défaut 3), `DISCOVERY_MAX_RESULTS` (30–200, défaut 120),
`BROWSER_MAX_PAGES` (0–50, défaut 10 ; 0 désactive Chromium).

```sh
docker compose --profile discovery up --build -d
curl -X POST 'http://localhost:8001/crawl?max_pages=1000&persist=true'
```

Validation reproductible : `scraper/tests/test_expanded_scraping.py` et
`scraper/validate_expanded.py` (test Chromium puis collecte réelle sur trois boutiques).
Le rapport réel est enregistré dans `scraper/expanded-live.json`.
Validation du 19 septembre : 75 tests Python réussis et rendu Chromium vérifié sur un produit
injecté par JavaScript. Collecte réelle avec un budget de 60 requêtes par boutique : UltraJeux
33 offres, Japan TCG Direct 32, Ludotrotter 10, soit 75 offres (indisponibles incluses).
UltraJeux et Ludotrotter atteignent ce budget ; ce relevé ne mesure pas une collecte à 1 000 requêtes
ni un gain comparatif avec l'ancienne version. L'image Docker du collecteur a été reconstruite.
Les chiffres et limites ci-dessous décrivent les validations antérieures.

## Recherche de nouvelles boutiques

Activer le moteur de recherche avec `docker compose --profile discovery up --build -d`.
Depuis l’accueil, choisissez un jeu, une langue, puis un set dans la liste nom + code. Les choix sont filtrés
par jeu et langue ; les sets avec des offres récentes passent en premier. Un lien ouvre les offres déjà collectées,
et le bouton de recherche explore les disponibilités sur le web. Les références sans offre restent sélectionnables :
leur présence dans le catalogue ne garantit pas un stock marchand. L’option « Mon set n’est pas dans la liste »
conserve la saisie libre. Le catalogue local a été alimenté avec 423 références le 18 septembre 2026
(Pokémon, One Piece et Gundam ; sources Yu-Gi-Oh! indisponibles). Les collectes resynchronisent le catalogue.
Sur une fiche de set, « Trouver d’autres boutiques » reprend l’identité du produit.
Les résultats ne sont pas limités aux boutiques configurées. Jusqu’à 30 fiches sont lues, avec trois liens au maximum
par domaine. Les prix explicites des fiches produit sont affichés directement, jamais déduits des extraits du moteur.
Les offres avec set, langue, quantité et stock confirmés dans les données de la fiche sont triées par prix croissant
en euros par display, hors livraison et frais d’import. Les cases affichent aussi leur quantité et leur prix total.
Les autres devises sont converties à titre indicatif (taux de repli si le fournisseur est indisponible).
Les prix incomplets, stocks non confirmés et fiches inaccessibles restent en fin de liste. Les variantes ambiguës
et prix agrégés sans prix de produit ne servent pas au classement. Les prix sont mis en cache cinq minutes.
Les langues explicitement incompatibles sont masquées par défaut et peuvent être réaffichées. Les langues inconnues
restent visibles. Un second filtre permet de n’afficher que les nouvelles sources. Les badges sont des indices,
pas des confirmations de langue, de stock ou de fiabilité. Des liens Google et DuckDuckGo servent de repli.
Les relevés de recherche ne sont pas importés dans l’historique et les boutiques ne sont pas ajoutées automatiquement
au collecteur. La lecture respecte robots.txt, borne les délais et la taille des pages, et refuse les adresses réseau
privées ainsi que les redirections hors domaine ; les connexions utilisent une adresse publique résolue et fixée.
La recherche peut renvoyer une autre langue ou un autre produit ; elle ne garantit pas une couverture exhaustive.
L’accueil corrige également les caractères abîmés et propose une recherche du catalogue sans distinction d’accents,
avec un bouton pour réinitialiser les filtres en cas de résultat vide.

Validation des améliorations : 69 tests Python, 40 contrôles d’intégration PHP, lint Twig et conteneur Symfony,
parcours navigateur des recherches et filtres sur ordinateur et mobile. Recherche réelle via `/api/discover` :
30 pistes sur OP-09 FR, avec sept prix lus en environ onze secondes et un statut partiel signalant des moteurs
indisponibles. Aucun de ces sept prix ne confirmait à la fois la langue FR et un stock disponible lors de ce test.
Sur OP-09 JP, un second essai a lu 14 prix, dont cinq offres comparables triées en ordre croissant.

Validation Docker du 18 septembre 2026 : services démarrés, trois migrations PostgreSQL exécutées,
accueil HTTP 200 et collecteur sain après correction des droits du cache Symfony.
Les 17 tests de découverte passent. Une recherche One Piece OP-08 a renvoyé 30 pistes sur 29 domaines
absents de la configuration ; certains moteurs étaient indisponibles (réponse partielle).
La validation stricte du schéma Doctrine signale encore des différences d’index, de valeurs par défaut
et de génération des identifiants entre les migrations et le mapping ; aucune synchronisation destructive n’a été appliquée.

Comparateur de produits scell?s Pok?mon, One Piece, Yu-Gi-Oh! et Gundam, avec catalogue, comparaison par display et suivi des prix en euros.

## D?marrage

```sh
docker compose up --build -d
docker compose exec app php bin/console doctrine:migrations:migrate --no-interaction
```

Application : http://localhost:8080 ? collecteur local : http://localhost:8001.

```sh
curl -X POST 'http://localhost:8001/crawl?max_pages=250&persist=true'
```

Pour cibler une boutique : `POST /crawl?stores=UltraJeux&max_pages=35&persist=true`. Plusieurs noms s?par?s par des virgules sont accept?s. `GET /stores` liste les noms exacts, `GET /status` donne le rapport de la derni?re collecte r?ussie et `GET /catalog` expose le cache du catalogue. Une seule collecte peut tourner ? la fois (409 sinon).

Apr?s les migrations, activer les collectes automatiques toutes les six heures :

```sh
docker compose --profile automation up -d scheduler
```

Configurer `CRAWL_INTERVAL_SECONDS` et `CRAWL_MAX_PAGES` dans le service scheduler pour modifier la fr?quence et le budget. Les graphiques se constituent au fil des collectes : aucun historique r?troactif n'est fabriqu?.

## Fonctionnalit?s V5

- Catalogue synchronis? avant la collecte, conserv? dans le volume `catalog`. Les r?f?rences sans offre sont consultables en d?cochant ? Avec offres ?.
- Correspondance des codes et noms, aliases fran?ais Pok?mon EV/EB, provenance du catalogue et s?paration stricte des ?ditions/langues. Les correspondances ambigu?s restent marchandes. Un set inconnu re?oit une identit? propre ? l'offre, au lieu de regrouper tous les produits sous UNKNOWN.
- Page `/sets/{id}` : toutes les boutiques, stock, date de v?rification, prix dans la devise d'origine, port, total estim? et prix par display.
- Cases : quantit? explicite seulement, frais appliqu?s une fois au panier puis total divis? par le nombre de displays. Une case de quantit? inconnue reste visible mais n'entre pas dans la comparaison unitaire.
- Graphiques 7 / 30 / 90 jours : minimum quotidien observ?, s?ries s?par?es pour port connu et inconnu, valeurs accessibles en tableau et absence de liaison sur les jours manquants.
- Baisses persist?es en base ? chaque collecte, sans ?v?nement pour un prix inchang?, une quantit? modifi?e ou un changement de statut du port. Consultation par le bouton ? Baisses de prix ? et `/api/alerts`.
- Prix cible enregistr? dans le navigateur sur une page de set ; v?rification toutes les minutes pendant que cette page reste ouverte. Pas d'envoi d'email, SMS ou notification lorsque le navigateur est ferm?.
- Les offres de plus de 48 h ne participent plus au meilleur prix ni aux seuils ; elles restent consultables sur la page du set.

## Catalogue : couverture et sources

- Pok?mon FR / JP : [TCGdex](https://tcgdex.dev/rest/sets), source communautaire, pas un catalogue officiel Pok?mon. Cache conserv? en cas d'indisponibilit?.
- One Piece FR / JP : catalogues ?diteur [fran?ais](https://fr.onepiece-cardgame.com/products/?page=1&subcategory=boosters) et [japonais](https://www.onepiece-cardgame.com/products/?page=1&subcategory=boosters), avec pagination born?e.
- Gundam JP / EN : catalogues ?diteur [japonais](https://www.gundam-gcg.com/jp/products/list.php) et [anglais](https://www.gundam-gcg.com/en/products/list.php). Aucune ?dition FR n'est d?duite du catalogue anglais.
- Yu-Gi-Oh! FR / JP : synchroniseurs pr?vus sur les pages ?diteur. Lors de la validation du 17 septembre 2026, la lecture de `robots.txt` ?tait indisponible : ces sources sont signal?es en erreur et ne sont pas contourn?es. Les offres marchandes restent collectables, avec identit? provisoire si le set n'est pas rapproch?.

La couverture n'est pas exhaustive : les ?diteurs peuvent limiter les archives disponibles. Une r?f?rence de set n'implique pas qu'un display commercial existe.

## Connecteurs et r?sultats mesur?s

Parcours d?di?s : UltraJeux, Ludotrotter, DestockTCG, Play-in, Nippon TCG et Japan TCG Direct. Extraction WooCommerce pour Ludotrotter, microdonn?es sur les fiches UltraJeux, JSON-LD, m?tadonn?es produit et variantes Shopify. Les autres boutiques configur?es utilisent le parcours structur? avec sitemap et cat?gories.

Validation r?seau du 17 septembre 2026, budget de 35 pages par boutique :

| Boutique | Offres r?cup?r?es |
| --- | ---: |
| Nippon TCG | 33 |
| Ludotrotter | 27 |
| Japan TCG Direct | 31 |
| DestockTCG | 11 |
| UltraJeux | 8 |
| Play-in | 23 |
| **Total** | **133** |

Ces chiffres incluent les offres indisponibles et les variantes ; ils ne sont ni un nombre de sets uniques, ni une garantie de disponibilit? future. Ce contr?le ne constitue pas un benchmark comparatif V4/V5. Reproduction : `cd scraper && python smoke_v5.py`. Le rapport complet est ?crit dans `scraper/live-validation.json`.

Le crawler respecte les chemins interdits par robots.txt, refuse les redirections hors domaine et borne la d?couverte et les pages. Il ne contourne pas les protections anti-bot. Les prix agr?g?s `lowPrice` et les stocks non confirm?s ne sont pas assimil?s ? une offre achetable en stock.

## Frais de port

Les frais d?clar?s dans `Offer.shippingDetails` sont import?s uniquement pour une destination FR et une devise EUR. Une r?gle de configuration par boutique peut les remplacer. Les frais inconnus restent explicitement affich?s hors estimation ; ils ne deviennent jamais une livraison gratuite implicite.

Exemple **fictif**, ? adapter aux tarifs v?rifi?s du marchand, dans le `.env` ? la racine :

```dotenv
SHIPPING_RULES_JSON='{"Nom exact de boutique":{"destination":"FR","flat_eur":5.90,"free_above_eur":150}}'
```

Recr?er le collecteur apr?s modification : `docker compose up -d scraper`. Les tarifs connus sont appliqu?s par offre/panier, pas par display. Les r?gles ne couvrent pas les surcharges de poids, zones particuli?res ou paniers mixtes. Le calcul d'import existant (TVA estim?e, forfait de droit, frais ?ventuels) demeure une estimation ; v?rifiez le montant final chez le marchand. Les taux de change disposent d'un repli configur?, et les devises non prises en charge sont exclues au lieu d'?tre trait?es comme des euros.

## Migration depuis V4

La migration `Version20260918000000` ajoute les quantit?s, co?ts unitaires, provenance et ?v?nements de baisse, en conservant les anciennes donn?es. Les anciens relev?s ne sont pas r?troactivement divis?s par une quantit? suppos?e : ils n'entrent dans les graphiques V5 qu'apr?s de nouvelles collectes comparables. Les r?f?rences historiques devenues vides restent conserv?es.

Le d?marrage Symfony est compl?t? (bundles, services, console, YAML, strat?gie de noms Doctrine). Docker utilise un unique bloc d'environnement pour le collecteur et une URL HTTP d'ingestion vers nginx, plut?t que le port FastCGI du service PHP. Composer est verrouill? pour PHP 8.3.

D?finir `APP_SECRET` et `INGEST_TOKEN` dans le `.env` racine avant une exposition publique ; le m?me token est transmis aux deux services. Le collecteur est li? ? localhost par d?faut.

## V?rifications

```sh
cd scraper
python -m pytest -q
cd ../app
php bin/console lint:twig templates
php bin/console lint:container
php bin/console doctrine:schema:validate --skip-sync
php tests/integration.php
```

Le test d'int?gration utilise une base SQLite isol?e et ?mule seulement le verrou PostgreSQL. Il v?rifie ingestion, d?duplication, cases, historique, ?v?nements, rendu et erreurs HTTP ; il ne remplace pas l'ex?cution des migrations PostgreSQL.

Pour les tests navigateur : exporter les pages avec `EXPORT_PREVIEW=1 php tests/integration.php`, puis lancer `python tests/ui_smoke.py` depuis la racine (Playwright/Chromium requis). Les captures g?n?r?es utilisent des donn?es de contr?le.

Validation locale : tests Python, contr?les Symfony/Doctrine, test d'int?gration et parcours navigateur ex?cut?s. Le moteur Docker n'?tait pas d?marr? sur cette machine : la migration PostgreSQL et le lancement de la stack compl?te restent ? ex?cuter dans l'environnement Docker.
