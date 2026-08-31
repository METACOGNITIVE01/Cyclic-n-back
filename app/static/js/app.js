/* CRIB-1 — orchestration de la passation. */
'use strict';

(() => {
  const $ = s => document.querySelector(s);
  const ecrans = ['accueil','calibration','questionnaire','avertissement','tache','pause','fin'];
  let ETAT = null, SESSION = null, PLAN = null, SUJET = null, RANG = 0;

  function montrer(nom){
    ecrans.forEach(e => $('#ecran-'+e).classList.toggle('actif', e === nom));
  }
  function fil(t){ $('#fil').textContent = t || ''; }
  function progression(t){ $('#progression').textContent = t || ''; }

  async function poster(url, corps){
    const r = await fetch(url, { method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify(corps) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error('erreur'), { detail: d.detail, statut: r.status });
    return d;
  }

  /* ---------------------------------------------------------------- */
  async function init(){
    ETAT = await (await fetch('/api/etat')).json();
    if (ETAT.avertissement_sans_norme){
      const b = $('#bandeau-norme');
      b.hidden = false;
      b.textContent = ETAT.avertissement_sans_norme;
    }
    const cfg = ETAT.sujet_configure || {};
    const f = $('#form-sujet');
    if (cfg.identifiant) f.id.value = cfg.identifiant;
    if (cfg.age_annees) f.age_annees.value = cfg.age_annees;
    if (cfg.sexe) f.sexe.value = cfg.sexe;
    if (cfg.niveau_education) f.niveau_education.value = cfg.niveau_education;
    montrer('accueil');
  }

  $('#form-sujet').addEventListener('submit', async ev => {
    ev.preventDefault();
    const numero = Number(ev.submitter.dataset.numero);
    const fd = new FormData(ev.target);
    SUJET = Object.fromEntries(fd.entries());
    SUJET.age_annees = Number(SUJET.age_annees);
    $('#erreur-accueil').hidden = true;
    try {
      await poster('/api/sujet', { ...SUJET, langue:'fr' });
      await calibrer();
      const r = await poster('/api/session/demarrer', {
        sujet_id: SUJET.id, numero,
        fuseau_local: Intl.DateTimeFormat().resolvedOptions().timeZone,
        refresh_hz: Chrono.hz });
      SESSION = r.session_id; PLAN = r.plan;
      await questionnaire('avant', r.questions_avant);
    } catch (e){
      const el = $('#erreur-accueil');
      el.hidden = false;
      el.textContent = (e.detail && (e.detail.message || e.detail)) || 'erreur inattendue';
      montrer('accueil');
    }
  });

  /* ---------------------------------------------------------------- */
  async function calibrer(){
    montrer('calibration');
    const n = (ETAT.chronometrie && ETAT.chronometrie.n_frames_calibration) || 120;
    const res = await Chrono.calibrer(n, p => {
      $('#jauge-remplissage').style.width = Math.round(p*100) + '%';
    });
    $('#texte-calibration').textContent =
      `taux mesure : ${res.hz.toFixed(1)} Hz — latence d'affichage estimee : ` +
      `${res.latenceAffichageMs.toFixed(1)} ms (soustraite des latences brutes)`;
    await Taches.dormir(700);
  }

  /* ---------------------------------------------------------------- */
  function questionnaire(moment, questions){
    return new Promise(resolve => {
      montrer('questionnaire');
      $('#titre-questionnaire').textContent =
        moment === 'avant' ? 'Avant la session' : 'Apres la session';
      const f = $('#form-questionnaire');
      f.innerHTML = '';
      questions.forEach(q => {
        const l = document.createElement('label');
        l.innerHTML = `${q.libelle} <small>(${q.unite})</small> ` +
          `<input type="range" name="${q.cle}" min="${q.min}" max="${q.max}" ` +
          `step="${(q.max-q.min)>20?1:0.5}" value="${(q.min+q.max)/2}" /> ` +
          `<output>${((q.min+q.max)/2).toFixed(1)}</output>`;
        const inp = l.querySelector('input'), out = l.querySelector('output');
        inp.addEventListener('input', () => out.textContent = Number(inp.value).toFixed(1));
        f.appendChild(l);
      });
      const b = document.createElement('button');
      b.textContent = 'Continuer'; b.type = 'submit';
      const d = document.createElement('div'); d.className='boutons'; d.appendChild(b);
      f.appendChild(d);
      f.onsubmit = async ev => {
        ev.preventDefault();
        const rep = {};
        questions.forEach(q => rep[q.cle] = Number(f.elements[q.cle].value));
        await poster('/api/questionnaire', { session_id: SESSION, moment, reponses: rep });
        resolve(moment === 'avant' ? boucleTaches() : terminer());
      };
    });
  }

  /* ---------------------------------------------------------------- */
  function apiTache(tacheId){
    return {
      essai: e => poster('/api/essai', { tache_id: tacheId,
        latence_affichage_ms: Chrono.latenceAffichageMs, ...e }),
      sequence: (() => { let i = 0;
        return longueur => poster('/api/empan/sequence',
          { tache_id: tacheId, longueur, index: i++ }); })(),
    };
  }

  async function avertissementK2(payload){
    return new Promise(resolve => {
      montrer('avertissement');
      const ul = $('#liste-avertissement'); ul.innerHTML = '';
      (payload.avertissement_prealable || []).forEach(t => {
        const li = document.createElement('li'); li.textContent = t; ul.appendChild(li);
      });
      if (payload.indisponible){
        const li = document.createElement('li');
        li.textContent = payload.motif_indisponible;
        li.style.color = 'var(--alerte)'; ul.appendChild(li);
        $('#btn-accepter-k2').disabled = true;
      }
      $('#btn-accepter-k2').onclick = () => resolve(true);
      $('#btn-refuser-k2').onclick  = () => resolve(false);
    });
  }

  async function pause(apresRang){
    montrer('pause');
    const duree = (ETAT.protocole && ETAT.protocole.pause_obligatoire_s) || 60;
    const t0 = Chrono.maintenant();
    for (let s = duree; s > 0; s--){
      $('#compte-a-rebours').textContent = String(s);
      await Taches.dormir(1000);
    }
    await poster('/api/pause', { session_id: SESSION, apres_rang: apresRang,
                                 duree_s: (Chrono.maintenant() - t0)/1000 });
  }

  async function boucleTaches(){
    for (RANG = 0; RANG < PLAN.ordre.length; RANG++){
      const code = PLAN.ordre[RANG];
      fil(`session ${PLAN.numero} — ${code}`);
      progression(`${RANG+1} / ${PLAN.ordre.length}`);

      const payload = await poster('/api/tache/demarrer',
        { session_id: SESSION, code });

      if (payload.optionnel){
        const accepte = await avertissementK2(payload);
        if (!accepte || payload.indisponible) continue;
      }

      montrer('tache');
      Taches.viderOptions(); Taches.cacherRetour();
      Chrono.demarrerEnregistrement();
      try {
        await Taches.lancer(payload, apiTache(payload.tache_id));
      } finally {
        const intervalles = Chrono.arreterEnregistrement();
        const chrono = await poster('/api/chronometrie',
          { tache_id: payload.tache_id, intervalles_ms: intervalles });
        if (chrono.passation_refusee){
          alert(`Tache ${code} : ${chrono.motif}\nElle ne sera pas scoree.`);
        }
      }
      await poster('/api/tache/terminer', { tache_id: payload.tache_id });

      if (PLAN.pauses_apres_rangs.includes(RANG) && RANG < PLAN.ordre.length - 1){
        await pause(RANG);
      }
    }
    const r = await poster('/api/session/terminer', { session_id: SESSION });
    return questionnaire('apres', r.questions_apres);
  }

  async function terminer(){
    montrer('fin'); fil(''); progression('');
    $('#texte-fin').textContent =
      `Session ${PLAN.numero} enregistree. Graine ${PLAN.graine}.`;
    $('#resume-fin').textContent =
      `ordre des taches : ${PLAN.ordre.join(', ')}\n` +
      `taux de rafraichissement : ${Chrono.hz ? Chrono.hz.toFixed(1) : '?'} Hz\n` +
      `latence d'affichage soustraite : ${Chrono.latenceAffichageMs.toFixed(1)} ms\n\n` +
      (ETAT.sans_norme
        ? 'Passation conduite SANS source normative : le rapport affichera\n' +
          '« pas de reference » pour chaque sub-test concerne.'
        : 'Generer le rapport :  python3 -m report.build_report');
  }

  init();
})();
