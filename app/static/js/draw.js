/* CRIB-1 — rendu canvas des specifications d'items produites cote serveur.
 * Le client ne genere aucun item : il dessine ce qu'on lui envoie (R2).
 */
'use strict';

const Dessin = (() => {

  function fond(ctx, w, h){
    ctx.clearRect(0,0,w,h);
  }

  function couleurTrait(){
    return getComputedStyle(document.body).getPropertyValue('--encre').trim() || '#1b1b1f';
  }

  /* ---------------- formes elementaires ---------------- */
  function forme(ctx, nom, cx, cy, r, rotationDeg, remplissage, couleur){
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((rotationDeg||0) * Math.PI/180);
    ctx.strokeStyle = couleur; ctx.fillStyle = couleur; ctx.lineWidth = 2;
    ctx.beginPath();
    if (nom === 'cercle') ctx.arc(0,0,r,0,Math.PI*2);
    else if (nom === 'carre') ctx.rect(-r,-r,2*r,2*r);
    else if (nom === 'triangle'){
      ctx.moveTo(0,-r); ctx.lineTo(r*0.87, r*0.5); ctx.lineTo(-r*0.87, r*0.5); ctx.closePath();
    } else if (nom === 'losange'){
      ctx.moveTo(0,-r); ctx.lineTo(r,0); ctx.lineTo(0,r); ctx.lineTo(-r,0); ctx.closePath();
    } else if (nom === 'hexagone'){
      for (let k=0;k<6;k++){ const a=Math.PI/3*k - Math.PI/2;
        const x=r*Math.cos(a), y=r*Math.sin(a); k?ctx.lineTo(x,y):ctx.moveTo(x,y); }
      ctx.closePath();
    } else { /* croix */
      const e=r*0.34;
      ctx.moveTo(-e,-r); ctx.lineTo(e,-r); ctx.lineTo(e,-e); ctx.lineTo(r,-e);
      ctx.lineTo(r,e); ctx.lineTo(e,e); ctx.lineTo(e,r); ctx.lineTo(-e,r);
      ctx.lineTo(-e,e); ctx.lineTo(-r,e); ctx.lineTo(-r,-e); ctx.lineTo(-e,-e);
      ctx.closePath();
    }
    if (remplissage === 'plein') ctx.fill();
    else if (remplissage === 'hachure'){
      ctx.save(); ctx.clip();
      for (let x=-r; x<=r; x+=5){ ctx.beginPath(); ctx.moveTo(x,-r); ctx.lineTo(x+r,r); ctx.stroke(); }
      ctx.restore(); ctx.stroke();
    } else ctx.stroke();
    ctx.restore();
  }

  function cellule(ctx, spec, x, y, w, h){
    if (!spec) return;
    const rBase = Math.min(w,h) * (0.12 + 0.07*(spec.taille||1));
    const n = spec.n || 1;
    const positions = [[0,0]];
    if (n===2) positions.splice(0,1,[-0.22,0],[0.22,0]);
    if (n===3) positions.splice(0,1,[0,-0.22],[-0.22,0.18],[0.22,0.18]);
    if (n>=4)  positions.splice(0,1,[-0.2,-0.2],[0.2,-0.2],[-0.2,0.2],[0.2,0.2]);
    const r = rBase / Math.sqrt(Math.max(1, n*0.55));
    positions.forEach(([dx,dy]) => {
      forme(ctx, spec.forme, x+w/2+dx*w, y+h/2+dy*h, r, spec.rotation,
            spec.remplissage, spec.couleur);
    });
  }

  /* ---------------- matrice 3x3 ---------------- */
  function matrice(ctx, item, W, H){
    fond(ctx, W, H);
    const marge = 40, taille = Math.min(W,H) - 2*marge;
    const x0 = (W-taille)/2, y0 = (H-taille)/2, c = taille/3;
    ctx.strokeStyle = couleurTrait(); ctx.globalAlpha = .25; ctx.lineWidth = 1;
    for (let k=0;k<=3;k++){
      ctx.beginPath(); ctx.moveTo(x0+k*c,y0); ctx.lineTo(x0+k*c,y0+taille); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x0,y0+k*c); ctx.lineTo(x0+taille,y0+k*c); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (let i=0;i<3;i++) for (let j=0;j<3;j++){
      const spec = item.grille[i][j];
      if (spec) cellule(ctx, spec, x0+j*c, y0+i*c, c, c);
      else {
        ctx.save(); ctx.globalAlpha=.5; ctx.setLineDash([6,5]);
        ctx.strokeStyle = couleurTrait(); ctx.lineWidth=2;
        ctx.strokeRect(x0+j*c+8, y0+i*c+8, c-16, c-16); ctx.restore();
      }
    }
  }

  /* ---------------- assemblages de cubes, projection isometrique ---------------- */
  function iso(x,y,z,e){ return { x:(x-y)*e*0.866, y:(x+y)*e*0.5 - z*e }; }

  function cubes(ctx, liste, W, H, echelleForcee){
    fond(ctx, W, H);
    if (!liste || !liste.length) return;
    const e = echelleForcee || Math.min(W,H)/(2.6 + Math.cbrt(liste.length));
    const pts = liste.map(c => iso(c[0],c[1],c[2],e));
    const minx = Math.min(...pts.map(p=>p.x)), maxx = Math.max(...pts.map(p=>p.x));
    const miny = Math.min(...pts.map(p=>p.y)), maxy = Math.max(...pts.map(p=>p.y));
    const ox = W/2 - (minx+maxx)/2, oy = H/2 - (miny+maxy)/2;
    // tri en profondeur : on dessine du fond vers l'avant
    const ordre = liste.map((c,i)=>({c,i})).sort((a,b)=>
      (a.c[0]+a.c[1]-a.c[2]) - (b.c[0]+b.c[1]-b.c[2]));
    const trait = couleurTrait();
    ordre.forEach(({c}) => {
      const [x,y,z] = c;
      const p = (dx,dy,dz)=>{ const q=iso(x+dx,y+dy,z+dz,e); return [q.x+ox, q.y+oy]; };
      const faces = [
        { pts:[p(0,0,1),p(1,0,1),p(1,1,1),p(0,1,1)], a:0.30 }, // dessus
        { pts:[p(0,0,0),p(0,0,1),p(0,1,1),p(0,1,0)], a:0.15 }, // gauche
        { pts:[p(0,1,0),p(0,1,1),p(1,1,1),p(1,1,0)], a:0.05 }  // droite
      ];
      faces.forEach(f => {
        ctx.beginPath();
        f.pts.forEach(([px,py],k)=> k?ctx.lineTo(px,py):ctx.moveTo(px,py));
        ctx.closePath();
        ctx.fillStyle = trait; ctx.globalAlpha = f.a; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = trait; ctx.lineWidth = 1.4; ctx.stroke();
      });
    });
  }

  /* ---------------- grille d'empan ---------------- */
  function grilleEmpan(ctx, W, H, nCases, allumee){
    fond(ctx, W, H);
    const cote = Math.round(Math.sqrt(nCases));
    const taille = Math.min(W,H)*0.68, c = taille/cote;
    const x0=(W-taille)/2, y0=(H-taille)/2;
    const trait = couleurTrait();
    for (let k=0;k<nCases;k++){
      const i=Math.floor(k/cote), j=k%cote;
      ctx.beginPath();
      ctx.roundRect(x0+j*c+6, y0+i*c+6, c-12, c-12, 8);
      ctx.globalAlpha = (k===allumee)?1:0.16;
      ctx.fillStyle = (k===allumee)?'#0a4fa8':trait; ctx.fill();
      ctx.globalAlpha = 1; ctx.strokeStyle = trait; ctx.lineWidth=1; ctx.stroke();
    }
  }

  function casesDepuisClic(W,H,nCases,mx,my){
    const cote = Math.round(Math.sqrt(nCases));
    const taille = Math.min(W,H)*0.68, c = taille/cote;
    const x0=(W-taille)/2, y0=(H-taille)/2;
    const j = Math.floor((mx-x0)/c), i = Math.floor((my-y0)/c);
    if (i<0||j<0||i>=cote||j>=cote) return -1;
    return i*cote+j;
  }

  /* ---------------- serie de lettres et de nombres ---------------- */
  function serie(ctx, item, W, H){
    fond(ctx, W, H);
    ctx.fillStyle = couleurTrait();
    ctx.font = '600 46px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    const els = [...item.elements, '?'];
    const pas = Math.min(120, (W-120)/els.length);
    const x0 = W/2 - pas*(els.length-1)/2;
    els.forEach((e,k)=>{
      ctx.globalAlpha = (k===els.length-1)?0.45:1;
      ctx.fillText(e, x0+k*pas, H/2);
    });
    ctx.globalAlpha = 1;
  }

  /* ---------------- objet unique (reconnaissance) ---------------- */
  function objet(ctx, spec, W, H){
    fond(ctx, W, H);
    forme(ctx, spec.forme, W/2, H/2, Math.min(W,H)*0.22, spec.rotation,
          spec.remplissage, spec.couleur);
  }

  /* ---------------- attention visuelle divisee ---------------- */
  function attentionDivisee(ctx, essai, W, H){
    fond(ctx, W, H);
    forme(ctx, essai.central.forme, W/2, H/2, 26, 0, 'plein', essai.central.couleur);
    const R = Math.min(W,H)/2 - 30;
    essai.peripheriques.forEach(p=>{
      const a = p.angle*Math.PI/180;
      forme(ctx, p.forme, W/2 + Math.cos(a)*R*p.rayon, H/2 + Math.sin(a)*R*p.rayon,
            13, 0, 'vide', couleurTrait());
    });
  }

  /* ---------------- Trail Making ---------------- */
  function trail(ctx, cibles, atteintes, W, H){
    fond(ctx, W, H);
    const trait = couleurTrait();
    ctx.strokeStyle = trait; ctx.lineWidth = 2; ctx.globalAlpha=.4;
    ctx.beginPath();
    atteintes.forEach((idx,k)=>{
      const c=cibles[idx]; const x=c.x*W, y=c.y*H;
      k?ctx.lineTo(x,y):ctx.moveTo(x,y);
    });
    ctx.stroke(); ctx.globalAlpha=1;
    cibles.forEach((c,i)=>{
      const x=c.x*W, y=c.y*H;
      ctx.beginPath(); ctx.arc(x,y,20,0,Math.PI*2);
      ctx.fillStyle = atteintes.includes(i) ? '#1d6b34' : 'transparent';
      ctx.globalAlpha = atteintes.includes(i)?0.22:1; ctx.fill(); ctx.globalAlpha=1;
      ctx.strokeStyle = trait; ctx.lineWidth=1.6; ctx.stroke();
      ctx.fillStyle = trait; ctx.font='600 16px system-ui';
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(c.etiquette, x, y);
    });
  }

  /* ---------------- code symboles-chiffres ---------------- */
  function symbole(ctx, id, cx, cy, r){
    ctx.save(); ctx.translate(cx,cy);
    ctx.strokeStyle = couleurTrait(); ctx.lineWidth=2.2; ctx.beginPath();
    const t = id % 12;
    if (t===0){ ctx.moveTo(-r,0); ctx.lineTo(r,0); ctx.moveTo(0,-r); ctx.lineTo(0,r); }
    else if (t===1){ ctx.moveTo(-r,-r); ctx.lineTo(r,r); ctx.moveTo(r,-r); ctx.lineTo(-r,r); }
    else if (t===2){ ctx.arc(0,0,r,0,Math.PI); }
    else if (t===3){ ctx.moveTo(-r,r); ctx.lineTo(0,-r); ctx.lineTo(r,r); }
    else if (t===4){ ctx.rect(-r,-r*0.5,2*r,r); }
    else if (t===5){ ctx.moveTo(-r,0); ctx.lineTo(0,-r); ctx.lineTo(r,0); ctx.lineTo(0,r); ctx.closePath(); }
    else if (t===6){ ctx.moveTo(-r,-r); ctx.lineTo(r,-r); ctx.lineTo(-r,r); ctx.lineTo(r,r); }
    else if (t===7){ ctx.arc(0,-r*0.4,r*0.6,0,Math.PI*2); ctx.moveTo(0,r*0.2); ctx.lineTo(0,r); }
    else if (t===8){ ctx.moveTo(-r,-r); ctx.lineTo(-r,r); ctx.lineTo(r,r); }
    else if (t===9){ ctx.moveTo(-r,0); ctx.lineTo(r,0); ctx.moveTo(r*0.4,-r*0.5); ctx.lineTo(r,0); ctx.lineTo(r*0.4,r*0.5); }
    else if (t===10){ ctx.arc(-r*0.4,0,r*0.5,0,Math.PI*2); ctx.moveTo(r*0.9,0); ctx.arc(r*0.4,0,r*0.5,0,Math.PI*2); }
    else { ctx.moveTo(0,-r); ctx.lineTo(r*0.87,r*0.5); ctx.lineTo(-r*0.87,r*0.5); ctx.closePath(); }
    ctx.stroke(); ctx.restore();
  }

  function codeSymboles(ctx, cle, chiffreCourant, W, H){
    fond(ctx, W, H);
    const trait = couleurTrait();
    const n = cle.length, pas = Math.min(92, (W-80)/n), x0 = W/2 - pas*(n-1)/2;
    cle.forEach((c,k)=>{
      const x = x0 + k*pas;
      symbole(ctx, c.symbole, x, 74, 20);
      ctx.fillStyle = trait; ctx.font='600 20px ui-monospace, monospace';
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(String(c.chiffre), x, 128);
      ctx.strokeStyle = trait; ctx.globalAlpha=.25; ctx.lineWidth=1;
      ctx.strokeRect(x-30, 44, 60, 104); ctx.globalAlpha=1;
    });
    if (chiffreCourant != null){
      const c = cle.find(v=>v.chiffre===chiffreCourant);
      symbole(ctx, c.symbole, W/2, H/2 + 60, 44);
    }
  }

  return { matrice, cubes, grilleEmpan, casesDepuisClic, serie, objet,
           attentionDivisee, trail, codeSymboles, symbole, forme, fond, cellule };
})();
