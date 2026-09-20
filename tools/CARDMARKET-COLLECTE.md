# Collecte progressive Cardmarket

Le compte doit être connecté dans la fenêtre du collecteur. Une connexion dans
une autre fenêtre peut ne pas être reprise. Ne pas lancer d'analyse dans
l'application pendant cette collecte, car elle utilise le même navigateur.

```powershell
python tools/cardmarket_crawl.py --query "Pikachu" --max-requests 100
```

Un seul processus de collecte peut fonctionner. Les lectures commencent à
20–35 secondes d'intervalle au minimum, sans requêtes en parallèle. Le programme
s'arrête au premier refus, à une demande de connexion ou à une vérification,
et conserve un délai de reprise de 30 minutes. Aucun délai ne garantit l'absence
de restriction du compte. Le programme ne résout pas les vérifications et
ne modifie ni le panier ni les commandes.

La file d'attente, les offres, les pages lues et les délais sont sauvegardés dans
`.local-browser/cardmarket-crawl.sqlite`. La même commande reprend les pages
restantes. `Ctrl+C` arrête la collecte. La limite de 100 requêtes par lancement
est un budget de session, pas une limite du nombre total de pages conservées.

```powershell
python tools/cardmarket_crawl.py --query "Pikachu" --status
python tools/cardmarket_crawl.py --query "Pikachu" --export .local-browser/cardmarket-offres.csv
```

Le mode `--scope pokemon --db .local-browser/cardmarket-pokemon.sqlite` part du
catalogue Pokémon. Il ne faut pas annoncer un catalogue complet tant que les
compteurs de pagination non confirmée ou de pages restantes sont non nuls.
Les liens de pagination doivent être visibles dans les fragments du navigateur.
Avec un ancien service local, une page produit pleine autorise une lecture lente
de la page suivante ; une page répétée arrête cette branche et laisse sa
couverture non confirmée. La découverte du catalogue n'est jamais déduite du
seul nombre d'offres d'une fiche.
Une page de recherche avec au moins 30 fiches nouvelles permet également de
sonder la page suivante au même rythme. Cette pagination déduite reste marquée
comme non confirmée tant que les liens explicites sont absents.

Les prix et langues sont ceux des offres. Un délai d'expédition n'est pas un coût
de livraison. Le port reste inconnu si aucun prix de port n'est visible. Les
relevés accumulés à des dates différentes ne constituent pas un instantané des
stocks actuels et doivent être actualisés avant une décision d'achat.
