# Store registry. `catalog_verified` means the shop/catalog was manually checked during
# the 2026-09-17 expansion pass. Generic crawling can still fail on JS/anti-bot sites.
STORES = [
# France / EU-facing shops
{"name":"Nippon TCG","url":"https://www.nippontcg.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Deck & Tresor","url":"https://deck-tresortcg.fr","country":"FR","currency":"EUR"},
{"name":"Kyseii","url":"https://kyseii.fr","country":"FR","currency":"EUR"},
{"name":"Arakemon","url":"https://www.arakemon.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Poke-Geek","url":"https://www.poke-geek.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Shop TCG","url":"https://shop-tcg.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"CardWave","url":"https://cardwave.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Asakusa Store","url":"https://asakusa-tcg.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Irahim TCG","url":"https://irahim.tcgshop.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Mystic-Ambre","url":"https://www.mystic-ambre.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Ludotrotter","url":"https://ludotrotter.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Uturi Trading","url":"https://uturitrading.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Returners","url":"https://returners.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Meka Neko","url":"https://mekaneko.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Hikaru Distribution","url":"https://hikarudistribution.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Tresor Geek","url":"https://tresor-geek.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Zone Gunpla","url":"https://www.zonegunpla.com","country":"FR","currency":"EUR","catalog_verified":True},

# Japan / international Japanese TCG specialists
{"name":"Japan TCG Direct","url":"https://japantcgdirect.com","country":"JP","currency":"USD","catalog_verified":True},
{"name":"Pokeca TCG Warehouse","url":"https://pokecatcgwarehouse.com","country":"JP","currency":"USD","catalog_verified":True},
{"name":"Osaka Trading Card Hub","url":"https://oth.jp","country":"JP","currency":"JPY"},
{"name":"Samurai Sword Tokyo","url":"https://samuraiswordtokyo.com","country":"JP","currency":"USD"},
{"name":"Meccha Japan","url":"https://www.mecchajapanstores.com","country":"JP","currency":"USD","catalog_verified":True},
{"name":"Rare Cards Japan","url":"https://rarecardsjapan.com","country":"JP","currency":"USD","catalog_verified":True},
{"name":"Tempurachan","url":"https://www.tempurachan.com","country":"JP","currency":"JPY","catalog_verified":True},
{"name":"Zenpan Japan","url":"https://zenpan-japan.com","country":"JP","currency":"USD","catalog_verified":True},
{"name":"PulloraX","url":"https://pullorax.com","country":"JP","currency":"USD","catalog_verified":True},

# International distributors with Japanese sealed catalogues (landed cost must include origin)
{"name":"Japanese-TCG.com","url":"https://japanese-tcg.com","country":"US","currency":"USD","catalog_verified":True},
{"name":"DestockTCG","url":"https://www.destocktcg.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"La Cabane de Yugi","url":"https://www.lacabanedeyugi.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"L Antre de Po","url":"https://lantredepo.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Black Rocket","url":"https://www.black-rocket.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Le Crescendo TCG","url":"https://lecrescendotcg.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"TCG Direct","url":"https://www.tcgdirect.fr","country":"FR","currency":"EUR","catalog_verified":True},

{"name":"UltraJeux","url":"https://www.ultrajeux.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"MEiSiA","url":"https://shop.cafemeisia.com","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"PokeFlip","url":"https://pokeflip.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Cyber Sell TCG","url":"https://www.cyberselltcg.fr","country":"FR","currency":"EUR","catalog_verified":True},
{"name":"Ecardstore","url":"https://ecardstore.fr","country":"FR","currency":"EUR","catalog_verified":True},

]
STORES.append({"name":"Play-in","url":"https://www.play-in.com","country":"FR","currency":"EUR"})
