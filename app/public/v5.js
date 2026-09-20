'use strict';
const $ = (s) => document.querySelector(s);
const money = (n) => new Intl.NumberFormat('fr-FR', {style:'currency',currency:'EUR'}).format(n);
async function getJSON(url) {
    const response = await fetch(url, {signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('Données temporairement indisponibles');
    return response.json();
}
function node(tag, text, parent) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (parent) parent.append(element);
    return element;
}
if ($('#grid')) {
    const cards = [...document.querySelectorAll('.card')];
    const normalize = text => text.toLocaleLowerCase('fr').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
    const filter = () => {
        let count = 0;
        const words = normalize($('#q').value).split(' ').filter(Boolean);
        for (const card of cards) {
            const show = words.every(word => normalize(card.dataset.text).includes(word)) && (!$('#game').value || card.dataset.game === $('#game').value)
                && (!$('#lang').value || card.dataset.lang === $('#lang').value) && (!$('#available').checked || +card.dataset.offers > 0);
            card.classList.toggle('hidden', !show);
            count += Number(show);
        }
        const sort = $('#sort').value;
        cards.sort((a,b) => sort === 'name' ? a.dataset.name.localeCompare(b.dataset.name) : sort === 'offers' ? b.dataset.offers-a.dataset.offers : a.dataset.price-b.dataset.price);
        $('#grid').append(...cards);
        $('#visible').textContent = `${count} set${count > 1 ? 's' : ''}`;
        $('#no-results').classList.toggle('hidden', count !== 0 || cards.length === 0);
    };
    ['q','game','lang','sort','available'].forEach(id => $('#'+id).addEventListener(id === 'q' ? 'input' : 'change', filter));
    $('#game').addEventListener('change',()=>{
        const matches=cards.filter(card=>!$('#game').value || card.dataset.game===$('#game').value);
        if ($('#lang').value && !matches.some(card=>card.dataset.lang===$('#lang').value)) $('#lang').value='';
        filter();
    });
    $('#reset-filters')?.addEventListener('click',()=>{
        ['q','game','lang'].forEach(id=>$('#'+id).value='');
        $('#available').checked=false; $('#sort').value='price'; filter(); $('#q').focus();
    });
    filter();
}
let requestNumber = 0;
async function drawHistory(days) {
    const request = ++requestNumber;
    const chart = $('#chart');
    chart.textContent = 'Chargement…';
    $('#chart-values').replaceChildren();
    document.querySelectorAll('[data-days]').forEach(button => button.setAttribute('aria-pressed', String(+button.dataset.days === days)));
    try {
        const {points} = await getJSON(`/api/sets/${$('#history').dataset.product}/history?days=${days}`);
        if (request !== requestNumber) return;
        if (!points.length) { chart.textContent = 'Aucun relevé comparable sur cette période. Les courbes se construiront au fil des collectes.'; return; }
        chart.replaceChildren();
        const ns = 'http://www.w3.org/2000/svg';
        const width = Math.max(300,chart.clientWidth);
        const svg = document.createElementNS(ns,'svg');
        svg.setAttribute('viewBox',`0 0 ${width} 280`); svg.setAttribute('role','img');
        svg.setAttribute('aria-label',`Prix minimal observé par display sur ${days} jours`);
        chart.append(svg);
        const shape = (tag, attrs, text) => {
            const element = document.createElementNS(ns,tag);
            Object.entries(attrs).forEach(([k,v])=>element.setAttribute(k,String(v)));
            if (text !== undefined) element.textContent=text;
            svg.append(element); return element;
        };
        const values = points.map(p=>p.price), low = Math.min(...values)*.95, high = Math.max(...values)*1.05;
        const today = new Date(); today.setUTCHours(0,0,0,0);
        const start = today.getTime()-(days-1)*86400000;
        const x = day => 65+(Date.parse(day+'T00:00:00Z')-start)/((days-1)*86400000)*(width-100);
        const y = price => 235-(price-low)/(high-low || 1)*205;
        for (let i=0;i<4;i++) {
            const value = low+(high-low)*i/3;
            shape('line',{x1:65,x2:width-30,y1:y(value),y2:y(value),stroke:'#293345'});
            shape('text',{x:4,y:y(value)+4,fill:'#9aaabe','font-size':11},money(value));
        }
        for (const known of [true,false]) {
            const series = points.filter(p=>p.shippingKnown === known);
            const color = known ? '#8cf5c4' : '#ffbc7d';
            let previous = null;
            series.forEach(point => {
                // Connect consecutive days only; missing days stay visibly empty.
                if (previous && Date.parse(point.day)-Date.parse(previous.day) === 86400000) shape('line',{x1:x(previous.day),y1:y(previous.price),x2:x(point.day),y2:y(point.price),stroke:color,'stroke-width':2});
                const circle = shape('circle',{cx:x(point.day),cy:y(point.price),r:4,fill:color});
                const title = document.createElementNS(ns,'title'); title.textContent=`${point.day} : ${money(point.price)} · port ${known?'connu':'inconnu'}`;circle.append(title);
                previous=point;
            });
        }
        shape('text',{x:65,y:270,fill:'#9aaabe','font-size':11},new Date(start).toLocaleDateString('fr-FR'));
        shape('text',{x:width-35,y:270,fill:'#9aaabe','font-size':11,'text-anchor':'end'},today.toLocaleDateString('fr-FR'));
        const table=node('table',undefined,$('#chart-values'));
        const head=node('tr',undefined,node('thead',undefined,table));
        ['Date','Par display','Port'].forEach(label=>node('th',label,head));
        const body=node('tbody',undefined,table);
        for (const point of points) {const row=node('tr',undefined,body);[point.day,money(point.price),point.shippingKnown?'Connu':'Inconnu'].forEach(value=>node('td',value,row));}
    } catch (error) { if (request === requestNumber) chart.textContent=error.message; }
}
if ($('#history')) {
    document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>drawHistory(+button.dataset.days)));
    drawHistory(30);
    let resizeTimer;
    window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>drawHistory(Number(document.querySelector('[data-days][aria-pressed=true]').dataset.days)),200);});
}
const dialog=$('#alerts');
$('#show-alerts').addEventListener('click',()=>dialog.showModal());
$('#close-alerts').addEventListener('click',()=>dialog.close());
async function updateAlerts() {
    try {
        const alerts=await getJSON('/api/alerts');
        $('#alert-count').textContent=String(alerts.length);
        const list=$('#alert-list');list.replaceChildren();
        if (!alerts.length) list.textContent='Aucune baisse observée pour le moment.';
        alerts.forEach(alert=>{
            const link=node('a',undefined,list);link.href='/sets/'+Number(alert.product_id);link.className='alert';
            node('strong',`${alert.set_name} · ${alert.language}`,link);
            node('div',`${alert.store} · ${money(alert.previous_cost)} → ${money(alert.new_cost)} (−${alert.percent} %)`,link);
            node('small',alert.created_at,link);
        });
    } catch (error) { $('#alert-list').textContent=error.message; }
}
updateAlerts();
setInterval(updateAlerts,60000);
if ($('#watch-form')) {
    const id=$('#watch-form').dataset.product, key='tcg-watch-'+id;
    const status=$('#watch-status');
    let target=null;
    try { target=Number(localStorage.getItem(key)) || null; } catch { status.textContent='Le stockage local est indisponible.'; }
    if (target) $('#target').value=target;
    async function checkTarget() {
        if (!target) return;
        try {
            const data=await getJSON(`/api/sets/${id}/best`);
            status.textContent=data.price !== null && data.price <= target ? `Seuil atteint : ${money(data.price)} par display${data.shippingKnown?'':' (hors port inconnu)'}.` : `Surveillance active : ${money(target)} maximum par display.`;
        } catch (error) {status.textContent=error.message;}
    }
    $('#watch-form').addEventListener('submit',event=>{
        event.preventDefault();
        const value=Number($('#target').value);
        if (!Number.isFinite(value) || value<=0) return;
        try {localStorage.setItem(key,String(value));target=value;checkTarget();} catch {status.textContent='Impossible de sauvegarder dans ce navigateur.';}
    });
    $('#remove-watch').addEventListener('click',()=>{try {localStorage.removeItem(key);} catch {} target=null;$('#target').value='';status.textContent='Surveillance supprimée.';});
    checkTarget();setInterval(checkTarget,60000);
}
if ($('#discovery-form')) {
    let syncCatalog=null;
    if ($('#discovery-set')) {
        const select=$('#discovery-set');
        let options=[...select.options].filter(option=>option.value);
        const manual=$('#discovery-manual');
        const showSelection=()=>{
            const option=select.selectedOptions[0];
            const count=Number(option?.dataset.offers || 0);
            const link=$('#set-choice-offers');
            link.classList.toggle('hidden',manual.checked || !option?.value);
            if (option?.value) {
                link.href='/sets/'+option.value;
                link.textContent=count?`Voir les ${count} offre(s) récente(s)`:'Voir la fiche du set';
            }
            $('#set-choice-status').textContent=manual.checked?'Recherchez un set absent du catalogue.'
                :option?.value?(count?`${count} offre(s) en stock relevée(s) depuis moins de 48 h.`:'Aucune offre récente collectée. Lancez une recherche web pour trouver des disponibilités.')
                :select.options.length>1?`${select.options.length-1} sets au choix pour ce jeu et cette langue.`:'Aucun set référencé pour ce jeu et cette langue. Vous pouvez saisir un set manuellement.';
        };
        const refreshOptions=(chooseLanguage=false)=>{
            const previous=select.value;
            const language=$('#discovery-language');
            const available=new Set(options.filter(option=>option.dataset.game===$('#discovery-game').value).map(option=>option.dataset.language));
            // Switching games must not leave an incompatible language hiding every set.
            if (chooseLanguage && !manual.checked && available.size && !available.has(language.value)) {
                const preferred=['FR','EN','JP'].find(value=>available.has(value));
                if (preferred) language.value=preferred;
            }
            [...language.options].forEach(option=>{
                const label={FR:'Français',JP:'Japonais',EN:'Anglais'}[option.value] || option.value;
                option.textContent=label+(available.size && !available.has(option.value)?' · aucun set référencé':'');
            });
            const matches=options.filter(option=>option.dataset.game===$('#discovery-game').value && option.dataset.language===$('#discovery-language').value);
            matches.sort((a,b)=>Number(b.dataset.offers>0)-Number(a.dataset.offers>0) || b.dataset.code.localeCompare(a.dataset.code,'fr',{numeric:true}));
            const placeholder=node('option','Choisir un set…');placeholder.value='';
            select.replaceChildren(placeholder,...matches);
            select.value=matches.some(option=>option.value===previous)?previous:'';
            showSelection();
        };
        $('#discovery-game').addEventListener('change',()=>refreshOptions(true));
        $('#discovery-language').addEventListener('change',()=>refreshOptions(false));
        select.addEventListener('change',showSelection);
        manual.addEventListener('change',()=>{
            select.disabled=manual.checked;select.required=!manual.checked;
            $('#discovery-name').disabled=!manual.checked;$('#discovery-name').required=manual.checked;
            $('#discovery-manual-field').classList.toggle('hidden',!manual.checked);
            refreshOptions(!manual.checked);
        });
        refreshOptions(true);
        let catalogPoll=null, catalogBusy=false, pollCount=0;
        syncCatalog=async(check=false)=>{
            if (catalogBusy) return;
            catalogBusy=true;
            clearTimeout(catalogPoll);
            try {
                const response=await fetch('/api/catalog',{
                    method:check?'POST':'GET', headers:{'X-Requested-With':'XMLHttpRequest'},signal:AbortSignal.timeout(6000)
                });
                if (!response.ok) throw new Error('Catalogue indisponible');
                const data=await response.json();
                // Empty/unavailable responses never erase the catalogue already displayed.
                if (Array.isArray(data.sets) && data.sets.length) {
                    const hadGame=options.some(option=>option.dataset.game===$('#discovery-game').value);
                    const merged=new Map(options.map(option=>[option.value,option]));
                    for (const set of data.sets) {
                        const option=node('option',`${set.code} · ${set.name}${Number(set.offers)?` · ${set.offers} offre(s) récente(s)`:''}`);
                        option.value=String(set.id);
                        Object.assign(option.dataset,{name:set.name,code:set.code,game:set.game,language:set.language,offers:String(set.offers || 0)});
                        merged.set(option.value,option);
                    }
                    options=[...merged.values()];
                    refreshOptions(!hadGame);
                }
                const state=data.status || {};
                const checked=state.last_checked?new Date(state.last_checked*1000).toLocaleDateString('fr-FR'):null;
                $('#catalog-status').textContent=state.refreshing?'Recherche de nouveaux sets en cours… Le catalogue en cache reste disponible.'
                    :state.last_error?'Mise à jour indisponible. Le catalogue en cache reste disponible ; une nouvelle tentative sera possible plus tard.'
                    :`${checked?`Catalogue vérifié le ${checked}. `:''}Les nouveaux sets sont recherchés tous les 7 jours lors de votre utilisation.${state.new_sets?` ${state.new_sets} nouvelle(s) référence(s) lors de la dernière mise à jour.`:''}`;
                if (state.refreshing && pollCount++<45) catalogPoll=setTimeout(()=>syncCatalog(false),5000);
                else pollCount=0;
            } catch (_) {
                $('#catalog-status').textContent='Catalogue en cache disponible. La vérification des nouveaux sets reprendra lors d’une prochaine recherche.';
            } finally { catalogBusy=false; }
        };
        syncCatalog(true);
    }
    let candidates=[];
    let discoveryRevision=0;
    const list=$('#discovery-results');
    $('#discovery-form').addEventListener('change',event=>{
        if (!['discovery-game','discovery-language','discovery-set','discovery-manual','discovery-name'].includes(event.target.id)) return;
        discoveryRevision++;
        candidates=[];list.replaceChildren();$('#discovery-status').textContent='';
        $('#discovery-filters').classList.add('hidden');$('#discovery-fallback')?.classList.add('hidden');
    });
    function renderCandidates() {
        list.replaceChildren();
        const originFilter=$('#discovery-origin')?.value || '';
        const rows=candidates.filter(row=>!['out_of_stock','preorder'].includes(row.stock_status) && (!$('#discovery-new').checked || !row.known_store)
            && ($('#discovery-other').checked || row.language_match!=='mismatch')
            && (!originFilter || (originFilter==='FR' ? row.shipping_origin?.country==='FR' : (row.shipping_origin?.region || 'unknown')===originFilter)));
        rows.sort((a,b)=>Number(Boolean(b.comparable))-Number(Boolean(a.comparable)) || (a.unit_price_eur ?? Infinity)-(b.unit_price_eur ?? Infinity));
        $('#discovery-count').textContent=`${rows.length} piste(s) affichée(s) sur ${candidates.length}`;
        if (!rows.length) node('p',candidates.length?'Des résultats existent, mais ils sont masqués par les filtres de langue, de source ou d’expédition. Réinitialisez les filtres pour les afficher.':'Aucun résultat reçu. Consultez le statut de la recherche ci-dessus ou utilisez les liens de recherche ci-dessous.',list);
        for (const row of rows) {
            const article=node('article',undefined,list); article.className='discovery-result';
            if (row.comparable) article.classList.add('comparable');
            if (row===rows[0] && row.comparable) {
                article.classList.add('best-offer');
                node('div','Prix le plus bas affiché',article).className='best-offer-label';
            }
            const merchant=node('div',undefined,article);merchant.className='merchant-heading';
            const monogram=node('span',row.domain.slice(0,1).toUpperCase(),merchant);monogram.className='merchant-icon';monogram.setAttribute('aria-hidden','true');
            const identity=node('div',undefined,merchant);
            node('strong',row.domain,identity);
            node('small',row.source_type==='catalog'?'Dernière collecte · source suivie':row.known_store?'Source déjà suivie':'Nouvelle source',identity);
            const heading=node('h3',undefined,article);heading.className='offer-title';
            const link=node('a',row.price_title || row.title,heading);link.href=row.price_url || row.url;link.target='_blank';link.rel='noopener noreferrer';link.title=row.price_title || row.title;
            const badges=node('div',undefined,article);badges.className='result-badges';
            node('span',row.language_match==='match'?(row.detected_languages || []).join(' / ') || 'Langue indiquée':row.language_match==='mismatch'?`Autre langue · ${(row.detected_languages || []).join(' / ')}`:'Langue à confirmer',badges);
            node('span',row.display_count>1?`Case · ${row.display_count} displays`:row.packaging==='case'?'Case':row.packaging==='display'?'Display':'Format à confirmer',badges);
            const priceArea=node('div',undefined,article);priceArea.className='offer-price-area';
            if (row.price_status==='read') {
                node('small',row.unit_price_eur!=null?'PRIX PAR DISPLAY':'PRIX DU PRODUIT',priceArea).className='price-eyebrow';
                const amount=node('div',undefined,priceArea);amount.className='web-price';
                const original=row.currency==='UNK'?`${row.price} (devise inconnue)`:new Intl.NumberFormat('fr-FR',{style:'currency',currency:row.currency}).format(row.price);
                amount.textContent=row.unit_price_eur!=null?`${row.currency==='EUR'?'':'≈ '}${money(row.unit_price_eur)}`:original;
                node('small','Hors livraison et frais d’import',priceArea);
                if (row.display_count>1) node('div',`${original} la case · ${row.display_count} displays`,priceArea).className='case-total';
                else if (row.currency!=='EUR' && row.unit_price_eur!=null) node('div',`${original} · conversion indicative`,priceArea).className='case-total';
                if (!row.display_count) node('small','Quantité de displays inconnue',priceArea);
            } else {
                node('small','PRIX DU PRODUIT',priceArea).className='price-eyebrow';
                node('div','À consulter',priceArea).className='price-unavailable';
                node('small','Le prix n’a pas pu être extrait automatiquement de cette page.',priceArea);
            }
            const stock=node('div',row.price_status!=='read'?'Disponibilité à vérifier':row.in_stock?(row.source_type==='catalog'?'En stock au dernier relevé':'En stock sur la fiche'):'Indisponible / stock non confirmé',article);
            stock.className='stock-state '+(row.price_status==='read'&&row.in_stock?'in-stock':'unconfirmed');
            const origin=row.shipping_origin || {};
            const shipping=node('div',undefined,article);shipping.className='shipping-origin';
            node('strong',`Expédition : ${origin.country_label || 'À confirmer'}${origin.region==='EU'?' · UE':origin.region==='outside_eu'?' · Hors UE':''}`,shipping);
            node('small',origin.tax_message || 'Pays de départ non confirmé : frais d’import à vérifier pour la France métropolitaine.',shipping);
            if (origin.sources?.length) {
                const sources=node('details',undefined,shipping);
                node('summary','Sources de l’expédition',sources);
                for (const source of origin.sources) {
                    node('p',source.evidence,sources);
                    node('small',`Vérifié le ${source.checked_at || 'date inconnue'}`,sources);
                    try {
                        const target=new URL(source.url);
                        if (['https:','http:'].includes(target.protocol)) {
                            const sourceLink=node('a','Source marchand ↗',sources);
                            sourceLink.href=target.href;sourceLink.target='_blank';sourceLink.rel='noopener noreferrer';
                        }
                    } catch (_) { /* Keep evidence text even if a stored link is invalid. */ }
                }
            }
            if (row.language_match==='mismatch') article.classList.add('language-mismatch');
            const details=node('details',undefined,article);details.className='offer-details';
            node('summary','Détails du relevé',details);
            node('p',row.price_status==='read'?'Prix relevé sur la fiche':'Offre non vérifiée',details);
            node('p',row.set_match?'Set repéré dans le titre.':'Correspondance du set à confirmer.',details);
            if (!row.comparable) node('p','Hors classement : stock, langue, quantité ou devise à confirmer.',details);
            if (row.checked_at) node('p',`Relevé le ${new Date(row.checked_at*1000).toLocaleString('fr-FR')}`,details);
            node('p',row.snippet,details);
            const cta=node('a',row.price_status==='read'?'Voir l’offre ↗':'Consulter le site ↗',article);
            cta.className='offer-cta';cta.href=row.price_url || row.url;cta.target='_blank';cta.rel='noopener noreferrer';
        }
    }
    ['discovery-new','discovery-other'].forEach(id=>$('#'+id).addEventListener('change',renderCandidates));
    $('#discovery-origin')?.addEventListener('change',renderCandidates);
    $('#discovery-reset')?.addEventListener('click',()=>{
        $('#discovery-new').checked=false;
        $('#discovery-other').checked=true;
        if ($('#discovery-origin')) $('#discovery-origin').value='';
        renderCandidates();
    });
    function fallbackLinks(queries) {
        const fallback=$('#discovery-fallback');
        if (!fallback) return;
        fallback.classList.remove('hidden');
        const links=fallback.querySelector('ul');links.replaceChildren();
        for (const query of queries) {
            const li=node('li',undefined,links);node('span',query,li);
            for (const [label,base] of [['Google','https://www.google.com/search?q='],['DuckDuckGo','https://duckduckgo.com/?q=']]) {
                const a=node('a',label+' ↗',li);a.href=base+encodeURIComponent(query);a.target='_blank';a.rel='noopener noreferrer';
            }
        }
    }
    $('#discovery-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form=event.currentTarget, button=form.querySelector('button');
        const status=$('#discovery-status'), list=$('#discovery-results');
        const payload={keywords:$('#discovery-keywords').value.trim()};
        const revision=discoveryRevision;
        if (syncCatalog) syncCatalog(true);
        if (!form.dataset.product) {
            const selected=$('#discovery-manual').checked?null:$('#discovery-set').selectedOptions[0];
            Object.assign(payload,{game:$('#discovery-game').value,name:selected?.value?selected.dataset.name:$('#discovery-name').value.trim(),language:$('#discovery-language').value});
            if (!payload.name) {status.textContent='Indiquez le nom ou le code du set.';$('#discovery-name').focus();return;}
            // A code typed on its own can be searched with and without punctuation.
            payload.code=selected?.value?selected.dataset.code:(/^[a-z]{1,5}[- ]?\d{1,3}(?:[a-z])?$/i.test(payload.name)?payload.name:'');
            const lang={FR:'français',JP:'japonais',EN:'anglais'}[payload.language];
            fallbackLinks([`${payload.game} ${payload.name} ${payload.code} display ${lang} ${payload.keywords}`.trim()]);
        }
        button.disabled=true; status.textContent='Recherche des offres et lecture des prix chez les marchands… Cela peut prendre une minute.'; list.replaceChildren();
        list.setAttribute('aria-busy','true');$('#discovery-filters').classList.add('hidden');
        try {
            const response=await fetch(form.dataset.product?`/api/sets/${form.dataset.product}/discover`:'/api/discover',{
                method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                body:JSON.stringify(payload),signal:AbortSignal.timeout(75000)
            });
            const data=await response.json();
            if (revision!==discoveryRevision) return;
            if (!response.ok) throw new Error(data.error || 'La recherche est indisponible.');
            candidates=data.candidates || [];
            if (data.queries?.length) fallbackLinks(data.queries);
            const newDomains=new Set(candidates.filter(row=>!row.known_store).map(row=>row.domain));
            status.textContent=data.status==='unconfigured' || data.status==='unavailable'
                ? (data.message || 'La recherche intégrée est indisponible. Utilisez les liens ci-dessous.')
                : `${data.priced_count ?? 0} prix relevés · ${data.comparable_count ?? 0} offres comparables · ${newDomains.size} nouvelles sources.${data.catalog_count?` ${data.catalog_count} offre(s) issue(s) des dernières collectes.`:''}${data.cached?` Cache web : ${Math.ceil((data.cache_ttl_seconds || 3600)/60)} min maximum.`:''}${data.message?' '+data.message:data.status==='partial'?' Certains moteurs n’ont pas répondu.':''}`;
            $('#discovery-filters').classList.toggle('hidden',!candidates.length);
            renderCandidates();
            if (syncCatalog) syncCatalog(false);
        } catch (error) {
            if (revision===discoveryRevision) status.textContent=error.name==='TimeoutError'?'La recherche prend trop de temps. Les liens ci-dessous restent disponibles.':error.message;
        } finally {button.disabled=false;list.setAttribute('aria-busy','false');}
    });
}
