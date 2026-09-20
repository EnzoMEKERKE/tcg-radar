'use strict';
(() => {
    const form = document.querySelector('#deals-form');
    if (!form) return;
    const find = s => document.querySelector(s);
    const create = (tag, text, parent) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; parent?.append(e); return e;};
    const euro = value => new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(value);
    const date = value => new Date(value).toLocaleString('fr-FR');
    const status = find('#deals-status');
    const list = find('#deals-list');
    let timer, activeJob, busy = false;
    let browserTimer;
    function remember(key,value) {try {localStorage.setItem(key,value);} catch {}}
    function stored(key) {try {return localStorage.getItem(key);} catch {return null;}}
    function settings() {
        const data={};
        for(const [key,value] of new FormData(form)) {
            const input=form.elements.namedItem(key);
            data[key]=input.type==='number'?Number(value):input.type==='checkbox'?input.checked:value.trim();
        }
        data.force=form.elements.force.checked;
        remember('tcg-deals-settings',JSON.stringify(data));
        return data;
    }
    try {
        const saved=JSON.parse(stored('tcg-deals-settings') || '{}');
        for(const [key,value] of Object.entries(saved)) {
            const input=form.elements.namedItem(key);
            if(input && input.type!=='checkbox') input.value=value;
        }
    } catch {}
    function disable(value) {
        busy=value;
        form.querySelector('button[type=submit]').disabled=value;
        find('#deals-import-form button').disabled=value;
        list.setAttribute('aria-busy',String(value));
    }
    async function api(url,data) {
        const response=await fetch(url,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(25000)});
        let result;
        try {result=await response.json();} catch {throw new Error('Réponse du serveur illisible. Réessayez.');}
        if(!response.ok) throw new Error(result.error || 'Analyse indisponible.');
        return result;
    }
    async function refreshBrowser(prepare=false) {
        const label=find('#local-browser-status');
        const button=find('#prepare-local-browser');
        if(!label || !button)return;
        clearTimeout(browserTimer);
        try {
            if(prepare){button.disabled=true;label.textContent='Ouverture des recherches dans Chrome…';}
            const data=await api('/api/deals/browser',prepare?{query:form.elements.query.value}:undefined);
            if(!data.available){label.textContent=data.message || 'Navigateur local arrêté. Lance tools/local_deals_browser.py depuis le dossier du projet.';return;}
            if(data.browser_open===false && !data.preparing){label.textContent='Chrome est fermé. Il sera rouvert au prochain scan, ou avec le bouton ci-dessus. Ton profil est conservé.';return;}
            const names={ebay_sold:'Ventes eBay',ebay_active:'Annonces eBay',cardmarket:'Cardmarket'};
            const states={ready:'page chargée',waiting:'page à vérifier dans Chrome',login_required:'connecte-toi dans Chrome',verification_required:'vérification à terminer dans Chrome'};
            label.textContent=data.error || (data.preparing?'Ouverture des onglets… ': 'Navigateur local disponible. ')+(data.pages || []).map(row=>`${names[row.source] || row.source} : ${states[row.status] || row.status}`).join(' · ');
            if(data.preparing || (data.pages || []).some(row=>row.status!=='ready'))browserTimer=setTimeout(()=>refreshBrowser(),4000);
        } catch(error){label.textContent=error.message;}
        finally{button.disabled=false;}
    }
    find('#prepare-local-browser')?.addEventListener('click',()=>refreshBrowser(true));
    refreshBrowser();
    function link(parent,label,url) {
        try {
            const parsed=new URL(url);
            if(parsed.protocol!=='https:' || !/^(www\.)?(ebay\.(fr|com|co\.uk|de|it|es)|cardmarket\.com)$/.test(parsed.hostname))return;
            const a=create('a',label,parent);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
        } catch {}
    }
    function render(job) {
        activeJob=job.id; remember('tcg-deals-job',job.id);
        status.textContent=(job.cached?'Résultat en cache. ':'')+job.message+(job.analyzed_at?' Analyse du '+date(job.analyzed_at)+'.':'');
        const sources=find('#deals-sources');sources.replaceChildren();
        for(const report of job.reports || []) {
            const partial=report.status==='ok' && (job.reports || []).some(other=>other.source===report.source && other.status!=='ok');
            const el=create('div',`${report.source} · ${report.message}${partial?' Collecte partielle : une autre page de cette source a échoué.':''}`,sources);el.className='deal-source'+(report.status!=='ok'?' issue':'');
            if(report.status!=='ok' && report.url) {
                const action=link(el,'Ouvrir cette recherche dans mon navigateur',report.url);
                if(action)action.className='deal-source-link';
            }
        }
        list.replaceChildren();
        const current=job.deals || [];
        const previous=!current.length && job.previous_result;
        const rows=previous?previous.deals:current;
        const summary=find('#deals-summary');
        summary.textContent=previous?`Ancien résultat du ${date(previous.analyzed_at)} — prix à revérifier.`:`${job.listing_count || 0} observations · ${job.matched_groups || 0} groupes comparables · ${current.length} opportunités`;
        for(const deal of rows) {
            const card=create('article',undefined,list);card.className='discovery-result';
            create('span',deal.direction==='cm_to_ebay'?'CARDMARKET → EBAY':'EBAY → CARDMARKET',card).className='deal-badge';
            create('h3',deal.card_name,card).className='offer-title';
            create('div',`${deal.language} · ${deal.condition} · ${deal.card_number} · ${deal.variant}`,card).className='muted';
            create('div','+'+euro(deal.net_profit),card).className='deal-profit';
            create('small',`Marge estimée avant impôts · rendement ${deal.roi} %`,card);
            create('p',deal.reference_kind==='sold_median'?`Référence : médiane de ${deal.reference_count} ventes eBay datées (${euro(deal.reference_price)}).`:`Référence : offre Cardmarket la moins chère parmi ${deal.reference_count} annonces (${euro(deal.reference_price)}). Prix demandé, revente non prouvée.`,card).className='deal-reference';
            const buy=link(card,`Voir l’offre d’achat · ${euro(deal.buy_price)}`,deal.buy_url);if(buy)buy.className='button';
            create('small',`Relevé du ${date(deal.observed_at)}${deal.provenance==='imported'?' · import utilisateur':''}`,card).className='muted';
            const details=create('details',undefined,card);create('summary','Calcul de la marge et références',details);
            const math=create('dl',undefined,details);math.className='deal-math';
            for(const [label,value] of [['Revente après marge de sécurité',deal.sale_target],['Achat',deal.buy_price],['Port d’achat'+(deal.shipping_estimated?' (hypothèse)':''),deal.buy_shipping],['Commissions et frais fixes',deal.fees],['Port de revente',deal.sell_shipping],['Emballage',deal.packaging],['Autres coûts',deal.other_costs]]) {create('dt',label,math);create('dd',euro(value),math);}
            const evidence=create('ul',undefined,details);evidence.className='deal-evidence';
            for(const row of deal.evidence || []) {const li=create('li',undefined,evidence);link(li,`${euro(row.price)} · ${date(row.date)}${row.provenance==='imported'?' · import':''}`,row.url);}
        }
        if(!rows.length && job.status!=='running') {
            create('p',['unavailable','error','partial','interrupted'].includes(job.status)?'Les données disponibles ne permettent pas de conclure. Consultez les sources ci-dessus ou importez vos relevés.':'Aucune opportunité ne respecte les critères avec ces observations. Vérifiez les exclusions et les frais.',list);
        }
        const excluded=find('#deals-exclusions');
        excluded.hidden=!Object.keys(job.excluded || {}).length;
        excluded.querySelector('div').replaceChildren();
        const reasons={lot_gradee_ou_reproduction:'Lot, carte gradée ou reproduction',langue_ou_etat_inconnu:'Langue ou état non confirmé',numero_ou_extension_manquant:'Numéro ou extension manquant',variante_non_confirmee:'Variante non confirmée',nom_non_identifie:'Nom non identifié',devise_non_eur:'Devise autre que EUR',prix_negocie_ou_approximatif:'Prix négocié ou approximatif',vente_non_datee_ou_ancienne:'Vente non datée ou hors période',offre_indisponible_ou_ancienne:'Offre indisponible ou relevé de plus de 24 h',echantillon_ventes_insuffisant:'Pas assez de ventes comparables'};
        reasons.identite_contradictoire='Le titre et les métadonnées se contredisent';
        for(const [key,value] of Object.entries(job.excluded || {}))create('p',`${reasons[key] || key} : ${value}`,excluded.querySelector('div'));
        disable(job.status==='running');
        clearTimeout(timer);
        if(job.status==='running')timer=setTimeout(()=>poll(job.id),2000);
    }
    async function poll(id) {
        try {const job=await api('/api/deals/status/'+id);if(activeJob===id)render(job);}
        catch(error) {status.textContent=error.message+' Le scan peut continuer sur le serveur ; rechargez cette page pour le retrouver.';disable(false);}
    }
    form.addEventListener('submit',async event=>{
        event.preventDefault();if(busy)return;clearTimeout(timer);disable(true);status.textContent='Démarrage de l’analyse…';
        try {render(await api('/api/deals/search',settings()));}
        catch(error){status.textContent=error.message;disable(false);}
    });
    find('#deals-import-form').addEventListener('submit',async event=>{
        event.preventDefault();if(busy || !form.reportValidity())return;
        const file=find('#deals-file').files[0];if(!file)return;
        if(file.size>2000000){status.textContent='Fichier trop volumineux : 2 Mo maximum.';return;}
        disable(true);status.textContent='Validation et analyse des observations…';clearTimeout(timer);
        try {render(await api('/api/deals/import',{settings:settings(),csv:await file.text()}));}
        catch(error){status.textContent=error.message;disable(false);}
    });
    const savedJob=stored('tcg-deals-job');
    if(savedJob && /^[a-f0-9]{32}$/.test(savedJob)){activeJob=savedJob;poll(savedJob);}
})();
