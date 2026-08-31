/* CRIB-1 — chronometrie client (§7).
 *
 * - performance.now() partout, jamais Date.now()
 * - taux de rafraichissement detecte et enregistre
 * - latence d'affichage estimee (demi-periode de rafraichissement) et soustraite
 * - refus de passation si le taux varie de plus de 5 % pendant une tache chronometree
 */
'use strict';

const Chrono = (() => {
  let intervalles = [];       // intervalles inter-frames de la tache en cours
  let hzReference = null;     // mediane mesuree a la calibration
  let latenceAffichageMs = 0;
  let enregistre = false;
  let rafId = null;
  let dernier = null;

  function mediane(a){ const b=[...a].sort((x,y)=>x-y); const n=b.length;
    return n ? (n%2 ? b[(n-1)/2] : (b[n/2-1]+b[n/2])/2) : NaN; }

  /* Calibration initiale : N frames avant toute passation. */
  function calibrer(nFrames, surProgression){
    return new Promise(resolve => {
      const ints = []; let prev = null;
      function tick(t){
        if (prev !== null) ints.push(t - prev);
        prev = t;
        if (surProgression) surProgression(ints.length / nFrames);
        if (ints.length < nFrames) requestAnimationFrame(tick);
        else {
          const m = mediane(ints);
          hzReference = 1000 / m;
          latenceAffichageMs = m / 2;   // le stimulus apparait en moyenne a mi-periode
          resolve({ hz: hzReference, latenceAffichageMs, intervalles: ints });
        }
      }
      requestAnimationFrame(tick);
    });
  }

  /* Enregistrement continu pendant une tache. */
  function demarrerEnregistrement(){
    intervalles = []; enregistre = true; dernier = null;
    function tick(t){
      if (!enregistre) return;
      if (dernier !== null) intervalles.push(t - dernier);
      dernier = t;
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);
  }

  function arreterEnregistrement(){
    enregistre = false;
    if (rafId !== null) cancelAnimationFrame(rafId);
    rafId = null;
    return intervalles.slice();
  }

  /* Horloge monotone depuis le chargement de la page. */
  const maintenant = () => performance.now();

  /* Latence corrigee : on retire la latence d'affichage estimee. */
  const corriger = (ms) => Math.max(0, ms - latenceAffichageMs);

  return {
    calibrer, demarrerEnregistrement, arreterEnregistrement, maintenant, corriger,
    get hz(){ return hzReference; },
    get latenceAffichageMs(){ return latenceAffichageMs; },
    mediane
  };
})();
