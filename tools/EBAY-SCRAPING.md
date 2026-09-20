# eBay sans clé API

Si l'inscription ou la connexion tourne en boucle dans la fenêtre automatisée :
fermer cette fenêtre dédiée, lancer `./open-ebay-manual.ps1`, puis effectuer
l'inscription ou la connexion soi-même. Ce script ouvre Chrome directement,
sans Scrapling ni pilotage automatique, avec le même profil dédié. Ne pas lancer
d'analyse pendant cette étape. Fermer ce Chrome manuel avant de rouvrir la
session locale dans l'application : les cookies restent dans le même profil.
Le script ne ferme pas les navigateurs et ne touche pas au profil personnel.
Une vérification eBay peut néanmoins persister ; ce mode ne garantit pas l'accès.

Le collecteur utilise Chrome local avec un profil dédié persistant, piloté par
Scrapling. BeautifulSoup extrait titres, prix, port, dates de vente, identifiants
d'annonces et noms de vendeurs lorsqu'ils sont présents. Aucun fournisseur à clé
API n'est activé par le parcours, même avec une ancienne configuration ScrapingBee.

1. Lancer `./start-local-browser.ps1`.
2. Ouvrir http://localhost:8080/deals puis « Ouvrir la session Chrome locale ».
3. Si eBay demande une connexion pour les ventes terminées, se connecter soi-même
   dans cette fenêtre. Ne pas fournir les identifiants à l'assistant.
4. Lancer l'analyse avec « Actualiser les données en cache ».

Les résultats contiennent une section « Annonces et ventes collectées », qui
permet de consulter les observations même si elles n'ont pas une identité assez
précise pour comparer les marges. Les prix négociés masqués ne servent pas de
référence. Une annonce active ne prouve jamais une vente réalisée.

Chaque lecture recharge la recherche (hors écran de connexion/vérification),
vérifie que les filtres demandés ont été conservés et ne transmet que des fragments
de résultats. Les cookies et les mots de passe restent dans Chrome local.
Les volumes sont bornés par les pages demandées et trois minutes par analyse.
Deux mille observations maximum sont conservées dans l'aperçu d'une analyse.

Validation locale du 20 septembre 2026 : 78 annonces actives Pikachu extraites,
72 avec port lisible. Les ventes terminées renvoient `login_required` et ne sont
pas encore validées après connexion. Rapport : `.validation/ebay-local-live.json`.
Le test complet après déploiement conserve 68 annonces actives dans l'application
et valide leur affichage, le filtre et le mobile (`.validation/ebay-app-live.json`).

Les anciennes classes de transport ScrapingBee restent isolées dans le dépôt
pour historique, sans être appelées par le collecteur.
