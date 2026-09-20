# PokéDeals dans TCG Radar

## Session locale (20 septembre 2026)

`tools/local_deals_browser.py` lance un pont sur `127.0.0.1:8766`. Le collecteur
le contacte via `DEALS_LOCAL_BROWSER_URL`, et réutilise le profil Chrome dédié
de Scrapling après la connexion ou vérification effectuée par l'utilisateur.
Le bouton de préparation est intégré dans `/deals`. Il ne réutilise pas le profil
Chrome personnel ; le répertoire `.local-browser` reste privé et exclu du dépôt.
Le pont ne renvoie ni cookies ni formulaires/scripts de compte ; seulement les
éléments des fiches et résultats. Quand `DEALS_LOCAL_BROWSER_URL` est configuré,
un pont indisponible arrête la lecture avec un message explicite : aucun repli
vers une autre session. Sans cette configuration, Playwright Docker reste utilisé.
Le statut des onglets est borné à 0,5 seconde par onglet pour qu'une page bloquée
ne rende pas le service indisponible. La préparation préserve les onglets de
connexion et de vérification, même lors d'un nouveau clic sur le bouton.
Les pages demandant une connexion restent ouvertes et ne sont pas écrasées par
une nouvelle recherche. Le résultat live validé est 80 annonces actives, pas encore
un accès réussi aux ventes terminées et offres Cardmarket.

Le moteur bidirectionnel, les filtres langue/état et les extracteurs eBay/Cardmarket
de `pokedeals-v2` sont portés dans le collecteur existant. L'ancien dossier reste
disponible comme source ; il n'est pas nécessaire de lancer son serveur React/FastAPI.
La nouvelle interface Symfony est accessible à `/deals` depuis TCG Radar.

## Différences nécessaires par rapport à v2

- V2 regroupait approximativement les noms et fusionnait Mint/NM et EX/Good.
  Ici : nom normalisé, numéro complet, code d'extension s'il est indiqué,
  variante, langue et état exact. Aucune langue déduite de `ebay.fr`.
  Les cartes gradées, lots, variantes inconnues et identités incomplètes sont exclues.
  Une correspondance stricte privilégie la précision ; des intitulés différents
  peuvent nécessiter une normalisation manuelle dans le CSV.
- V2 considérait tout résultat d'une recherche « vendu » comme vendu.
  Ici : preuve de vente et date dans chaque ligne. Les annonces sponsorisées actives,
  les fourchettes et les meilleurs prix négociés inconnus sont exclus.
- CM → eBay : médiane des ventes récentes, au moins trois par défaut, dédupliquées
  par identifiant eBay. Les frais de port ne gonflent pas le prix de référence.
- eBay → CM : minimum des offres concurrentes disponibles ; c'est un prix demandé,
  pas une preuve de vente. Aucun taux de rotation ni prix de vente CM n'est inventé.
- Marge = prix de revente avec décote de sécurité − achat − port d'achat −
  commission − frais fixes − port de revente − emballage − autres coûts.
  Rendement = marge / (achat + port d'achat + autres coûts).
  Les taux par défaut sont des hypothèses éditables, pas des barèmes contractuels.
  Estimation avant impôts ; importer les frais éventuels dans « autres coûts ».
- EUR seulement : aucune conversion sur un taux de secours non daté.
- Offres actives de moins de 24 h, ventes dans la fenêtre choisie (90 jours par défaut).

## Collecte et persistance

POST `/deals/search` lance un job non bloquant. GET `/deals/status/{id}` expose
son avancement et les sources réellement accessibles. Symfony relaie ces routes
sous `/api/deals`. Le budget est borné par les pages, fiches et 180 secondes.
Une seule analyse réseau à la fois. Les pages publiques utilisent maintenant
Chromium via Playwright, avec une session dédiée à l'analyse. Les erreurs sont
isolées par source : un refus sur eBay vendu ne désactive pas eBay actif.
Les navigations sont limitées aux recherches et produits des deux plateformes.
Le JavaScript normal du site s'exécute ; aucun CAPTCHA n'est résolu automatiquement,
aucun compte personnel n'est utilisé et aucune action d'achat n'est effectuée.

Les résultats et paramètres sont persistés dans `DEALS_CACHE=/data/deals.sqlite`
sur le volume Docker existant. Cache 3 h pour un résultat complet, délai de 60 s
avant une nouvelle tentative après échec (actualisation manuelle possible).
Un échec conserve le dernier résultat du même scénario, explicitement ancien.
Les jobs sont conservés 30 jours. Le navigateur retrouve sa dernière analyse.

## Import lorsque les sources refusent la collecte

`/deals-template.csv` fournit les colonnes. POST `/deals/import` reçoit
`{"settings": {...}, "csv": "..."}`. Maximum 2 Mo / 2 000 lignes.
Ce format est un format d'échange interne, pas un import automatique des fichiers
natifs eBay ou Cardmarket. Les lignes sont validées avant toute écriture.

Renseigner source, titre, lien HTTPS, prix et date de relevé ; préciser numéro,
variante, langue, état et extension pour une comparaison. Les ventes exigent
`sold=true` et `sold_at`. Prix hors port, dates ISO avec fuseau, décimales avec point
(virgule acceptée si correctement délimitée). `price_exact=false` pour un montant
négocié inconnu. Les imports n'ont jamais la provenance « scraped ».

## Vérification de l'accès, 19 septembre 2026

Après passage à Playwright, le test dans le conteneur a extrait 71 annonces eBay
actives pour la recherche de contrôle. Les ventes terminées eBay et Cardmarket
restent en HTTP 403, même avec le navigateur. Le parcours live affiche donc un
résultat partiel, sans opportunité prouvée. Aucun deal de démonstration n'est injecté
dans les résultats de production.

Contre-vérification locale : Selenium avec Chrome 151 charge des annonces actives
eBay mais ne débloque ni les ventes terminées ni Cardmarket. Le moteur Scrapling
du PokéDeals original redirige les ventes eBay vers `signin.ebay.fr` et reçoit une
vérification Cloudflare (HTTP 403) sur Cardmarket. Les statuts `login_required` et
`verification_required` distinguent désormais ces pages d'un résultat vide. Le
bouton de chaque source permet d'ouvrir sa recherche dans le navigateur de
l'utilisateur ; il ne transfère pas sa session vers Docker et ne déverrouille pas
automatiquement la collecte du serveur.

L'API eBay Marketplace Insights est à accès restreint :
https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html
Le Price Guide officiel CM est agrégé, et ne remplace pas les offres par vendeur,
langue et état :
https://news.cardmarket.com/en/Magic/were-making-the-price-guide-and-product-catalogue-available-for-download

## Tests

`python -m pytest -q` dans `scraper` ; `php tests/integration.php` dans `app`.
Pour l'UI, exporter avec `EXPORT_PREVIEW=1`, puis `python tests/deals_ui_smoke.py`.
Les jeux de données de contrôle restent isolés de la production.
