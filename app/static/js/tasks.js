/* CRIB-1 — moteurs de taches.
 *
 * R5 : aucune consigne verbale a l'interieur des sub-tests du noyau. Chaque
 * tache s'apprend par des DEMONSTRATIONS ANIMEES avec retour immediat (la
 * regle est montree en surlignant successivement les elements pertinents),
 * puis 3 essais de qualification.
 */
'use strict';

const Taches = (() => {
  const toile = () => document.getElementById('toile');
  const ctx2d = () => toile().getContext('2d');
  const optionsEl = () => document.getElementById('options');
  const retourEl = () => document.getElementById('retour');
  const phaseEl = () => document.getElementById('phase-indicateur');

  const dormir = ms => new Promise(r => setTimeout(r, ms));

  function poserPhase(texte){ phaseEl().textContent = texte || ''; }

  function montrerRetour(ok){
    const r = retourEl();
    r.hidden = false;
    r.textContent = ok ? '✓' : '✗';
    r.className = 'retour ' + (ok ? 'ok' : 'non');
  }
  function cacherRetour(){ const r = retourEl(); r.hidden = true; r.textContent=''; }

  function viderOptions(){ optionsEl().innerHTML = ''; }

  /* ------------------------------------------------------------------ */
  /* Options a choix multiple (8 vignettes, la derniere = « aucune »)     */
  /* ------------------------------------------------------------------ */
  function rendreOptions(item, dessineur){
    viderOptions();
    const el = optionsEl();
    item.options.forEach((opt, k) => {
      const d = document.createElement('div');
      d.className = 'option'; d.dataset.index = String(k);
      if (opt && opt.aucune){
        const s = document.createElement('div');
        s.className = 'aucune';
        s.textContent = '∅';           // symbole, pas une phrase (R5)
        s.title = 'aucune de celles-ci';
        d.appendChild(s);
      } else {
        const c = document.createElement('canvas');
        c.width = 200; c.height = 200;
        dessineur(c.getContext('2d'), opt, 200, 200);
        d.appendChild(c);
      }
      el.appendChild(d);
    });
  }

  function attendreChoix(){
    return new Promise(resolve => {
      const el = optionsEl();
      const t0 = Chrono.maintenant();
      function clic(ev){
        const cible = ev.target.closest('.option');
        if (!cible) return;
        el.removeEventListener('click', clic);
        [...el.children].forEach(c => c.classList.remove('choisie'));
        cible.classList.add('choisie');
        resolve({ index: Number(cible.dataset.index),
                  latence: Chrono.maintenant() - t0 });
      }
      el.addEventListener('click', clic);
    });
  }

  /* Animation de demonstration : surligne la ligne puis la bonne option. */
  async function animerDemo(item, dessineurPrincipal, dessineurOption){
    const c = ctx2d(), W = toile().width, H = toile().height;
    for (let k = 0; k < 3; k++){
      dessineurPrincipal(c, item, W, H);
      c.save();
      c.globalAlpha = 0.16; c.fillStyle = '#0a4fa8';
      const marge = 40, taille = Math.min(W,H) - 2*marge;
      const x0=(W-taille)/2, y0=(H-taille)/2, cc=taille/3;
      c.fillRect(x0, y0 + k*cc, taille, cc);
      c.restore();
      await dormir(430);
    }
    dessineurPrincipal(c, item, W, H);
    const bonne = optionsEl().children[item.reponse];
    if (bonne){
      bonne.classList.add('correcte');
      await dormir(700);
      bonne.classList.remove('correcte');
    }
  }

  /* ------------------------------------------------------------------ */
  /* Moteur generique a choix multiple : C1, C2, C6, K1                   */
  /* ------------------------------------------------------------------ */
  async function choixMultiple(payload, api, dessineurs){
    const { principal, option } = dessineurs;
    const c = ctx2d(), W = toile().width, H = toile().height;

    for (const [phase, items, libelle] of [
      ['demo', payload.demonstrations, 'demonstration'],
      ['qualification', payload.qualification, 'qualification'],
    ]){
      for (let i = 0; i < items.length; i++){
        const item = items[i];
        poserPhase(`${libelle} ${i+1}/${items.length}`);
        cacherRetour();
        principal(c, item, W, H);
        rendreOptions(item, option);
        if (phase === 'demo') await animerDemo(item, principal, option);
        const rep = await attendreChoix();
        const ok = rep.index === item.reponse;
        montrerRetour(ok);                      // retour immediat (R5)
        if (!ok && phase === 'demo'){
          const bonne = optionsEl().children[item.reponse];
          if (bonne) bonne.classList.add('correcte');
        }
        await api.essai({ phase, index_essai: i, item, reponse: rep.index,
                          correct: ok, latence_ms: rep.latence,
                          t_monotone_ms: Chrono.maintenant() });
        await dormir(phase === 'demo' ? 900 : 450);
      }
    }

    /* Phase de test : items standard + items faciles inseres + supplementaires */
    const sequence = [];
    payload.standard.forEach((it, i) => {
      sequence.push(it);
      payload.faciles.filter(f => f.insere_apres === i).forEach(f => sequence.push(f));
    });
    (payload.supplementaires || []).forEach(it => sequence.push(it));

    cacherRetour();
    for (let i = 0; i < sequence.length; i++){
      const item = sequence[i];
      poserPhase(`${i+1}/${sequence.length}`);
      principal(c, item, W, H);
      rendreOptions(item, option);
      const rep = await attendreChoix();
      await api.essai({ phase:'test', index_essai:i, item,
                        reponse: rep.index, correct: rep.index === item.reponse,
                        latence_ms: rep.latence, t_monotone_ms: Chrono.maintenant(),
                        item_facile: !!item.item_facile });
      await dormir(160);
    }
    viderOptions(); poserPhase('');
  }

  /* ------------------------------------------------------------------ */
  /* Empan spatial : C3, C4, C5                                          */
  /* ------------------------------------------------------------------ */
  async function presenterSequence(sequence, nCases, msParCase = 620){
    const c = ctx2d(), W = toile().width, H = toile().height;
    for (const k of sequence){
      Dessin.grilleEmpan(c, W, H, nCases, k);
      await dormir(msParCase * 0.62);
      Dessin.grilleEmpan(c, W, H, nCases, -1);
      await dormir(msParCase * 0.38);
    }
  }

  function attendreSaisieGrille(nCases, longueur){
    return new Promise(resolve => {
      const cv = toile(), c = ctx2d(), W = cv.width, H = cv.height;
      const saisie = []; const t0 = Chrono.maintenant();
      Dessin.grilleEmpan(c, W, H, nCases, -1);
      function clic(ev){
        const r = cv.getBoundingClientRect();
        const mx = (ev.clientX - r.left) * cv.width / r.width;
        const my = (ev.clientY - r.top) * cv.height / r.height;
        const k = Dessin.casesDepuisClic(W, H, nCases, mx, my);
        if (k < 0) return;
        saisie.push(k);
        Dessin.grilleEmpan(c, W, H, nCases, k);
        setTimeout(() => Dessin.grilleEmpan(c, W, H, nCases, -1), 130);
        if (saisie.length >= longueur){
          cv.removeEventListener('click', clic);
          resolve({ saisie, latence: Chrono.maintenant() - t0 });
        }
      }
      cv.addEventListener('click', clic);
    });
  }

  const memeSequence = (a,b) => a.length===b.length && a.every((v,i)=>v===b[i]);

  async function empan(payload, api){
    const esc = payload.escalier, nCases = 9;
    let index = 0;

    for (const [phase, items, libelle] of [
      ['demo', payload.demonstrations, 'demonstration'],
      ['qualification', payload.qualification, 'qualification'],
    ]){
      for (let i = 0; i < items.length; i++){
        const item = items[i];
        poserPhase(`${libelle} ${i+1}/${items.length}`);
        cacherRetour();
        await presenterSequence(item.sequence, item.n_cases);
        const rep = await attendreSaisieGrille(item.n_cases, item.longueur);
        const ok = memeSequence(rep.saisie, item.reponse_attendue);
        montrerRetour(ok);
        if (phase === 'demo' && !ok){
          /* retour immediat : on rejoue la bonne reponse */
          await dormir(350);
          await presenterSequence(item.reponse_attendue, item.n_cases, 480);
        }
        await api.essai({ phase, index_essai:i, item, reponse: rep.saisie,
                          correct: ok, latence_ms: rep.latence,
                          t_monotone_ms: Chrono.maintenant() });
        await dormir(500);
      }
    }

    /* Escalier adaptatif : deux essais par longueur, arret apres deux echecs. */
    cacherRetour();
    let longueur = esc.longueur_min, maxAtteint = 0;
    while (longueur <= esc.longueur_max){
      let echecs = 0;
      for (let e = 0; e < esc.essais_par_longueur; e++){
        const item = await api.sequence(longueur);
        poserPhase(`longueur ${longueur}`);
        await presenterSequence(item.sequence, item.n_cases);
        if (esc.complexe && item.intercalaires){
          for (const inter of item.intercalaires){
            Dessin.fond(ctx2d(), toile().width, toile().height);
            await dormir(260);
          }
        }
        const rep = await attendreSaisieGrille(item.n_cases, item.longueur);
        const ok = memeSequence(rep.saisie, item.reponse_attendue);
        if (ok) maxAtteint = Math.max(maxAtteint, longueur); else echecs++;
        await api.essai({ phase:'test', index_essai:index++, item,
                          reponse: rep.saisie, correct: ok,
                          latence_ms: rep.latence, t_monotone_ms: Chrono.maintenant() });
        await dormir(400);
      }
      if (echecs >= esc.echecs_pour_arret) break;
      longueur++;
    }
    poserPhase('');
    return { niveau_maximal: maxAtteint };
  }

  /* ------------------------------------------------------------------ */
  /* Reconnaissance d'objets : C7                                        */
  /* ------------------------------------------------------------------ */
  function attendreBinaire(){
    return new Promise(resolve => {
      const el = optionsEl(); el.innerHTML = '';
      const t0 = Chrono.maintenant();
      [['●', true], ['○', false]].forEach(([sym, val]) => {
        const d = document.createElement('div');
        d.className = 'option'; d.style.fontSize = '30px';
        d.textContent = sym;
        d.onclick = () => resolve({ valeur: val, latence: Chrono.maintenant() - t0 });
        el.appendChild(d);
      });
    });
  }

  async function reconnaissance(payload, api){
    const c = ctx2d(), W = toile().width, H = toile().height;
    poserPhase('familiarisation');
    for (const o of payload.bloc.familiarisation){
      Dessin.objet(c, o, W, H); await dormir(760);
      Dessin.fond(c, W, H); await dormir(180);
    }
    const essais = payload.bloc.essais;
    for (let i = 0; i < essais.length; i++){
      poserPhase(`${i+1}/${essais.length}`);
      Dessin.objet(c, essais[i].objet, W, H);
      const rep = await attendreBinaire();
      const ok = rep.valeur === essais[i].deja_vu;
      await api.essai({ phase:'test', index_essai:i, item: essais[i],
                        reponse: rep.valeur, correct: ok, latence_ms: rep.latence,
                        t_monotone_ms: Chrono.maintenant() });
      await dormir(130);
    }
    viderOptions(); poserPhase('');
  }

  /* ------------------------------------------------------------------ */
  /* Attention visuelle divisee : V1 (chronometree)                      */
  /* ------------------------------------------------------------------ */
  async function attentionDivisee(payload, api){
    const c = ctx2d(), W = toile().width, H = toile().height;
    const essais = payload.bloc.essais;
    for (let i = 0; i < essais.length; i++){
      poserPhase(`${i+1}/${essais.length}`);
      Dessin.fond(c, W, H); await dormir(420);
      Dessin.attentionDivisee(c, essais[i], W, H);
      const tAffiche = Chrono.maintenant();
      await dormir(essais[i].duree_ms);
      Dessin.fond(c, W, H);
      const rep = await attendreBinaire();
      const ok = rep.valeur === essais[i].cible_presente;
      await api.essai({ phase:'test', index_essai:i, item: essais[i],
                        reponse: rep.valeur, correct: ok,
                        latence_ms: Chrono.maintenant() - tAffiche,
                        t_monotone_ms: Chrono.maintenant() });
    }
    viderOptions(); poserPhase('');
  }

  /* ------------------------------------------------------------------ */
  /* Trail Making A : V2 (chronometree)                                  */
  /* ------------------------------------------------------------------ */
  async function trailMaking(payload, api){
    const cv = toile(), c = ctx2d(), W = cv.width, H = cv.height;
    const cibles = payload.bloc.cibles;
    const atteintes = []; let suivant = 0;
    const t0 = Chrono.maintenant();
    Dessin.trail(c, cibles, atteintes, W, H);
    poserPhase('');
    await new Promise(resolve => {
      function clic(ev){
        const r = cv.getBoundingClientRect();
        const mx = (ev.clientX - r.left) * cv.width / r.width;
        const my = (ev.clientY - r.top) * cv.height / r.height;
        const i = cibles.findIndex(t =>
          Math.hypot(t.x*W - mx, t.y*H - my) < 24);
        if (i < 0) return;
        const correct = (i === suivant);
        api.essai({ phase:'test', index_essai: atteintes.length,
                    item: { cible: cibles[i], attendu: suivant },
                    reponse: i, correct,
                    latence_ms: Chrono.maintenant() - t0,
                    t_monotone_ms: Chrono.maintenant() });
        if (correct){
          atteintes.push(i); suivant++;
          Dessin.trail(c, cibles, atteintes, W, H);
          if (suivant >= cibles.length){
            cv.removeEventListener('click', clic);
            resolve();
          }
        }
      }
      cv.addEventListener('click', clic);
    });
    return { temps_s: (Chrono.maintenant() - t0) / 1000 };
  }

  /* ------------------------------------------------------------------ */
  /* Code symboles-chiffres : V3 (90 s)                                  */
  /* ------------------------------------------------------------------ */
  async function codeSymboles(payload, api){
    const c = ctx2d(), W = toile().width, H = toile().height;
    const bloc = payload.bloc, cle = bloc.cle;
    const fin = Chrono.maintenant() + bloc.duree_s * 1000;
    let i = 0, corrects = 0;

    function clavier(){
      return new Promise(resolve => {
        const t0 = Chrono.maintenant();
        function touche(ev){
          const n = Number(ev.key);
          if (!Number.isInteger(n) || n < 1 || n > cle.length) return;
          document.removeEventListener('keydown', touche);
          resolve({ valeur: n, latence: Chrono.maintenant() - t0 });
        }
        document.addEventListener('keydown', touche);
      });
    }

    while (Chrono.maintenant() < fin && i < bloc.items.length){
      const chiffre = bloc.items[i];
      poserPhase(`${Math.max(0, Math.round((fin - Chrono.maintenant())/1000))} s`);
      Dessin.codeSymboles(c, cle, chiffre, W, H);
      const rep = await Promise.race([
        clavier(),
        dormir(Math.max(0, fin - Chrono.maintenant())).then(() => null)
      ]);
      if (!rep) break;
      const ok = rep.valeur === chiffre;
      if (ok) corrects++;
      await api.essai({ phase:'test', index_essai:i, item:{ chiffre },
                        reponse: rep.valeur, correct: ok, latence_ms: rep.latence,
                        t_monotone_ms: Chrono.maintenant() });
      i++;
    }
    poserPhase('');
    return { n_corrects: corrects, n_tentes: i, duree_s: bloc.duree_s };
  }

  /* ------------------------------------------------------------------ */
  const MOTEURS = {
    C1: p => ({ moteur: choixMultiple, dessineurs: {
          principal: Dessin.matrice,
          option: (c,o,w,h) => { Dessin.fond(c,w,h); Dessin.cellule(c,o,0,0,w,h); } } }),
    C2: p => ({ moteur: choixMultiple, dessineurs: {
          principal: (c,it,w,h) => Dessin.cubes(c, it.cible, w, h),
          option: (c,o,w,h) => Dessin.cubes(c, o.cubes, w, h, 15) } }),
    K1: p => ({ moteur: choixMultiple, dessineurs: {
          principal: Dessin.serie,
          option: (c,o,w,h) => { Dessin.fond(c,w,h); c.fillStyle =
              getComputedStyle(document.body).getPropertyValue('--encre');
            c.font='600 40px ui-monospace, monospace'; c.textAlign='center';
            c.textBaseline='middle'; c.fillText(String(o), w/2, h/2); } } }),
  };
  MOTEURS.C6 = MOTEURS.C1;

  async function lancer(payload, api){
    const code = payload.code_reference;
    if (MOTEURS[code]){
      const { moteur, dessineurs } = MOTEURS[code](payload);
      return moteur(payload, api, dessineurs);
    }
    if (['C3','C4','C5'].includes(code)) return empan(payload, api);
    if (code === 'C7') return reconnaissance(payload, api);
    if (code === 'V1') return attentionDivisee(payload, api);
    if (code === 'V2') return trailMaking(payload, api);
    if (code === 'V3') return codeSymboles(payload, api);
    throw new Error(`aucun moteur pour ${code}`);
  }

  return { lancer, dormir, poserPhase, viderOptions, cacherRetour };
})();
