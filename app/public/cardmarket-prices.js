'use strict';
(() => {
    const form=document.querySelector('#cm-prices-form');
    if(!form)return;
    const status=document.querySelector('#cm-prices-status'),results=document.querySelector('#cm-prices-results');
    const previous=document.querySelector('#cm-prices-prev'),next=document.querySelector('#cm-prices-next');
    const pageLabel=document.querySelector('#cm-prices-page'),summary=document.querySelector('#cm-filter-summary');
    const dialog=document.querySelector('#cm-image-dialog');
    const labels={low:'Prix bas',trend:'Tendance',avg1:'Moyenne 1 jour',avg7:'Moyenne 7 jours',avg30:'Moyenne 30 jours'};
    const euro=value=>value==null?'Non renseigné':new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(value);
    const date=value=>new Date(value).toLocaleString('fr-FR');
    const add=(parent,tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;parent.append(node);return node;};
    let page=1,timer,sequence=0,controller,imagePolls=0;
    const params=new URLSearchParams(location.search);
    for(const field of form.elements){if(field.name && params.has(field.name) && field.name!=='expansion')field.value=params.get(field.name);}
    if(params.get('expansion'))form.elements.expansion.add(new Option('Extension n° '+params.get('expansion'),params.get('expansion'),true,true));
    let filters=Object.fromEntries(new FormData(form));
    function prices(parent,values,suffix='') {
        const dl=add(parent,'dl',undefined,'deal-math');
        for(const [key,label] of Object.entries(labels)){add(dl,'dt',label);add(dl,'dd',euro(values[key+suffix]));}
    }
    function illustration(card,row){
        const frame=add(card,'div',undefined,'cm-card-image');
        if(!row.image_url){add(frame,'span','Illustration indisponible','muted');return;}
        const button=add(frame,'button');button.type='button';button.setAttribute('aria-label','Agrandir '+row.name);
        const img=add(button,'img');img.alt=row.name+' — illustration anglaise';img.loading='lazy';img.decoding='async';img.width=180;img.height=252;
        img.addEventListener('error',()=>{frame.replaceChildren();add(frame,'span','Illustration indisponible','muted');},{once:true});
        img.src=row.image_url;
        button.addEventListener('click',()=>{const large=dialog.querySelector('img');large.src=row.image_large;large.alt=img.alt;dialog.querySelector('p').textContent=row.name+' · Illustration anglaise · TCGdex';dialog.showModal();});
        add(frame,'small','Illustration anglaise · TCGdex','muted');
    }
    dialog.querySelector('button').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
    function saveUrl(){const url=new URL(location.href);url.search='';for(const [k,v]of Object.entries(filters))if(v)url.searchParams.set(k,v);history.replaceState(null,'',url);}
    async function load(background=false){
        const current=++sequence;clearTimeout(timer);controller?.abort();controller=new AbortController();
        const activeController=controller,timeout=setTimeout(()=>activeController.abort(),25000);
        form.querySelector('[type=submit]').disabled=true;previous.disabled=true;next.disabled=true;
        results.setAttribute('aria-busy','true');if(!background)status.textContent='Lecture des prix Cardmarket…';
        try{
            const query=new URLSearchParams({page});for(const [k,v]of Object.entries(filters))if(v!=='')query.set(k,v);
            const response=await fetch('/api/deals/cardmarket-prices?'+query,{signal:controller.signal});
            const data=await response.json();if(current!==sequence)return;
            if(!response.ok)throw new Error(data.error || 'Prix Cardmarket indisponibles.');
            previous.hidden=true;next.hidden=true;pageLabel.textContent='';
            if(data.status==='loading'){results.replaceChildren();status.textContent=data.message;timer=setTimeout(()=>load(true),2000);return;}
            if(data.status==='unavailable'){results.replaceChildren();status.textContent=data.message;return;}
            page=data.page;
            status.textContent=`${data.total.toLocaleString('fr-FR')} références trouvées · ${data.indexed_count.toLocaleString('fr-FR')} références avec prix · Guide Cardmarket du ${date(data.guide_date)}.`;
            if(data.status==='stale')status.textContent+=' Données en cache à actualiser.';
            if(data.message)status.textContent+=' '+data.message;
            if(data.images_loading)status.textContent+=' Recherche des illustrations…';
            if(data.refreshing || (data.images_loading && imagePolls++<30))timer=setTimeout(()=>load(true),4000);
            const expansion=form.elements.expansion;expansion.replaceChildren(new Option('Toutes les extensions',''));
            for(const item of data.expansions || [])expansion.add(new Option(`${item.name || 'Extension n° '+item.id} (${item.count})`,String(item.id)));
            if(filters.expansion && ![...expansion.options].some(o=>o.value===filters.expansion))expansion.add(new Option('Extension n° '+filters.expansion,filters.expansion));
            expansion.value=filters.expansion;
            summary.textContent=`${labels[filters.metric]} · ${filters.variant==='holo'?'série holo':'série principale'}${filters.min_price?' · dès '+euro(Number(filters.min_price)):''}${filters.max_price?' · jusqu’à '+euro(Number(filters.max_price)):''}`;
            results.replaceChildren();
            for(const row of data.rows){
                const card=add(results,'article',undefined,'discovery-result');illustration(card,row);
                add(card,'h3',row.name,'offer-title');
                add(card,'p',`${row.set_name || 'Extension n° '+(row.expansion_id ?? 'inconnue')}${row.card_number?' · Carte '+row.card_number:''} · Réf. ${row.id}`,'muted');
                add(card,'strong',euro(row.selected_price),'cm-selected-price');
                const shownKey=row.selected_price_key || data.price_key;
                add(card,'small',(labels[shownKey.replace('-holo','')] || labels[filters.metric])+(filters.variant==='holo'?' · série holo':'')+(shownKey!==data.price_key?' · autre prix publié':''),'muted');
                prices(card,row.prices,filters.variant==='holo'?'-holo':'');
                if(filters.variant!=='holo' && Object.entries(row.prices).some(([key,value])=>key.endsWith('-holo') && value!=null)){
                    const details=add(card,'details');add(details,'summary','Variante « holo » du guide');prices(details,row.prices,'-holo');
                }
                const link=add(card,'a','Voir les offres de cette carte','button');link.href=row.product_url;link.target='_blank';link.rel='noopener noreferrer';
            }
            if(!data.rows.length)add(results,'p','Aucune carte ne correspond à ces filtres. Élargissez le budget ou réinitialisez la recherche.');
            previous.hidden=page<=1;next.hidden=page*data.limit>=data.total;
            pageLabel.textContent=data.total?`Page ${page} sur ${Math.ceil(data.total/data.limit)}`:'';
        }catch(error){if(current===sequence){status.textContent=error.name==='AbortError'?'La lecture a pris trop de temps. Réessayez.':error.message;if(!background)results.replaceChildren();previous.hidden=true;next.hidden=true;pageLabel.textContent='';}}
        finally{clearTimeout(timeout);if(current===sequence){form.querySelector('[type=submit]').disabled=false;previous.disabled=false;next.disabled=false;results.setAttribute('aria-busy','false');}}
    }
    function apply(){
        form.elements.max_price.setCustomValidity('');
        if(form.elements.min_price.value && form.elements.max_price.value && Number(form.elements.min_price.value)>Number(form.elements.max_price.value))form.elements.max_price.setCustomValidity('Le maximum doit être supérieur ou égal au minimum.');
        if(!form.reportValidity())return;
        filters=Object.fromEntries(new FormData(form));filters.q=filters.q.trim();page=1;imagePolls=0;saveUrl();load();
    }
    form.addEventListener('submit',event=>{event.preventDefault();apply();});
    form.addEventListener('input',()=>form.elements.max_price.setCustomValidity(''));
    form.addEventListener('change',event=>{if(event.target.tagName==='SELECT')apply();});
    form.addEventListener('reset',()=>setTimeout(()=>{form.elements.q.value='';form.elements.expansion.value='';apply();},0));
    previous.addEventListener('click',()=>{page--;imagePolls=0;load();});next.addEventListener('click',()=>{page++;imagePolls=0;load();});
    load();
})();
