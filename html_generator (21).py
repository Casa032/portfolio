"""
html_generator.py
=========================
Génère le dashboard html

Pages : Vue d'ensemble · Par domaine · Collaborateurs · Roadmap Gantt · Évolutions

Usage :
    python html_generator.py
    python html_generator.py --quinzaine T1_2026_R1
    python html_generator.py --llm
    python html_generator.py --config config.yaml --output frontend/dashboard.html
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
import re as _re
from datetime import timedelta
from pathlib import Path 
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

try:
    from storage.storage import StorageManager
except ImportError:
    from storage import StorageManager  # type: ignore

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)


# ── Donnees ───────────────────────────────────────────────────────────────────

def _calculer_snapshot(sm, q, quinzaines):
    df   = sm.charger_quinzaines(quinzaines=[q])
    kpis = sm.kpis(quinzaine=q)
    idx  = quinzaines.index(q)
    q_prev = quinzaines[idx - 1] if idx > 0 else None
    delta = []
    if q_prev:
        df_d = sm.delta_quinzaines(q_prev, q)
        if not df_d.empty:
            delta = df_d.where(df_d.notna(), None).to_dict(orient="records")
    projets = df.where(df.notna(), None).to_dict(orient="records") if not df.empty else []
    par_domaine, par_resp, par_entite = {}, {}, {}
    _CLE = {"En cours":"en_cours","À risque":"a_risque","En retard":"en_retard","Terminé":"terminé","Stand by":"stand_by"}
    for p in projets:
        d = p.get("domaine") or "Autre"
        par_domaine.setdefault(d, {"total":0,"en_cours":0,"a_risque":0,"en_retard":0,"terminé":0,"stand_by":0})
        par_domaine[d]["total"] += 1
        s_raw = (p.get("statut") or "").strip()
        cle = _CLE.get(s_raw)
        if cle and cle in par_domaine[d]:
            par_domaine[d][cle] += 1
        r = p.get("responsable_principal") or "Non assigné"
        par_resp.setdefault(r, {"total":0,"en_cours":0,"domaines":[],"nb_projets":0,"nb_autres":0})
        par_resp[r]["total"] += 1
        type_val = (p.get("type") or p.get("type_meta") or "").upper().strip()
        if type_val in ("PROJET", "", "NAN"):
            par_resp[r]["nb_projets"] += 1
        else:
            par_resp[r]["nb_autres"] += 1
        if s_raw in ("En cours","À risque"): par_resp[r]["en_cours"] += 1
        dom = p.get("domaine") or ""
        if dom and dom not in par_resp[r]["domaines"]:
            par_resp[r]["domaines"].append(dom)
        
        entite_raw = p.get("entite_concerne") or ""
        entite_list = [e.strip() for e in _re.split(r"[;,]", str(entite_raw)) if e.strip()] if entite_raw else []
        for ent in (entite_list or ["Non assigné"]):
            par_entite.setdefault(ent, {"total":0,"en_cours":0,"a_risque":0,"en_retard":0,"terminé":0})
            par_entite[ent]["total"] += 1
            if cle and cle in par_entite[ent]:
                par_entite[ent][cle] += 1
    return {
        "projets": projets, "kpis": kpis, "par_domaine": par_domaine,
        "par_resp": par_resp, "par_entite": par_entite,
        "domaines": sorted({p.get("domaine") 
                            for p in projets
                            if isinstance(p.get("domaine"), str) and p.get("domaine")}),
        "q_prev": q_prev, "delta": delta,
    }


def preparer_donnees(sm, quinzaine=None):
    import yaml as _yaml
    cfg= _yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) if Path("config.yaml").exists() else {}
    quinzaines = sm.lister_quinzaines()
    if not quinzaines:
        log.error("Aucune donnee — lance excel_parser.py d'abord")
        return {}
    quinzaines_triees = sorted(quinzaines)
    q_active = quinzaine or quinzaines_triees[-1]
    if q_active not in quinzaines_triees:
        q_active = quinzaines_triees[-1]
    meta = sm.charger_meta()
    df_all = sm.charger_quinzaines()
    historiques = {}
    if not df_all.empty:
        col_id = "projet_id" if "projet_id" in df_all.columns else "ref_sujet"
        for pid in df_all[col_id].unique():
            h = sm.projet(pid)
            if not h.empty:
                historiques[str(pid)] = h.where(h.notna(), None).to_dict(orient="records")
    snapshots = {}
    for q in quinzaines_triees:
        log.info(f"Preparation snapshot : {q}")
        snapshots[q] = _calculer_snapshot(sm, q, quinzaines_triees)
    snap = snapshots[q_active]
    meta_list = meta.where(meta.notna(), None).to_dict(orient="records") if not meta.empty else []
    agenda = sm.charger_agenda()
    agenda_list = agenda.where(agenda.notna(), None).to_dict(orient="records") if not agenda.empty else []


    archivage = sm.charger_archivage(mois_glissants=12)
    archivage_list = archivage.where(archivage.notna(), None).to_dict(orient="records") if not archivage.empty else []

  
    entites = sm.lister_entites()
    

    # KPIs META-based : compter par type depuis META
    kpis_meta = {"nb_projets": 0, "nb_gouvernance": 0, "nb_outil": 0,
                 "nb_formation": 0, "nb_autre_type": 0,"nb_veille":0, "nb_communication":0}
    TYPE_MAP = {"PROJET": "nb_projets", "GOUVERNANCE": "nb_gouvernance",
                "OUTILS": "nb_outil", "FORMATION": "nb_formation",
               "VEILLE" : "nb_veille", "COMMUNICATION" : "nb_communication"}
    if not meta.empty and "type" in meta.columns:
        for _, row in meta.iterrows():
            t = str(row.get("type", "") or "").upper()
            key = TYPE_MAP.get(t, "nb_autre_type")
            kpis_meta[key] += 1

    return {
        "genere_le":      datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "quinzaines":     quinzaines_triees,
        "quinzaine":      q_active,
        "q_prev":         snap["q_prev"],
        "kpis":           snap["kpis"],
        "projets":        snap["projets"],
        "domaines":       snap["domaines"],
        "par_domaine":    snap["par_domaine"],
        "par_resp":       snap["par_resp"],
        "delta":          snap["delta"],
        "entites":        entites,
        "meta":           meta_list,
        "historiques":    historiques,
        "snapshots":      snapshots,
        "agenda":         agenda_list,
        "archivage":      archivage_list,
        "carte_pays" :  cfg.get("carte_entites"),
        "par_entite":     snap["par_entite"],
        "kpis_meta":      kpis_meta,
        "syntheses":       {},
        "config_llm":      cfg.get("api", {"host": "https://datalab-lil-gpu.cm-cic.fr/users/vincenry/dash/api/chat"})
    }

# ----
#bg-> page centrale, bg2:sidebar ; bg3->encadré; bg4->
# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@300;400;500;600;700&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  /* ── Light mode (défaut) ── */
  --bg:#f5f4f0;
  --bg2:#ffffff;
  --bg3:#eeecea;
  --bg4:#e2e0db;
  --border:#d4d1ca;
  --border2:#b8b5ae;
 
  --text:#0f0e0c;      
  --text2:#2a2826;     
  --text3:#524f4a;  
 
  --cyan:#2563eb;
  --cyan2:#1d4ed8;
  --cyan-dim:rgba(37,99,235,.10);
 
  --violet:#7c3aed;
  --violet-dim:rgba(124,58,237,.10);
 
  --green:#059669;
  --green-dim:rgba(5,150,105,.10);
 
  --amber:#d97706;
  --amber-dim:rgba(217,119,6,.10);
 
  --red:#dc2626;
  --red-dim:rgba(220,38,38,.10);
 
  --font-body:'DM Sans',system-ui,-apple-system,sans-serif;
  --font-mono:'JetBrains Mono','Courier New',monospace;
  --radius:8px;
  --radius-lg:12px;
  --view_cadre-dim:rgba(0,0,0,.45);
}
 
/* ── Dark mode ── */
body.dark{
  --bg:#151310;
  --bg2:#1c1a18;
  --bg3:#252320;
  --bg4:#302e2b;
  --border:var(--border);
  --border2:#4e5053;
 
  --text:#ebebeb;
  --text2:#c8c5c0;
  --text3:#8a8780;
 
  --cyan:#4dd0c7;
  --cyan2:#3bb3aa;
  --cyan-dim:rgba(77,208,199,.14);
 
  --violet:#a78bfa;
  --violet-dim:rgba(167,139,250,.12);
 
  --green:#10d994;
  --green-dim:rgba(16,217,148,.10);
 
  --amber:#f59e0b;
  --amber-dim:rgba(245,158,11,.10);
 
  --red:#f43f5e;
  --red-dim:rgba(244,63,94,.10);
 
  --view_cadre-dim:rgba(0,0,0,.88);
}
html,body{height:100%;font-size:13px;background:var(--bg);color:var(--text);}
body{font-family:var(--font-body);line-height:1.5;overflow:hidden;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:var(--bg2);}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px;}
.shell{display:flex;height:100vh;}
.sidebar{width:220px;min-width:220px;background:var(--bg2);border-right:1px solid var(--border);
         display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0;}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;}
.topbar{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 20px;
        display:flex;align-items:center;gap:12px;flex-shrink:0;}
.content{flex:1;overflow-y:auto;padding:20px;background:var(--bg);}
.logo{padding:18px 16px 14px;border-bottom:1px solid var(--border);}
.logo-title{font-family:var(--font-mono);font-size:14px;font-weight:600;color:var(--cyan);
            letter-spacing:.12em;text-transform:uppercase;}
.logo-sub{font-size:10px;color:var(--text3);margin-top:3px;font-family:var(--font-mono);}
.logo-date{font-size:9px;color:var(--text3);margin-top:6px;font-family:var(--font-mono);}
.q-selector-wrap{padding:12px 14px;border-bottom:1px solid var(--border);}
.q-selector-label{font-size:9px;font-weight:600;color:var(--text3);letter-spacing:.1em;
                  text-transform:uppercase;margin-bottom:5px;font-family:var(--font-mono);}
.q-selector{width:100%;background:var(--bg3);color:var(--text);border:1px solid var(--border);
            border-radius:var(--radius);padding:6px 8px;font-size:11px;cursor:pointer;outline:none;
            font-family:var(--font-mono);}
.q-selector:focus{border-color:var(--cyan);}
.nav-section{padding:14px 16px 4px;font-size:9px;font-weight:600;text-transform:uppercase;
             letter-spacing:.1em;color:var(--text3);font-family:var(--font-mono);}
.nav-item{display:flex;align-items:center;gap:10px;padding:8px 14px;font-size:12px;
          cursor:pointer;transition:all .12s;color:var(--text2);border-left:2px solid transparent;user-select:none;}
.nav-item:hover{background:var(--bg3);color:var(--text);}
.nav-item.active{background:var(--cyan-dim);color:var(--cyan);border-left-color:var(--cyan);font-weight:500;}
.nav-icon{font-size:13px;width:18px;text-align:center;flex-shrink:0;}
.nav-badge{margin-left:auto;font-size:9px;font-family:var(--font-mono);background:var(--bg4);
           color:var(--text3);padding:1px 5px;border-radius:10px;}
.nav-item.active .nav-badge{background:var(--cyan-dim);color:var(--cyan);}
.sidebar-footer{margin-top:auto;padding:12px 14px;border-top:1px solid var(--border);
                font-size:9px;color:var(--text3);font-family:var(--font-mono);}
.page-title{font-size:13px;font-weight:600;color:var(--text);font-family:var(--font-mono);}
.page-title::before{content:'> ';color:var(--cyan);}
.snap-info{font-size:10px;color:var(--text3);font-family:var(--font-mono);background:var(--bg3);
           padding:3px 8px;border-radius:20px;border:1px solid var(--border);}
.spacer{flex:1;}
.gen-at{font-size:10px;color:var(--text3);font-family:var(--font-mono);}
.btn-theme{font-size:10px;padding:5px 12px;background:transparent;color:var(--cyan);
         border:1px solid var(--cyan);border-radius:var(--radius);cursor:pointer;
         transition:all .15s;}
.btn-theme:hover{background:var(--cyan);color:var(--bg);}
.page{display:none;}.page.active{display:block;}
.metrics-row{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;}
.metric-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);
             padding:14px 16px;position:relative;overflow:hidden;transition:border-color .15s;}
.metric-card:hover{border-color:var(--border2);}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;}
.metric-card.c-cyan::before{background:linear-gradient(90deg,var(--cyan),transparent);}
.metric-card.c-red::before{background:linear-gradient(90deg,var(--red),transparent);}
.metric-card.c-green::before{background:linear-gradient(90deg,var(--green),transparent);}
.metric-card.c-violet::before{background:linear-gradient(90deg,var(--violet),transparent);}
.metric-card.c-amber::before{background:linear-gradient(90deg,var(--amber),transparent);}
.metric-label{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.1em;
              font-family:var(--font-mono);margin-bottom:6px;}
.metric-value{font-size:26px;font-weight:700;font-family:var(--font-mono);line-height:1;}
.metric-sub{font-size:9px;color:var(--text3);margin-top:4px;font-family:var(--font-mono);}
.metric-card.c-cyan .metric-value{color:var(--cyan);}
.metric-card.c-red .metric-value{color:var(--red);}
.metric-card.c-green .metric-value{color:var(--green);}
.metric-card.c-violet .metric-value{color:var(--violet);}
.metric-card.c-amber .metric-value{color:var(--amber);}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);
      padding:16px;margin-bottom:12px;}
.card-title{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;
            color:var(--text3);margin-bottom:12px;font-family:var(--font-mono);
            display:flex;align-items:center;gap:6px;}
.card-title::before{content:'▸';color:var(--cyan);font-size:10px;}
.bar-rows{display:flex;flex-direction:column;gap:8px;}
.bar-row{display:flex;align-items:center;gap:8px;}
.bar-label{font-size:11px;min-width:110px;max-width:110px;color:var(--text2);
           overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bar-track{flex:1;height:5px;background:var(--bg4);border-radius:4px;overflow:hidden;}
.bar-fill{height:100%;border-radius:4px;}
.bar-count{font-size:10px;font-weight:600;min-width:22px;text-align:right;
           color:var(--text2);font-family:var(--font-mono);}
.proj-list{display:flex;flex-direction:column;gap:4px;}
.proj-item{display:flex;align-items:center;gap:7px;padding:8px 10px;border-radius:var(--radius);
           border:1px solid transparent;font-size:11px;cursor:pointer;
           transition:all .12s;background:var(--bg3);}
.proj-item:hover{border-color:var(--border2);background:var(--bg4);}
.proj-partage{background:rgba(245, 179, 10, 0.65)!important;border-color:rgba(245,182,56,.3)!important;animation:partage-pulse 2s ease-in-out infinite;}
.proj-partage.traite{background:var(--bg3)!important;border-color:transparent!important;animation:none;}
@keyframes partage-pulse{0%,100%{opacity:1;}50%{opacity:.7;}}
.proj-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.proj-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);}
.proj-resp{font-size:9px;color:var(--text3);min-width:70px;text-align:right;font-family:var(--font-mono);}
.proj-pct{font-size:10px;font-weight:600;color:var(--text2);min-width:32px;
          text-align:right;font-family:var(--font-mono);}
.badge{font-size:9px;padding:2px 7px;border-radius:20px;font-weight:600;white-space:nowrap;
       flex-shrink:0;font-family:var(--font-mono);letter-spacing:.04em;}
.bON_TRACK{background:var(--green-dim);color:var(--green);border:1px solid rgba(16,217,148,.2);}
.bAT_RISK{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2);}
.bLATE{background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2);}
.bDONE{background:var(--violet-dim);color:var(--violet);border:1px solid rgba(139,92,246,.2);}
.bON_HOLD{background:var(--bg4);color:var(--text3);border:1px solid var(--border);}
.bLIVRE{background:var(--green-dim);color:var(--green);border:1px solid rgba(16,217,148,.2);}
.bEN_COURS{background:var(--cyan-dim);color:var(--cyan);border:1px solid rgba(0,212,255,.2);}
.bNON_LIVRE{background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2);}
.bREPORTE{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2);}
.collab-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;}
.collab-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);
             padding:14px;cursor:pointer;transition:all .15s;}
.collab-card:hover{border-color:var(--border2);background:var(--bg3);}
.collab-card.selected{border-color:var(--cyan);box-shadow:0 0 0 1px var(--cyan-dim);}
.avatar{width:36px;height:36px;border-radius:var(--radius);display:flex;align-items:center;
        justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;font-family:var(--font-mono);}
.collab-header{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.collab-name{font-size:12px;font-weight:600;color:var(--text);}
.collab-sub{font-size:9px;color:var(--text3);font-family:var(--font-mono);}
.charge-bar{height:3px;background:var(--bg4);border-radius:3px;overflow:hidden;margin-top:8px;}
.charge-fill{height:100%;border-radius:3px;background:var(--cyan);}
.fchip.active { color: var(--ent-col, var(--cyan)); border-color: var(--ent-col, var(--cyan)); }
.gantt-controls{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;}
.gantt-controls select,.gantt-controls label{font-size:11px;color:var(--text2);font-family:var(--font-mono);}
.gantt-controls select{padding:4px 8px;border:1px solid var(--border);border-radius:var(--radius);
                       background:var(--bg3);color:var(--text);cursor:pointer;}
.gantt-wrap{overflow-x:auto;}
.gantt-table{border-collapse:collapse;min-width:700px;width:100%;font-size:10px;}
.gantt-table th,.gantt-table td{border:0;padding:0;}
.g-label{padding:5px 10px;font-size:10px;color:var(--text2);white-space:nowrap;
         max-width:160px;min-width:160px;overflow:hidden;text-overflow:ellipsis;
         cursor:pointer;font-family:var(--font-mono);}
.g-label:hover{color:var(--cyan);}
.g-header{text-align:center;font-size:9px;color:var(--text3);padding:4px 2px;
          border-bottom:1px solid var(--border);min-width:44px;font-family:var(--font-mono);}
.g-cell{padding:3px 2px;position:relative;min-width:44px;height:28px;vertical-align:middle;}
.g-bar{position:absolute;top:6px;bottom:6px;border-radius:3px;}
.g-now{position:absolute;top:0;width:1.5px;bottom:0;z-index:5;background:var(--red);opacity:.8;}
.g-today-head{border-bottom:2px solid var(--red)!important;color:var(--red)!important;font-weight:700;}
.gantt-legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;}
.gantt-legend span{font-size:9px;color:var(--text3);display:flex;align-items:center;
                   gap:4px;font-family:var(--font-mono);}

.gantt-scroll-wrap{overflow-x:auto;overflow-y:auto;max-height:70vh;cursor:grab;user-select:none;position:relative;}
.gantt-scroll-wrap:active{cursor:grabbing;}
.gantt-labelcol{position:sticky;left:0;z-index:20;background:var(--bg2);
  border-right:1px solid var(--border);box-shadow:2px 0 6px -2px rgba(0,0,0,.18);}
.gantt-lc-head{display:flex;align-items:center;padding:0 12px;font-size:9px;font-weight:600;
  letter-spacing:.1em;color:var(--text3);font-family:var(--font-mono);
  border-bottom:1px solid var(--border);background:var(--bg3);position:sticky;top:0;z-index:2;}
.gantt-lc-group{position:absolute;left:0;right:0;display:flex;align-items:center;padding:0 12px;
  font-size:9px;font-weight:700;letter-spacing:.08em;font-family:var(--font-mono);
  background:var(--bg3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.gantt-lc-proj{position:absolute;left:0;right:0;display:flex;align-items:center;gap:7px;padding:0 12px;
  font-size:10px;font-family:var(--font-mono);color:var(--text2);cursor:pointer;
  overflow:hidden;transition:background .12s;}
.gantt-lc-proj:hover{background:var(--bg3);color:var(--cyan);}
.gantt-lc-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
.gantt-lc-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.gantt-svg-layer{pointer-events:auto;}
.gantt-svg-container{position:relative;}
.gantt-toolbar{display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap;}
.gantt-toolbar select{font-size:11px;padding:4px 8px;border:1px solid var(--border2);
  border-radius:var(--radius);background:var(--bg3);color:var(--text);cursor:pointer;
  font-family:var(--font-mono);}
.granularity-btn{font-size:10px;padding:3px 10px;border-radius:20px;
  border:1px solid var(--border2);color:var(--text2);cursor:pointer;
  background:var(--bg2);font-family:var(--font-mono);transition:all .12s;}
.granularity-btn.active{background:var(--cyan-dim);color:var(--cyan);border-color:var(--cyan);}
.gantt-nav-btn{font-size:13px;padding:3px 12px;background:var(--bg2);
  border:1px solid var(--border2);border-radius:var(--radius);
  color:var(--text);cursor:pointer;font-family:var(--font-mono);transition:all .12s;}
.gantt-nav-btn:hover{border-color:var(--cyan);color:var(--cyan);}
.stat-tab:hover { color: var(--text) !important; }
.stat-tab.active { color: var(--cyan) !important; }
.tl-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);}
.tl-item:last-child{border-bottom:none;}
.tl-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:4px;}
.tl-body{flex:1;}
.tl-title{font-size:12px;font-weight:600;margin-bottom:3px;cursor:pointer;color:var(--text);}
.tl-title:hover{color:var(--cyan);}
.tl-meta{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin-top:3px;}
.modal-overlay{display:none;position:fixed;inset:0;background:var(--view_cadre-dim);
               backdrop-filter:blur(4px);z-index:200;align-items:center;justify-content:center;}
.modal-overlay.open{display:flex;}
.modal{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);
       width:600px;max-width:95vw;max-height:88vh;overflow-y:auto;padding:24px;
       box-shadow:0 24px 64px rgba(0,0,0,.5);}
.modal-close{float:right;cursor:pointer;font-size:16px;color:var(--text3);
             border:none;background:none;line-height:1;padding:0;font-family:var(--font-mono);}
.modal-close:hover{color:var(--text);}
.modal-title{font-size:15px;font-weight:600;margin-bottom:4px;color:var(--text);}
.modal-id{font-size:9px;color:var(--cyan);font-family:var(--font-mono);margin-bottom:10px;}
.modal-row{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px;}
.modal-sec{margin-top:14px;}
.modal-stitle{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;
              color:var(--text3);margin-bottom:6px;font-family:var(--font-mono);}
.modal-stitle::before{content:'▸ ';color:var(--cyan);}
.modal-text{font-size:12px;color:var(--text2);line-height:1.7;}
.prog-track{height:6px;background:var(--bg4);border-radius:4px;overflow:hidden;margin-top:6px;}
.prog-fill{height:100%;border-radius:4px;}
.meta-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px;}
.meta-item{background:var(--bg3);border-radius:var(--radius);padding:7px 10px;}
.meta-key{font-size:8px;color:var(--text3);font-family:var(--font-mono);text-transform:uppercase;
          letter-spacing:.08em;margin-bottom:2px;}
.meta-val{font-size:11px;color:var(--text);font-family:var(--font-mono);}
.hist-row{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);font-size:10px;}
.hist-q{min-width:100px;color:var(--text3);font-family:var(--font-mono);}
.filter-strip{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px;}
.fchip{font-size:10px;padding:3px 10px;border-radius:20px;border:1px solid var(--border);
       color:var(--text2);cursor:pointer;background:var(--bg2);transition:all .12s;font-family:var(--font-mono);}
.fchip:hover{border-color:var(--cyan);color:var(--cyan);}
.fchip.active{background:var(--cyan-dim);color:var(--cyan);border-color:var(--cyan);}
@media(max-width:1100px){.metrics-row{grid-template-columns:repeat(3,1fr);}
@media(max-width:900px){.grid2{grid-template-columns:1fr;}.collab-grid{grid-template-columns:1fr 1fr;}
@media print{
  .sidebar,.topbar,.modal-overlay{display:none!important;}
  .content{overflow:visible;padding:10px;}
  .page{display:block!important;}
  body{background:#fff;color:#000;}
  .card,.metric-card{border:1px solid #ccc;background:#fff;}
}

.trim-block-cal{margin-bottom:0}
.trim-header-cal{padding:6px 14px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:9px;font-weight:600;color:var(--text3);letter-spacing:.07em;display:flex;align-items:center;gap:8px;font-family:var(--font-mono)}
.trim-badge-cal{font-size:9px;padding:1px 7px;border-radius:8px;font-weight:600;font-family:var(--font-mono)}
.jalon-table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed; min-width:400px}
.jalon-table th{padding:8px 24px;text-align:left;font-size:9px;font-weight:600;color:var(--text3);background:var(--bg3);text-transform:uppercase;letter-spacing:.07em;font-family:var(--font-mono)}
.jalon-table td, .jalon-table th{overflow:hidden; text-overflow:ellipsis;white-space:nowrap}
.jalon-table td{padding:16px 16px;border-bottom:1px solid var(--border);color:var(--text);vertical-align:middle}
.jalon-table tr:hover td{background:var(--bg3)}
.jalon-table tr:last-child td{border-bottom:none}


"""


# ── SCRIPT JS ─────────────────────────────────────────────────────────────────

SCRIPT = """
const PALETTE=["#00d4ff","#10d994","#8b5cf6","#f59e0b","#f43f5e","#a855f7","#06b6d4","#84cc16","#fb923c","#e879f9"];
const SC={"En cours":"#10d994","À risque":"#f59e0b","En retard":"#f43f5e","Terminé":"#8b5cf6","Stand by":"#94a3b8"};
const PAGES={overview:"Vue d'ensemble",domaines:"Analyse par domaine",collabs:"Analyse par collaborateur",gantt:"Roadmap",evolutions:"Évolution"};
let selCollab=null;
let selEntiteGantt="";
let ganttGranularity = "month";   
let ganttOffsetPx    = 0;
let ganttTodayX      = 0;
let ganttFiltreStatut = "";
let ganttFiltreEntite = "";
let ganttFiltreDomaine = "";
let ganttFiltreCollab = "";
let ganttGroupBy = "domaine";   // "domaine" | "collab"
let ganttIsDragging  = false;
let ganttDragStartX  = 0;
let ganttDragStartOffset = 0;
 
const GANTT_UNIT_W = { week:40, month:80, quarter:180 };
const GANTT_PAST   = { week:2,  month:4,  quarter:1   };
const GANTT_FUTURE = { week:8, month:10,  quarter:6   };

function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function badge(st){const cls={"En cours":"bEN_COURS","À risque":"bAT_RISK","En retard":"bLATE","Terminé":"bDONE","Stand by":"bON_HOLD"}[st]||"bON_HOLD";return`<span class="badge ${cls}">${st||"—"}</span>`;}
function domColor(d){const ds=[...new Set(DATA.projets.map(p=>p.domaine).filter(Boolean))].sort();return PALETTE[ds.indexOf(d)%PALETTE.length]||PALETTE[0];}
function entColor(e){const es=[...new Set((DATA.entites||[]))].sort();return PALETTE[(es.indexOf(e)+5)%PALETTE.length]||PALETTE[5];}
function respColor(r){const rs=[...new Set(Object.keys(DATA.par_resp||{}))].sort();return PALETTE[(rs.indexOf(r)+3)%PALETTE.length]||PALETTE[3];}
function initials(n){return(n||"??").split(/\\s+/).map(w=>w[0]).join("").toUpperCase().slice(0,2);}
function avStyle(n){const c=[["rgba(0,212,255,.12)","#00d4ff"],["rgba(16,217,148,.12)","#10d994"],["rgba(139,92,246,.12)","#8b5cf6"],["rgba(245,158,11,.12)","#f59e0b"],["rgba(244,63,94,.12)","#f43f5e"],["rgba(168,85,247,.12)","#a855f7"]];const[bg,fg]=c[(n||"X").charCodeAt(0)%c.length];return`background:${bg};color:${fg}`;}
function pp(p){return p.avancement_pct||0;}
function nom(p){return p.projet_nom||p.sujet||"";}
function pid(p){return p.projet_id||p.ref_sujet||"";}
function projItem(p){
  const col=SC[p.statut]||"#475569";
  const prio=p.priorite||p.priorite_meta||"";
  const PRIO_STYLE={
    "ÉLEVÉ":  "background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2)",
    "ELEVE":  "background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2)",
    "MOYEN":  "background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)",
    "FAIBLE": "background:var(--green-dim);color:var(--green);border:1px solid rgba(16,217,148,.2)",
  };
  const prioKey=(prio||"").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  const prioStyle=PRIO_STYLE[prioKey]||PRIO_STYLE[(prio||"").toUpperCase()]||"background:var(--bg4);color:var(--text3);border:1px solid var(--border)";
  const prioTag=prio&&prio!=="nan"?`<span style="font-size:9px;padding:2px 7px;border-radius:20px;font-weight:600;white-space:nowrap;flex-shrink:0;font-family:var(--font-mono);letter-spacing:.04em;${prioStyle}">Priorité : ${esc(prio)}</span>`:"";
  return`<div class="proj-item" onclick="openModal('${esc(pid(p))}')">
    <span class="proj-dot" style="background:${col}"></span>
    <span class="proj-name" title="${esc(nom(p))}">${esc(nom(p))}</span>
    ${badge(p.statut)}
    ${prioTag}
    <span class="proj-resp">${esc(p.responsable_principal||"")}</span>
  </div>`;
}



function switchQuinzaine(q){
  if(!DATA.snapshots||!DATA.snapshots[q])return;
  const snap=DATA.snapshots[q];
  DATA.quinzaine=q;DATA.q_prev=snap.q_prev;DATA.kpis=snap.kpis;DATA.projets=snap.projets;
  DATA.domaines=snap.domaines;DATA.par_domaine=snap.par_domaine;DATA.par_resp=snap.par_resp;DATA.delta=snap.delta;
  DATA.par_entite=snap.par_entite;
  document.getElementById("snap-info").textContent=q+(snap.q_prev?" <- "+snap.q_prev:"");
  document.getElementById("nb-overview").textContent=DATA.projets.length;
  const nbEvol=(DATA.delta||[]).filter(d=>{
  const statutChange=d.statut_avant&&d.statut_apres&&d.statut_avant!==d.statut_apres;
  const avancementChange=d.delta_avancement&&Math.abs(d.delta_avancement)>=5;
  const phaseChange=d.phase_avant&&d.phase_apres&&d.phase_avant!==d.phase_apres;
  return statutChange||avancementChange||phaseChange;
}).length;
  document.getElementById("nb-evol").textContent=nbEvol;
  renderOverview();renderDomaines();renderCollabs();renderEvolutions();
  const gp=document.getElementById("page-gantt");
  if(gp&&gp.innerHTML.trim()!=="")renderGantt();
}

(function init(){
  document.getElementById("logo-date").textContent="Généré le "+DATA.genere_le;
  document.getElementById("gen-at").textContent=DATA.genere_le;
  document.getElementById("snap-info").textContent=DATA.quinzaine+(DATA.q_prev?" <- "+DATA.q_prev:"");
  document.getElementById("nb-overview").textContent=DATA.projets.length;
  const nbEvol=(DATA.delta||[]).filter(d=>{
  const statutChange=d.statut_avant&&d.statut_apres&&d.statut_avant!==d.statut_apres;
  const avancementChange=d.delta_avancement&&Math.abs(d.delta_avancement)>=5;
  const phaseChange=d.phase_avant&&d.phase_apres&&d.phase_avant!==d.phase_apres;
  return statutChange||avancementChange||phaseChange;
}).length;
document.getElementById("nb-evol").textContent=nbEvol;
  document.getElementById("sidebar-footer").textContent=DATA.quinzaines.length+" quinzaine(s) chargee(s)";
  const sel=document.getElementById("q-selector");
  [...DATA.quinzaines].reverse().forEach(q=>{const o=document.createElement("option");o.value=q;o.textContent=q;if(q===DATA.quinzaine)o.selected=true;sel.appendChild(o);});
  document.querySelectorAll(".nav-item[data-page]").forEach(el=>{
    el.addEventListener("click",()=>{
      document.querySelectorAll(".nav-item").forEach(n=>n.classList.remove("active"));
      document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));
      el.classList.add("active");const pg=el.dataset.page;
      document.getElementById("page-"+pg).classList.add("active");
      document.getElementById("page-title").textContent=PAGES[pg];
      if(pg==="gantt")renderGantt();
    });
  });
  document.getElementById("modal-overlay").addEventListener("click",e=>{if(e.target===document.getElementById("modal-overlay"))closeModal();});
  renderOverview();renderDomaines();renderCollabs();renderEvolutions();
})();

function _eclaterEntites(val){
  if(!val||String(val).trim()==="")return[];
  return String(val).split(/[;,]/).map(e=>e.trim()).filter(Boolean);
}

const ENTITE_GROUPE="COFIDIS GROUP";
function _projetMatchEntite(p, ent){
  if(!ent)return true;
  const entites=_eclaterEntites(p.entite_concerne||p.entite_concerne_meta||"");
  // Si le projet est tagué COFIDIS GROUP, il matche toutes les entités
  if(entites.some(e=>e.toUpperCase()===ENTITE_GROUPE))return true;
  return entites.includes(ent);
}

function buildFiltreEntite(prefix){
  const entites=DATA.entites||[];
  if(!entites.length)return"";
  return`<div class="filter-strip" id="fe-${prefix}" style="margin-bottom:8px">
    <span style="font-size:9px;color:var(--text3);line-height:22px;font-family:var(--font-mono)">entité :</span>
    <span class="fchip active" data-ent="" onclick="handleFiltreEntite('${prefix}',this,'')">Toutes</span>
    ${entites.map(e=>`<span class="fchip" data-ent="${esc(e)}" style="--ent-col:${entColor(e)}" onclick="handleFiltreEntite('${prefix}',this,'${esc(e)}')">${esc(e)}</span>`).join("")}
  </div>`;
}

function handleFiltreEntite(prefix, el, ent){
  document.querySelectorAll(`#fe-${prefix} .fchip`).forEach(c=>c.classList.remove("active"));
  el.classList.add("active");
  if(prefix==="ov")filterOverviewByEntite(ent);
  else if(prefix==="dom")filterDomainesByEntite(ent);
  else if(prefix==="col")filterCollabsByEntite(ent);
  else if(prefix==="gantt"){selEntiteGantt=ent;buildGantt();}
}

function attachFiltreEntite(prefix, callback){
  document.querySelectorAll(`#fe-${prefix} .fchip`).forEach(c=>{
    c.onclick=()=>{
      document.querySelectorAll(`#fe-${prefix} .fchip`).forEach(x=>x.classList.remove("active"));
      c.classList.add("active");
      callback(c.dataset.ent||"");
    };
  });
}

function filterOverviewByEntite(ent){
  const PRIO_H=["ÉLEVÉ","ELEVE","ELEVÉ","HIGH"];
  const alertes=DATA.projets.filter(p=>(p.statut==="En retard"||p.statut==="À risque"||p.points_blocage)&&_projetMatchEntite(p,ent));
  const allF=DATA.projets.filter(p=>_projetMatchEntite(p,ent));
  const sortFn=(a,b)=>({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[a.statut]||9)-
                       ({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[b.statut]||9);
  const hasPrio=p=>{const pv=(p.priorite||p.priorite_meta||"").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");return PRIO_H.some(h=>pv.includes(h));};
  const top=[...allF.filter(hasPrio).sort(sortFn),...allF.filter(p=>!hasPrio(p)).sort(sortFn)].slice(0,10);
  const listAl=document.getElementById("ov-proj-list");
  if(listAl)listAl.innerHTML=alertes.map(projItem).join("")||'<div style="font-size:10px;color:var(--text3);padding:8px;font-family:var(--font-mono)">// aucune alerte pour cette entite</div>';
  const listTop=document.getElementById("ov-top-list");
  if(listTop)listTop.innerHTML=top.map(projItem).join("")||'<div style="font-size:10px;color:var(--text3);padding:8px;font-family:var(--font-mono)">// aucun projet pour cette entite</div>';
}

function filterDomainesByEntite(ent){
  document.querySelectorAll(".dom-sec").forEach(s=>{
    if(!ent){s.style.display="";
      // Remettre tous les projets
      const dom=s.dataset.dom;
      const list=s.querySelector(".proj-list");
      if(list)list.innerHTML=DATA.projets.filter(p=>p.domaine===dom).map(projItem).join("");
      return;
    }
    const dom=s.dataset.dom;
    const projFiltres=DATA.projets.filter(p=>p.domaine===dom&&_projetMatchEntite(p,ent));
    if(!projFiltres.length){s.style.display="none";return;}
    s.style.display="";
    const list=s.querySelector(".proj-list");
    if(list)list.innerHTML=projFiltres.map(projItem).join("");
  });
}

function filterCollabsByEntite(ent){
  const filtered=ent?DATA.projets.filter(p=>_projetMatchEntite(p,ent)):DATA.projets;
  const resp=selCollab;
  const detail=filtered.filter(p=>p.responsable_principal===resp);
  const list=document.querySelector("#page-collabs .card .proj-list");
  if(list)list.innerHTML=detail.map(projItem).join("")||'<div style="font-size:10px;color:var(--text3);padding:8px;font-family:var(--font-mono)">// aucun projet pour cette entite</div>';
}

function renderSynthese(q){
  const syntheses=DATA.syntheses||{};
  const s=syntheses[q];
  if(!s||(!s.resume_executif&&!s.brut))return"";
  const texte=s.resume_executif||s.brut||"";
  if(!texte||texte.trim()==="")return"";
  return`<div class="card" style="margin-bottom:12px;border-left:3px solid var(--cyan)">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="card-title" style="margin-bottom:0">Synthèse IA</div>
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">généré par LLM</span>
    </div>
    <div style="font-size:11px;color:var(--text2);line-height:1.8;white-space:pre-wrap">${texte.replace(/</g,"&lt;").replace(/>/g,"&gt;")}</div>
  </div>`;
}


function buildArchivageSection(){
  const arch=DATA.archivage||[];
  if(!arch.length)return"";
  const MFR_S=["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];

  function _formatDate(v){
    if(!v||String(v).trim()===""||String(v)==="nan"||String(v)==="None")return"";
    const s=String(v).trim();
    const parts=s.includes("/")?s.split("/"):s.includes("-")?s.split("-").reverse():null;
    if(!parts||parts.length!==3)return s;
    try{
      const dt=new Date(parts[2],parts[1]-1,parts[0]);
      if(isNaN(dt.getTime()))return"";
      return"clôt. "+dt.getDate()+" "+MFR_S[dt.getMonth()]+" "+dt.getFullYear();
    }catch(e){return"";}
  }

  function _valide(v){
    return v&&String(v).trim()!==""&&String(v)!=="nan"&&String(v)!=="None"&&String(v)!=="undefined";
  }

  function buildListe(items, titre){
    if(!items.length)return"";
    return`<div class="card" style="margin-bottom:8px">
      <div class="card-title">${titre} (${items.length})</div>
      <div class="proj-list">
        ${items.map(a=>{
          const entites=_eclaterEntites(a.entite_concerne||"").filter(_valide);
          const dateStr=_formatDate(a.date_fin);
          const domaine=_valide(a.domaine)?a.domaine:"";
          return`<div class="proj-item" onclick="openModalArchivage('${esc(a.projet_id||a.ref_sujet)}')">
            <span class="proj-dot" style="background:var(--violet)"></span>
            <span class="proj-name">${esc(a.projet_nom||a.sujet||"")}</span>
            <span class="badge bDONE">Terminé</span>
            ${domaine?`<span style="font-size:9px;padding:1px 5px;border-radius:8px;background:var(--bg4);color:var(--text3);font-family:var(--font-mono)">${esc(domaine)}</span>`:""}
            ${entites.slice(0,2).map(e=>`<span style="font-size:9px;padding:1px 5px;border-radius:8px;background:var(--violet-dim);color:var(--violet);border:1px solid rgba(124,58,237,.2);font-family:var(--font-mono)">${esc(e)}</span>`).join("")}
            ${dateStr?`<span class="proj-resp">${dateStr}</span>`:""}
          </div>`;
        }).join("")}
      </div>
    </div>`;
  }

  const projetsArch=arch.filter(a=>{
    const t=(a.type||a.type_meta||"").toUpperCase().trim();
    return t==="PROJET";
  });
  const autresArch=arch.filter(a=>{
    const t=(a.type||a.type_meta||"").toUpperCase().trim();
    return t!=="PROJET"&&t!=="";
  });

  return buildListe(projetsArch,"projets archivés — 12 mois glissants")
       + buildListe(autresArch,"autres sujets archivés — 12 mois glissants");
}


function openModalArchivage(pid){
  const a=(DATA.archivage||[]).find(x=>(x.projet_id||x.ref_sujet)===pid);
  if(!a)return;
  const entites=_eclaterEntites(a.entite_concerne||"");
  const collabsTemp=a.collaborateurs_temporaires?String(a.collaborateurs_temporaires).split(/[;,]/).map(c=>c.trim()).filter(Boolean):[];
  document.getElementById("modal-body").innerHTML=`
    <button class="modal-close" onclick="closeModal()">x</button>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span class="badge bDONE">Archivé</span>
      ${entites.map(e=>`<span style="font-size:9px;padding:2px 6px;border-radius:8px;background:var(--violet-dim);color:var(--violet);border:1px solid rgba(139,92,246,.2)">${esc(e)}</span>`).join("")}
    </div>
    <div class="modal-title">${esc(a.projet_nom||a.sujet||pid)}</div>
    <div class="modal-id">${esc(a.projet_id||a.ref_sujet||"")}</div>
    <div class="modal-row">
      ${a.domaine?`<span class="badge bON_HOLD">${esc(a.domaine)}</span>`:""}
      ${a.priorite?`<span class="badge bON_HOLD">prio:${esc(a.priorite)}</span>`:""}
      ${a.eta_projet?`<span class="badge bDONE">${esc(a.eta_projet)}</span>`:""}
    </div>
    <div class="modal-sec"><div class="modal-stitle">informations projet</div>
      <div class="meta-grid">
        ${[["responsable",a.responsable_principal],["date début",a.date_debut],["date fin prév.",a.date_fin],["effectifs",a.effectifs],["type",a.type]].filter(([,v])=>v&&v!=="undefined"&&v!=="nan").map(([k,v])=>`<div class="meta-item"><div class="meta-key">${k}</div><div class="meta-val">${esc(v)}</div></div>`).join("")}
      </div>
    </div>
    ${collabsTemp.length?`<div class="modal-sec"><div class="modal-stitle">collaborateurs temporaires</div>
      <div style="display:flex;gap:4px;flex-wrap:wrap">${collabsTemp.map(c=>`<span style="font-size:10px;padding:2px 8px;border-radius:12px;background:var(--bg3);color:var(--text2);border:1px solid var(--border2)">${esc(c)}</span>`).join("")}</div>
    </div>`:""}
    ${a.eta_intervention?`<div class="modal-sec"><div class="modal-stitle">période d'intervention</div><div class="modal-text">${esc(a.eta_intervention)}</div></div>`:""}
    ${a.description?`<div class="modal-sec"><div class="modal-stitle">description</div><div class="modal-text" style="color:var(--text3)">${esc(a.description)}</div></div>`:""}
  `;
  document.getElementById("modal-overlay").classList.add("open");
}


  function openModalNouveauProjet(pid){console.log("openModalNouveauProjet appelée avec :", pid)
  const np=(DATA.meta||[]).find(x=>(x.projet_id||x.ref_sujet)===pid)
  ||(DATA.projets||[]).find(x=>(x.projet_id||x.ref_sujet)===pid)
  if(!np)return;
  const m=(DATA.meta||[]).find(x=>(x.projet_id||x.ref_sujet)===pid)||{};
  document.getElementById("modal-body").innerHTML=`
    <button class="modal-close" onclick="closeModal()">x</button>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span class="badge" style="background:var(--cyan-dim);color:var(--cyan);border:1px solid var(--cyan)">NOUVEAU</span>
      ${(()=>{
          if(!np.priorite||np.priorite==="nan")return"";
          const pv=np.priorite.toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
          const s=pv.includes("ELEVE")?"background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2)":
          pv.includes("MOYEN")?"background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)":
          pv.includes("FAIBLE")?"background:var(--green-dim);color:var(--green);border:1px solid rgba(16,217,148,.2)":
          "background:var(--bg4);color:var(--text3);border:1px solid var(--border)";
          return'<span class="badge" style="'+s+'">Priorité : '+esc(np.priorite)+'</span>';
    })()}
    </div>
    <div class="modal-title">${esc(np.projet_nom||np.projet_id)}</div>
    <div class="modal-id">${esc(np.projet_id)}</div>
    <div class="modal-row">
      ${np.domaine&&np.domaine!=="nan"?`<span class="badge bON_HOLD">${esc(np.domaine)}</span>`:""}
    </div>
    <div class="modal-sec"><div class="modal-stitle">informations projet</div>
      <div class="meta-grid">
        ${[
          ["responsable",np.responsable_principal],
          ["date début",np.date_debut],
          ["entité",np.entite_concerne],
          ["type",np.type],
          ["effectifs",m.effectifs],
        ].filter(([,v])=>v&&v!=="nan"&&v!=="None").map(([k,v])=>
          `<div class="meta-item"><div class="meta-key">${k}</div><div class="meta-val">${esc(v)}</div></div>`
        ).join("")}
      </div>
    </div>
    ${m.collaborateurs_temporaires&&m.collaborateurs_temporaires!=="nan"?
      `<div class="modal-sec"><div class="modal-stitle">collaborateurs temporaires</div>
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          ${String(m.collaborateurs_temporaires).split(/[;,]/).map(c=>c.trim()).filter(Boolean)
            .map(c=>`<span style="font-size:10px;padding:2px 8px;border-radius:12px;background:var(--bg3);color:var(--text2);border:1px solid var(--border2)">${esc(c)}</span>`).join("")}
        </div>
      </div>`:""}
      ${m.description&&m.description!=="nan"?`<div class="modal-sec"><div class="modal-stitle">description</div><div class="modal-text" style="color:var(--text3)">${esc(m.description)}</div></div>`:""}
  `;
  document.getElementById("modal-overlay").classList.add("open");};


function renderOverview(){
  const k=DATA.kpis||{};const P=DATA.projets||[];
  const km=DATA.kpis_meta||{};

  
   const dateRef=dateDeQuinzaine(DATA.quinzaine);
const seuilDebut=new Date(dateRef.getTime()-30*24*3600*1000);
const seuilFin=new Date(dateRef.getTime()+90*24*3600*1000);

function parseDateNP(s){
  if(!s||s==="nan"||s==="None")return null;
  const p=String(s).trim().split("/");
  if(p.length===3)return new Date(+p[2],+p[1]-1,+p[0]);
  try{return new Date(s);}catch(e){return null;}
}

function dateDeQuinzaine(q){
  const m=(q||"").match(/T\\d_(\\d{4})_R\\d+_S(\\d+)/);
  if(!m)return new Date();
  const annee=+m[1],semaine=+m[2];
  const jan4=new Date(annee,0,4);
  const lundi=new Date(jan4);
  lundi.setDate(jan4.getDate()+(semaine-1)*7-(jan4.getDay()||7)+1);
  return lundi;
}

const NP=(DATA.meta||[]).filter(m=>{
  const t=(m.type||"").toUpperCase().trim();
  if(t&&t!=="PROJET"&&t!=="NAN"&&t!=="")return false;
  const dDebut=parseDateNP(m.date_debut);
  if(!dDebut)return false;
  return dDebut>=seuilDebut&&dDebut<=seuilFin;
});


  const ARCH=DATA.archivage||[];
  const maxD=Object.values(DATA.par_domaine||{}).length?Math.max(...Object.values(DATA.par_domaine).map(d=>d.total),1):1;
  const maxR=Object.values(DATA.par_resp||{}).length?Math.max(...Object.values(DATA.par_resp).map(r=>r.total),1):1;

  // ── Approche "tous types de sujets" (plus centrée projet) ──────────
  const norm=s=>String(s||"").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").trim();
  const typeLabel=t=>{const u=norm(t);return (u===""||u==="NAN")?"NON DÉFINI":u;};

  // Tous les sujets actifs de la quinzaine (indépendamment du type)
  const sujetsActifs=P.filter(p=>{const s=(p.statut||"").trim();return s!=="Terminé"&&s!=="Stand by";});
  const nbSujetsActifs=sujetsActifs.length;

  // Ventilation par type (s'adapte aux nouveaux types ajoutés à la main)
  const ventil={};
  sujetsActifs.forEach(p=>{const t=typeLabel(p.type||p.type_meta);ventil[t]=(ventil[t]||0)+1;});
  const ventilTri=Object.entries(ventil).sort((a,b)=>b[1]-a[1]);

  // À risque / en retard : TOUS types désormais
  const nbRetard=P.filter(p=>p.statut==="En retard").length;
  const nbRisque=P.filter(p=>p.statut==="À risque").length;

  // Terminés (archivage) : tous types
  const nbTermines=(DATA.archivage||[]).length;

  // ── Échéances proches (< 30 j) : date_prevision puis date_fin ──────
  const now=new Date();
  const h30=new Date(now.getTime()+30*24*3600*1000);
  function dEch(p){return parseDateNP(p.date_prevision||p.date_prevision_meta||p.date_fin||p.date_fin_meta);}
  const echeancesProches=sujetsActifs.filter(p=>{const d=dEch(p);return d&&d>=now&&d<=h30;});
  const nbEcheances=echeancesProches.length;

  const nbNouveaux=NP.length;

  const PRIO_HAUTE=["ÉLEVÉ","ELEVE","ELEVÉ","ÉLEVEE","HIGH"];
  const topPrio=[...P].filter(p=>{
    const pv=norm(p.priorite||p.priorite_meta);
    return PRIO_HAUTE.some(h=>pv.includes(h));
  }).sort((a,b)=>({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[a.statut]||9)-
                  ({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[b.statut]||9));
  const autresPrio=[...P].filter(p=>{
    const pv=norm(p.priorite||p.priorite_meta);
    return !PRIO_HAUTE.some(h=>pv.includes(h));
  }).sort((a,b)=>({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[a.statut]||9)-
                  ({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[b.statut]||9));
  const top=[...topPrio,...autresPrio].slice(0,10);

  // Alertes : sur TOUS les sujets (retard, risque, ou blocage), plus seulement les projets
  const alertes=P.filter(p=>p.statut==="En retard"||p.statut==="À risque"||p.points_blocage);

  // Ventilation formatée pour le sous-texte (abréviations lisibles)
  const abbr={"PROJET":"proj","GOUVERNANCE":"gouv","OUTILS":"outil","OUTIL":"outil",
              "FORMATION":"form","VEILLE":"veille","COMMUNICATION":"com","NON DÉFINI":"n/d"};
  const ventilSub=ventilTri.slice(0,5).map(([t,n])=>`${n} ${abbr[t]||t.toLowerCase().slice(0,5)}`).join(" · ");

  document.getElementById("page-overview").innerHTML=`
    <div class="metrics-row" style="grid-template-columns:repeat(6,1fr)">
      <div class="metric-card c-cyan">
        <div class="metric-label">sujets en cours</div>
        <div class="metric-value">${nbSujetsActifs}</div>
        <div class="metric-sub">tous types</div>
      </div>
      <div class="metric-card c-red">
        <div class="metric-label">à risque / retard</div>
        <div class="metric-value">${nbRetard+nbRisque}</div>
        <div class="metric-sub">${nbRetard} retard · ${nbRisque} risque</div>
      </div>
      <div class="metric-card c-green">
        <div class="metric-label">terminés</div>
        <div class="metric-value">${nbTermines}</div>
        <div class="metric-sub">dans les 12 derniers mois</div>
      </div>
      <div class="metric-card c-violet">
        <div class="metric-label">par type</div>
        <div class="metric-value">${ventilTri.length}</div>
        <div class="metric-sub">${esc(ventilSub||"—")}</div>
      </div>
      <div class="metric-card c-amber">
        <div class="metric-label">échéances proches</div>
        <div class="metric-value">${nbEcheances}</div>
        <div class="metric-sub">projection &lt; 30 j</div>
      </div>
      <div class="metric-card c-cyan">
        <div class="metric-label">nouveaux</div>
        <div class="metric-value">${nbNouveaux}</div>
        <div class="metric-sub">derniers 30 j</div>
      </div>
    </div>
    ${alertes.length?`<div class="card"><div class="card-title">alertes actives (${alertes.length})</div><div class="proj-list" style="max-height:220px;overflow-y:auto" id="ov-proj-list">${alertes.map(projItem).join("")}</div></div>`:""}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px">
     <div class="card"><div class="card-title">par entité</div>
        <div class="bar-rows">${Object.entries(DATA.par_entite||{}).sort((a,b)=>b[1].total-a[1].total).map(([e,s])=>`
          <div class="bar-row" style="max-height:200px;overflow-y:auto">
            <span class="bar-label" title="${esc(e)}">${esc(e)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.round(s.total/Math.max(...Object.values(DATA.par_entite).map(x=>x.total),1)*100)}%;background:${entColor(e)}"></div></div>
            <span class="bar-count">${s.total}</span>
          </div>`).join("")}</div>
      </div>
      <div class="card"><div class="card-title">par domaine</div>
        <div class="bar-rows">${Object.entries(DATA.par_domaine).sort((a,b)=>b[1].total-a[1].total).map(([d,s])=>`
          <div class="bar-row" style="max-height:200px;overflow-y:auto">
            <span class="bar-label" title="${esc(d)}">${esc(d)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.round(s.total/maxD*100)}%;background:${domColor(d)}"></div></div>
            <span class="bar-count">${s.total}</span>
          </div>`).join("")}</div>
      </div>
      <div class="card"><div class="card-title">par responsable</div>
        <div class="bar-rows">${Object.entries(DATA.par_resp).sort((a,b)=>b[1].total-a[1].total).map(([r,s])=>`
          <div class="bar-row" style="max-height:200px;overflow-y:auto">
            <span class="bar-label" title="${esc(r)}">${esc(r)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.round(s.total/maxR*100)}%;background:${respColor(r)}"></div></div>
            <span class="bar-count">${s.total}</span>
          </div>`).join("")}</div>
      </div>
      
    </div>
    ${NP.length?`<div class="card"><div class="card-title">nouveaux projets  (${NP.length})</div>
      <div class="proj-list" style="max-height:180px;overflow-y:auto">
        ${NP.map(np=>`<div class="proj-item" style="cursor:pointer" onclick="openModalNouveauProjet('${esc(np.projet_id)}')">
          <span class="proj-dot" style="background:var(--cyan)"></span>
          <span class="proj-name">${esc(np.projet_nom||np.projet_id)}</span>
          <span style="font-size:9px;font-family:var(--font-mono);color:var(--cyan);white-space:nowrap">NOUVEAU</span>
          ${(()=>{
  const pv=(np.priorite||"").trim();
  if(!pv||pv==="nan")return"";
  const PRIO_STYLE={
    "ÉLEVÉ":"background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2)",
    "ELEVE":"background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,.2)",
    "MOYEN":"background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)",
    "FAIBLE":"background:var(--green-dim);color:var(--green);border:1px solid rgba(16,217,148,.2)",
  };
  const key=pv.toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  const style=PRIO_STYLE[key]||"background:var(--bg4);color:var(--text3);border:1px solid var(--border)";
  return`<span style="font-size:9px;padding:2px 7px;border-radius:20px;font-weight:600;white-space:nowrap;font-family:var(--font-mono);${style}">Priorité : ${esc(pv)}</span>`;
})()}
          <span class="proj-resp">${esc(np.responsable_principal||"")}</span>
        </div>`).join("")}
      </div></div>`:""}
    <div class="card"><div class="card-title">projets — vue prioritaire (${top.length})</div><div class="proj-list" style="max-height:320px;overflow-y:auto" id="ov-top-list">${top.map(projItem).join("")}</div></div>
    ${renderSynthese(DATA.quinzaine)}
    ${buildArchivageSection()}`;

}



function renderDomaines(){
  let html=buildFiltreEntite("dom")+'<div class="filter-strip" id="df"><span class="fchip active" data-val="">Tous</span>'+DATA.domaines.map(d=>'<span class="fchip" data-val="'+esc(d)+'">'+esc(d)+'</span>').join('')+'</div>';
  html+=DATA.domaines.map(dom=>{
    const entActive=document.querySelector("#fe-dom .fchip.active")?.dataset?.ent||"";
    const pr=DATA.projets.filter(p=>p.domaine===dom&&_projetMatchEntite(p,entActive));
    const s=DATA.par_domaine[dom]||{};
    let badges='';
    if(s.en_cours)badges+=`<span class="badge bEN_COURS">${s.en_cours} En cours</span>`;
    if(s.a_risque)badges+=`<span class="badge bAT_RISK">${s.a_risque} À risque</span>`;
    if(s.late)badges+=`<span class="badge bLATE">${s.late} En retard</span>`;
    if(s.terminé)badges+=`<span class="badge bDONE">${s.terminé} Terminé</span>`;
    return`<div class="card dom-sec" data-dom="${esc(dom)}"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px"><div style="display:flex;align-items:center;gap:8px"><span style="width:8px;height:8px;border-radius:50%;background:${domColor(dom)};flex-shrink:0"></span><span style="font-size:12px;font-weight:600;color:var(--text);font-family:var(--font-mono)">${esc(dom)}</span></div><div style="display:flex;gap:4px;flex-wrap:wrap">${badges}</div></div><div class="proj-list">${pr.map(projItem).join("")}</div></div>`;
  }).join("");
  document.getElementById("page-domaines").innerHTML=html;
  document.querySelectorAll("#df .fchip").forEach(c=>{c.addEventListener("click",()=>{document.querySelectorAll("#df .fchip").forEach(x=>x.classList.remove("active"));c.classList.add("active");const v=c.dataset.val;document.querySelectorAll(".dom-sec").forEach(s=>{s.style.display=(!v||s.dataset.dom===v)?"":"none";});});});
}

function marquerTraite(el){
  const item=el.closest(".proj-item");
  if(item)item.classList.add("traite");
}

function renderCollabs(sel){
  sel=sel||selCollab||Object.keys(DATA.par_resp)[0]||"";selCollab=sel;

  // ── Collaborateurs actifs (quinzaine courante) ───────────────────
  const resps=Object.entries(DATA.par_resp).sort((a,b)=>b[1].total-a[1].total);
  const maxE=Math.max(...resps.map(([,r])=>r.en_cours||0),1);

  // ── Collaborateurs absents (présents dans historique mais pas cette quinzaine) ──
  const respActifs=new Set(DATA.projets.map(p=>p.responsable_principal).filter(Boolean));
const quinzaineActive=DATA.quinzaine||"";
const respHistorique={};
Object.values(DATA.historiques||{}).forEach(rows=>{
  rows.forEach(r=>{
    const resp=r.responsable_principal;
    // Ignorer les quinzaines postérieures à la quinzaine active
    if(resp&&!respActifs.has(resp)&&r.quinzaine<quinzaineActive){
      if(!respHistorique[resp]||r.quinzaine>respHistorique[resp].quinzaine)
        respHistorique[resp]=r;
    }
  });
});

  // ── Détail du collaborateur sélectionné ─────────────────────────
  // Cherche dans quinzaine active puis dans historique si absent
  let detail=DATA.projets.filter(p=>p.responsable_principal===sel)
    .sort((a,b)=>({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[a.statut]||9)-
                  ({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[b.statut]||9));
  let isAbsent=false;
  if(!detail.length&&respHistorique[sel]){
    // Collaborateur absent — afficher ses projets de la dernière quinzaine connue
    const lastQ=respHistorique[sel].quinzaine;
    const snap=DATA.snapshots[lastQ];
    detail=(snap?.projets||[]).filter(p=>p.responsable_principal===sel)
      .sort((a,b)=>({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[a.statut]||9)-
                    ({"En retard":0,"À risque":1,"En cours":2,"Stand by":3,"Terminé":4}[b.statut]||9));
    isAbsent=true;
    
  }

  // ── Cartes collaborateurs absents ────────────────────────────────
  const absentCards=Object.entries(respHistorique).sort().map(([name,lastRow])=>`
    <div class="collab-card ${name===sel?"selected":""}" onclick="renderCollabs('${esc(name)}')"
         style="opacity:.65;border-style:dashed">
      <div class="collab-header">
        <div class="avatar" style="background:${respColor(name)}22;color:${respColor(name)}">${initials(name)}</div>
        <div>
          <div class="collab-name">${esc(name)}</div>
          <div class="collab-sub" style="color:var(--amber)">Absent cette quinzaine</div>
          <div style="font-size:8px;color:var(--text3);font-family:var(--font-mono)">
            dernier suivi : ${esc(lastRow.quinzaine)}
          </div>
        </div>
      </div>
      <div class="charge-bar"><div class="charge-fill" style="width:0%;background:var(--amber)"></div></div>
    </div>`).join("");

  document.getElementById("page-collabs").innerHTML=`
    <div class="collab-grid">
      ${resps.map(([name,r])=>`
        <div class="collab-card ${name===sel?"selected":""}" onclick="renderCollabs('${esc(name)}')">
          <div class="collab-header">
            <div class="avatar" style="background:${respColor(name)}22;color:${respColor(name)}">${initials(name)}</div>
            <div>
              <div class="collab-name">${esc(name)}</div>
              <div class="collab-sub">${r.nb_projets||r.total} proj · ${r.nb_autres||0} autres · ${r.en_cours||0} actif${(r.en_cours||0)>1?"s":""}</div>
            </div>
          </div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px">
            ${(r.domaines||[]).slice(0,3).map(d=>`<span style="font-size:9px;padding:2px 6px;border-radius:10px;background:var(--bg4);color:var(--text3);font-family:var(--font-mono)">${esc(d)}</span>`).join("")}
          </div>
          <div class="charge-bar"><div class="charge-fill" style="width:${Math.round((r.en_cours||0)/maxE*100)}%;background:${respColor(name)}"></div></div>
        </div>`).join("")}
      ${absentCards}
    </div>
    ${isAbsent?`<div style="font-size:10px;color:var(--amber);font-family:var(--font-mono);margin-bottom:8px;padding:6px 10px;background:var(--amber-dim);border-radius:var(--radius);border:1px solid rgba(245,158,11,.2)">
      ⚠ ${esc(sel)} est absent cette quinzaine — données de la dernière quinzaine renseignée
    </div>`:""}
    <div class="card">
      <div class="card-title">projets :: ${esc(sel)} (${detail.filter(p=>{const t=(p.type||p.type_meta||"").toUpperCase().trim();return t==="PROJET"||t===""||t==="NAN";}).length})</div>
      <div class="proj-list">
        ${(()=>{
        const lastQ=respHistorique[sel]?.quinzaine||"";
const lastQAbs=isAbsent?(respHistorique[sel]?.quinzaine||""):"";
const projItemFn=p=>{
  const partage=(p.partage_prochain_point||"").toString().toLowerCase().trim();
  const aPartager=partage==="oui"||partage==="yes"||partage==="1";
  let html=projItem(p);
  // Absent : rediriger vers modal historique
  if(isAbsent){
    const id=p.projet_id||p.ref_sujet;
    html=html.replace(`openModal('${esc(id)}')`,`openModalHistorique('${esc(id)}','${esc(lastQAbs)}')`);
  }
  // Partage prochain point 
  if(aPartager){
    const id=p.projet_id||p.ref_sujet;
  html=html.replace('class="proj-item"','class="proj-item proj-partage"');
  // Rediriger le onclick pour marquer comme traité
  if(isAbsent){
    html=html.replace(
      `onclick="openModalHistorique('${esc(id)}','${esc(lastQAbs)}')"`,
      `onclick="marquerTraite(this);openModalHistorique('${esc(id)}','${esc(lastQAbs)}')"`
    );
  } else {
    html=html.replace(
      `onclick="openModal('${esc(id)}')"`,
      `onclick="marquerTraite(this);openModal('${esc(id)}')"`
    );
  }
  html=html.replace('</div>',`<span style="font-size:9px;background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.3);padding:1px 5px;border-radius:8px;font-family:var(--font-mono);flex-shrink:0;margin-left:auto">!!! à partager</span></div>`);
}
  return html;
};
const projets=detail.filter(p=>{const t=(p.type||p.type_meta||"").toUpperCase().trim();return t==="PROJET"||t===""||t==="NAN";});
const autres=detail.filter(p=>{const t=(p.type||p.type_meta||"").toUpperCase().trim();return t!=="PROJET"&&t!==""&&t!=="NAN";});
return (projets.length?projets.map(projItemFn).join(""):"")

            +(autres.length?`<div style="font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);font-family:var(--font-mono);padding:8px 0 4px">autres sujets (${autres.length})</div>`+autres.map(projItemFn).join(""):"")
            ||'<div style="color:var(--text3);font-size:11px;font-family:var(--font-mono);padding:8px">// aucun projet</div>';
        })()}
      </div>
    </div>`;
}

 
function renderGantt(){
  const el = document.getElementById("page-gantt");
  if(!el) return;
  el.innerHTML = `
    <div class="gantt-toolbar">
      <button class="gantt-nav-btn" onclick="ganttNav(-3)">&#8249;&#8249;</button>
      <button class="gantt-nav-btn" onclick="ganttNav(-1)">&#8249;</button>
      <button class="gantt-nav-btn" onclick="ganttGoToday()">Aujourd'hui</button>
      <button class="gantt-nav-btn" onclick="ganttNav(1)">&#8250;</button>
      <button class="gantt-nav-btn" onclick="ganttNav(3)">&#8250;&#8250;</button>
      <div style="flex:1"></div>
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">granularité :</span>
      <button class="granularity-btn " id="gbtn-week"    onclick="setGranularity('week')">Semaine</button>
      <button class="granularity-btn active"        id="gbtn-month"   onclick="setGranularity('month')">Mois</button>
      <button class="granularity-btn"        id="gbtn-quarter" onclick="setGranularity('quarter')">Trimestre</button>
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono);margin-left:8px">statut :</span>
      <select id="gf" onchange="ganttFiltreStatut=this.value;buildGantt()">
        <option value="">Tous</option>
        <option value="En cours">En cours</option>
        <option value="À risque">À risque</option>
        <option value="En retard">En retard</option>
        <option value="Terminé">Terminé</option>
      </select>
      ${(DATA.entites||[]).length?`
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">entité :</span>
      <select id="ge" onchange="ganttFiltreEntite=this.value;buildGantt()">
        <option value="">Toutes</option>
        ${(DATA.entites||[]).map(e=>`<option value="${esc(e)}">${esc(e)}</option>`).join("")}
      </select>`:""}
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono);margin-left:8px">vue :</span>
      <button class="granularity-btn" id="gbtn-ent" onclick="setGanttGroup('entite')">Entité</button>
      <button class="granularity-btn active" id="gbtn-dom" onclick="setGanttGroup('domaine')">Domaine</button>
      <button class="granularity-btn" id="gbtn-col" onclick="setGanttGroup('collab')">Collaborateur</button>
      <select id="gdom" onchange="ganttFiltreDomaine=this.value;buildGantt()" style="margin-left:8px">
        <option value="">Tous domaines</option>
        ${(DATA.domaines||[]).map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join("")}
      </select>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <div id="gantt-scroll-area" class="gantt-scroll-wrap">
        <div id="gantt-inner"></div>
      </div>
    </div>
    <div class="gantt-legend" id="gl"></div>`;
 
  // Démarrer en vue mois par défaut
  ganttGranularity = "month";
  ganttOffsetPx    = 0;
  buildGantt();
  _attachGanttScroll();
  // Centrer sur aujourd'hui au premier affichage
  setTimeout(ganttGoToday, 30);
}
 
function setGranularity(g){
  ganttGranularity = g;
  ganttOffsetPx    = 0;
  document.querySelectorAll(".granularity-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById("gbtn-"+g)?.classList.add("active");
  buildGantt();
}
 
function setGanttGroup(g){
  ganttGroupBy=g;
  document.getElementById("gbtn-dom")?.classList.toggle("active", g==="domaine");
  document.getElementById("gbtn-col")?.classList.toggle("active", g==="collab");
  document.getElementById("gbtn-ent")?.classList.toggle("active", g==="entite");
  buildGantt();
}

function ganttNav(n){
  const area=document.getElementById("gantt-scroll-area");
  if(!area)return;
  const uw=GANTT_UNIT_W[ganttGranularity]||80;
  area.scrollBy({left:n*uw*2, behavior:"smooth"});
}

function ganttGoToday(){
  const area=document.getElementById("gantt-scroll-area");
  if(!area)return;
  const containerW=area.getBoundingClientRect().width;
  // ganttTodayX = position pixel de la ligne "aujourd'hui" dans le SVG
  const target=Math.max(0, (ganttTodayX||0) - containerW*0.4);
  area.scrollTo({left:target, behavior:"smooth"});
}
 
function _attachGanttScroll(){
  const area = document.getElementById("gantt-scroll-area");
  if(!area || area._dragBound) return;
  area._dragBound = true;

  let isDrag=false, startX=0, startY=0, sLeft=0, sTop=0;

  area.addEventListener("mousedown", e=>{
    isDrag=true; area.style.cursor="grabbing";
    startX=e.clientX; startY=e.clientY;
    sLeft=area.scrollLeft; sTop=area.scrollTop;
    e.preventDefault();
  });
  window.addEventListener("mouseup", ()=>{ isDrag=false; area.style.cursor="grab"; });
  window.addEventListener("mousemove", e=>{
    if(!isDrag)return;
    area.scrollLeft = sLeft - (e.clientX-startX);
    area.scrollTop  = sTop  - (e.clientY-startY);
  });

  // Molette verticale → scroll horizontal quand pas de deltaX
  area.addEventListener("wheel", e=>{
    if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){
      area.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }, {passive:false});
}
 
function buildGantt(){
  const inner = document.getElementById("gantt-inner");
  if(!inner) return;
 
  const uw    = GANTT_UNIT_W[ganttGranularity] || 80;
  const past  = GANTT_PAST[ganttGranularity]   || 3;
  const fut   = GANTT_FUTURE[ganttGranularity] || 9;
  const now   = new Date();
  const ROW_H = 28;
  const HDR_H = 48;
  const LBL_W = 170;
  const MFR   = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];
  const TRIM  = ["T1","T2","T3","T4"];
 
  // ── Générer les unités temporelles ──────────────────────────────────
  function startOfWeek(d){
    const r=new Date(d);r.setDate(r.getDate()-(r.getDay()||7)+1);
    r.setHours(0,0,0,0);return r;
  }
 
  let units = [];  // { label, start, end }
  if(ganttGranularity === "week"){
    const origin = startOfWeek(now);
    for(let i=-past*4; i<=fut*4; i++){
      const s = new Date(origin); s.setDate(s.getDate()+i*7);
      const e = new Date(s); e.setDate(e.getDate()+6);
      units.push({ label: s.getDate()+"/"+MFR[s.getMonth()], start:new Date(s), end:new Date(e) });
    }
  } else if(ganttGranularity === "month"){
    for(let i=-past; i<=fut; i++){
      const s = new Date(now.getFullYear(), now.getMonth()+i, 1);
      const e = new Date(now.getFullYear(), now.getMonth()+i+1, 0);
      units.push({ label: MFR[s.getMonth()]+"'"+String(s.getFullYear()).slice(2), start:new Date(s), end:new Date(e) });
    }
  } else {
    for(let i=-past; i<=fut; i++){
      const qBase = Math.floor(now.getMonth()/3);
      const qOff  = qBase + i;
      const yr    = now.getFullYear() + Math.floor(qOff/4);
      const qIdx  = ((qOff%4)+4)%4;
      const s     = new Date(yr, qIdx*3, 1);
      const e     = new Date(yr, qIdx*3+3, 0);
      units.push({ label: TRIM[qIdx]+" "+yr, start:new Date(s), end:new Date(e) });
    }
  }
 
  const totalUnits = units.length;
  const RIGHT_PAD = 
      ganttGranularity === "week" ? 40 :
      ganttGranularity === "month" ? 20 :
      10
  const svgW = LBL_W + totalUnits * uw + RIGHT_PAD;
 
  // ── Position pixel d'une date ────────────────────────────────────────
  const rangeStart = units[0].start;
  const rangeEnd   = units[units.length-1].end;
  const rangeMs    = rangeEnd - rangeStart;
  function xPos(d){
      const ratio = Math.max (
      0,
      Math.min(1, (d- rangeStart) / rangeMs)
      );
    return LBL_W + ratio * (totalUnits *uw - RIGHT_PAD);
  }
 
  // ── Position "aujourd'hui" ───────────────────────────────────────────
  const todayX = xPos(now);
 
  // ── Filtrer projets avec dates valides ───────────────────────────────
  const metaById={};
  (DATA.meta||[]).forEach(m=>{ metaById[m.projet_id||m.ref_sujet]=m; });
 
  function parseDate(s){
    if(!s||String(s).trim()===""||String(s)==="nan")return null;
    const v=String(s).trim();
    const parts=v.includes("/")?v.split("/"):null;
    if(parts&&parts.length===3)return new Date(parts[2],parts[1]-1,parts[0]);
    try{return new Date(v);}catch(e){return null;}
  }
 
  let projets = DATA.projets.filter(p=>{
    if(ganttFiltreStatut&&p.statut!==ganttFiltreStatut) return false;
    if(ganttFiltreEntite&&!_projetMatchEntite(p,ganttFiltreEntite)) return false;
    if(ganttFiltreDomaine&&p.domaine!==ganttFiltreDomaine) return false;
    if(ganttFiltreCollab&&p.responsable_principal!==ganttFiltreCollab) return false;
    const m = metaById[p.projet_id||p.ref_sujet]||{};
    const deb = parseDate(p.date_debut||m.date_debut);
    const fin = parseDate(p.date_fin||m.date_fin);
    return deb&&fin; // masquer sans dates
  });
 
  // ── Grouper selon ganttGroupBy ──────────────────────────────────────
  const groups={};
  projets.forEach(p=>{
    const k=ganttGroupBy==="collab"
      ?(p.responsable_principal||"Non assigné")
      :ganttGroupBy==="entite"
      ?(_eclaterEntites(p.entite_concerne||"")[0]||"Non assigné")
      :(p.domaine||"Autre");
    if(!groups[k])groups[k]=[];
    groups[k].push(p);
  });
 
  // ── Calcul hauteur totale SVG ────────────────────────────────────────
  let totalRows = 0;
  Object.values(groups).forEach(items=>{ totalRows += 1 + items.length; });
  const svgH = HDR_H + totalRows * ROW_H + 20;

  // Collecte des libellés de lignes pour la colonne fixe (sticky)
  const rowLabels = [];  // {y, type:'group'|'proj', label, color, pid}

  // ── Construction SVG ─────────────────────────────────────────────────
  let svg = `<svg xmlns="http://www.w3.org/2000/svg"
    width="${svgW}" height="${svgH}"
    style="display:block">`;
 
  // Fond et grille verticale
  svg += `<rect width="100%" height="100%" fill="var(--bg2)"/>`;
 
  // En-têtes unités
  units.forEach((u,i)=>{
    const x = LBL_W + i*uw;
    const isNow = u.start <= now && now <= u.end;
    svg += `<rect x="${x}" y="0" width="${uw}" height="${HDR_H}"
      fill="${isNow?"var(--cyan-dim)":"var(--bg3)"}"
      stroke="var(--border)" stroke-width="0.5"/>`;
    svg += `<text x="${x+uw/2}" y="${HDR_H/2+4}" text-anchor="middle"
      font-size="10" fill="${isNow?"var(--cyan)":"var(--text3)"}"
      font-family="var(--font-mono)" font-weight="${isNow?"600":"400"}">${u.label}</text>`;
    // Ligne verticale grille
    svg += `<line x1="${x}" y1="${HDR_H}" x2="${x}" y2="${svgH}"
      stroke="var(--border)" stroke-width="0.5" opacity="0.45"/>`;
  });
 
  // Bandeau coin haut-gauche (au-dessus de la colonne sticky) — dans le SVG on ne dessine plus les libellés
  // La grille démarre sous l'en-tête ; la colonne de gauche est gérée en HTML sticky.

  // Lignes projets
  let rowIdx = 0;
  Object.entries(groups).sort().forEach(([grp,items],gi)=>{
    const gc = PALETTE[gi%PALETTE.length];
    const gy = HDR_H + rowIdx * ROW_H;

    // Bandeau de groupe (fond) sur toute la largeur timeline
    svg += `<rect x="${LBL_W}" y="${gy}" width="${svgW-LBL_W}" height="${ROW_H}"
      fill="var(--bg3)"/>`;
    svg += `<line x1="${LBL_W}" y1="${gy+ROW_H}" x2="${svgW}" y2="${gy+ROW_H}"
      stroke="var(--border)" stroke-width="0.5"/>`;
    rowLabels.push({y:gy, h:ROW_H, type:"group", label:grp, color:gc});
    rowIdx++;

    items.forEach(p=>{
      const ry  = HDR_H + rowIdx * ROW_H;
      const col = SC[p.statut]||gc;
      const m   = metaById[p.projet_id||p.ref_sujet]||{};
      const deb = parseDate(p.date_debut||m.date_debut);
      const fin = parseDate(p.date_fin||m.date_fin);
      const prev = parseDate(p.date_prevision||m.date_prevision);
      const pv  = p.avancement_pct||0;
      const isOver  = fin < now && p.statut!=="Terminé";
      const isSoon  = fin > now && (fin-now)<30*24*3600*1000;
      const x1  = xPos(deb);
      const x2  = Math.max(xPos(fin), x1+4);
      const bw  = x2-x1;

      // Fond ligne alternée (zone timeline uniquement)
      svg += `<rect x="${LBL_W}" y="${ry}" width="${svgW-LBL_W}" height="${ROW_H}"
        fill="${rowIdx%2===0?"var(--bg3)":"transparent"}" opacity="${rowIdx%2===0?"0.35":"1"}"/>`;
      svg += `<line x1="${LBL_W}" y1="${ry+ROW_H}" x2="${svgW}" y2="${ry+ROW_H}"
        stroke="var(--border)" stroke-width="0.3" opacity="0.6"/>`;

      rowLabels.push({y:ry, h:ROW_H, type:"proj", label:nom(p), color:col,
                      pid:(p.projet_id||p.ref_sujet), statut:p.statut});

      // Barre projet
      if(bw>0){
        if(isOver){
          // Barre pointillée pour projets dépassés
          svg += `<rect x="${x1}" y="${ry+6}" width="${bw}" height="${ROW_H-14}"
            fill="none" stroke="${col}" stroke-width="1.5"
            stroke-dasharray="4,3" rx="3"/>`;
        } else {
          // Barre pleine (track clair + remplissage avancement)
          svg += `<rect x="${x1}" y="${ry+6}" width="${bw}" height="${ROW_H-14}"
            fill="${col}" rx="3" opacity="0.30"/>`;
          if(pv>0){
            svg += `<rect x="${x1}" y="${ry+6}" width="${bw*Math.min(pv,100)/100}" height="${ROW_H-14}"
              fill="${col}" rx="3"/>`;
          }
          svg += `<rect x="${x1}" y="${ry+6}" width="${bw}" height="${ROW_H-14}"
            fill="none" stroke="${col}" stroke-width="1" rx="3" opacity="0.9"/>`;
          // Label pourcentage si assez large
          if(bw>30){
            svg += `<text x="${x1+bw/2}" y="${ry+ROW_H/2+4}" text-anchor="middle"
              font-size="9" font-weight="600" fill="var(--text)" font-family="var(--font-mono)"
              pointer-events="none">${pv}%</text>`;
          }
        }
        // Point rouge échéance proche
        if(isSoon){
          svg += `<circle cx="${x2}" cy="${ry+ROW_H/2}" r="4"
            fill="var(--red)" stroke="var(--bg2)" stroke-width="1.5"/>`;
        }
        // Losange de projection (date_prevision) — repère avant la date de fin
        if(prev){
          const xp=xPos(prev);
          // n'afficher que si la projection tombe dans la fenêtre visible
          if(xp>=LBL_W-6 && xp<=svgW+6){
            const cyD=ry+ROW_H/2, r=4.5;
            const prevAvantFin = prev<=fin;
            svg += `<path d="M ${xp} ${cyD-r} L ${xp+r} ${cyD} L ${xp} ${cyD+r} L ${xp-r} ${cyD} Z"
              fill="${prevAvantFin?"var(--amber)":"var(--red)"}" stroke="var(--bg2)" stroke-width="1.2">
              <title>projection : ${esc(String(p.date_prevision||m.date_prevision||""))}${prevAvantFin?"":" (après la date de fin !)"}</title>
            </path>`;
          }
        }
      }
      rowIdx++;
    });
  });
 
  // Ligne aujourd'hui — par-dessus tout (limitée à la zone timeline)
  svg += `<line x1="${todayX}" y1="0" x2="${todayX}" y2="${svgH}"
    stroke="var(--red)" stroke-width="1.5" opacity="0.8" stroke-dasharray="4,3"/>`;
  svg += `<text x="${todayX+4}" y="12" font-size="8" fill="var(--red)"
    font-weight="600" font-family="var(--font-mono)">auj.</text>`;
 
  svg += `</svg>`;

  // ── Colonne de libellés fixe (sticky) ────────────────────────────────
  let labelCol = `<div class="gantt-labelcol" style="width:${LBL_W}px;height:${svgH}px">`;
  // En-tête colonne
  labelCol += `<div class="gantt-lc-head" style="height:${HDR_H}px">PROJET</div>`;
  rowLabels.forEach(r=>{
    if(r.type==="group"){
      labelCol += `<div class="gantt-lc-group" style="top:${r.y}px;height:${r.h}px;color:${r.color}">${esc((r.label||"").toUpperCase())}</div>`;
    } else {
      labelCol += `<div class="gantt-lc-proj" style="top:${r.y}px;height:${r.h}px" title="${esc(r.label)}" onclick="openModal('${esc(r.pid)}')">`+
        `<span class="gantt-lc-dot" style="background:${r.color}"></span>`+
        `<span class="gantt-lc-name">${esc(r.label)}</span></div>`;
    }
  });
  labelCol += `</div>`;

  // Injection — colonne sticky (gauche) + SVG timeline
  ganttTodayX = todayX;
  inner.style.position="relative";
  inner.style.width=svgW+"px";
  inner.innerHTML = labelCol + `<div class="gantt-svg-layer" style="margin-top:${-svgH}px;margin-left:0">${svg}</div>`;

  // Légende
  const gl = document.getElementById("gl");
  if(gl){
    gl.innerHTML =
      `<span><i style="width:12px;height:0;border-top:1.5px dashed var(--red);display:inline-block"></i> aujourd'hui</span>`+
      `<span><i style="width:12px;height:8px;border:1.5px dashed var(--text3);border-radius:2px;display:inline-block"></i> échéance dépassée</span>`+
      `<span><i style="width:6px;height:6px;border-radius:50%;background:var(--red);display:inline-block"></i> échéance &lt;30j</span>`+
      `<span><i style="width:8px;height:8px;background:var(--amber);display:inline-block;transform:rotate(45deg);margin:0 2px"></i> date prévisionnelle</span>`+
      `<span style="color:var(--text3);font-family:var(--font-mono);font-size:9px">glisser ou molette pour naviguer</span>`;
  }
}

function computeStats(){
  const snaps=DATA.snapshots||{};
  const qs=DATA.quinzaines||[];
  const hist=DATA.historiques||{};
  const meta=DATA.meta||[];

  // ── Série temporelle : une entrée par quinzaine ──────────────────
  const serie=qs.map(q=>{
    const s=snaps[q]||{};
    const k=s.kpis||{};
    const p=s.projets||[];
    const total=p.length||1;
    const enDiff=(k.nb_at_risk||0)+(k.nb_en_retard||0);
    const livres=p.filter(x=>x.livrable_statut==="LIVRE").length;
    const nonLivres=p.filter(x=>x.livrable_statut==="NON LIVRE").length;
    const reportes=p.filter(x=>x.livrable_statut==="REPORTE").length;
    const avecLivrable=p.filter(x=>x.livrable_statut&&x.livrable_statut.trim()!=="").length;
    return {
      q,
      avancement:k.avancement_moyen||0,
      tauxDiff:Math.round(enDiff/total*100),
      nbDiff:enDiff,
      nbBlocages:k.nb_blocages||0,
      nbDecisions:k.nb_decisions||0,
      nbActifs:k.nb_projets_actifs||0,
      livres, nonLivres, reportes, avecLivrable,
      tauxLivre:avecLivrable>0?Math.round(livres/avecLivrable*100):null,
      parDomaine:s.par_domaine||{},
      parResp:s.par_resp||{},
      projets:p,
    };
  });

  // ── Nouveaux projets par quinzaine ────────────────────────────────
  // Pour chaque quinzaine Q, un projet est "nouveau" s'il apparaît
  // dans Q mais pas dans les quinzaines antérieures
  const serieNouveaux=[];
  const idsVus=new Set();
  qs.forEach(q=>{
    const projIds=new Set(
      (snaps[q]?.projets||[])
        .filter(p=>{const t=(p.type||p.type_meta||"").toUpperCase();return t===""||t==="PROJET"||t==="NAN";})
        .map(p=>p.projet_id||p.ref_sujet)
        .filter(Boolean)
    );
    let nbNew=0;
    projIds.forEach(id=>{if(!idsVus.has(id)){nbNew++;idsVus.add(id);}});
    serieNouveaux.push({q,nbNew,nbCumul:idsVus.size});
  });

  // ── Vélocité par domaine : delta avancement moyen entre quinzaines ─
  const domaines=[...new Set(qs.flatMap(q=>(snaps[q]?.projets||[]).map(p=>p.domaine).filter(Boolean)))];
  const velociteDomaine={};
  domaines.forEach(dom=>{
    const pts=[];
    for(let i=1;i<qs.length;i++){
      const avant=(snaps[qs[i-1]]?.projets||[]).filter(p=>p.domaine===dom);
      const apres=(snaps[qs[i]]?.projets||[]).filter(p=>p.domaine===dom);
      if(!avant.length||!apres.length)continue;
      const avMap={};avant.forEach(p=>avMap[p.projet_id||p.ref_sujet]=p.avancement_pct||0);
      const deltas=apres.map(p=>{const id=p.projet_id||p.ref_sujet;return avMap[id]!=null?(p.avancement_pct||0)-avMap[id]:null;}).filter(x=>x!=null);
      if(deltas.length)pts.push(deltas.reduce((a,b)=>a+b,0)/deltas.length);
    }
    velociteDomaine[dom]=pts.length?Math.round(pts.reduce((a,b)=>a+b,0)/pts.length*10)/10:null;
  });

  // ── Signaux faibles ───────────────────────────────────────────────
  const signauxFaibles=[];
  Object.entries(hist).forEach(([pid,rows])=>{
    if(rows.length<2)return;
    const sorted=[...rows].sort((a,b)=>a.quinzaine.localeCompare(b.quinzaine));
    const nom=sorted[0].projet_nom||sorted[0].sujet||pid;

    // Stagnation : delta < 5% sur 2 quinzaines consécutives
    for(let i=1;i<sorted.length;i++){
      const delta=Math.abs((sorted[i].avancement_pct||0)-(sorted[i-1].avancement_pct||0));
      if(delta<5&&sorted[i].statut!=="Terminé"&&sorted[i].statut!=="Stand by"){
        signauxFaibles.push({
          type:"STAGNATION",
          nom, pid,
          detail:`Avancement stable (Δ${Math.round(delta)}%) entre ${sorted[i-1].quinzaine} et ${sorted[i].quinzaine}`,
          statut:sorted[i].statut, quinzaine:sorted[i].quinzaine,
        });
        break;
      }
    }

    // Oscillation : statut change ≥ 3 fois
    const changements=sorted.filter((r,i)=>i>0&&r.statut!==sorted[i-1].statut).length;
    if(changements>=3){
      signauxFaibles.push({
        type:"OSCILLATION",
        nom, pid,
        detail:`Statut a changé ${changements} fois sur ${sorted.length} quinzaines`,
        statut:sorted[sorted.length-1].statut,
        quinzaine:sorted[sorted.length-1].quinzaine,
      });
    }

    // Trainards : ≥ 3 quinzaines consécutives En retard ou À risque
    let streak=0,maxStreak=0;
    sorted.forEach(r=>{
      if(r.statut==="En retard"||r.statut==="À risque"){streak++;maxStreak=Math.max(maxStreak,streak);}
      else streak=0;
    });
    if(maxStreak>=3){
      signauxFaibles.push({
        type:"TRAINARD",
        nom, pid,
        detail:`${maxStreak} quinzaines consécutives en difficulté`,
        statut:sorted[sorted.length-1].statut,
        quinzaine:sorted[sorted.length-1].quinzaine,
      });
    }
  });

  // Concentration charge : responsable avec > 40% des projets actifs
  const dernierSnap=serie[serie.length-1]||{};
  const parResp=dernierSnap.parResp||{};
  const totalActifs=Object.values(parResp).reduce((s,r)=>s+r.total,0)||1;
  const concentrations=Object.entries(parResp)
    .map(([r,d])=>{return{resp:r,n:d.total,pct:Math.round(d.total/totalActifs*100)};  })
    .filter(x=>x.pct>40);

  return {serie, velociteDomaine, signauxFaibles, concentrations, domaines, serieNouveaux};
}

// ── SVG helpers ────────────────────────────────────────────────────────

function svgLine(points,color,h=120,pad=30){
  if(points.length<2)return"";
  const vals=points.map(p=>p.y);
  const min=Math.min(...vals),max=Math.max(...vals);
  const range=max-min||1;
  const w=points.length>1?(points[points.length-1].x-points[0].x):1;
  const pts=points.map(p=>{
    const x=pad+(p.x-points[0].x)/(w||1)*(400-pad*2);
    const y=pad+(1-(p.y-min)/range)*(h-pad*2);
    return`${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const first=pts.split(" ")[0],last=pts.split(" ").pop();
  const [lx,ly]=last.split(",");
  const [fx,fy]=first.split(",");
  return`<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <polygon points="${pts} ${lx},${h-pad} ${fx},${h-pad}" fill="${color}" opacity="0.08"/>
    ${points.map((p,i)=>{const[px,py]=pts.split(" ")[i].split(",");return`<circle cx="${px}" cy="${py}" r="3" fill="${color}" stroke="var(--bg2)" stroke-width="1.5"/>`;}  ).join("")}`;
}

function svgChart(serie,keyFn,color,label,unit="%",h=140){
  if(!serie.length)return`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:12px">// données insuffisantes</div>`;
  const pad=32;const W=400;
  const points=serie.map((s,i)=>({x:i,y:keyFn(s),label:s.q}));
  const vals=points.map(p=>p.y);
  const min=Math.min(...vals),max=Math.max(...vals);
  const range=max-min||1;

  // Ticks sans doublons
  const rawTicks=[0,.25,.5,.75,1].map(t=>min+t*range);
  const ticks=[...new Set(rawTicks.map(t=>Math.round(t)))];

  // Coordonnées X cohérentes entre points et labels
  const xOf=i=>pad+i/(points.length-1||1)*(W-pad*2);
  const yOf=v=>pad+(1-(v-min)/range)*(h-pad*2);

  const ptsStr=points.map(p=>`${xOf(p.x).toFixed(1)},${yOf(p.y).toFixed(1)}`).join(" ");
  const [lx]=ptsStr.split(" ").pop().split(",");
  const [fx]=ptsStr.split(" ")[0].split(",");

  return`<svg viewBox="0 0 ${W} ${h}" style="width:100%;height:${h}px;overflow:visible">
    <defs><linearGradient id="g${label.replace(/\\s/g,"_")}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity=".3"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    ${ticks.map(t=>{const y=yOf(t);
      return`<line x1="${pad}" y1="${y.toFixed(1)}" x2="${W-10}" y2="${y.toFixed(1)}" stroke="var(--border)" stroke-width="0.5"/>
        <text x="${pad-4}" y="${(y+3).toFixed(1)}" text-anchor="end" font-size="8" fill="var(--text3)" font-family="var(--font-mono)">${t}${unit}</text>`;
    }).join("")}
    <polyline points="${ptsStr}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <polygon points="${ptsStr} ${lx},${h-pad} ${fx},${h-pad}" fill="${color}" opacity="0.08"/>
    ${points.map((p,i)=>`
      <circle cx="${xOf(i).toFixed(1)}" cy="${yOf(p.y).toFixed(1)}" r="3" fill="${color}" stroke="var(--bg2)" stroke-width="1.5"/>
      <text x="${xOf(i).toFixed(1)}" y="${h-4}" text-anchor="middle" font-size="7.5" fill="var(--text3)" font-family="var(--font-mono)">${p.label.replace(/_/g," ")}</text>
    `).join("")}
  </svg>`;
}

function barChart(items,color){
  if(!items.length)return`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// aucune donnée</div>`;
  const max=Math.max(...items.map(i=>i.val),1);
  return items.sort((a,b)=>b.val-a.val).map(item=>{
    const pct=Math.round(item.val/max*100);
    const color2=item.color||color;
    return`<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">
      <span style="font-size:10px;min-width:110px;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2)" title="${esc(item.label)}">${esc(item.label)}</span>
      <div style="flex:1;height:6px;background:var(--bg4);border-radius:4px;overflow:hidden">
        <div style="width:${pct}%;height:100%;border-radius:4px;background:${color2};transition:width .5s ease"></div>
      </div>
      <span style="font-size:10px;font-weight:600;min-width:32px;text-align:right;font-family:var(--font-mono);color:var(--text2)">${item.val}${item.unit||""}</span>
    </div>`;
  }).join("");
}

function jauge(val,max,color,label,sublabel=""){
  const pct= val / max;
  const angle= Math.PI * pct;
  const r=38;const cx=50;const cy=50;
  const x=cx + r * Math.cos(Math.PI + angle);
  const y=cy + r * Math.sin(Math.PI + angle);
  const large=pct>50?1:0;
  return`<div style="text-align:center">
    <svg viewBox="0 0 100 70" style="width:90px;height:63px">
      <path d="M${cx-r},${cy} A${r},${r} 0 1 1 ${cx+r},${cy}" fill="none" stroke="var(--bg4)" stroke-width="8" stroke-linecap="round"/>
      ${pct>0?`<path d="M${cx-r},${cy} A${r},${r} 0 ${large} 1 ${x.toFixed(1)},${y.toFixed(1)}" fill="none" stroke="${color}" stroke-width="8" stroke-linecap="round"/>`:"" }
      <text x="50" y="52" text-anchor="middle" font-size="14" font-weight="700" fill="${color}" font-family="var(--font-mono)">${val}${max===100?"%":""}</text>
    </svg>
    <div style="font-size:10px;font-weight:600;color:var(--text);margin-top:-6px">${label}</div>
    ${sublabel?`<div style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">${sublabel}</div>`:""}
  </div>`;
}

// ── Render principal ────────────────────────────────────────────────────

function renderStats(){
  const el=document.getElementById("page-stats");
  if(!el)return;
  const st=computeStats();
  const s=st.serie;
  const last=s[s.length-1]||{};
  const hasHist=s.length>=2;

  // Sous-onglets
  const TABS=[
    {id: "carte" , label:"Carte"},
    {id:"signaux", label:"Signaux faibles"},
  ];
  let activeTab="carte";


  el.innerHTML=`
    <div style="display:flex;gap:4px;margin-bottom:14px;border-bottom:1px solid var(--border);padding-bottom:0" id="stats-tabs">
      ${TABS.map(t=>`<div class="stat-tab${t.id===activeTab?" active":""}" data-tab="${t.id}"
        style="font-size:11px;padding:7px 14px;cursor:pointer;font-family:var(--font-mono);
        border-bottom:2px solid ${t.id===activeTab?"var(--cyan)":"transparent"};
        color:${t.id===activeTab?"var(--cyan)":"var(--text3)"};
        margin-bottom:-1px;transition:all .12s"
        onclick="switchStatTab('${t.id}')">${t.label}</div>`).join("")}
    </div>
    <div id="stats-body"></div>`;

 function renderTab(){
    const body=document.getElementById("stats-body");if(!body)return;
    if(activeTab==="signaux") body.innerHTML=renderSignaux(st,last);
    else if(activeTab==="carte")renderCarteOnglet()
    
  }
  
  window.switchStatTab=function(tab){
    activeTab=tab;
    document.querySelectorAll(".stat-tab").forEach(t=>{
      const isActive=t.dataset.tab===tab;
      t.style.borderBottom=isActive?"2px solid var(--cyan)":"2px solid transparent";
      t.style.color=isActive?"var(--cyan)":"var(--text3)";
    });
    renderTab();
  };
  renderTab();
}

// ── Onglet Santé ────────────────────────────────────────────────────────

function buildRepDomaine(last){
  const P=last.projets||[];
  const byDom={};
  P.forEach(p=>{
    const d=p.domaine||"Autre";
    if(!byDom[d])byDom[d]={total:0,statuts:{}};
    byDom[d].total++;
    byDom[d].statuts[p.statut]=(byDom[d].statuts[p.statut]||0)+1;
  });
  const max=Math.max(...Object.values(byDom).map(d=>d.total),1);
  return Object.entries(byDom).sort((a,b)=>b[1].total-a[1].total).map(([d,data])=>{
    const pct=Math.round(data.total/max*100);
    const tags=Object.entries(data.statuts).sort((a,b)=>b[1]-a[1])
      .map(([st,n])=>`<span style="font-size:8px;padding:1px 5px;border-radius:8px;background:${SC[st]||"#475569"}22;color:${SC[st]||"#475569"};border:1px solid ${SC[st]||"#475569"}44">${st}:${n}</span>`).join(" ");
    return`<div style="margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
        <span style="font-size:10px;min-width:100px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2)" title="${esc(d)}">${esc(d)}</span>
        <div style="flex:1;height:5px;background:var(--bg4);border-radius:4px;overflow:hidden">
          <div style="width:${pct}%;height:100%;border-radius:4px;background:${domColor(d)}"></div>
        </div>
        <span style="font-size:10px;font-weight:600;min-width:20px;text-align:right;font-family:var(--font-mono);color:var(--text2)">${data.total}</span>
      </div>
      <div style="padding-left:106px;display:flex;gap:3px;flex-wrap:wrap">${tags}</div>
    </div>`;
  }).join("");
}

function buildRepCollab(last){
  const P=last.projets||[];
  const byCol={};
  P.forEach(p=>{
    const r=p.responsable_principal||"Non assigné";
    if(!byCol[r])byCol[r]={total:0,statuts:{}};
    byCol[r].total++;
    byCol[r].statuts[p.statut]=(byCol[r].statuts[p.statut]||0)+1;
  });
  const max=Math.max(...Object.values(byCol).map(d=>d.total),1);
  return Object.entries(byCol).sort((a,b)=>b[1].total-a[1].total).map(([r,data])=>{
    const pct=Math.round(data.total/max*100);
    const col=respColor(r);
    const tags=Object.entries(data.statuts).sort((a,b)=>b[1]-a[1])
      .map(([st,n])=>`<span style="font-size:8px;padding:1px 5px;border-radius:8px;background:${SC[st]||"#475569"}22;color:${SC[st]||"#475569"};border:1px solid ${SC[st]||"#475569"}44">${st}:${n}</span>`).join(" ");
    return`<div style="margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
        <span style="font-size:10px;min-width:100px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2)" title="${esc(r)}">${esc(r)}</span>
        <div style="flex:1;height:5px;background:var(--bg4);border-radius:4px;overflow:hidden">
          <div style="width:${pct}%;height:100%;border-radius:4px;background:${col}"></div>
        </div>
        <span style="font-size:10px;font-weight:600;min-width:20px;text-align:right;font-family:var(--font-mono);color:var(--text2)">${data.total}</span>
      </div>
      <div style="padding-left:106px;display:flex;gap:3px;flex-wrap:wrap">${tags}</div>
    </div>`;
  }).join("");
}

const EUROPE_GEOJSON = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"iso":"FRA","nom":"France","focus":true},"geometry":{"type":"MultiPolygon","coordinates":[[[[2.537,51.065],[2.608,50.961],[2.587,50.845],[2.787,50.723],[2.887,50.697],[3.129,50.779],[3.232,50.696],[3.271,50.527],[3.608,50.477],[3.697,50.298],[4.003,50.344],[4.198,50.258],[4.126,50.128],[4.21,50.06],[4.132,49.975],[4.435,49.932],[4.646,49.984],[4.682,50.084],[4.816,50.161],[4.872,50.14],[4.784,49.958],[4.86,49.913],[4.849,49.794],[5.259,49.691],[5.456,49.499],[5.746,49.549],[5.961,49.441],[6.194,49.499],[6.403,49.465],[6.512,49.425],[6.714,49.159],[6.914,49.207],[7.043,49.108],[7.274,49.105],[7.41,49.169],[7.635,49.038],[8.2,48.959],[8.09,48.808],[7.81,48.615],[7.751,48.341],[7.586,48.13],[7.621,47.971],[7.512,47.707],[7.586,47.585],[7.379,47.431],[6.973,47.489],[6.867,47.354],[7.037,47.33],[6.665,47.021],[6.443,46.944],[6.429,46.761],[6.118,46.583],[6.054,46.419],[6.135,46.37],[6.094,46.253],[5.955,46.2],[5.959,46.13],[6.14,46.15],[6.281,46.24],[6.214,46.315],[6.269,46.375],[6.483,46.449],[6.787,46.414],[6.75,46.346],[6.828,46.269],[6.766,46.152],[7.022,45.925],[6.801,45.826],[6.796,45.718],[6.963,45.641],[6.983,45.511],[7.161,45.411],[7.055,45.214],[6.603,45.103],[6.723,45.013],[6.745,44.908],[7.007,44.822],[7.055,44.685],[6.96,44.683],[6.836,44.534],[6.918,44.436],[6.866,44.372],[6.983,44.242],[7.331,44.125],[7.656,44.176],[7.69,44.067],[7.478,43.866],[7.476,43.765],[7.152,43.655],[7.139,43.554],[6.962,43.54],[6.894,43.428],[6.731,43.408],[6.591,43.269],[6.693,43.273],[6.68,43.202],[6.402,43.147],[6.375,43.091],[6.193,43.109],[6.18,43.036],[5.941,43.134],[5.879,43.12],[5.951,43.08],[5.857,43.045],[5.674,43.18],[5.347,43.216],[5.369,43.27],[5.294,43.355],[5.034,43.335],[5.026,43.409],[5.226,43.48],[5.029,43.559],[5.051,43.429],[4.868,43.421],[4.901,43.367],[4.856,43.342],[4.758,43.422],[4.742,43.524],[4.695,43.579],[4.743,43.423],[4.82,43.346],[4.592,43.36],[4.513,43.456],[4.182,43.464],[4.105,43.552],[3.953,43.54],[3.513,43.281],[3.318,43.263],[3.114,43.106],[3.039,42.943],[3.042,42.629],[3.181,42.431],[2.934,42.47],[2.69,42.406],[2.662,42.339],[2.515,42.326],[2.277,42.429],[1.996,42.349],[1.927,42.437],[1.712,42.494],[1.765,42.563],[1.722,42.61],[1.543,42.649],[1.429,42.595],[1.343,42.709],[1.151,42.707],[0.813,42.832],[0.656,42.838],[0.644,42.684],[0.354,42.717],[0.275,42.669],[0.169,42.726],[-0.039,42.685],[-0.323,42.843],[-0.569,42.773],[-0.76,42.947],[-1.15,43.006],[-1.294,43.055],[-1.286,43.109],[-1.366,43.033],[-1.457,43.045],[-1.404,43.243],[-1.622,43.247],[-1.796,43.374],[-1.661,43.4],[-1.477,43.58],[-1.257,44.556],[-1.187,44.665],[-1.045,44.669],[-1.172,44.778],[-1.26,44.627],[-1.085,45.569],[-0.766,45.326],[-0.716,45.135],[-0.535,44.895],[-0.596,45.025],[-0.494,44.998],[-0.656,45.099],[-0.795,45.477],[-1.247,45.71],[-1.23,45.792],[-1.164,45.807],[-0.987,45.717],[-1.152,45.868],[-1.073,45.904],[-1.111,46.018],[-1.049,46.039],[-1.211,46.175],[-1.111,46.303],[-1.24,46.284],[-1.795,46.495],[-1.91,46.692],[-2.119,46.82],[-2.129,46.893],[-1.991,47.035],[-2.241,47.142],[-2.165,47.168],[-2.161,47.271],[-2.015,47.3],[-1.804,47.219],[-1.727,47.211],[-2.01,47.32],[-2.278,47.246],[-2.542,47.3],[-2.436,47.307],[-2.556,47.383],[-2.392,47.424],[-2.495,47.491],[-2.364,47.506],[-2.632,47.52],[-2.599,47.529],[-2.577,47.554],[-2.817,47.499],[-2.909,47.558],[-2.741,47.551],[-2.689,47.604],[-2.684,47.623],[-2.707,47.643],[-2.919,47.596],[-2.975,47.664],[-2.94,47.561],[-3.123,47.599],[-3.085,47.478],[-3.132,47.478],[-3.201,47.64],[-3.118,47.732],[-3.193,47.746],[-3.159,47.711],[-3.224,47.656],[-3.358,47.697],[-3.283,47.691],[-3.358,47.711],[-3.283,47.787],[-3.446,47.705],[-3.528,47.78],[-3.852,47.801],[-3.962,47.9],[-4.037,47.855],[-4.132,47.924],[-4.111,47.869],[-4.186,47.874],[-4.185,47.813],[-4.372,47.807],[-4.347,47.863],[-4.435,47.976],[-4.728,48.041],[-4.285,48.115],[-4.379,48.232],[-4.485,48.243],[-4.557,48.177],[-4.547,48.253],[-4.626,48.287],[-4.547,48.347],[-4.516,48.296],[-4.269,48.288],[-4.187,48.308],[-4.325,48.322],[-4.269,48.363],[-4.454,48.335],[-4.29,48.432],[-4.768,48.345],[-4.765,48.52],[-4.577,48.568],[-4.564,48.63],[-4.194,48.65],[-3.974,48.733],[-3.955,48.658],[-3.852,48.63],[-3.81,48.733],[-3.585,48.683],[-3.528,48.739],[-3.582,48.791],[-3.515,48.842],[-3.398,48.807],[-3.23,48.872],[-3.221,48.794],[-3.091,48.871],[-3.125,48.76],[-3.008,48.821],[-3.042,48.788],[-2.933,48.767],[-2.682,48.509],[-2.316,48.699],[-2.33,48.63],[-2.251,48.65],[-2.214,48.582],[-2.052,48.65],[-1.98,48.514],[-1.953,48.575],[-2.029,48.643],[-1.946,48.699],[-1.844,48.712],[-1.861,48.641],[-1.796,48.616],[-1.357,48.643],[-1.554,48.747],[-1.603,48.849],[-1.508,49.034],[-1.594,49.029],[-1.61,49.216],[-1.548,49.225],[-1.625,49.219],[-1.699,49.356],[-1.816,49.384],[-1.885,49.531],[-1.84,49.62],[-1.935,49.724],[-1.607,49.65],[-1.263,49.696],[-1.228,49.624],[-1.306,49.558],[-1.123,49.345],[-0.94,49.392],[-0.219,49.28],[0.411,49.452],[0.493,49.494],[0.257,49.464],[0.077,49.535],[0.236,49.729],[1.221,49.979],[1.521,50.215],[1.673,50.193],[1.542,50.278],[1.61,50.371],[1.555,50.405],[1.61,50.548],[1.581,50.869],[1.921,50.997],[2.537,51.065]],[[1.948,42.451],[1.999,42.444],[1.957,42.482],[1.948,42.451]]],[[[8.56,42.154],[8.688,42.273],[8.549,42.377],[8.66,42.43],[8.709,42.579],[8.787,42.562],[9.118,42.732],[9.292,42.675],[9.347,43.004],[9.464,42.99],[9.443,42.641],[9.528,42.564],[9.56,42.147],[9.403,41.953],[9.402,41.706],[9.292,41.626],[9.351,41.581],[9.211,41.448],[9.223,41.373],[9.096,41.404],[9.08,41.482],[8.792,41.561],[8.802,41.639],[8.923,41.695],[8.655,41.75],[8.785,41.824],[8.805,41.907],[8.614,41.901],[8.586,41.969],[8.745,42.057],[8.56,42.154]]]]}},{"type":"Feature","properties":{"iso":"MAR","nom":"Maroc","focus":false},"geometry":{"type":"Polygon","coordinates":[[[-6.866,34.0],[-6.292,34.881],[-5.927,35.781],[-5.599,35.822],[-5.405,35.927],[-5.249,35.585],[-4.77,35.241],[-4.348,35.15],[-3.919,35.267],[-3.904,35.214],[-3.787,35.209],[-3.7,35.291],[-3.362,35.195],[-3.077,35.288],[-2.969,35.446],[-2.964,35.286],[-2.856,35.131],[-2.748,35.116],[-2.878,35.246],[-2.667,35.108],[-2.417,35.149],[-2.223,35.089],[-2.194,35.004],[-1.77,34.741],[-1.871,34.597],[-1.703,34.48],[-1.81,34.372],[-1.67,34.079],[-1.689,34.0],[-6.866,34.0]]]}},{"type":"Feature","properties":{"iso":"UKR","nom":"Ukraine","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[30.991,46.601],[30.791,46.553],[30.772,46.396],[30.652,46.345],[30.682,46.3],[30.494,46.08],[30.205,45.856],[30.138,45.82],[30.127,45.891],[30.095,45.815],[29.969,45.839],[29.932,45.724],[29.802,45.737],[29.865,45.672],[29.734,45.614],[29.694,45.781],[29.634,45.821],[29.59,45.559],[29.707,45.573],[29.606,45.478],[29.755,45.447],[29.709,45.223],[29.659,45.216],[29.65,45.346],[29.57,45.395],[29.322,45.444],[28.93,45.279],[28.79,45.321],[28.779,45.231],[28.577,45.248],[28.33,45.323],[28.202,45.469],[28.271,45.522],[28.502,45.509],[28.537,45.58],[28.474,45.658],[28.738,45.838],[28.74,45.953],[28.957,46.001],[28.939,46.089],[29.015,46.183],[28.934,46.259],[28.946,46.455],[29.184,46.538],[29.201,46.357],[29.307,46.472],[29.375,46.416],[29.458,46.485],[29.616,46.362],[29.714,46.471],[29.828,46.339],[30.132,46.423],[29.902,46.531],[29.95,46.579],[29.928,46.81],[29.559,46.946],[29.602,47.061],[29.478,47.112],[29.545,47.136],[29.557,47.324],[29.41,47.28],[29.156,47.45],[29.117,47.533],[29.239,47.756],[29.178,47.79],[29.236,47.871],[29.124,47.976],[28.95,47.935],[28.799,48.112],[28.574,48.155],[28.48,48.065],[28.412,48.171],[28.317,48.135],[28.358,48.239],[28.093,48.237],[28.076,48.315],[27.583,48.486],[27.209,48.361],[26.832,48.391],[26.774,48.287],[26.68,48.33],[26.587,48.249],[26.303,48.212],[26.173,47.993],[25.262,47.899],[25.08,47.743],[24.897,47.71],[24.542,47.944],[24.231,47.897],[23.78,47.988],[23.461,47.971],[23.139,48.098],[23.063,48.007],[22.924,48.005],[22.878,47.947],[22.801,48.091],[22.605,48.097],[22.481,48.243],[22.357,48.243],[22.272,48.403],[22.133,48.405],[22.139,48.57],[22.31,48.682],[22.369,48.856],[22.561,49.086],[22.867,49.01],[22.841,49.095],[22.682,49.161],[22.738,49.275],[22.641,49.529],[22.766,49.674],[23.682,50.368],[23.981,50.405],[24.108,50.541],[24.081,50.713],[23.958,50.808],[24.143,50.856],[23.979,50.938],[23.864,51.148],[23.635,51.305],[23.698,51.404],[23.608,51.511],[23.617,51.625],[23.981,51.586],[24.244,51.718],[24.391,51.88],[25.138,51.949],[25.768,51.929],[26.855,51.749],[27.151,51.757],[27.189,51.664],[27.277,51.651],[27.267,51.587],[27.693,51.589],[27.664,51.493],[27.714,51.464],[27.831,51.613],[28.071,51.558],[28.21,51.652],[28.334,51.528],[28.604,51.554],[28.637,51.45],[28.729,51.401],[28.8,51.533],[29.063,51.631],[29.16,51.603],[29.32,51.366],[29.638,51.491],[29.829,51.43],[30.149,51.484],[30.32,51.402],[30.355,51.305],[30.54,51.235],[30.646,51.367],[30.515,51.604],[30.742,51.898],[31.0,52.076],[30.991,46.601]]]]}},{"type":"Feature","properties":{"iso":"BLR","nom":"Biélorussie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[23.602,51.531],[23.532,51.659],[23.676,51.994],[23.637,52.084],[23.166,52.289],[23.392,52.51],[23.869,52.67],[23.922,52.743],[23.859,53.068],[23.894,53.152],[23.591,53.611],[23.486,53.939],[23.627,53.898],[24.17,53.959],[24.378,53.887],[24.667,53.994],[24.806,53.975],[24.822,54.135],[25.072,54.132],[25.206,54.257],[25.459,54.299],[25.554,54.231],[25.502,54.222],[25.516,54.145],[25.763,54.156],[25.789,54.236],[25.696,54.321],[25.529,54.321],[25.631,54.508],[25.74,54.569],[25.721,54.767],[25.783,54.87],[25.87,54.939],[26.139,54.969],[26.264,55.14],[26.601,55.121],[26.657,55.215],[26.801,55.273],[26.45,55.327],[26.616,55.688],[26.823,55.706],[26.981,55.827],[27.593,55.794],[27.645,55.923],[27.927,56.109],[28.111,56.157],[28.311,56.043],[28.611,56.088],[28.732,55.947],[29.031,56.024],[29.396,55.948],[29.444,55.907],[29.344,55.787],[29.481,55.681],[29.908,55.843],[30.2,55.858],[30.469,55.794],[30.742,55.594],[30.913,55.572],[30.918,55.388],[30.794,55.286],[30.96,55.163],[31.0,55.022],[30.913,55.025],[30.936,54.973],[30.815,54.928],[30.763,54.802],[31.0,54.671],[31.0,52.076],[30.742,51.898],[30.515,51.604],[30.646,51.367],[30.551,51.237],[30.355,51.305],[30.32,51.402],[30.149,51.484],[29.829,51.43],[29.638,51.491],[29.32,51.366],[29.16,51.603],[29.063,51.631],[28.8,51.533],[28.729,51.401],[28.637,51.45],[28.604,51.554],[28.334,51.528],[28.21,51.652],[28.071,51.558],[27.831,51.613],[27.714,51.464],[27.664,51.493],[27.693,51.589],[27.267,51.587],[27.277,51.651],[27.189,51.664],[27.151,51.757],[26.855,51.749],[25.768,51.929],[25.138,51.949],[24.391,51.88],[24.244,51.718],[23.981,51.586],[23.726,51.645],[23.606,51.618],[23.602,51.531]]]}},{"type":"Feature","properties":{"iso":"LTU","nom":"Lituanie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[26.604,55.643],[26.45,55.327],[26.801,55.273],[26.657,55.215],[26.601,55.121],[26.264,55.14],[26.139,54.969],[25.87,54.939],[25.783,54.87],[25.721,54.767],[25.74,54.569],[25.631,54.508],[25.529,54.321],[25.696,54.321],[25.789,54.236],[25.763,54.156],[25.516,54.145],[25.502,54.222],[25.554,54.231],[25.459,54.299],[25.206,54.257],[25.072,54.132],[24.822,54.135],[24.789,53.97],[24.667,53.994],[24.378,53.887],[24.17,53.959],[23.627,53.898],[23.486,53.939],[23.474,54.113],[23.354,54.217],[23.05,54.295],[22.963,54.382],[22.767,54.356],[22.707,54.419],[22.701,54.68],[22.848,54.814],[22.565,55.068],[22.077,55.029],[22.003,55.093],[21.504,55.194],[21.375,55.29],[21.268,55.249],[21.257,55.369],[21.183,55.346],[21.248,55.418],[21.223,55.52],[21.147,55.678],[21.061,55.789],[21.053,56.073],[21.19,56.084],[21.328,56.224],[22.094,56.417],[22.666,56.349],[22.925,56.412],[23.062,56.304],[23.288,56.373],[23.707,56.354],[24.139,56.257],[24.481,56.269],[24.871,56.443],[25.073,56.198],[25.662,56.141],[26.28,55.743],[26.604,55.643]]]]}},{"type":"Feature","properties":{"iso":"RUS","nom":"Russie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[30.999,54.671],[30.763,54.802],[30.815,54.928],[30.936,54.973],[30.913,55.025],[31.0,55.022],[30.999,54.671]]],[[[30.994,55.067],[30.794,55.286],[30.918,55.388],[30.886,55.6],[30.742,55.594],[30.469,55.794],[30.2,55.858],[29.908,55.843],[29.481,55.681],[29.351,55.766],[29.444,55.907],[29.377,55.954],[29.031,56.024],[28.732,55.947],[28.538,56.098],[28.29,56.047],[28.149,56.142],[28.217,56.271],[28.093,56.502],[28.132,56.536],[27.865,56.743],[27.914,56.82],[27.786,56.871],[27.628,56.844],[27.751,57.042],[27.682,57.104],[27.824,57.159],[27.84,57.291],[27.511,57.43],[27.528,57.528],[27.353,57.528],[27.328,57.583],[27.391,57.68],[27.508,57.715],[27.525,57.807],[27.799,57.861],[27.665,57.918],[27.63,58.088],[27.495,58.221],[27.555,58.395],[27.411,58.755],[27.478,58.875],[27.713,58.992],[27.882,59.276],[28.182,59.356],[28.019,59.482],[28.073,59.578],[28.007,59.758],[28.124,59.792],[28.224,59.691],[28.375,59.666],[28.476,59.852],[28.833,59.787],[28.976,59.831],[29.034,59.887],[28.98,59.93],[29.148,60.0],[30.162,59.868],[30.246,59.975],[30.213,60.0],[31.0,60.0],[30.994,55.067]]],[[[22.767,54.356],[19.68,54.437],[19.61,54.457],[19.9,54.667],[19.977,54.965],[20.482,54.976],[20.925,55.283],[20.99,55.27],[20.531,54.965],[21.091,54.902],[21.243,54.961],[21.183,55.202],[21.375,55.29],[21.504,55.194],[22.003,55.093],[22.077,55.029],[22.541,55.076],[22.633,54.958],[22.821,54.885],[22.846,54.796],[22.701,54.68],[22.68,54.453],[22.767,54.356]]]]}},{"type":"Feature","properties":{"iso":"CZE","nom":"Rép. Tch.","focus":true},"geometry":{"type":"Polygon","coordinates":[[[14.7,50.816],[14.982,50.859],[15.004,51.021],[15.144,51.012],[15.27,50.953],[15.356,50.775],[15.792,50.743],[15.848,50.675],[15.971,50.679],[15.982,50.604],[16.332,50.644],[16.426,50.568],[16.2,50.406],[16.344,50.37],[16.661,50.093],[17.015,50.218],[16.893,50.433],[17.188,50.378],[17.424,50.241],[17.708,50.311],[17.748,50.218],[17.589,50.163],[17.633,50.106],[17.732,50.095],[17.839,49.974],[18.032,50.003],[18.002,50.047],[18.292,49.908],[18.559,49.907],[18.618,49.714],[18.788,49.669],[18.833,49.51],[18.536,49.482],[18.385,49.342],[18.161,49.259],[18.076,49.047],[17.914,49.01],[17.727,48.863],[17.535,48.813],[17.167,48.86],[16.945,48.604],[16.873,48.719],[16.52,48.806],[16.358,48.727],[16.085,48.743],[15.818,48.872],[15.681,48.858],[15.275,48.987],[15.142,48.937],[15.137,48.993],[15.004,49.01],[14.94,48.763],[14.8,48.777],[14.676,48.576],[14.458,48.643],[14.316,48.558],[14.041,48.601],[13.991,48.7],[13.609,48.946],[13.427,48.96],[13.0,49.295],[12.778,49.333],[12.644,49.429],[12.496,49.67],[12.384,49.743],[12.524,49.905],[12.247,50.045],[12.08,50.243],[12.076,50.315],[12.149,50.312],[12.3,50.161],[12.51,50.389],[12.817,50.443],[12.953,50.404],[13.01,50.493],[13.16,50.497],[13.369,50.628],[13.448,50.597],[13.557,50.707],[13.835,50.724],[14.347,50.88],[14.382,50.921],[14.238,50.982],[14.288,51.037],[14.482,51.037],[14.574,50.975],[14.55,50.912],[14.629,50.921],[14.613,50.846],[14.7,50.816]]]}},{"type":"Feature","properties":{"iso":"DEU","nom":"Allemagne","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[13.816,48.766],[13.802,48.612],[13.717,48.522],[13.455,48.573],[13.406,48.377],[12.739,48.113],[12.991,47.847],[12.892,47.724],[13.072,47.659],[13.002,47.466],[12.779,47.555],[12.813,47.612],[12.762,47.667],[12.497,47.629],[12.424,47.692],[12.239,47.679],[12.242,47.732],[12.177,47.706],[12.174,47.605],[11.62,47.59],[11.237,47.394],[10.979,47.391],[10.859,47.531],[10.429,47.577],[10.428,47.396],[10.16,47.271],[10.209,47.372],[10.083,47.359],[9.946,47.541],[9.782,47.588],[9.613,47.522],[9.183,47.67],[8.882,47.656],[8.558,47.801],[8.391,47.665],[8.607,47.656],[8.574,47.592],[8.233,47.622],[8.042,47.561],[7.61,47.565],[7.66,47.597],[7.586,47.585],[7.512,47.707],[7.621,47.971],[7.579,48.114],[7.751,48.341],[7.81,48.615],[8.09,48.808],[8.2,48.959],[7.635,49.038],[7.41,49.169],[7.274,49.105],[7.043,49.108],[6.914,49.207],[6.726,49.156],[6.512,49.425],[6.345,49.455],[6.351,49.567],[6.5,49.712],[6.503,49.796],[6.303,49.835],[6.096,50.049],[6.147,50.214],[6.375,50.315],[6.337,50.481],[6.171,50.518],[6.249,50.614],[6.012,50.709],[5.973,50.782],[6.064,50.908],[5.858,51.019],[6.147,51.152],[6.057,51.212],[6.208,51.388],[6.193,51.509],[5.939,51.732],[5.931,51.816],[6.156,51.842],[6.127,51.897],[6.345,51.821],[6.744,51.908],[6.809,51.98],[6.68,52.06],[7.026,52.231],[7.048,52.365],[6.973,52.451],[6.715,52.462],[6.672,52.542],[6.744,52.56],[6.737,52.635],[7.018,52.626],[7.062,52.824],[7.193,52.998],[7.195,53.245],[7.255,53.32],[7.367,53.303],[7.024,53.376],[7.051,53.513],[7.142,53.537],[7.087,53.587],[7.226,53.666],[8.031,53.708],[8.168,53.553],[8.077,53.469],[8.205,53.411],[8.315,53.475],[8.231,53.525],[8.271,53.613],[8.552,53.544],[8.49,53.486],[8.504,53.358],[8.498,53.475],[8.566,53.547],[8.486,53.7],[8.588,53.87],[8.861,53.831],[9.211,53.872],[9.582,53.591],[9.832,53.544],[9.584,53.612],[9.395,53.831],[9.258,53.886],[8.985,53.897],[8.916,53.937],[8.833,54.036],[8.997,54.03],[9.018,54.098],[8.813,54.18],[8.963,54.318],[8.678,54.269],[8.6,54.338],[8.696,54.359],[8.648,54.406],[8.886,54.418],[9.012,54.506],[8.689,54.735],[8.661,54.896],[8.904,54.898],[9.244,54.802],[9.58,54.866],[9.824,54.757],[9.948,54.78],[10.018,54.701],[9.929,54.674],[10.039,54.667],[10.027,54.56],[9.84,54.475],[10.143,54.492],[10.204,54.461],[10.142,54.324],[10.318,54.443],[10.731,54.31],[11.136,54.386],[11.067,54.359],[11.067,54.184],[10.753,54.05],[10.902,53.961],[11.175,54.018],[11.243,53.945],[11.458,53.906],[11.519,54.036],[11.69,54.155],[12.088,54.194],[12.092,54.114],[12.115,54.098],[12.109,54.183],[12.534,54.488],[12.921,54.433],[12.624,54.423],[12.527,54.372],[12.438,54.388],[12.369,54.269],[12.412,54.251],[12.458,54.256],[12.41,54.269],[12.479,54.332],[12.681,54.411],[12.855,54.358],[13.009,54.438],[13.115,54.28],[13.484,54.091],[13.712,54.174],[13.808,54.105],[13.746,54.036],[13.906,53.943],[13.819,53.878],[13.817,53.853],[14.037,53.755],[14.264,53.752],[14.213,53.708],[14.264,53.7],[14.442,53.252],[14.343,53.049],[14.144,52.96],[14.124,52.851],[14.645,52.577],[14.545,52.382],[14.584,52.291],[14.712,52.236],[14.686,52.121],[14.761,52.077],[14.586,51.804],[14.732,51.658],[14.71,51.53],[14.955,51.435],[15.022,51.237],[14.955,51.064],[14.759,50.81],[14.613,50.846],[14.629,50.921],[14.55,50.912],[14.574,50.975],[14.482,51.037],[14.288,51.037],[14.238,50.982],[14.382,50.921],[14.347,50.88],[13.835,50.724],[13.557,50.707],[13.448,50.597],[13.369,50.628],[13.16,50.497],[13.01,50.493],[12.953,50.404],[12.817,50.443],[12.51,50.389],[12.3,50.161],[12.24,50.257],[12.076,50.315],[12.247,50.045],[12.524,49.905],[12.384,49.743],[12.496,49.67],[12.644,49.429],[12.778,49.333],[13.0,49.295],[13.427,48.96],[13.609,48.946],[13.816,48.766]]],[[[14.193,53.911],[13.84,53.85],[13.932,53.899],[13.904,53.995],[14.048,53.941],[14.051,54.005],[13.946,54.067],[13.891,54.01],[13.774,54.023],[13.815,54.101],[13.753,54.153],[13.815,54.174],[14.193,53.911]]],[[[13.579,54.455],[13.766,54.345],[13.723,54.278],[13.651,54.297],[13.712,54.332],[13.617,54.318],[13.691,54.352],[13.5,54.345],[13.36,54.275],[13.407,54.228],[13.115,54.338],[13.267,54.386],[13.157,54.427],[13.273,54.482],[13.143,54.543],[13.298,54.52],[13.369,54.585],[13.349,54.524],[13.377,54.565],[13.507,54.488],[13.521,54.571],[13.441,54.557],[13.369,54.612],[13.253,54.565],[13.293,54.642],[13.231,54.653],[13.391,54.688],[13.445,54.68],[13.383,54.636],[13.425,54.585],[13.671,54.566],[13.579,54.455]]]]}},{"type":"Feature","properties":{"iso":"EST","nom":"Estonie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[24.317,57.877],[24.464,58.072],[24.471,58.251],[24.551,58.334],[24.362,58.397],[24.112,58.241],[23.741,58.343],[23.679,58.524],[23.501,58.562],[23.498,58.697],[23.533,58.747],[23.874,58.772],[23.429,58.765],[23.526,58.82],[23.422,58.929],[23.628,58.979],[23.622,59.015],[23.56,59.053],[23.614,59.011],[23.553,58.971],[23.408,59.026],[23.518,59.073],[23.471,59.212],[23.73,59.23],[23.757,59.284],[24.081,59.271],[24.035,59.389],[24.222,59.355],[24.163,59.402],[24.334,59.471],[24.643,59.436],[24.675,59.496],[24.773,59.45],[24.803,59.571],[24.934,59.508],[25.409,59.491],[25.544,59.535],[25.485,59.67],[25.677,59.566],[25.695,59.671],[25.826,59.575],[25.989,59.634],[26.665,59.552],[26.938,59.45],[27.873,59.408],[28.019,59.482],[28.186,59.375],[27.882,59.276],[27.713,58.992],[27.478,58.875],[27.411,58.755],[27.555,58.395],[27.495,58.221],[27.63,58.088],[27.665,57.918],[27.799,57.861],[27.525,57.807],[27.508,57.715],[27.391,57.68],[27.328,57.583],[27.353,57.528],[26.873,57.627],[26.5,57.516],[26.025,57.774],[26.015,57.843],[25.602,57.912],[25.282,58.073],[25.232,57.985],[25.094,58.067],[24.317,57.877]]],[[[22.922,58.617],[23.325,58.442],[23.157,58.478],[22.723,58.225],[22.323,58.207],[22.203,57.994],[22.048,57.915],[21.963,57.984],[22.203,58.148],[21.844,58.294],[22.011,58.354],[21.832,58.511],[21.996,58.513],[22.089,58.422],[22.195,58.546],[22.273,58.502],[22.322,58.585],[22.583,58.635],[22.648,58.587],[22.922,58.617]]],[[[22.382,58.882],[22.045,58.936],[22.463,58.971],[22.598,59.09],[22.934,58.984],[23.041,58.841],[22.88,58.833],[22.845,58.777],[22.778,58.824],[22.556,58.687],[22.463,58.716],[22.382,58.882]]]]}},{"type":"Feature","properties":{"iso":"LVA","nom":"Lettonie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[27.528,57.528],[27.511,57.43],[27.846,57.267],[27.824,57.159],[27.682,57.104],[27.751,57.042],[27.628,56.844],[27.786,56.871],[27.914,56.82],[27.865,56.743],[28.126,56.548],[28.093,56.502],[28.217,56.271],[28.149,56.142],[27.927,56.109],[27.645,55.923],[27.593,55.794],[26.981,55.827],[26.823,55.706],[26.481,55.678],[26.28,55.743],[25.662,56.141],[25.073,56.198],[24.871,56.443],[24.481,56.269],[24.139,56.257],[23.707,56.354],[23.288,56.373],[23.062,56.304],[22.925,56.412],[22.666,56.349],[22.094,56.417],[21.328,56.224],[21.19,56.084],[21.053,56.073],[20.969,56.253],[21.006,56.52],[21.08,56.403],[20.992,56.549],[21.053,56.829],[21.382,57.009],[21.434,57.306],[21.73,57.574],[22.484,57.742],[22.61,57.755],[22.591,57.645],[22.656,57.586],[23.13,57.371],[23.261,57.099],[23.695,56.967],[23.953,57.013],[24.401,57.258],[24.306,57.868],[25.094,58.067],[25.217,57.985],[25.284,58.008],[25.282,58.073],[25.602,57.912],[26.015,57.843],[26.025,57.774],[26.5,57.516],[26.873,57.627],[27.085,57.549],[27.528,57.528]]]}},{"type":"Feature","properties":{"iso":"NOR","nom":"Norvège","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[12.36,60.0],[11.85,59.872],[11.897,59.714],[11.675,59.607],[11.812,59.25],[11.612,58.893],[11.452,58.896],[11.389,59.081],[11.182,59.116],[11.176,59.197],[11.032,59.128],[10.948,59.183],[10.916,59.142],[10.902,59.197],[10.823,59.164],[10.773,59.252],[10.738,59.217],[10.779,59.313],[10.674,59.316],[10.592,59.431],[10.69,59.481],[10.56,59.726],[10.656,59.857],[10.718,59.738],[10.753,59.889],[10.529,59.882],[10.475,59.85],[10.491,59.731],[10.615,59.608],[10.543,59.536],[10.437,59.518],[10.398,59.688],[10.224,59.724],[10.379,59.658],[10.381,59.535],[10.237,59.56],[10.478,59.43],[10.445,59.349],[10.514,59.303],[10.47,59.248],[10.361,59.271],[10.307,59.06],[10.272,59.114],[10.262,59.039],[10.224,59.114],[10.207,59.016],[10.017,59.034],[10.015,58.973],[9.846,58.956],[9.782,59.051],[9.539,59.121],[9.724,58.984],[9.299,58.882],[9.271,58.833],[9.45,58.833],[9.306,58.739],[9.071,58.741],[9.216,58.703],[9.059,58.683],[9.201,58.672],[9.034,58.595],[8.913,58.607],[8.944,58.526],[8.501,58.257],[8.409,58.272],[8.123,58.102],[8.047,58.117],[8.08,58.162],[8.004,58.223],[7.956,58.093],[7.579,58.018],[7.25,58.059],[7.007,57.993],[7.147,58.1],[6.901,58.052],[6.908,58.1],[6.804,58.1],[6.989,58.141],[6.778,58.182],[6.808,58.121],[6.731,58.12],[6.722,58.189],[6.688,58.121],[6.783,58.065],[6.596,58.076],[6.531,58.121],[6.846,58.271],[6.681,58.223],[6.634,58.275],[6.687,58.327],[6.562,58.243],[6.01,58.385],[5.955,58.477],[5.646,58.549],[5.478,58.755],[5.573,58.894],[5.537,58.956],[5.626,58.926],[5.523,58.991],[5.551,59.039],[5.716,58.977],[5.716,58.867],[5.854,58.965],[6.093,58.847],[6.229,58.84],[6.058,58.902],[6.195,58.984],[6.626,59.053],[6.16,58.998],[6.034,58.905],[5.975,58.963],[6.051,58.998],[5.875,59.066],[6.126,59.148],[6.009,59.149],[6.171,59.261],[6.462,59.32],[6.154,59.268],[6.085,59.307],[6.236,59.32],[5.995,59.334],[6.042,59.384],[6.243,59.511],[6.544,59.56],[6.236,59.526],[6.286,59.649],[6.153,59.459],[5.983,59.43],[5.995,59.381],[5.924,59.356],[5.886,59.447],[6.153,59.477],[5.902,59.479],[5.807,59.539],[5.798,59.463],[5.646,59.409],[5.784,59.429],[5.86,59.351],[5.612,59.293],[5.646,59.334],[5.587,59.416],[5.505,59.278],[5.436,59.308],[5.433,59.405],[5.399,59.297],[5.348,59.416],[5.297,59.345],[5.182,59.511],[5.344,59.648],[5.413,59.595],[5.4,59.67],[5.489,59.738],[5.488,59.575],[5.417,59.505],[5.516,59.539],[5.564,59.677],[5.754,59.61],[5.879,59.656],[5.746,59.676],[5.814,59.729],[6.038,59.745],[6.312,59.854],[6.002,59.759],[5.934,59.779],[5.969,59.861],[5.832,59.772],[5.646,59.854],[5.972,59.96],[5.95,60.0],[12.36,60.0]]],[[[5.491,59.852],[5.482,59.788],[5.422,59.759],[5.363,59.764],[5.407,59.779],[5.314,59.789],[5.25,59.909],[5.326,59.977],[5.491,59.852]]]]}},{"type":"Feature","properties":{"iso":"SWE","nom":"Suède","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[18.868,59.994],[19.072,59.896],[19.068,59.834],[18.886,59.93],[18.924,59.852],[18.734,59.769],[19.074,59.75],[18.913,59.752],[18.64,59.584],[18.269,59.477],[18.307,59.397],[18.188,59.407],[18.181,59.458],[18.009,59.409],[18.146,59.34],[18.095,59.327],[18.221,59.32],[18.318,59.376],[18.47,59.337],[18.448,59.395],[18.496,59.395],[18.427,59.436],[18.485,59.434],[18.646,59.33],[18.291,59.323],[18.279,59.262],[18.412,59.215],[18.314,59.234],[18.424,59.144],[18.014,59.045],[17.893,58.861],[17.774,58.961],[17.803,58.908],[17.774,58.886],[17.769,59.121],[17.71,59.053],[17.659,59.169],[17.577,58.957],[17.627,58.918],[17.536,58.902],[17.591,58.861],[17.447,58.895],[17.488,58.8],[17.337,58.806],[17.358,58.751],[17.028,58.751],[17.146,58.697],[16.975,58.685],[17.036,58.641],[16.924,58.625],[16.234,58.669],[16.255,58.635],[16.179,58.635],[16.789,58.607],[16.94,58.491],[16.748,58.429],[16.441,58.486],[16.413,58.477],[16.767,58.369],[16.632,58.354],[16.711,58.299],[16.799,58.324],[16.707,58.271],[16.824,58.193],[16.777,58.131],[16.617,58.203],[16.736,58.085],[16.686,58.059],[16.746,58.017],[16.631,58.028],[16.735,57.972],[16.758,57.877],[16.611,57.895],[16.645,57.921],[16.515,57.999],[16.573,57.894],[16.46,57.902],[16.7,57.744],[16.419,57.895],[16.715,57.703],[16.577,57.71],[16.631,57.629],[16.521,57.627],[16.515,57.566],[16.629,57.557],[16.689,57.472],[16.469,57.275],[16.465,57.177],[16.583,57.045],[16.44,57.052],[16.468,56.949],[16.408,56.799],[16.472,56.777],[16.361,56.764],[16.372,56.661],[16.246,56.642],[16.038,56.255],[15.852,56.086],[15.789,56.106],[15.827,56.159],[15.592,56.161],[15.586,56.209],[15.366,56.141],[15.295,56.188],[14.725,56.168],[14.682,56.117],[14.768,56.031],[14.612,56.011],[14.569,56.058],[14.346,55.953],[14.194,55.742],[14.363,55.524],[14.158,55.387],[13.897,55.435],[13.381,55.346],[12.833,55.383],[12.986,55.448],[12.917,55.547],[13.055,55.694],[12.923,55.749],[12.926,55.834],[12.451,56.304],[12.814,56.236],[12.829,56.279],[12.622,56.419],[12.89,56.455],[12.934,56.547],[12.872,56.649],[12.732,56.647],[12.598,56.821],[12.356,56.924],[12.341,57.014],[12.149,57.188],[12.191,57.213],[12.101,57.237],[12.157,57.243],[12.095,57.25],[12.144,57.31],[12.05,57.351],[12.109,57.394],[12.059,57.459],[11.979,57.347],[11.903,57.394],[11.917,57.621],[11.835,57.662],[11.924,57.703],[11.705,57.698],[11.81,57.781],[11.656,57.839],[11.759,57.902],[11.793,58.1],[11.89,58.217],[11.809,58.302],[11.883,58.333],[11.727,58.327],[11.506,58.243],[11.67,58.422],[11.589,58.401],[11.553,58.463],[11.522,58.336],[11.396,58.265],[11.424,58.388],[11.346,58.346],[11.424,58.443],[11.221,58.346],[11.286,58.58],[11.177,58.719],[11.233,58.808],[11.198,58.923],[11.108,58.954],[11.184,58.991],[11.115,59.008],[11.194,59.08],[11.321,59.1],[11.452,58.896],[11.664,58.92],[11.812,59.25],[11.675,59.607],[11.897,59.714],[11.85,59.872],[12.144,59.898],[12.36,60.0],[18.868,59.994]]],[[[17.097,57.317],[16.637,56.56],[16.566,56.346],[16.428,56.218],[16.419,56.586],[16.621,56.872],[16.731,56.904],[16.966,57.305],[17.055,57.358],[17.097,57.317]]],[[[18.851,57.915],[19.085,57.826],[18.941,57.73],[18.807,57.734],[18.765,57.627],[18.81,57.607],[18.773,57.472],[18.926,57.393],[18.68,57.31],[18.714,57.243],[18.406,57.143],[18.455,57.127],[18.338,57.031],[18.4,57.004],[18.312,56.948],[18.139,56.922],[18.29,57.093],[18.201,57.065],[18.228,57.134],[18.099,57.259],[18.179,57.38],[18.128,57.548],[18.678,57.914],[18.742,57.918],[18.803,57.826],[18.851,57.915]]],[[[11.814,58.211],[11.805,58.126],[11.708,58.098],[11.458,58.072],[11.407,58.131],[11.686,58.291],[11.814,58.211]]]]}},{"type":"Feature","properties":{"iso":"FIN","nom":"Finlande","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[23.44,59.994],[23.222,59.886],[23.251,59.841],[22.888,59.813],[23.247,59.922],[23.321,60.0],[23.44,59.994]]]]}},{"type":"Feature","properties":{"iso":"LUX","nom":"Luxembourg","focus":false},"geometry":{"type":"Polygon","coordinates":[[[6.111,50.106],[6.117,50.004],[6.223,49.887],[6.303,49.835],[6.334,49.84],[6.397,49.809],[6.462,49.805],[6.497,49.799],[6.503,49.796],[6.5,49.712],[6.351,49.567],[6.345,49.455],[6.194,49.499],[5.961,49.441],[5.791,49.538],[5.885,49.644],[5.728,49.8],[5.719,49.891],[5.962,50.166],[6.111,50.106]]]}},{"type":"Feature","properties":{"iso":"BEL","nom":"Belgique","focus":true},"geometry":{"type":"Polygon","coordinates":[[[2.542,51.097],[3.349,51.375],[3.392,51.247],[3.61,51.29],[3.927,51.206],[4.221,51.368],[4.308,51.271],[4.261,51.369],[4.411,51.357],[4.377,51.443],[4.429,51.462],[4.63,51.418],[4.779,51.495],[4.823,51.414],[4.762,51.413],[4.91,51.392],[5.028,51.477],[5.215,51.259],[5.493,51.287],[5.568,51.208],[5.829,51.156],[5.846,51.103],[5.722,50.959],[5.764,50.959],[5.624,50.83],[5.707,50.754],[5.995,50.75],[6.249,50.614],[6.171,50.518],[6.337,50.481],[6.375,50.315],[6.157,50.223],[6.117,50.12],[5.962,50.166],[5.719,49.891],[5.728,49.8],[5.885,49.644],[5.837,49.561],[5.456,49.499],[5.259,49.691],[4.849,49.794],[4.86,49.913],[4.784,49.958],[4.863,50.148],[4.682,50.084],[4.657,49.989],[4.465,49.936],[4.132,49.975],[4.21,50.06],[4.126,50.128],[4.198,50.258],[4.003,50.344],[3.697,50.298],[3.608,50.477],[3.271,50.527],[3.232,50.696],[3.129,50.779],[2.887,50.697],[2.787,50.723],[2.587,50.845],[2.608,50.961],[2.542,51.097]]]}},{"type":"Feature","properties":{"iso":"MKD","nom":"Macédoine","focus":false},"geometry":{"type":"Polygon","coordinates":[[[20.542,41.862],[20.723,41.867],[20.785,42.082],[21.098,42.196],[21.289,42.09],[21.436,42.247],[21.677,42.235],[21.929,42.335],[22.061,42.301],[22.269,42.37],[22.531,42.129],[22.838,42.019],[23.01,41.716],[22.933,41.612],[22.941,41.35],[22.751,41.315],[22.705,41.14],[22.048,41.152],[21.909,41.097],[21.766,40.924],[21.582,40.866],[21.405,40.909],[20.965,40.849],[20.94,40.907],[20.717,40.913],[20.5,41.236],[20.482,41.341],[20.54,41.401],[20.444,41.55],[20.535,41.585],[20.5,41.734],[20.542,41.862]]]}},{"type":"Feature","properties":{"iso":"ALB","nom":"Albanie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[20.599,41.961],[20.535,41.585],[20.444,41.55],[20.54,41.401],[20.482,41.341],[20.5,41.236],[20.717,40.913],[20.957,40.895],[20.944,40.765],[21.037,40.64],[20.937,40.473],[20.771,40.422],[20.648,40.094],[20.298,39.987],[20.397,39.818],[20.28,39.804],[20.296,39.717],[20.184,39.637],[19.989,39.687],[20.01,39.866],[19.906,39.906],[19.941,39.94],[19.863,40.045],[19.476,40.214],[19.29,40.42],[19.475,40.348],[19.479,40.454],[19.419,40.492],[19.391,40.522],[19.386,40.543],[19.434,40.506],[19.455,40.554],[19.386,40.551],[19.304,40.653],[19.407,40.821],[19.381,40.908],[19.441,40.949],[19.441,40.872],[19.523,40.921],[19.495,41.003],[19.48,40.954],[19.448,40.934],[19.442,41.144],[19.517,41.256],[19.393,41.414],[19.517,41.513],[19.441,41.585],[19.613,41.605],[19.558,41.661],[19.592,41.819],[19.365,41.852],[19.372,42.104],[19.272,42.181],[19.699,42.655],[19.784,42.475],[20.039,42.558],[20.153,42.494],[20.238,42.32],[20.482,42.231],[20.599,41.961]]]}},{"type":"Feature","properties":{"iso":"XKX","nom":"Kosovo","focus":false},"geometry":{"type":"Polygon","coordinates":[[[20.077,42.56],[20.104,42.653],[20.035,42.751],[20.183,42.743],[20.226,42.807],[20.476,42.856],[20.459,42.95],[20.665,43.085],[20.604,43.198],[20.794,43.263],[20.865,43.217],[20.839,43.17],[21.093,43.091],[21.261,42.887],[21.408,42.847],[21.379,42.744],[21.773,42.648],[21.617,42.387],[21.516,42.342],[21.564,42.246],[21.367,42.224],[21.299,42.091],[21.098,42.196],[20.785,42.082],[20.681,41.844],[20.567,41.873],[20.599,41.961],[20.501,42.211],[20.238,42.32],[20.077,42.56]]]}},{"type":"Feature","properties":{"iso":"TUR","nom":"Turquie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[31.0,36.85],[30.687,36.891],[30.602,36.838],[30.57,36.528],[30.475,36.402],[30.52,36.342],[30.399,36.206],[30.384,36.274],[30.234,36.309],[29.672,36.123],[29.584,36.185],[29.624,36.199],[29.412,36.267],[29.35,36.233],[29.096,36.391],[29.115,36.553],[29.014,36.548],[29.096,36.665],[28.939,36.751],[28.829,36.603],[28.746,36.698],[28.623,36.699],[28.61,36.816],[28.487,36.802],[28.452,36.884],[28.377,36.854],[28.396,36.789],[28.257,36.846],[28.295,36.72],[28.036,36.565],[27.959,36.603],[28.09,36.644],[27.966,36.689],[28.116,36.719],[28.118,36.801],[27.918,36.74],[27.719,36.756],[27.671,36.658],[27.37,36.679],[27.645,36.806],[28.028,36.781],[28.042,36.939],[28.165,36.912],[28.212,37.0],[28.329,37.037],[27.562,36.973],[27.376,37.028],[27.263,36.963],[27.229,37.062],[27.294,37.11],[27.26,37.11],[27.253,37.124],[27.565,37.126],[27.528,37.193],[27.61,37.2],[27.616,37.275],[27.464,37.252],[27.491,37.327],[27.397,37.323],[27.407,37.413],[27.33,37.352],[27.191,37.357],[27.209,37.597],[27.011,37.666],[27.25,37.744],[27.239,37.988],[26.975,38.065],[26.873,38.035],[26.76,38.217],[26.636,38.204],[26.595,38.104],[26.39,38.262],[26.235,38.274],[26.294,38.37],[26.385,38.318],[26.513,38.433],[26.388,38.454],[26.349,38.635],[26.403,38.677],[26.63,38.519],[26.588,38.419],[26.673,38.307],[26.702,38.43],[26.795,38.359],[27.164,38.453],[26.935,38.435],[26.815,38.543],[26.89,38.508],[26.849,38.597],[26.719,38.653],[26.719,38.721],[26.903,38.735],[26.897,38.817],[27.063,38.887],[27.041,38.94],[26.806,38.95],[26.794,39.022],[26.875,39.091],[26.719,39.263],[26.609,39.275],[26.93,39.488],[26.938,39.575],[26.074,39.475],[26.157,39.649],[26.168,39.974],[26.311,40.019],[26.408,40.194],[26.736,40.404],[26.991,40.389],[27.287,40.468],[27.294,40.406],[27.452,40.322],[27.763,40.315],[27.884,40.386],[27.684,40.496],[27.76,40.537],[28.034,40.474],[27.904,40.4],[27.945,40.366],[29.034,40.364],[29.152,40.434],[28.793,40.553],[28.986,40.645],[29.491,40.727],[29.939,40.735],[29.378,40.757],[29.255,40.811],[29.264,40.87],[29.008,41.031],[29.062,41.076],[29.091,41.141],[29.069,41.153],[29.17,41.233],[30.137,41.144],[30.282,41.216],[31.0,41.083],[31.0,36.85]]],[[[28.017,41.973],[27.972,41.822],[28.233,41.519],[29.109,41.235],[28.992,41.008],[28.625,40.968],[28.552,41.081],[28.541,40.99],[28.165,41.085],[27.941,40.971],[27.524,40.989],[27.288,40.704],[26.683,40.455],[26.346,40.2],[26.376,40.154],[26.157,40.055],[26.272,40.23],[26.219,40.331],[26.829,40.602],[26.79,40.661],[26.506,40.599],[26.091,40.605],[26.054,40.661],[26.033,40.735],[26.359,40.965],[26.321,41.246],[26.632,41.358],[26.595,41.612],[26.333,41.713],[26.334,41.79],[26.526,41.824],[26.606,41.967],[26.939,41.996],[27.047,42.083],[27.273,42.092],[27.546,41.901],[27.687,41.969],[27.815,41.947],[27.816,41.995],[28.017,41.973]]]]}},{"type":"Feature","properties":{"iso":"ESP","nom":"Espagne","focus":true},"geometry":{"type":"MultiPolygon","coordinates":[[[[-1.796,43.374],[-1.622,43.247],[-1.404,43.243],[-1.457,43.045],[-1.366,43.033],[-1.348,43.093],[-1.286,43.109],[-1.294,43.055],[-1.15,43.006],[-0.76,42.947],[-0.569,42.773],[-0.323,42.843],[-0.039,42.685],[0.169,42.726],[0.275,42.669],[0.354,42.717],[0.657,42.688],[0.656,42.838],[0.813,42.832],[1.151,42.707],[1.343,42.709],[1.429,42.595],[1.448,42.435],[1.707,42.503],[1.927,42.437],[2.009,42.347],[2.277,42.429],[2.515,42.326],[2.934,42.47],[3.181,42.431],[3.187,42.35],[3.318,42.323],[3.263,42.24],[3.119,42.218],[3.232,41.946],[2.933,41.712],[2.267,41.449],[2.131,41.304],[1.017,41.052],[0.714,40.815],[0.874,40.728],[0.858,40.686],[0.677,40.565],[0.592,40.582],[0.733,40.634],[0.563,40.59],[-0.323,39.516],[-0.158,39.002],[0.235,38.742],[-0.51,38.338],[-0.504,38.207],[-0.624,38.162],[-0.761,37.796],[-0.856,37.742],[-0.705,37.62],[-0.925,37.556],[-1.088,37.581],[-1.106,37.532],[-1.324,37.562],[-1.671,37.363],[-1.813,37.207],[-1.9,36.941],[-2.127,36.736],[-2.362,36.837],[-2.561,36.819],[-2.718,36.682],[-2.933,36.752],[-3.415,36.696],[-3.839,36.752],[-4.403,36.724],[-4.659,36.508],[-4.903,36.507],[-5.187,36.411],[-5.339,36.141],[-5.425,36.18],[-5.439,36.063],[-5.612,36.006],[-5.917,36.184],[-6.037,36.19],[-6.31,36.534],[-6.231,36.473],[-6.179,36.514],[-6.395,36.637],[-6.433,36.751],[-6.346,36.795],[-6.338,36.884],[-6.223,36.902],[-6.195,36.932],[-6.345,36.901],[-6.388,36.808],[-6.5,36.96],[-6.893,37.167],[-6.853,37.295],[-6.963,37.234],[-6.928,37.172],[-7.101,37.224],[-7.414,37.193],[-7.514,37.601],[-7.273,37.977],[-7.024,38.023],[-6.948,38.197],[-7.104,38.174],[-7.359,38.446],[-7.27,38.738],[-7.056,38.855],[-6.973,39.014],[-7.016,39.097],[-7.157,39.105],[-7.258,39.211],[-7.314,39.457],[-7.557,39.68],[-7.021,39.694],[-6.88,40.009],[-7.043,40.181],[-6.794,40.356],[-6.857,40.442],[-6.816,40.857],[-6.942,41.016],[-6.804,41.064],[-6.647,41.268],[-6.321,41.411],[-6.206,41.57],[-6.366,41.664],[-6.542,41.659],[-6.577,41.74],[-6.524,41.867],[-6.609,41.962],[-7.051,41.942],[-7.145,41.987],[-7.219,41.879],[-7.443,41.806],[-7.722,41.899],[-7.897,41.858],[-7.906,41.914],[-8.049,41.816],[-8.18,41.811],[-8.23,41.905],[-8.095,42.041],[-8.204,42.07],[-8.222,42.154],[-8.627,42.051],[-8.881,41.893],[-8.895,42.119],[-8.827,42.131],[-8.623,42.347],[-8.868,42.256],[-8.831,42.342],[-8.655,42.441],[-8.844,42.404],[-8.943,42.469],[-8.827,42.462],[-8.731,42.688],[-8.785,42.641],[-8.84,42.682],[-9.026,42.543],[-9.071,42.596],[-9.03,42.708],[-8.888,42.831],[-9.1,42.758],[-9.135,42.918],[-9.196,42.949],[-9.273,42.893],[-9.28,43.055],[-9.108,43.141],[-9.218,43.155],[-8.933,43.235],[-8.988,43.283],[-8.83,43.341],[-8.693,43.293],[-8.388,43.386],[-8.354,43.349],[-8.331,43.406],[-8.21,43.313],[-8.175,43.416],[-8.305,43.451],[-8.169,43.492],[-8.333,43.472],[-8.313,43.567],[-8.052,43.643],[-8.059,43.709],[-7.909,43.766],[-7.847,43.718],[-7.909,43.67],[-7.858,43.668],[-7.686,43.793],[-7.692,43.727],[-7.367,43.68],[-7.271,43.561],[-7.044,43.559],[-7.045,43.479],[-6.944,43.566],[-6.069,43.57],[-5.907,43.588],[-5.852,43.663],[-5.677,43.561],[-5.394,43.555],[-5.414,43.507],[-5.3,43.538],[-4.482,43.384],[-3.827,43.497],[-3.769,43.479],[-3.811,43.425],[-3.579,43.518],[-3.432,43.467],[-3.502,43.431],[-3.461,43.412],[-3.008,43.321],[-3.029,43.376],[-2.947,43.431],[-2.769,43.453],[-2.691,43.368],[-2.661,43.412],[-2.128,43.287],[-1.796,43.374]]],[[[1.601,39.082],[1.623,39.029],[1.403,38.832],[1.217,38.885],[1.357,39.078],[1.601,39.082]]],[[[3.136,39.789],[3.474,39.75],[3.454,39.66],[3.253,39.386],[3.061,39.269],[2.959,39.363],[2.787,39.376],[2.682,39.559],[2.493,39.47],[2.351,39.576],[2.813,39.873],[3.179,39.969],[3.097,39.914],[3.207,39.893],[3.136,39.789]]],[[[4.105,40.079],[4.337,39.867],[4.248,39.816],[3.981,39.936],[3.831,39.936],[3.803,40.018],[4.105,40.079]]]]}},{"type":"Feature","properties":{"iso":"DNK","nom":"Danemark","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[8.669,54.914],[8.682,55.133],[8.564,55.143],[8.499,55.066],[8.459,55.103],[8.489,55.197],[8.689,55.142],[8.618,55.438],[8.442,55.464],[8.313,55.583],[8.239,55.558],[8.313,55.469],[8.095,55.549],[8.182,55.729],[8.128,55.988],[8.194,55.812],[8.393,55.909],[8.282,56.076],[8.15,56.111],[8.135,55.994],[8.108,56.024],[8.122,56.552],[8.179,56.672],[8.22,56.709],[8.202,56.64],[8.307,56.554],[8.566,56.579],[8.637,56.48],[8.727,56.483],[8.763,56.563],[8.682,56.627],[9.063,56.813],[9.176,56.709],[9.059,56.634],[9.061,56.566],[9.155,56.661],[9.276,56.633],[9.25,56.579],[9.326,56.53],[9.373,56.565],[9.294,56.561],[9.306,56.695],[9.169,56.689],[9.243,56.747],[9.175,56.806],[9.2,56.939],[9.437,57.024],[9.608,56.97],[9.689,57.039],[9.916,57.059],[9.796,57.106],[9.245,57.002],[9.115,57.059],[8.68,56.953],[8.491,56.794],[8.476,56.716],[8.527,56.695],[8.408,56.689],[8.586,56.689],[8.56,56.593],[8.352,56.693],[8.302,56.764],[8.244,56.777],[8.246,56.704],[8.236,56.771],[8.248,56.812],[8.618,57.123],[9.412,57.165],[9.967,57.591],[10.198,57.601],[10.539,57.744],[10.649,57.737],[10.43,57.571],[10.547,57.435],[10.539,57.237],[10.347,57.01],[10.24,56.993],[9.995,57.093],[9.927,57.059],[10.002,57.084],[10.192,56.994],[10.314,56.983],[10.266,56.908],[10.341,56.717],[10.146,56.722],[9.806,56.64],[10.334,56.704],[10.34,56.62],[10.214,56.558],[10.183,56.47],[10.33,56.603],[10.47,56.521],[10.822,56.534],[10.964,56.448],[10.912,56.334],[10.739,56.155],[10.629,56.238],[10.548,56.101],[10.509,56.17],[10.355,56.202],[10.491,56.216],[10.505,56.278],[10.403,56.298],[10.22,56.148],[10.231,56.017],[10.278,56.018],[10.182,55.834],[10.102,55.882],[9.867,55.852],[10.046,55.814],[10.005,55.701],[9.556,55.712],[9.854,55.627],[9.498,55.489],[9.66,55.478],[9.587,55.427],[9.71,55.249],[9.486,55.156],[9.457,55.126],[9.56,55.085],[9.434,55.038],[9.731,54.995],[9.746,54.836],[9.623,54.865],[9.615,54.933],[9.437,54.81],[9.317,54.802],[8.669,54.914]]],[[[11.849,54.773],[11.811,54.655],[11.474,54.626],[10.999,54.787],[11.108,54.832],[11.032,54.919],[11.232,54.961],[11.595,54.811],[11.649,54.914],[11.849,54.773]]],[[[12.505,55.02],[12.543,54.951],[12.115,54.907],[12.177,54.989],[12.287,54.989],[12.262,55.064],[12.505,55.02]]],[[[10.026,54.96],[10.064,54.881],[9.954,54.863],[9.874,54.893],[9.992,54.879],[9.781,54.917],[9.758,54.982],[9.848,54.948],[9.799,55.017],[9.628,55.058],[9.793,55.081],[10.026,54.96]]],[[[10.697,54.931],[10.957,55.154],[10.694,54.735],[10.601,54.838],[10.724,54.886],[10.697,54.931]]],[[[15.147,55.128],[15.073,54.992],[14.684,55.101],[14.761,55.309],[15.147,55.128]]],[[[10.621,55.064],[10.084,55.087],[10.156,55.14],[10.094,55.188],[10.004,55.197],[10.026,55.126],[9.986,55.128],[9.98,55.213],[9.884,55.253],[9.885,55.349],[9.703,55.468],[9.812,55.441],[9.676,55.496],[10.308,55.618],[10.519,55.533],[10.42,55.459],[10.472,55.443],[10.609,55.493],[10.567,55.524],[10.628,55.614],[10.742,55.487],[10.571,55.461],[10.554,55.443],[10.698,55.44],[10.834,55.29],[10.773,55.287],[10.783,55.124],[10.621,55.064]]],[[[11.883,54.941],[12.17,54.838],[11.961,54.694],[11.949,54.569],[11.869,54.66],[11.91,54.722],[11.711,54.941],[11.883,54.982],[11.616,55.092],[11.827,55.051],[11.718,55.126],[11.807,55.147],[11.718,55.208],[11.261,55.201],[11.286,55.256],[11.153,55.328],[11.19,55.345],[11.088,55.359],[11.214,55.404],[11.164,55.502],[11.081,55.513],[11.146,55.576],[10.93,55.668],[11.088,55.66],[10.875,55.743],[11.163,55.749],[11.122,55.737],[11.193,55.7],[11.364,55.765],[11.348,55.838],[11.505,55.869],[11.477,55.941],[11.305,55.968],[11.273,55.997],[11.768,55.971],[11.744,55.904],[11.663,55.907],[11.718,55.811],[11.608,55.783],[11.739,55.797],[11.763,55.749],[11.657,55.731],[11.746,55.731],[11.78,55.66],[11.954,55.854],[11.935,55.934],[12.052,55.737],[11.91,55.66],[12.001,55.699],[12.06,55.654],[12.095,55.729],[12.026,55.941],[11.866,55.973],[12.245,56.129],[12.622,56.044],[12.513,55.928],[12.602,55.709],[12.198,55.487],[12.435,55.364],[12.465,55.29],[12.183,55.227],[12.099,55.141],[12.015,55.167],[12.047,55.14],[12.169,55.128],[12.118,55.074],[12.162,55.004],[11.91,55.01],[11.883,54.941]]],[[[8.813,56.735],[8.658,56.678],[8.515,56.738],[8.669,56.826],[8.621,56.832],[8.652,56.894],[8.929,56.977],[8.813,56.735]]]]}},{"type":"Feature","properties":{"iso":"TUN","nom":"Tunisie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[7.504,34.068],[7.765,34.245],[7.832,34.414],[8.236,34.648],[8.3,35.068],[8.431,35.242],[8.294,35.325],[8.337,35.538],[8.241,35.828],[8.358,36.43],[8.17,36.526],[8.43,36.663],[8.462,36.733],[8.413,36.784],[8.624,36.826],[8.603,36.94],[8.824,36.979],[9.192,37.226],[9.745,37.345],[9.859,37.329],[9.772,37.213],[9.816,37.152],[9.914,37.178],[9.82,37.228],[9.882,37.264],[10.272,37.179],[10.128,37.159],[10.227,37.118],[10.182,37.027],[10.347,36.88],[10.188,36.798],[10.272,36.816],[10.355,36.731],[10.519,36.756],[10.585,36.876],[10.733,36.896],[10.902,37.049],[11.051,37.08],[11.131,36.854],[11.022,36.788],[10.8,36.452],[10.551,36.377],[10.475,36.112],[10.622,35.843],[11.041,35.638],[11.015,35.555],[11.085,35.507],[11.042,35.334],[11.159,35.219],[10.918,34.957],[10.871,34.797],[10.625,34.633],[10.597,34.545],[10.102,34.304],[10.005,34.171],[10.044,34.0],[7.501,34.0],[7.504,34.068]]]]}},{"type":"Feature","properties":{"iso":"ROU","nom":"Roumanie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[22.638,47.772],[23.139,48.098],[23.461,47.971],[23.78,47.988],[24.231,47.897],[24.542,47.944],[24.897,47.71],[25.08,47.743],[25.262,47.899],[26.173,47.993],[26.303,48.212],[26.689,48.275],[26.938,48.205],[27.169,47.983],[27.281,47.693],[27.576,47.46],[27.572,47.375],[28.069,46.989],[28.234,46.662],[28.246,46.428],[28.109,46.234],[28.145,46.183],[28.083,46.015],[28.168,45.632],[28.062,45.594],[28.33,45.323],[28.71,45.227],[28.803,45.244],[28.79,45.321],[28.93,45.279],[29.322,45.444],[29.57,45.395],[29.65,45.346],[29.624,45.21],[29.7,45.162],[29.618,44.861],[29.156,44.784],[29.001,44.689],[28.975,44.745],[29.139,44.804],[29.044,44.866],[29.111,44.97],[28.983,45.012],[28.869,44.943],[28.946,44.765],[28.798,44.72],[28.784,44.649],[28.898,44.717],[28.967,44.701],[28.988,44.675],[28.758,44.627],[28.758,44.465],[28.925,44.621],[28.635,44.316],[28.672,43.997],[28.578,43.741],[28.221,43.762],[27.981,43.849],[27.912,43.993],[27.722,43.949],[27.633,44.03],[27.384,44.015],[27.251,44.122],[27.027,44.177],[26.151,44.012],[25.781,43.732],[25.403,43.65],[24.964,43.75],[24.466,43.802],[24.159,43.753],[23.485,43.881],[22.889,43.84],[22.886,43.995],[23.023,44.032],[23.031,44.093],[22.691,44.229],[22.682,44.305],[22.549,44.349],[22.477,44.464],[22.58,44.565],[22.765,44.583],[22.426,44.734],[22.127,44.503],[21.994,44.659],[21.656,44.688],[21.578,44.778],[21.396,44.79],[21.356,44.857],[21.536,44.889],[21.351,44.998],[21.493,45.145],[20.981,45.333],[20.767,45.479],[20.786,45.753],[20.688,45.743],[20.243,46.108],[20.469,46.174],[20.664,46.138],[20.799,46.268],[21.033,46.231],[21.144,46.284],[21.179,46.384],[21.281,46.416],[21.245,46.477],[21.301,46.604],[21.502,46.704],[21.503,46.805],[21.671,46.993],[21.633,47.023],[22.002,47.394],[22.008,47.517],[22.162,47.586],[22.273,47.724],[22.638,47.772]]]}},{"type":"Feature","properties":{"iso":"HUN","nom":"Hongrie","focus":true},"geometry":{"type":"Polygon","coordinates":[[[22.861,47.934],[22.638,47.772],[22.273,47.724],[22.162,47.586],[22.008,47.517],[22.002,47.394],[21.633,47.023],[21.671,46.993],[21.503,46.805],[21.502,46.704],[21.301,46.604],[21.245,46.477],[21.281,46.416],[21.051,46.236],[20.82,46.272],[20.664,46.138],[20.469,46.174],[20.243,46.108],[19.55,46.164],[19.263,45.981],[19.088,46.019],[18.982,45.922],[18.656,45.908],[18.404,45.742],[17.858,45.772],[17.657,45.845],[17.591,45.936],[17.345,45.956],[17.209,46.117],[16.975,46.211],[16.838,46.382],[16.515,46.502],[16.368,46.643],[16.411,46.668],[16.314,46.743],[16.325,46.839],[16.094,46.863],[16.275,47.004],[16.486,46.999],[16.425,47.024],[16.51,47.138],[16.413,47.187],[16.473,47.277],[16.434,47.397],[16.641,47.453],[16.689,47.538],[16.63,47.622],[16.408,47.661],[16.568,47.754],[16.797,47.675],[17.075,47.708],[17.004,47.863],[17.185,48.02],[17.826,47.75],[18.693,47.778],[18.816,47.833],[18.749,47.871],[18.743,47.971],[18.838,48.04],[19.428,48.086],[19.514,48.204],[19.623,48.227],[19.929,48.13],[20.324,48.28],[20.482,48.526],[20.8,48.569],[21.109,48.489],[21.425,48.561],[21.759,48.334],[22.272,48.403],[22.364,48.239],[22.481,48.243],[22.605,48.097],[22.831,48.072],[22.861,47.934]]]}},{"type":"Feature","properties":{"iso":"SVK","nom":"Slovaquie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[22.532,49.056],[22.31,48.682],[22.139,48.57],[22.096,48.379],[21.728,48.341],[21.592,48.493],[21.425,48.561],[21.109,48.489],[20.8,48.569],[20.511,48.534],[20.324,48.28],[19.929,48.13],[19.623,48.227],[19.514,48.204],[19.428,48.086],[18.838,48.04],[18.743,47.971],[18.749,47.871],[18.816,47.833],[18.693,47.778],[17.742,47.765],[17.338,47.999],[17.07,48.036],[17.08,48.098],[16.844,48.366],[17.025,48.746],[17.167,48.86],[17.535,48.813],[17.727,48.863],[17.914,49.01],[18.076,49.047],[18.161,49.259],[18.385,49.342],[18.536,49.482],[18.932,49.504],[18.962,49.389],[19.142,49.394],[19.234,49.507],[19.443,49.602],[19.627,49.402],[19.769,49.393],[19.786,49.188],[19.938,49.225],[20.05,49.173],[20.136,49.309],[20.318,49.392],[20.69,49.401],[20.919,49.29],[21.073,49.357],[21.054,49.414],[21.261,49.449],[21.82,49.377],[22.041,49.197],[22.532,49.056]]]}},{"type":"Feature","properties":{"iso":"POL","nom":"Pologne","focus":true},"geometry":{"type":"Polygon","coordinates":[[[18.837,49.527],[18.788,49.669],[18.618,49.714],[18.559,49.907],[18.292,49.908],[18.002,50.047],[18.032,50.003],[17.839,49.974],[17.732,50.095],[17.633,50.106],[17.589,50.163],[17.748,50.218],[17.708,50.311],[17.424,50.241],[17.188,50.378],[16.893,50.433],[17.015,50.218],[16.661,50.093],[16.344,50.37],[16.2,50.406],[16.426,50.568],[16.332,50.644],[15.982,50.604],[15.971,50.679],[15.848,50.675],[15.792,50.743],[15.356,50.775],[15.27,50.953],[15.144,51.012],[14.961,50.993],[14.982,50.859],[14.81,50.858],[15.019,51.272],[14.945,51.449],[14.71,51.53],[14.732,51.658],[14.586,51.804],[14.761,52.077],[14.686,52.121],[14.712,52.236],[14.584,52.291],[14.545,52.382],[14.645,52.577],[14.124,52.851],[14.144,52.96],[14.343,53.049],[14.442,53.252],[14.264,53.7],[14.294,53.749],[14.591,53.598],[14.624,53.653],[14.545,53.704],[14.631,53.852],[14.587,53.813],[14.432,53.906],[14.319,53.818],[14.175,53.906],[15.86,54.25],[16.179,54.263],[16.215,54.3],[16.138,54.29],[16.324,54.35],[16.282,54.359],[16.57,54.557],[16.94,54.606],[17.337,54.749],[18.152,54.838],[18.34,54.833],[18.752,54.69],[18.835,54.603],[18.456,54.788],[18.413,54.747],[18.523,54.647],[18.588,54.434],[18.886,54.35],[19.377,54.378],[19.61,54.457],[22.698,54.343],[22.838,54.401],[23.449,54.155],[23.591,53.611],[23.894,53.152],[23.859,53.068],[23.922,52.743],[23.869,52.67],[23.392,52.51],[23.166,52.289],[23.637,52.084],[23.676,51.994],[23.543,51.593],[23.698,51.404],[23.635,51.305],[23.864,51.148],[23.979,50.938],[24.143,50.856],[23.958,50.808],[24.081,50.713],[24.108,50.541],[23.981,50.405],[23.682,50.368],[22.666,49.567],[22.738,49.275],[22.682,49.161],[22.853,49.085],[22.855,48.994],[22.041,49.197],[21.928,49.331],[21.601,49.426],[21.069,49.419],[21.073,49.357],[20.919,49.29],[20.69,49.401],[20.318,49.392],[20.136,49.309],[20.05,49.173],[19.938,49.225],[19.761,49.194],[19.809,49.271],[19.769,49.393],[19.627,49.402],[19.457,49.598],[19.117,49.391],[18.962,49.389],[18.961,49.493],[18.837,49.527]]]}},{"type":"Feature","properties":{"iso":"IRL","nom":"Irlande","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[-6.94,55.239],[-7.405,55.004],[-7.543,54.742],[-7.93,54.697],[-7.708,54.604],[-8.174,54.462],[-7.88,54.287],[-7.856,54.211],[-7.327,54.114],[-7.153,54.224],[-7.192,54.335],[-7.018,54.413],[-6.88,54.342],[-6.788,54.203],[-6.64,54.168],[-6.631,54.042],[-6.378,54.063],[-6.355,54.111],[-6.107,54.014],[-6.36,54.016],[-6.378,53.935],[-6.243,53.865],[-6.23,53.657],[-6.077,53.555],[-6.195,53.461],[-6.062,53.367],[-6.218,53.347],[-6.097,53.286],[-5.994,52.957],[-6.13,52.816],[-6.209,52.546],[-6.366,52.344],[-6.496,52.364],[-6.409,52.289],[-6.373,52.323],[-6.347,52.197],[-6.806,52.213],[-6.764,52.261],[-6.932,52.125],[-6.904,52.172],[-6.997,52.289],[-6.955,52.179],[-7.017,52.138],[-7.106,52.173],[-7.6,52.101],[-7.627,52.063],[-7.545,52.055],[-7.59,51.991],[-7.723,51.945],[-7.85,51.98],[-7.891,51.882],[-8.021,51.824],[-8.246,51.803],[-8.187,51.893],[-8.409,51.892],[-8.298,51.83],[-8.297,51.766],[-8.484,51.678],[-8.491,51.699],[-8.512,51.706],[-8.558,51.706],[-8.498,51.693],[-8.532,51.611],[-8.758,51.645],[-8.69,51.631],[-8.696,51.577],[-9.121,51.563],[-9.224,51.487],[-9.381,51.474],[-9.32,51.535],[-9.402,51.501],[-9.443,51.56],[-9.82,51.446],[-9.834,51.487],[-9.546,51.611],[-9.848,51.549],[-9.459,51.684],[-9.56,51.762],[-9.627,51.685],[-9.874,51.656],[-10.156,51.583],[-9.981,51.732],[-9.581,51.878],[-10.136,51.741],[-10.235,51.851],[-10.341,51.788],[-10.396,51.885],[-10.254,51.909],[-10.307,51.953],[-10.266,51.988],[-9.758,52.152],[-10.437,52.097],[-10.461,52.18],[-10.172,52.287],[-10.166,52.235],[-10.101,52.241],[-10.06,52.31],[-9.947,52.238],[-9.738,52.248],[-9.869,52.273],[-9.834,52.375],[-9.95,52.412],[-9.635,52.474],[-9.683,52.495],[-9.648,52.57],[-9.272,52.577],[-8.751,52.673],[-8.961,52.694],[-8.943,52.775],[-9.286,52.591],[-9.333,52.598],[-9.279,52.639],[-9.434,52.612],[-9.581,52.666],[-9.707,52.58],[-9.936,52.557],[-9.499,52.753],[-9.354,52.933],[-9.478,52.94],[-9.272,53.147],[-9.073,53.118],[-9.128,53.159],[-8.936,53.146],[-8.895,53.221],[-9.046,53.221],[-8.943,53.262],[-9.022,53.275],[-9.512,53.228],[-9.555,53.291],[-9.612,53.236],[-9.553,53.385],[-9.807,53.302],[-9.902,53.324],[-9.799,53.42],[-10.177,53.413],[-10.012,53.482],[-10.18,53.555],[-9.697,53.598],[-9.908,53.646],[-9.908,53.762],[-9.566,53.796],[-9.622,53.817],[-9.56,53.865],[-9.944,53.879],[-9.908,53.92],[-9.916,53.954],[-9.788,53.916],[-9.899,54.025],[-9.834,54.112],[-9.971,54.079],[-9.908,54.118],[-10.011,54.218],[-10.117,54.096],[-10.06,54.222],[-10.115,54.235],[-9.998,54.304],[-9.881,54.263],[-9.977,54.242],[-9.91,54.204],[-9.844,54.277],[-9.765,54.256],[-9.846,54.321],[-9.786,54.338],[-9.268,54.304],[-9.141,54.146],[-9.051,54.289],[-8.511,54.208],[-8.621,54.256],[-8.47,54.277],[-8.573,54.314],[-8.519,54.327],[-8.664,54.359],[-8.467,54.475],[-8.21,54.502],[-8.271,54.524],[-8.121,54.647],[-8.457,54.565],[-8.388,54.62],[-8.673,54.619],[-8.798,54.692],[-8.637,54.768],[-8.457,54.756],[-8.53,54.788],[-8.408,54.763],[-8.558,54.818],[-8.491,54.852],[-8.326,54.832],[-8.381,54.856],[-8.337,54.904],[-8.451,54.922],[-8.367,54.948],[-8.457,55.003],[-8.32,55.034],[-8.278,55.161],[-8.156,55.124],[-7.977,55.222],[-8.004,55.174],[-7.856,55.139],[-7.866,55.215],[-7.799,55.256],[-7.816,55.195],[-7.718,55.167],[-7.703,55.099],[-7.695,55.207],[-7.788,55.219],[-7.644,55.273],[-7.526,55.116],[-7.681,54.954],[-7.456,55.056],[-7.55,55.215],[-7.524,55.29],[-7.257,55.284],[-7.384,55.386],[-6.94,55.239]]]]}},{"type":"Feature","properties":{"iso":"GBR","nom":"Royaume-Uni","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[-7.405,55.004],[-7.054,55.049],[-6.963,55.195],[-6.476,55.249],[-6.101,55.212],[-6.037,55.168],[-6.062,55.074],[-5.968,55.044],[-5.986,54.982],[-5.69,54.793],[-5.907,54.606],[-5.575,54.68],[-5.434,54.461],[-5.516,54.338],[-5.577,54.403],[-5.558,54.512],[-5.702,54.578],[-5.626,54.441],[-5.709,54.352],[-5.58,54.384],[-5.553,54.299],[-5.656,54.23],[-5.862,54.231],[-5.894,54.105],[-6.08,54.035],[-6.355,54.111],[-6.378,54.063],[-6.631,54.042],[-6.64,54.168],[-6.788,54.203],[-6.88,54.342],[-7.018,54.413],[-7.192,54.335],[-7.153,54.224],[-7.28,54.126],[-7.609,54.14],[-7.856,54.211],[-7.88,54.287],[-8.174,54.462],[-7.708,54.604],[-7.93,54.697],[-7.543,54.742],[-7.405,55.004]]],[[[-2.694,51.596],[-2.975,51.563],[-3.185,51.398],[-3.539,51.399],[-3.738,51.491],[-3.842,51.622],[-4.29,51.556],[-4.29,51.617],[-4.091,51.64],[-4.071,51.676],[-4.315,51.677],[-4.365,51.789],[-4.941,51.597],[-5.12,51.678],[-4.845,51.714],[-4.879,51.762],[-4.824,51.796],[-4.934,51.775],[-4.911,51.718],[-5.183,51.689],[-5.25,51.734],[-5.11,51.779],[-5.126,51.856],[-5.311,51.864],[-5.07,52.026],[-4.841,52.015],[-4.72,52.113],[-4.316,52.216],[-4.11,52.365],[-4.057,52.529],[-3.947,52.549],[-4.125,52.604],[-3.988,52.734],[-4.149,52.812],[-4.078,52.927],[-4.407,52.893],[-4.516,52.789],[-4.763,52.789],[-4.358,53.028],[-4.341,53.113],[-4.321,53.102],[-4.178,53.218],[-3.831,53.289],[-3.878,53.338],[-3.602,53.289],[-3.33,53.352],[-3.088,53.235],[-3.186,53.393],[-3.058,53.435],[-2.881,53.288],[-2.7,53.352],[-2.925,53.35],[-3.102,53.558],[-2.899,53.735],[-3.049,53.77],[-3.057,53.906],[-2.858,53.968],[-2.83,54.016],[-2.918,54.034],[-2.796,54.125],[-2.854,54.194],[-2.81,54.212],[-2.796,54.249],[-2.939,54.155],[-3.049,54.222],[-3.145,54.064],[-3.241,54.112],[-3.207,54.263],[-3.307,54.192],[-3.634,54.513],[-3.388,54.883],[-3.022,54.976],[-3.571,54.995],[-3.582,54.884],[-3.817,54.886],[-3.824,54.825],[-4.012,54.768],[-4.064,54.832],[-4.123,54.773],[-4.201,54.866],[-4.271,54.839],[-4.403,54.907],[-4.417,54.846],[-4.344,54.795],[-4.382,54.68],[-4.859,54.866],[-4.955,54.805],[-4.859,54.633],[-5.157,54.879],[-5.171,55.009],[-5.115,55.032],[-4.996,54.92],[-5.05,55.027],[-5.008,55.141],[-4.618,55.496],[-4.693,55.605],[-4.921,55.709],[-4.861,55.757],[-4.886,55.92],[-4.482,55.928],[-4.673,55.962],[-4.824,56.079],[-4.779,55.992],[-4.852,55.988],[-4.865,56.067],[-4.756,56.207],[-4.852,56.113],[-4.921,56.168],[-4.893,55.99],[-4.955,55.997],[-4.914,55.962],[-4.983,55.871],[-5.124,56.01],[-5.087,55.901],[-5.181,55.969],[-5.242,55.893],[-5.201,55.831],[-5.297,55.853],[-5.338,55.997],[-4.921,56.278],[-5.369,56.009],[-5.444,56.028],[-5.455,55.956],[-5.318,55.783],[-5.49,55.645],[-5.455,55.592],[-5.585,55.427],[-5.525,55.359],[-5.783,55.314],[-5.681,55.674],[-5.455,55.846],[-5.599,55.764],[-5.66,55.797],[-5.571,55.935],[-5.696,55.916],[-5.571,56.038],[-5.708,55.943],[-5.532,56.086],[-5.51,56.188],[-5.606,56.14],[-5.493,56.26],[-5.592,56.25],[-5.573,56.328],[-5.448,56.36],[-5.538,56.36],[-5.457,56.441],[-5.209,56.447],[-5.119,56.508],[-5.065,56.565],[-5.201,56.462],[-5.469,56.476],[-5.428,56.538],[-5.357,56.52],[-5.242,56.565],[-5.414,56.545],[-5.318,56.661],[-4.996,56.716],[-5.238,56.717],[-5.12,56.818],[-5.674,56.497],[-6.008,56.642],[-5.544,56.695],[-6.162,56.678],[-6.234,56.729],[-5.757,56.785],[-5.851,56.829],[-5.734,56.845],[-5.66,56.873],[-5.921,56.894],[-5.852,56.9],[-5.832,56.997],[-5.755,57.027],[-5.659,56.979],[-5.571,56.984],[-5.523,57.004],[-5.629,56.992],[-5.776,57.076],[-5.646,57.129],[-5.558,57.1],[-5.4,57.106],[-5.681,57.158],[-5.578,57.267],[-5.407,57.23],[-5.502,57.278],[-5.441,57.319],[-5.729,57.298],[-5.501,57.371],[-5.448,57.422],[-5.808,57.355],[-5.873,57.494],[-5.839,57.579],[-5.64,57.511],[-5.513,57.541],[-5.66,57.545],[-5.806,57.643],[-5.791,57.696],[-5.674,57.71],[-5.804,57.744],[-5.811,57.833],[-5.699,57.869],[-5.66,57.792],[-5.606,57.77],[-5.585,57.831],[-5.654,57.895],[-5.613,57.929],[-5.487,57.856],[-5.415,57.908],[-5.222,57.847],[-5.366,57.943],[-5.071,57.833],[-5.447,58.084],[-5.301,58.07],[-5.242,58.148],[-5.392,58.261],[-4.934,58.223],[-5.173,58.354],[-5.143,58.415],[-5.016,58.388],[-5.098,58.415],[-4.996,58.437],[-5.106,58.506],[-4.988,58.628],[-4.836,58.605],[-4.818,58.525],[-4.777,58.607],[-4.66,58.556],[-4.761,58.448],[-4.585,58.574],[-4.427,58.546],[-4.495,58.45],[-4.344,58.539],[-4.029,58.595],[-3.364,58.601],[-3.413,58.656],[-3.375,58.677],[-3.019,58.64],[-3.129,58.513],[-3.053,58.466],[-3.13,58.369],[-4.002,57.936],[-4.084,57.964],[-3.988,57.908],[-4.009,57.868],[-4.392,57.908],[-4.04,57.818],[-3.779,57.856],[-3.988,57.696],[-4.043,57.737],[-4.295,57.68],[-4.428,57.578],[-4.009,57.689],[-4.105,57.579],[-4.263,57.552],[-4.208,57.538],[-4.249,57.497],[-4.035,57.557],[-4.084,57.586],[-3.591,57.641],[-3.409,57.723],[-3.035,57.669],[-1.998,57.703],[-1.829,57.613],[-1.759,57.474],[-1.98,57.319],[-2.186,56.915],[-2.426,56.751],[-2.515,56.591],[-2.728,56.47],[-3.061,56.452],[-3.323,56.366],[-2.885,56.458],[-2.803,56.428],[-2.803,56.345],[-2.577,56.278],[-2.784,56.192],[-2.964,56.206],[-3.164,56.064],[-3.343,56.027],[-3.837,56.106],[-3.656,56.01],[-3.078,55.947],[-2.823,56.06],[-2.635,56.058],[-2.138,55.915],[-1.816,55.633],[-1.631,55.585],[-1.518,55.157],[-1.275,54.748],[-1.172,54.701],[-1.204,54.626],[-0.563,54.477],[-0.37,54.248],[-0.076,54.112],[-0.219,54.023],[0.133,53.643],[0.149,53.61],[0.131,53.573],[-0.26,53.735],[-0.637,53.732],[-0.726,53.701],[-0.279,53.707],[0.219,53.42],[0.357,53.146],[0.01,52.886],[0.385,52.768],[0.57,52.969],[1.275,52.929],[1.644,52.776],[1.747,52.625],[1.771,52.486],[1.582,52.081],[1.332,51.94],[1.264,51.994],[1.158,52.029],[1.274,51.961],[1.069,51.953],[1.282,51.947],[1.2,51.878],[1.276,51.845],[1.065,51.775],[0.98,51.844],[0.874,51.747],[0.699,51.72],[0.93,51.744],[0.924,51.588],[0.456,51.506],[0.385,51.453],[0.695,51.477],[0.723,51.447],[0.555,51.412],[0.726,51.419],[0.764,51.364],[0.977,51.349],[1.448,51.383],[1.378,51.326],[1.384,51.152],[1.067,51.064],[0.966,50.983],[0.98,50.918],[0.762,50.931],[0.271,50.747],[-0.27,50.831],[-0.758,50.777],[-0.79,50.73],[-0.939,50.843],[-1.021,50.844],[-1.083,50.781],[-1.069,50.844],[-1.165,50.844],[-1.151,50.781],[-1.466,50.918],[-1.317,50.8],[-1.561,50.719],[-1.94,50.691],[-2.039,50.74],[-2.083,50.699],[-1.953,50.677],[-1.965,50.602],[-2.398,50.646],[-2.453,50.528],[-2.484,50.59],[-2.865,50.734],[-3.368,50.617],[-3.464,50.679],[-3.487,50.459],[-3.556,50.432],[-3.487,50.405],[-3.632,50.312],[-3.661,50.221],[-4.054,50.3],[-4.201,50.459],[-4.29,50.397],[-4.194,50.377],[-4.194,50.322],[-4.338,50.371],[-4.694,50.343],[-5.002,50.144],[-5.053,50.196],[-5.126,50.096],[-5.057,50.061],[-5.191,49.959],[-5.304,50.08],[-5.475,50.13],[-5.705,50.052],[-5.685,50.162],[-5.315,50.254],[-5.05,50.429],[-5.016,50.538],[-4.845,50.514],[-4.921,50.589],[-4.792,50.595],[-4.577,50.775],[-4.526,51.015],[-4.338,50.997],[-4.208,51.076],[-4.229,51.192],[-3.769,51.248],[-3.022,51.192],[-2.975,51.384],[-2.696,51.513],[-2.383,51.773],[-2.694,51.596]]],[[[-1.062,50.693],[-1.279,50.583],[-1.569,50.658],[-1.319,50.772],[-1.062,50.693]]],[[[-4.069,53.31],[-4.222,53.182],[-4.407,53.131],[-4.385,53.182],[-4.495,53.18],[-4.571,53.275],[-4.571,53.393],[-4.325,53.42],[-4.203,53.298],[-4.069,53.31]]],[[[-5.093,55.5],[-5.118,55.44],[-5.305,55.462],[-5.393,55.647],[-5.297,55.723],[-5.198,55.704],[-5.093,55.5]]],[[[-6.033,55.718],[-6.287,55.578],[-6.319,55.628],[-6.243,55.66],[-6.325,55.715],[-6.25,55.777],[-6.504,55.681],[-6.445,55.849],[-6.331,55.89],[-6.311,55.818],[-6.14,55.941],[-6.033,55.718]]],[[[-5.746,56.142],[-5.689,56.112],[-5.962,55.805],[-6.062,55.809],[-6.075,55.916],[-5.886,55.976],[-5.996,55.986],[-5.746,56.142]]],[[[-5.68,56.428],[-5.809,56.319],[-5.873,56.358],[-6.267,56.263],[-6.366,56.322],[-6.247,56.312],[-6.021,56.382],[-6.203,56.38],[-6.017,56.504],[-6.127,56.474],[-6.338,56.552],[-6.29,56.572],[-6.325,56.606],[-6.151,56.652],[-5.68,56.428]]],[[[-7.232,57.319],[-7.257,57.237],[-7.353,57.243],[-7.26,57.16],[-7.346,57.148],[-7.216,57.114],[-7.353,57.1],[-7.455,57.237],[-7.39,57.312],[-7.428,57.388],[-7.353,57.408],[-7.223,57.34],[-7.394,57.381],[-7.37,57.355],[-7.232,57.319]]],[[[-7.312,57.689],[-7.065,57.634],[-7.216,57.641],[-7.126,57.571],[-7.312,57.552],[-7.158,57.511],[-7.545,57.593],[-7.312,57.689]]],[[[-6.581,57.339],[-6.784,57.456],[-6.716,57.514],[-6.607,57.444],[-6.631,57.502],[-6.564,57.504],[-6.655,57.552],[-6.64,57.607],[-6.311,57.463],[-6.416,57.646],[-6.311,57.703],[-6.154,57.59],[-6.188,57.394],[-6.127,57.408],[-6.099,57.332],[-6.154,57.306],[-5.901,57.243],[-5.647,57.265],[-6.007,57.028],[-5.987,57.118],[-5.845,57.188],[-5.986,57.175],[-6.044,57.23],[-6.089,57.127],[-6.164,57.201],[-6.318,57.161],[-6.277,57.202],[-6.346,57.188],[-6.346,57.243],[-6.482,57.312],[-6.324,57.311],[-6.531,57.415],[-6.581,57.339]]],[[[-6.973,57.733],[-7.125,57.837],[-6.839,57.936],[-7.113,57.99],[-6.935,58.052],[-7.058,58.039],[-7.024,58.08],[-7.113,58.1],[-7.113,58.182],[-7.017,58.189],[-7.031,58.245],[-6.907,58.217],[-6.937,58.211],[-6.86,58.107],[-6.869,58.189],[-6.709,58.189],[-6.819,58.285],[-6.223,58.499],[-6.167,58.347],[-6.366,58.237],[-6.151,58.258],[-6.16,58.217],[-6.4,58.21],[-6.373,58.141],[-6.619,58.086],[-6.407,58.107],[-6.352,58.039],[-6.545,58.018],[-6.455,57.977],[-6.537,57.921],[-6.661,57.929],[-6.709,58.004],[-6.592,58.059],[-6.688,58.059],[-6.764,58.004],[-6.661,57.88],[-6.787,57.899],[-6.742,57.831],[-6.853,57.833],[-6.973,57.733]]],[[[-2.714,58.967],[-2.839,58.883],[-2.981,58.96],[-3.203,58.916],[-3.228,59.039],[-3.289,58.95],[-3.367,59.016],[-3.324,59.127],[-3.183,59.147],[-2.994,59.073],[-3.117,58.998],[-2.781,58.99],[-2.838,58.95],[-2.795,58.926],[-2.714,58.967]]]]}},{"type":"Feature","properties":{"iso":"GRC","nom":"Grèce","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[20.965,40.849],[21.766,40.924],[21.909,41.097],[22.048,41.152],[22.705,41.14],[22.781,41.335],[23.157,41.316],[23.288,41.398],[23.612,41.371],[24.035,41.451],[24.047,41.526],[24.233,41.562],[24.296,41.515],[24.51,41.562],[24.58,41.441],[24.774,41.348],[24.886,41.401],[25.286,41.239],[26.121,41.358],[26.163,41.529],[26.048,41.689],[26.226,41.75],[26.595,41.612],[26.636,41.4],[26.61,41.331],[26.321,41.246],[26.359,40.965],[26.082,40.736],[26.006,40.804],[26.054,40.831],[25.538,40.87],[25.181,40.943],[25.138,41.01],[24.802,40.853],[24.629,40.859],[24.505,40.962],[24.11,40.728],[23.732,40.752],[23.7,40.674],[23.915,40.539],[23.823,40.507],[23.868,40.414],[24.002,40.386],[24.011,40.449],[24.394,40.152],[24.3,40.128],[24.169,40.275],[23.937,40.365],[23.73,40.359],[23.716,40.255],[23.991,40.119],[23.991,39.954],[23.827,40.009],[23.675,40.218],[23.438,40.279],[23.34,40.228],[23.364,40.15],[23.748,39.93],[23.361,39.961],[23.299,40.235],[22.888,40.386],[22.822,40.502],[22.983,40.553],[22.91,40.645],[22.579,40.468],[22.661,40.369],[22.553,40.167],[22.571,40.054],[22.708,39.961],[22.939,39.581],[23.097,39.502],[23.344,39.18],[23.204,39.105],[23.052,39.098],[23.217,39.18],[23.135,39.297],[22.936,39.361],[22.943,39.303],[22.843,39.288],[22.826,39.221],[22.998,39.07],[22.964,39.009],[23.073,39.036],[22.792,38.878],[22.622,38.914],[22.525,38.858],[23.042,38.747],[23.105,38.638],[23.187,38.686],[23.306,38.653],[23.285,38.556],[23.382,38.535],[23.335,38.504],[23.567,38.501],[23.573,38.453],[23.673,38.356],[23.951,38.291],[24.081,38.166],[23.989,38.123],[24.012,37.892],[24.087,37.785],[24.033,37.652],[23.866,37.808],[23.779,37.802],[23.697,37.94],[23.561,37.973],[23.575,38.047],[22.995,37.882],[23.182,37.809],[23.121,37.741],[23.176,37.72],[23.169,37.614],[23.337,37.535],[23.312,37.617],[23.399,37.638],[23.395,37.515],[23.526,37.439],[23.263,37.401],[23.278,37.35],[23.169,37.3],[23.073,37.355],[23.132,37.449],[23.005,37.46],[22.922,37.54],[22.854,37.515],[22.778,37.597],[22.726,37.566],[22.758,37.398],[23.114,36.781],[23.031,36.726],[23.036,36.649],[23.196,36.433],[22.972,36.52],[22.815,36.671],[22.787,36.793],[22.686,36.809],[22.577,36.783],[22.484,36.607],[22.491,36.391],[22.355,36.512],[22.388,36.706],[22.138,36.917],[22.153,37.021],[21.943,36.993],[21.97,36.795],[21.883,36.727],[21.823,36.809],[21.707,36.818],[21.71,36.943],[21.57,37.116],[21.696,37.316],[21.675,37.396],[21.55,37.561],[21.402,37.655],[21.312,37.638],[21.285,37.785],[21.106,37.878],[21.134,37.946],[21.326,38.021],[21.284,38.015],[21.374,38.221],[21.622,38.155],[21.849,38.341],[22.68,38.067],[22.867,37.94],[22.975,37.979],[22.875,38.049],[23.173,38.079],[23.223,38.159],[22.806,38.227],[22.646,38.39],[22.563,38.294],[22.402,38.453],[22.382,38.343],[22.189,38.323],[21.958,38.412],[21.518,38.296],[21.323,38.496],[21.337,38.396],[21.156,38.304],[21.085,38.344],[21.14,38.399],[21.087,38.41],[21.096,38.532],[21.031,38.511],[20.988,38.664],[20.86,38.804],[20.773,38.761],[20.729,38.81],[20.805,38.868],[20.77,38.959],[21.027,38.933],[21.085,38.864],[21.102,38.911],[21.177,38.876],[21.16,38.998],[21.085,39.063],[21.058,39.009],[20.901,39.077],[20.886,39.036],[20.845,39.037],[20.822,39.114],[20.743,39.029],[20.832,38.964],[20.766,38.978],[20.735,38.95],[20.482,39.283],[20.325,39.304],[20.236,39.399],[20.267,39.447],[20.216,39.495],[20.264,39.509],[20.134,39.53],[20.182,39.624],[20.0,39.694],[20.2,39.64],[20.296,39.717],[20.28,39.804],[20.389,39.798],[20.298,39.987],[20.648,40.094],[20.771,40.422],[21.019,40.559],[20.965,40.849]]],[[[26.312,35.297],[26.278,35.1],[26.147,35.002],[25.985,35.039],[24.739,34.932],[24.718,35.094],[24.402,35.191],[23.611,35.235],[23.518,35.308],[23.58,35.576],[23.605,35.613],[23.62,35.524],[23.718,35.513],[23.742,35.687],[23.817,35.535],[24.025,35.521],[24.082,35.59],[24.183,35.586],[24.183,35.513],[24.072,35.498],[24.252,35.479],[24.265,35.37],[24.34,35.348],[24.721,35.427],[24.971,35.425],[25.077,35.344],[25.454,35.294],[25.766,35.336],[25.713,35.183],[25.795,35.115],[26.061,35.233],[26.155,35.198],[26.312,35.297]]],[[[28.226,36.418],[28.062,36.117],[28.09,36.055],[27.993,36.062],[27.827,35.914],[27.733,35.915],[27.757,36.084],[27.684,36.158],[27.9,36.34],[28.226,36.418]]],[[[25.534,37.201],[25.592,37.143],[25.581,37.018],[25.45,36.918],[25.342,37.083],[25.534,37.201]]],[[[27.068,37.774],[27.061,37.707],[26.861,37.643],[26.708,37.714],[26.598,37.677],[26.58,37.741],[26.806,37.815],[26.966,37.748],[26.945,37.789],[27.068,37.774]]],[[[20.709,37.925],[20.987,37.73],[20.996,37.699],[20.894,37.733],[20.815,37.652],[20.619,37.864],[20.709,37.925]]],[[[24.954,37.906],[24.958,37.686],[24.716,37.879],[24.694,37.966],[24.779,38.0],[24.848,37.915],[24.954,37.906]]],[[[20.718,38.066],[20.51,38.111],[20.445,38.276],[20.425,38.175],[20.345,38.182],[20.4,38.364],[20.53,38.337],[20.538,38.474],[20.631,38.258],[20.682,38.282],[20.805,38.116],[20.718,38.066]]],[[[26.151,38.53],[26.164,38.303],[26.112,38.223],[26.01,38.157],[25.89,38.221],[25.876,38.275],[25.989,38.379],[25.843,38.515],[25.849,38.58],[26.016,38.602],[26.151,38.53]]],[[[24.588,38.159],[24.552,37.978],[24.43,38.021],[24.372,37.972],[24.286,38.086],[24.204,38.09],[24.185,38.218],[24.126,38.217],[24.153,38.281],[24.025,38.331],[24.042,38.402],[23.649,38.406],[23.594,38.453],[23.614,38.558],[23.202,38.83],[22.969,38.889],[22.982,38.845],[22.837,38.854],[23.309,39.038],[23.594,38.77],[24.156,38.653],[24.126,38.599],[24.231,38.522],[24.185,38.408],[24.252,38.228],[24.344,38.159],[24.588,38.159]]],[[[26.612,39.04],[26.539,39.019],[26.489,39.114],[26.437,39.104],[26.547,38.988],[26.166,39.022],[26.088,39.083],[26.28,39.196],[26.187,39.202],[26.064,39.091],[25.889,39.145],[25.842,39.228],[25.917,39.297],[26.163,39.324],[26.164,39.379],[26.362,39.379],[26.417,39.33],[26.382,39.277],[26.612,39.04]]],[[[20.097,39.423],[20.106,39.365],[19.912,39.43],[19.626,39.748],[19.852,39.825],[19.948,39.79],[19.845,39.653],[19.928,39.625],[19.937,39.473],[20.097,39.423]]],[[[25.441,40.026],[25.348,39.906],[25.349,39.788],[25.239,39.858],[25.251,39.919],[25.177,39.845],[25.215,39.803],[25.143,39.817],[25.165,39.859],[25.047,39.838],[25.033,39.995],[25.225,40.009],[25.285,39.953],[25.441,40.026]]],[[[24.765,40.734],[24.78,40.612],[24.642,40.571],[24.517,40.639],[24.642,40.804],[24.765,40.734]]]]}},{"type":"Feature","properties":{"iso":"AUT","nom":"Autriche","focus":false},"geometry":{"type":"Polygon","coordinates":[[[16.954,48.557],[16.844,48.366],[17.08,48.098],[17.07,48.036],[17.148,48.005],[17.004,47.863],[17.075,47.708],[16.797,47.675],[16.568,47.754],[16.408,47.661],[16.63,47.622],[16.689,47.538],[16.641,47.453],[16.434,47.397],[16.473,47.277],[16.413,47.187],[16.51,47.138],[16.425,47.024],[16.486,46.999],[16.275,47.004],[15.982,46.828],[16.017,46.671],[15.851,46.724],[15.636,46.718],[15.463,46.615],[15.062,46.65],[14.85,46.601],[14.789,46.507],[14.54,46.379],[14.396,46.441],[12.405,46.69],[12.269,46.789],[12.267,46.868],[12.127,46.909],[12.181,47.085],[11.735,46.971],[11.174,46.964],[10.997,46.769],[10.723,46.786],[10.739,46.83],[10.647,46.864],[10.486,46.846],[10.373,46.996],[10.111,46.847],[9.875,46.927],[9.858,47.015],[9.581,47.057],[9.616,47.107],[9.521,47.263],[9.65,47.41],[9.547,47.535],[9.677,47.523],[9.782,47.588],[10.023,47.488],[10.083,47.359],[10.209,47.372],[10.16,47.271],[10.428,47.396],[10.429,47.577],[10.859,47.531],[10.979,47.391],[11.237,47.394],[11.62,47.59],[12.174,47.605],[12.177,47.706],[12.242,47.732],[12.239,47.679],[12.424,47.692],[12.497,47.629],[12.762,47.667],[12.813,47.612],[12.779,47.555],[13.002,47.466],[13.072,47.659],[12.892,47.724],[12.991,47.847],[12.745,48.121],[13.406,48.377],[13.455,48.573],[13.717,48.522],[13.802,48.612],[13.816,48.766],[13.982,48.706],[14.075,48.592],[14.325,48.559],[14.458,48.643],[14.676,48.576],[14.8,48.777],[14.94,48.763],[14.982,49.008],[15.137,48.993],[15.142,48.937],[15.275,48.987],[15.681,48.858],[15.818,48.872],[16.085,48.743],[16.624,48.783],[16.873,48.719],[16.954,48.557]]]}},{"type":"Feature","properties":{"iso":"ITA","nom":"Italie","focus":true},"geometry":{"type":"MultiPolygon","coordinates":[[[[7.008,45.921],[7.541,45.984],[7.844,45.919],[8.111,46.127],[8.087,46.272],[8.399,46.452],[8.438,46.235],[8.602,46.123],[8.809,46.09],[8.768,45.983],[8.871,45.947],[8.9,45.826],[9.002,45.821],[9.063,45.899],[8.981,45.964],[9.002,46.039],[9.225,46.231],[9.282,46.497],[9.435,46.498],[9.444,46.375],[9.536,46.299],[9.918,46.371],[10.076,46.22],[10.159,46.262],[10.092,46.329],[10.141,46.403],[10.026,46.446],[10.033,46.533],[10.192,46.627],[10.444,46.538],[10.459,46.624],[10.369,46.672],[10.454,46.864],[10.997,46.769],[11.174,46.964],[11.735,46.971],[12.181,47.085],[12.127,46.909],[12.267,46.868],[12.269,46.789],[12.405,46.69],[13.701,46.52],[13.677,46.452],[13.365,46.29],[13.41,46.208],[13.637,46.18],[13.462,46.006],[13.606,45.985],[13.566,45.83],[13.779,45.743],[13.895,45.632],[13.848,45.585],[13.712,45.593],[13.808,45.614],[13.574,45.79],[13.402,45.675],[13.431,45.707],[13.369,45.745],[13.119,45.772],[13.075,45.697],[13.15,45.704],[13.085,45.642],[12.424,45.438],[12.582,45.553],[12.397,45.539],[12.424,45.498],[12.31,45.489],[12.216,45.316],[12.154,45.313],[12.181,45.258],[12.217,45.294],[12.23,45.204],[12.307,45.231],[12.297,45.089],[12.369,45.011],[12.369,45.066],[12.534,44.97],[12.445,44.821],[12.407,44.891],[12.416,44.803],[12.266,44.827],[12.284,44.488],[12.369,44.251],[12.692,43.991],[13.616,43.56],[14.075,42.599],[14.56,42.226],[14.709,42.175],[14.741,42.085],[15.165,41.928],[16.14,41.92],[16.184,41.78],[15.9,41.615],[15.961,41.459],[17.057,41.082],[17.476,40.83],[18.007,40.651],[18.037,40.557],[18.238,40.458],[18.516,40.139],[18.389,39.817],[18.072,39.912],[17.863,40.286],[17.512,40.304],[17.2,40.42],[17.323,40.498],[16.976,40.493],[16.605,40.084],[16.632,39.966],[16.49,39.775],[16.546,39.661],[16.782,39.612],[17.159,39.406],[17.115,39.269],[17.125,39.091],[17.206,39.029],[17.172,38.961],[17.104,38.899],[16.839,38.918],[16.586,38.798],[16.535,38.7],[16.57,38.43],[16.169,38.143],[16.077,37.94],[15.684,37.954],[15.633,38.22],[15.813,38.301],[15.918,38.517],[15.837,38.649],[16.153,38.731],[16.222,38.857],[16.083,39.075],[15.995,39.439],[15.806,39.696],[15.774,39.891],[15.624,40.078],[15.41,39.994],[15.261,40.029],[15.127,40.17],[14.911,40.242],[14.998,40.398],[14.782,40.67],[14.343,40.571],[14.474,40.73],[14.294,40.839],[14.048,40.79],[14.021,40.922],[13.722,41.252],[13.544,41.207],[13.286,41.296],[13.045,41.228],[12.894,41.399],[12.635,41.447],[12.239,41.736],[12.17,41.88],[12.02,41.993],[11.827,42.034],[11.658,42.279],[11.377,42.407],[11.107,42.391],[11.099,42.443],[11.188,42.48],[11.158,42.564],[10.944,42.743],[10.731,42.804],[10.764,42.918],[10.5,42.94],[10.528,43.247],[10.317,43.493],[10.252,43.847],[10.091,44.025],[9.845,44.109],[9.832,44.042],[9.231,44.354],[9.211,44.305],[8.762,44.432],[8.466,44.304],[8.068,43.897],[7.502,43.792],[7.478,43.866],[7.69,44.067],[7.656,44.176],[7.341,44.124],[6.973,44.249],[6.87,44.363],[6.918,44.436],[6.836,44.534],[6.96,44.683],[7.055,44.685],[7.005,44.828],[6.745,44.908],[6.723,45.013],[6.603,45.103],[6.844,45.13],[7.108,45.259],[7.161,45.411],[6.983,45.511],[6.963,45.641],[6.816,45.697],[6.782,45.777],[7.008,45.921]],[[12.386,43.925],[12.49,43.939],[12.482,43.983],[12.386,43.925]],[[12.453,41.903],[12.454,41.904],[12.453,41.904],[12.453,41.903]]],[[[15.559,38.3],[15.652,38.275],[15.213,37.761],[15.092,37.477],[15.104,37.33],[15.252,37.258],[15.183,37.207],[15.332,37.012],[15.158,36.924],[15.094,36.655],[14.487,36.793],[14.279,37.044],[13.716,37.171],[13.174,37.487],[13.026,37.493],[12.943,37.569],[12.659,37.565],[12.427,37.797],[12.493,38.021],[12.705,38.111],[12.732,38.193],[12.901,38.028],[13.061,38.083],[13.101,38.19],[13.318,38.221],[13.391,38.103],[13.514,38.111],[13.791,37.974],[14.021,38.049],[14.512,38.044],[14.907,38.188],[15.088,38.128],[15.237,38.265],[15.292,38.207],[15.559,38.3]]],[[[9.821,40.536],[9.626,40.263],[9.732,40.084],[9.635,39.297],[9.566,39.149],[9.519,39.105],[9.292,39.221],[9.166,39.187],[9.014,39.264],[9.08,39.225],[9.018,39.146],[9.026,38.995],[8.853,38.878],[8.717,38.933],[8.641,38.864],[8.56,39.057],[8.373,39.222],[8.432,39.302],[8.374,39.379],[8.463,39.577],[8.444,39.757],[8.517,39.702],[8.566,39.701],[8.504,39.722],[8.555,39.853],[8.395,39.913],[8.377,40.034],[8.49,40.104],[8.476,40.292],[8.386,40.352],[8.38,40.469],[8.292,40.595],[8.147,40.593],[8.193,40.964],[8.31,40.851],[8.521,40.827],[8.823,40.947],[9.231,41.263],[9.268,41.237],[9.267,41.202],[9.278,41.195],[9.422,41.181],[9.443,41.092],[9.469,41.146],[9.56,41.126],[9.512,41.016],[9.663,41.003],[9.504,40.927],[9.642,40.921],[9.724,40.845],[9.658,40.8],[9.821,40.536]]]]}},{"type":"Feature","properties":{"iso":"CHE","nom":"Suisse","focus":false},"geometry":{"type":"Polygon","coordinates":[[[10.458,46.937],[10.369,46.672],[10.459,46.624],[10.444,46.538],[10.192,46.627],[10.033,46.533],[10.026,46.446],[10.141,46.403],[10.118,46.231],[10.043,46.22],[9.918,46.371],[9.536,46.299],[9.444,46.375],[9.435,46.498],[9.263,46.485],[9.225,46.231],[9.002,46.039],[8.981,45.964],[9.063,45.899],[9.002,45.821],[8.9,45.826],[8.871,45.947],[8.768,45.983],[8.809,46.09],[8.602,46.123],[8.438,46.235],[8.399,46.452],[8.087,46.272],[8.111,46.127],[7.831,45.914],[7.541,45.984],[7.067,45.89],[6.851,46.05],[6.869,46.112],[6.774,46.135],[6.828,46.269],[6.75,46.346],[6.787,46.414],[6.614,46.456],[6.302,46.394],[6.214,46.315],[6.281,46.24],[6.108,46.139],[5.959,46.13],[5.959,46.212],[6.09,46.246],[6.136,46.359],[6.054,46.419],[6.118,46.583],[6.429,46.761],[6.443,46.944],[6.665,47.021],[7.037,47.33],[6.867,47.354],[6.973,47.489],[7.181,47.488],[7.238,47.417],[7.406,47.438],[7.483,47.542],[7.637,47.595],[7.61,47.565],[7.683,47.544],[8.233,47.622],[8.561,47.589],[8.607,47.656],[8.391,47.665],[8.558,47.801],[8.882,47.656],[9.273,47.65],[9.65,47.452],[9.487,47.21],[9.477,47.064],[9.858,47.015],[9.875,46.927],[10.111,46.847],[10.379,46.996],[10.458,46.937]]]}},{"type":"Feature","properties":{"iso":"NLD","nom":"Pays-Bas","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[7.197,53.217],[7.193,52.998],[7.062,52.824],[7.037,52.647],[6.737,52.635],[6.744,52.56],[6.672,52.542],[6.715,52.462],[6.973,52.451],[7.048,52.365],[7.026,52.231],[6.673,52.05],[6.811,51.961],[6.345,51.821],[6.127,51.897],[6.156,51.842],[5.931,51.816],[5.939,51.732],[6.099,51.644],[6.205,51.458],[6.194,51.345],[6.057,51.212],[6.147,51.152],[5.938,51.031],[5.852,51.043],[5.875,50.965],[6.004,50.974],[6.064,50.908],[5.969,50.795],[5.995,50.75],[5.707,50.754],[5.624,50.83],[5.764,50.959],[5.722,50.959],[5.846,51.103],[5.829,51.156],[5.568,51.208],[5.493,51.287],[5.215,51.259],[5.028,51.477],[4.91,51.392],[4.762,51.413],[4.823,51.414],[4.779,51.495],[4.63,51.418],[4.483,51.474],[4.377,51.443],[4.392,51.35],[3.999,51.453],[3.827,51.391],[3.451,51.53],[3.56,51.595],[3.851,51.611],[3.872,51.549],[4.016,51.531],[4.105,51.446],[4.283,51.448],[4.268,51.508],[3.988,51.59],[4.207,51.59],[4.113,51.639],[4.177,51.686],[3.862,51.816],[4.078,51.844],[4.016,51.988],[4.142,52.006],[4.508,52.336],[4.745,52.968],[4.874,52.904],[5.078,52.954],[5.379,53.097],[5.447,53.221],[5.592,53.303],[5.981,53.406],[6.829,53.451],[6.901,53.352],[7.197,53.217]]],[[[3.511,51.408],[3.834,51.343],[3.984,51.41],[4.221,51.368],[3.927,51.206],[3.635,51.288],[3.367,51.263],[3.349,51.375],[3.511,51.408]]]]}},{"type":"Feature","properties":{"iso":"LIE","nom":"Liechtenstein","focus":false},"geometry":{"type":"Polygon","coordinates":[[[9.53,47.254],[9.616,47.107],[9.561,47.052],[9.477,47.064],[9.53,47.254]]]}},{"type":"Feature","properties":{"iso":"SRB","nom":"Serbie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[20.17,46.146],[20.7,45.735],[20.786,45.753],[20.767,45.479],[20.981,45.333],[21.493,45.145],[21.351,44.998],[21.536,44.889],[21.356,44.857],[21.396,44.79],[21.578,44.778],[21.656,44.688],[21.994,44.659],[22.127,44.503],[22.426,44.734],[22.765,44.583],[22.484,44.5],[22.523,44.375],[22.682,44.305],[22.692,44.228],[22.606,44.175],[22.593,44.064],[22.4,43.993],[22.349,43.808],[22.519,43.474],[22.985,43.175],[22.727,42.887],[22.427,42.814],[22.483,42.734],[22.425,42.573],[22.537,42.478],[22.424,42.326],[22.269,42.37],[21.575,42.242],[21.516,42.342],[21.617,42.387],[21.764,42.67],[21.379,42.744],[21.408,42.847],[21.261,42.887],[21.093,43.091],[20.839,43.17],[20.819,43.257],[20.604,43.198],[20.644,43.052],[20.459,42.95],[20.476,42.856],[20.345,42.827],[20.337,42.907],[19.929,43.114],[19.805,43.09],[19.598,43.176],[19.176,43.481],[19.253,43.589],[19.49,43.564],[19.507,43.647],[19.244,44.002],[19.529,43.977],[19.619,44.036],[19.324,44.264],[19.117,44.344],[19.13,44.518],[19.377,44.863],[19.187,44.928],[19.016,44.866],[18.991,44.915],[19.132,44.953],[19.045,45.137],[19.138,45.146],[19.122,45.196],[19.408,45.203],[18.977,45.371],[19.031,45.416],[19.01,45.499],[19.106,45.512],[18.904,45.573],[18.968,45.669],[18.855,45.857],[19.065,46.012],[19.263,45.981],[19.55,46.164],[20.17,46.146]]]}},{"type":"Feature","properties":{"iso":"HRV","nom":"Croatie","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[16.344,46.547],[16.838,46.382],[17.053,46.153],[17.209,46.117],[17.29,45.985],[17.591,45.936],[17.657,45.845],[17.858,45.772],[18.404,45.742],[18.656,45.908],[18.901,45.931],[18.845,45.816],[18.968,45.669],[18.904,45.573],[19.106,45.512],[19.01,45.499],[19.031,45.416],[18.977,45.371],[19.408,45.203],[19.122,45.196],[19.138,45.146],[19.045,45.137],[19.132,44.953],[18.991,44.915],[19.016,44.866],[18.89,44.861],[18.783,44.914],[18.792,45.002],[18.684,45.085],[18.517,45.056],[18.238,45.157],[18.154,45.098],[18.003,45.149],[17.836,45.064],[17.685,45.164],[17.482,45.114],[17.269,45.19],[17.187,45.149],[16.924,45.285],[16.812,45.181],[16.529,45.222],[16.316,45.001],[16.02,45.214],[15.792,45.19],[15.728,44.769],[16.028,44.625],[16.006,44.541],[16.116,44.521],[16.216,44.208],[16.327,44.082],[17.031,43.548],[17.271,43.463],[17.29,43.303],[17.628,43.047],[17.635,42.95],[17.516,42.959],[17.502,43.031],[17.434,43.017],[16.881,43.406],[16.391,43.511],[16.473,43.538],[16.434,43.55],[15.959,43.504],[15.919,43.629],[15.966,43.641],[15.905,43.648],[15.953,43.651],[15.95,43.689],[15.706,43.763],[15.145,44.195],[15.141,44.282],[15.295,44.251],[15.261,44.333],[15.424,44.268],[15.529,44.272],[15.007,44.57],[14.884,44.724],[14.922,44.959],[14.853,45.094],[14.571,45.294],[14.312,45.344],[14.151,44.977],[14.069,44.95],[14.084,44.986],[14.04,45.039],[14.076,44.984],[13.973,44.901],[14.0,44.813],[13.89,44.833],[13.918,44.778],[13.903,44.772],[13.623,45.073],[13.613,45.118],[13.726,45.135],[13.596,45.145],[13.61,45.32],[13.541,45.346],[13.507,45.512],[13.889,45.424],[13.972,45.514],[14.373,45.478],[14.581,45.668],[14.797,45.465],[14.923,45.515],[15.139,45.43],[15.325,45.453],[15.361,45.482],[15.269,45.602],[15.374,45.64],[15.255,45.723],[15.676,45.842],[15.698,46.036],[15.59,46.114],[15.64,46.208],[16.019,46.299],[16.058,46.378],[16.276,46.373],[16.235,46.493],[16.344,46.547]]],[[[18.442,42.543],[18.496,42.416],[17.893,42.791],[17.721,42.826],[17.762,42.779],[17.749,42.772],[17.214,42.983],[17.046,42.995],[17.002,43.051],[17.741,42.839],[17.653,42.891],[17.812,42.91],[17.858,42.817],[18.442,42.543]]],[[[16.67,43.125],[16.372,43.196],[16.583,43.189],[16.521,43.229],[16.563,43.229],[17.193,43.127],[16.67,43.125]]],[[[16.422,43.318],[16.447,43.395],[16.892,43.312],[16.628,43.264],[16.422,43.318]]],[[[14.897,44.491],[14.734,44.703],[15.254,44.34],[15.165,44.367],[15.22,44.313],[15.129,44.312],[15.117,44.387],[14.897,44.491]]],[[[14.508,44.653],[14.428,44.657],[14.294,44.909],[14.411,44.956],[14.278,45.113],[14.314,45.172],[14.473,44.971],[14.452,44.799],[14.508,44.653]]],[[[14.706,44.947],[14.621,45.046],[14.425,45.087],[14.53,45.135],[14.549,45.249],[14.815,44.977],[14.706,44.947]]]]}},{"type":"Feature","properties":{"iso":"SVN","nom":"Slovénie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[13.643,45.459],[13.569,45.539],[13.895,45.632],[13.581,45.809],[13.606,45.985],[13.462,46.006],[13.637,46.18],[13.41,46.208],[13.365,46.29],[13.677,46.452],[13.701,46.52],[14.54,46.379],[14.789,46.507],[14.85,46.601],[15.062,46.65],[15.463,46.615],[15.636,46.718],[15.851,46.724],[16.017,46.671],[15.972,46.821],[16.094,46.863],[16.325,46.839],[16.314,46.743],[16.411,46.668],[16.376,46.629],[16.501,46.545],[16.515,46.502],[16.264,46.516],[16.276,46.373],[16.058,46.378],[16.019,46.299],[15.64,46.208],[15.59,46.114],[15.698,46.036],[15.676,45.842],[15.255,45.723],[15.374,45.64],[15.269,45.602],[15.361,45.482],[15.325,45.453],[15.139,45.43],[14.923,45.515],[14.797,45.465],[14.581,45.668],[14.373,45.478],[13.972,45.514],[13.889,45.424],[13.643,45.459]]]}},{"type":"Feature","properties":{"iso":"BGR","nom":"Bulgarie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[26.295,41.71],[26.212,41.75],[26.054,41.702],[26.176,41.432],[26.121,41.358],[25.882,41.304],[25.551,41.316],[25.239,41.241],[24.886,41.401],[24.774,41.348],[24.58,41.441],[24.51,41.562],[24.077,41.536],[24.035,41.451],[23.612,41.371],[23.288,41.398],[23.157,41.316],[22.917,41.336],[22.936,41.626],[23.009,41.74],[22.881,41.873],[22.838,42.019],[22.531,42.129],[22.345,42.313],[22.533,42.458],[22.425,42.573],[22.483,42.734],[22.427,42.814],[22.727,42.887],[22.981,43.199],[22.519,43.474],[22.349,43.808],[22.4,43.993],[22.593,44.064],[22.606,44.175],[22.692,44.228],[23.031,44.093],[23.023,44.032],[22.886,43.995],[22.889,43.84],[23.485,43.881],[24.159,43.753],[24.466,43.802],[24.964,43.75],[25.403,43.65],[25.781,43.732],[26.151,44.012],[27.027,44.177],[27.251,44.122],[27.384,44.015],[27.633,44.03],[27.722,43.949],[27.912,43.993],[27.981,43.849],[28.221,43.762],[28.578,43.741],[28.56,43.454],[28.473,43.367],[28.322,43.428],[28.119,43.392],[28.018,43.233],[27.904,43.202],[27.946,43.169],[27.884,43.031],[27.892,42.711],[27.733,42.715],[27.74,42.661],[27.628,42.629],[27.65,42.558],[27.541,42.565],[27.453,42.48],[27.466,42.428],[27.719,42.415],[27.714,42.349],[27.788,42.311],[27.756,42.258],[27.987,42.072],[28.017,41.973],[27.812,41.995],[27.815,41.947],[27.687,41.969],[27.546,41.901],[27.273,42.092],[27.047,42.083],[26.939,41.996],[26.606,41.967],[26.526,41.824],[26.376,41.817],[26.295,41.71]]]}},{"type":"Feature","properties":{"iso":"SMR","nom":"San Marino","focus":false},"geometry":{"type":"Polygon","coordinates":[[[12.46,43.895],[12.396,43.948],[12.482,43.983],[12.46,43.895]]]}},{"type":"Feature","properties":{"iso":"MCO","nom":"Monaco","focus":false},"geometry":{"type":"Polygon","coordinates":[[[7.407,43.764],[7.404,43.718],[7.366,43.723],[7.407,43.764]]]}},{"type":"Feature","properties":{"iso":"DZA","nom":"Algérie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[-1.689,34.0],[-1.81,34.372],[-1.703,34.48],[-1.871,34.597],[-1.77,34.741],[-2.194,35.004],[-2.223,35.089],[-1.761,35.13],[-1.295,35.365],[-1.183,35.576],[-1.033,35.683],[-0.802,35.774],[-0.626,35.723],[-0.479,35.89],[-0.349,35.907],[-0.145,35.79],[-0.038,35.813],[0.127,36.051],[0.342,36.206],[1.045,36.487],[2.33,36.637],[2.601,36.596],[2.933,36.809],[3.14,36.742],[3.227,36.812],[3.48,36.777],[3.874,36.917],[4.787,36.895],[5.304,36.643],[5.465,36.665],[5.734,36.832],[6.197,36.902],[6.267,37.018],[6.416,37.093],[6.544,37.059],[6.599,36.973],[6.909,36.893],[7.157,36.915],[7.254,36.995],[7.182,37.077],[7.223,37.09],[7.713,36.963],[7.799,36.994],[7.773,36.89],[7.866,36.854],[8.233,36.958],[8.463,36.902],[8.603,36.94],[8.643,36.849],[8.413,36.784],[8.462,36.733],[8.43,36.663],[8.17,36.526],[8.358,36.43],[8.241,35.828],[8.337,35.538],[8.294,35.325],[8.431,35.242],[8.3,35.068],[8.236,34.648],[7.832,34.414],[7.765,34.245],[7.604,34.175],[7.501,34.0],[-1.689,34.0]]]}},{"type":"Feature","properties":{"iso":"AND","nom":"Andorre","focus":false},"geometry":{"type":"Polygon","coordinates":[[[1.765,42.563],[1.448,42.435],[1.406,42.529],[1.467,42.641],[1.543,42.649],[1.722,42.61],[1.765,42.563]]]}},{"type":"Feature","properties":{"iso":"MNE","nom":"Monténégro","focus":false},"geometry":{"type":"Polygon","coordinates":[[[18.498,42.431],[18.437,42.559],[18.55,42.668],[18.454,42.793],[18.434,42.954],[18.483,43.015],[18.639,43.02],[18.664,43.233],[18.821,43.341],[18.923,43.347],[18.992,43.267],[19.07,43.309],[18.906,43.491],[18.977,43.546],[19.195,43.533],[19.192,43.455],[19.372,43.384],[19.598,43.176],[19.805,43.09],[19.929,43.114],[20.354,42.891],[20.345,42.827],[20.183,42.743],[20.027,42.743],[20.104,42.653],[20.077,42.56],[19.982,42.511],[19.801,42.468],[19.722,42.646],[19.622,42.605],[19.275,42.191],[19.372,42.104],[19.365,41.852],[19.17,41.938],[19.084,42.11],[18.886,42.284],[18.779,42.271],[18.678,42.386],[18.545,42.424],[18.7,42.393],[18.687,42.483],[18.498,42.431]]]}},{"type":"Feature","properties":{"iso":"BIH","nom":"Bosnie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[17.812,42.91],[17.556,42.935],[17.663,42.966],[17.628,43.047],[17.29,43.303],[17.271,43.463],[17.031,43.548],[16.327,44.082],[16.216,44.208],[16.116,44.521],[16.006,44.541],[16.028,44.625],[15.728,44.769],[15.792,45.19],[16.02,45.214],[16.316,45.001],[16.529,45.222],[16.812,45.181],[16.924,45.285],[17.187,45.149],[17.269,45.19],[17.482,45.114],[17.685,45.164],[17.836,45.064],[18.003,45.149],[18.154,45.098],[18.238,45.157],[18.517,45.056],[18.678,45.087],[18.792,45.002],[18.783,44.914],[18.89,44.861],[19.187,44.928],[19.369,44.887],[19.318,44.715],[19.13,44.518],[19.107,44.383],[19.157,44.294],[19.307,44.274],[19.611,44.055],[19.529,43.977],[19.273,44.012],[19.229,43.958],[19.462,43.762],[19.49,43.564],[19.411,43.541],[19.347,43.609],[19.217,43.533],[18.911,43.507],[19.07,43.309],[18.992,43.267],[18.923,43.347],[18.821,43.341],[18.664,43.233],[18.639,43.02],[18.453,42.993],[18.445,42.817],[18.55,42.668],[18.492,42.565],[17.995,42.74],[17.812,42.91]]]}},{"type":"Feature","properties":{"iso":"PRT","nom":"Portugal","focus":true},"geometry":{"type":"MultiPolygon","coordinates":[[[[-7.056,38.855],[-7.281,38.72],[-7.359,38.446],[-7.104,38.174],[-6.948,38.197],[-7.024,38.023],[-7.273,37.977],[-7.53,37.567],[-7.408,37.165],[-7.512,37.172],[-7.82,36.999],[-8.58,37.124],[-8.998,37.021],[-8.816,37.418],[-8.827,37.601],[-8.752,37.731],[-8.809,37.723],[-8.805,37.902],[-8.895,37.953],[-8.774,38.187],[-8.795,38.359],[-8.943,38.481],[-8.799,38.426],[-8.607,38.419],[-8.736,38.452],[-8.773,38.565],[-8.788,38.481],[-8.906,38.512],[-9.231,38.419],[-9.184,38.552],[-9.253,38.665],[-9.108,38.659],[-8.943,38.776],[-9.012,38.913],[-8.943,39.015],[-8.827,39.049],[-8.765,39.098],[-8.936,39.041],[-9.1,38.83],[-9.113,38.714],[-9.472,38.702],[-9.497,38.81],[-9.351,39.197],[-9.409,39.375],[-9.218,39.406],[-9.09,39.579],[-8.868,40.125],[-8.785,40.119],[-8.908,40.201],[-8.753,40.641],[-8.573,40.756],[-8.668,40.747],[-8.684,40.783],[-8.646,40.824],[-8.655,40.845],[-8.751,40.653],[-8.648,41.153],[-8.737,41.25],[-8.831,41.672],[-8.696,41.722],[-8.88,41.737],[-8.868,41.859],[-8.627,42.051],[-8.222,42.154],[-8.204,42.07],[-8.095,42.041],[-8.232,41.886],[-8.093,41.807],[-7.906,41.914],[-7.897,41.858],[-7.722,41.899],[-7.443,41.806],[-7.219,41.879],[-7.16,41.986],[-6.609,41.962],[-6.524,41.867],[-6.577,41.74],[-6.542,41.659],[-6.366,41.664],[-6.206,41.57],[-6.321,41.411],[-6.647,41.268],[-6.804,41.064],[-6.942,41.016],[-6.816,40.857],[-6.857,40.442],[-6.794,40.356],[-7.043,40.181],[-6.88,40.009],[-7.021,39.694],[-7.557,39.68],[-7.314,39.457],[-7.327,39.341],[-7.244,39.196],[-7.157,39.105],[-6.986,39.067],[-7.056,38.855]]]]}},{"type":"Feature","properties":{"iso":"MDA","nom":"Moldavie","focus":false},"geometry":{"type":"Polygon","coordinates":[[[26.619,48.267],[26.68,48.33],[26.774,48.287],[26.832,48.391],[27.209,48.361],[27.605,48.484],[28.076,48.315],[28.093,48.237],[28.358,48.239],[28.317,48.135],[28.412,48.171],[28.48,48.065],[28.574,48.155],[28.799,48.112],[28.95,47.935],[29.124,47.976],[29.236,47.871],[29.178,47.79],[29.239,47.756],[29.117,47.533],[29.156,47.45],[29.41,47.28],[29.557,47.324],[29.545,47.136],[29.478,47.112],[29.602,47.061],[29.559,46.946],[29.928,46.81],[29.95,46.579],[29.902,46.531],[30.132,46.423],[29.828,46.339],[29.714,46.471],[29.616,46.362],[29.458,46.485],[29.375,46.416],[29.307,46.472],[29.201,46.357],[29.184,46.538],[28.946,46.455],[28.934,46.259],[29.015,46.183],[28.939,46.089],[28.957,46.001],[28.74,45.953],[28.738,45.838],[28.474,45.658],[28.537,45.58],[28.502,45.509],[28.271,45.522],[28.199,45.462],[28.062,45.594],[28.168,45.632],[28.083,46.015],[28.145,46.183],[28.109,46.234],[28.246,46.428],[28.247,46.621],[28.083,46.972],[27.807,47.145],[27.733,47.276],[27.572,47.375],[27.576,47.46],[27.304,47.667],[27.043,48.127],[26.805,48.258],[26.619,48.267]]]}},{"type":"Feature","properties":{"iso":"GIB","nom":"Gibraltar","focus":false},"geometry":{"type":"Polygon","coordinates":[[[-5.358,36.141],[-5.339,36.124],[-5.342,36.111],[-5.358,36.141]]]}},{"type":"Feature","properties":{"iso":"VAT","nom":"Vatican","focus":false},"geometry":{"type":"Polygon","coordinates":[[[12.454,41.903],[12.453,41.904],[12.454,41.904],[12.454,41.903]]]}},{"type":"Feature","properties":{"iso":"MLT","nom":"Malte","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[14.563,35.87],[14.528,35.801],[14.424,35.824],[14.322,35.973],[14.377,35.994],[14.563,35.87]]]]}},{"type":"Feature","properties":{"iso":"JEY","nom":"Jersey","focus":false},"geometry":{"type":"Polygon","coordinates":[[[-2.068,49.251],[-2.025,49.171],[-2.234,49.185],[-2.241,49.26],[-2.068,49.251]]]}},{"type":"Feature","properties":{"iso":"GGY","nom":"Guernsey","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[-2.673,49.433],[-2.502,49.507],[-2.542,49.431],[-2.673,49.433]]]]}},{"type":"Feature","properties":{"iso":"IMN","nom":"Isle of Man","focus":false},"geometry":{"type":"Polygon","coordinates":[[[-4.621,54.07],[-4.79,54.064],[-4.71,54.221],[-4.531,54.366],[-4.351,54.414],[-4.376,54.348],[-4.312,54.287],[-4.621,54.07]]]}},{"type":"Feature","properties":{"iso":"ALA","nom":"Aland","focus":false},"geometry":{"type":"MultiPolygon","coordinates":[[[[20.302,59.999],[20.442,60.0],[20.447,59.995],[20.307,59.954],[20.302,59.999]]]]}}]};


function renderCarteOnglet() {
  const body = document.getElementById("stats-body");
  if (!body) return;

  const PAYS_CONFIG = DATA.carte_pays || {};
  const isDark = document.body.classList.contains("dark");
  const SC  = { "En cours":"#10d994","À risque":"#f59e0b","En retard":"#f43f5e","Terminé":"#a78bfa","Stand by":"#8a8780" };
const SBG = isDark
  ? { "En cours":"rgba(16,217,148,.12)","À risque":"rgba(245,158,11,.12)","En retard":"rgba(244,63,94,.12)","Terminé":"rgba(167,139,250,.12)","Stand by":"rgba(138,135,128,.12)" }
  : { "En cours":"#EAF3DE","À risque":"#FAEEDA","En retard":"#FCEBEB","Terminé":"#EEEDFE","Stand by":"#F1EFE8" };

  // ── Construire les données par pays ────────────────────────────────────────
  const donneesParIso = {};
  Object.entries(PAYS_CONFIG).forEach(([pays, cfg]) => {
    const iso = cfg.iso;
    const entitesList = cfg.entites || [];
    const projets = DATA.projets.filter(p => {
      if (!entitesList.length) return false;
      const ents = (p.entite_concerne || "").split(/[;,]/).map(e => e.trim());
      return entitesList.some(e => ents.includes(e) || _projetMatchEntite(p, e));
    });
    donneesParIso[iso] = { pays, entites: entitesList, projets };
  });

  const maxProjets = Math.max(1, ...Object.values(donneesParIso).map(d => d.projets.length));

  // ── Interpolation couleur ─────────────────────────────────────────
  // #B5D4F4 (181,212,244) → #0C447C (12,68,124)
  function couleur(iso) {
    const d = donneesParIso[iso];
    if (!d || !d.projets.length) return isDark ? "#2b2926" : "#e8e5df";
    const t = d.projets.length / maxProjets;
    const r = Math.round(181 + t * (12  - 181));
    const g = Math.round(212 + t * (68  - 212));
    const b = Math.round(244 + t * (124 - 244));
    return `rgb(${r},${g},${b})`;
  }

  function legendColor(t) {
    const r = Math.round(181 + t * (12  - 181));
    const g = Math.round(212 + t * (68  - 212));
    const b = Math.round(244 + t * (124 - 244));
    return `rgb(${r},${g},${b})`;
  }

  // ── Projection Mercator manuelle ──────────────────────────────────────────
  // Fenêtre Europe élargie : focus sur les entités, contexte tout autour
  const LON_MIN = -11, LON_MAX = 31;
  const LAT_MIN = 34,  LAT_MAX = 60;

  function mercatorY(lat) {
    const rad = lat * Math.PI / 180;
    return Math.log(Math.tan(Math.PI / 4 + rad / 2));
  }

  const yMin = mercatorY(LAT_MIN);
  const yMax = mercatorY(LAT_MAX);

  function project(lon, lat, W, H, pad) {
    const px = pad + (lon - LON_MIN) / (LON_MAX - LON_MIN) * (W - 2 * pad);
    const my = mercatorY(lat);
    const py = H - pad - (my - yMin) / (yMax - yMin) * (H - 2 * pad);
    return [px, py];
  }

  // ── Convertir un anneau GeoJSON en points SVG ─────────────────────────────
  function ringToPoints(ring, W, H, pad) {
    return ring.map(([lon, lat]) => project(lon, lat, W, H, pad).join(",")).join(" ");
  }

  // ── Centroïde d'un polygone ───────────────────────────────────────────────
  function centroid(ring, W, H, pad) {
    const pts = ring.map(([lon, lat]) => project(lon, lat, W, H, pad));
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    return [cx, cy];
  }

  // ── Injection HTML ─────────────────────────────────────────────────────────
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 280px;gap:12px;align-items:start">
      <div style="background:var(--bg2);border:1px solid var(--border);
                  border-radius:var(--radius-lg);overflow:hidden">
        <div id="carte-map" style="width:100%;"></div>
      </div>
      <div id="carte-detail"
           style="background:var(--bg2);border:1px solid var(--border);
                  border-radius:var(--radius-lg);padding:14px;
                  min-height:180px;max-height:380px;overflow-y:auto">
        <p style="font-size:12px;color:var(--text3);margin:0">
          Cliquez sur un pays coloré pour voir les projets par entité, domaine et responsable
        </p>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap">
      <span style="font-size:11px;color:var(--text3)">Intensité = nombre de projets :</span>
      ${[0.15, 0.4, 0.7, 1].map(t =>
        `<span style="display:inline-flex;align-items:center;gap:4px">
          <span style="width:14px;height:8px;border-radius:2px;
                       background:${legendColor(t)};display:inline-block"></span>
        </span>`).join("")}
      <span style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">faible → élevé</span>
    </div>`;

  setTimeout(initMap, 0);

  // ── Rendu SVG pur ─────────────────────────────────────────────────────────
  function initMap() {
    const container = document.getElementById("carte-map");
    if (!container) return;

    const PAD = 16;
    const W   = container.getBoundingClientRect().width || 600;
    // Hauteur dérivée de la projection Mercator pour éviter toute déformation
    const lonSpan = LON_MAX - LON_MIN;
    const ySpan   = yMax - yMin;            // en unités Mercator
    const lonRad  = lonSpan * Math.PI / 180;
    const H = Math.round((W - 2*PAD) * (ySpan / lonRad) + 2*PAD);

    // SVG de base
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width",  "100%");
    svg.setAttribute("height", H);
    svg.style.display = "block";

    // Fond océan
    const bg = document.createElementNS(ns, "rect");
    bg.setAttribute("width",  W);
    bg.setAttribute("height", H);
    bg.setAttribute("fill", document.body.classList.contains("dark")? "#11161f" : "#dde9f4");
    svg.appendChild(bg);

    const isDark = document.body.classList.contains("dark");
    // Couleurs de fond / frontières selon le thème
    const LAND_CTX   = isDark ? "#2b2926" : "#e7e4dd";   // pays "contexte" (sans entité)
    const BORDER_CTX2= isDark ? "#3a3833" : "#c4c0b8";
    const BORDER_DATA= isDark ? "#0a1420" : "#42566b";

    // ── Passe 1 : remplissages + frontières ────────────────────────────────
    EUROPE_GEOJSON.features.forEach(feat => {
      const iso  = feat.properties.iso;
      const isFocus = !!feat.properties.focus;
      const hasDonnees = isFocus && !!donneesParIso[iso];
      const fill = hasDonnees ? couleur(iso) : LAND_CTX;
      const geom = feat.geometry;

      const rings = geom.type === "Polygon"
        ? [geom.coordinates]
        : geom.coordinates;   // MultiPolygon : tableau de polygones (chacun = [outer, ...holes])

      rings.forEach(polygon => {
        const outer = polygon[0];
        const path  = document.createElementNS(ns, "polygon");
        path.setAttribute("points", ringToPoints(outer, W, H, PAD));
        path.setAttribute("fill", fill);
        path.setAttribute("stroke", hasDonnees ? BORDER_DATA : BORDER_CTX2);
        path.setAttribute("stroke-width", hasDonnees ? "1.3" : "0.7");
        path.setAttribute("stroke-linejoin", "round");
        path.setAttribute("data-iso", iso);
        path.style.transition = "opacity .15s, stroke-width .15s";

        if (hasDonnees) {
          path.style.cursor = "pointer";
          path.addEventListener("mouseenter", () => {
            svg.querySelectorAll(`[data-iso="${iso}"]`).forEach(el=>{
              el.setAttribute("opacity","0.85"); el.setAttribute("stroke-width","2.4");
            });
            showDetail(iso);
          });
          path.addEventListener("mouseleave", () => {
            svg.querySelectorAll(`[data-iso="${iso}"]`).forEach(el=>{
              el.setAttribute("opacity","1"); el.setAttribute("stroke-width","1.3");
            });
          });
          path.addEventListener("click", () => showDetail(iso));
        }
        svg.appendChild(path);
      });
    });

    // ── Passe 2 : libellés (au-dessus de toutes les frontières) ─────────────
    EUROPE_GEOJSON.features.forEach(feat => {
      const iso = feat.properties.iso;
      const isFocus = !!feat.properties.focus;
      const geom = feat.geometry;

      // Anneau le plus grand pour positionner le label
      let biggest = geom.type === "Polygon" ? geom.coordinates[0]
                  : geom.coordinates.map(p=>p[0]).sort((a,b)=>b.length-a.length)[0];
      const [cx, cy] = centroid(biggest, W, H, PAD);
      if (isNaN(cx) || isNaN(cy)) return;

      const dCty = donneesParIso[iso];
      const hasDonnees = isFocus && !!dCty;

      if (!isFocus) {
        // Pays de contexte : petit label discret, pas de compteur
        const t = document.createElementNS(ns, "text");
        t.setAttribute("x", cx); t.setAttribute("y", cy);
        t.setAttribute("text-anchor","middle");
        t.setAttribute("font-size","8");
        t.setAttribute("fill", isDark ? "#6b6862" : "#a8a399");
        t.setAttribute("font-family","var(--font-mono)");
        t.style.pointerEvents="none";
        t.textContent = feat.properties.nom;
        svg.appendChild(t);
        return;
      }

      // Pays focus : nom + nb projets, couleur adaptée à l'intensité
      const intensite = (dCty && dCty.projets.length) ? dCty.projets.length / maxProjets : 0;
      const labelMain = intensite > 0.45 ? "#ffffff" : (isDark ? "#ebebeb" : "#16263a");
      const labelSub  = intensite > 0.45 ? "rgba(255,255,255,.85)" : (isDark ? "#b8b5b0" : "#3d5066");

      const g = document.createElementNS(ns, "g");
      g.style.pointerEvents = "none";

      const t1 = document.createElementNS(ns, "text");
      t1.setAttribute("x", cx); t1.setAttribute("y", cy - 4);
      t1.setAttribute("text-anchor","middle");
      t1.setAttribute("font-size","9.5"); t1.setAttribute("font-weight","700");
      t1.setAttribute("fill", labelMain);
      t1.textContent = feat.properties.nom;
      g.appendChild(t1);

      const nbProj = dCty ? dCty.projets.length : 0;
      const t2 = document.createElementNS(ns, "text");
      t2.setAttribute("x", cx); t2.setAttribute("y", cy + 8);
      t2.setAttribute("text-anchor","middle");
      t2.setAttribute("font-size","8.5");
      t2.setAttribute("fill", labelSub);
      t2.setAttribute("font-family","var(--font-mono)");
      t2.textContent = `${nbProj} proj.`;
      g.appendChild(t2);

      svg.appendChild(g);
    });

    container.innerHTML = "";
    container.appendChild(svg);
  }

  // ── Détail d'un pays ──────────────────────────────────────────────────────
  function showDetail(iso) {
    const d = donneesParIso[iso];
    if (!d) return;

    const entitesPresentes = [
      ...new Set(
        d.projets
          .flatMap(p => (p.entite_concerne || "").split(/[;,]/).map(e => e.trim()))
          .filter(e => e && d.entites.includes(e))
      )
    ];

    let html = `
      <div style="border-bottom:0.5px solid var(--border);padding-bottom:8px;margin-bottom:10px">
        <div style="font-size:13px;font-weight:600;color:var(--text)">${esc(d.pays)}</div>
        <div style="font-size:10px;color:var(--text3);margin-top:2px">
          ${entitesPresentes.join(" · ") || "—"}
        </div>
      </div>`;

    if (!d.projets.length) {
      html += `<p style="font-size:11px;color:var(--text3);margin:0">Aucun projet</p>`;
      document.getElementById("carte-detail").innerHTML = html;
      return;
    }

    // Grouper entité → domaine → responsable
    const parEntite = {};
    d.projets.forEach(p => {
      const ents = (p.entite_concerne || "").split(/[;,]/).map(e => e.trim())
      .filter(e=> e && donneesParIso[iso].entites.includes(e));
      (ents.length ? ents : [donneesParIso[iso].entites[0]||"-"]).forEach(e => {
        if (!parEntite[e]) parEntite[e] = {};
        const dom  = p.domaine || "Autre";
        if (!parEntite[e][dom]) parEntite[e][dom] = {};
        const resp = p.responsable_principal || "—";
        if (!parEntite[e][dom][resp]) parEntite[e][dom][resp] = [];
        parEntite[e][dom][resp].push(p);
      });
    });

    Object.entries(parEntite).forEach(([entite, doms]) => {
      if (Object.keys(parEntite).length > 1)
        html += `<div style="font-size:10px;font-weight:600;color:var(--cyan);margin-bottom:6px">${esc(entite)}</div>`;

      Object.entries(doms).forEach(([dom, resps]) => {
        html += `
          <div style="margin-bottom:8px">
            <div style="font-size:9px;font-weight:500;color:var(--text3);
                        text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px">
              ${esc(dom)}
            </div>`;
        Object.entries(resps).forEach(([resp, projs]) => {
          html += `<div style="font-size:10px;color:var(--text3);margin-bottom:3px">${esc(resp)}</div>`;
          projs.forEach(p => {
            html += `
              <div style="display:flex;align-items:center;gap:5px;padding:4px 7px;
                          border-radius:var(--radius);
                          background:${SBG[p.statut] || "var(--bg3)"};margin-bottom:2px">
                <span style="font-size:10px;color:var(--text);flex:1;
                             overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  ${esc(p.projet_nom || p.sujet || "")}
                </span>
                <span style="font-size:9px;padding:1px 5px;border-radius:8px;
                             color:${SC[p.statut]};background:${SBG[p.statut]};
                             border:0.5px solid ${SC[p.statut]}66;white-space:nowrap">
                  ${esc(p.statut)}
                </span>
              </div>`;
          });
        });
        html += `</div>`;
      });
    });

    document.getElementById("carte-detail").innerHTML = html;
  }
}




function renderSante(st,s,last,hasHist){
  const avMoy=last.avancement||0;
  const tauxDiff=last.tauxDiff||0;
  const nbBloc=last.nbBlocages||0;

  // Tendance avancement
  let tendAv="stable",tendCol="var(--text3)";
  if(s.length>=2){
    const delta=s[s.length-1].avancement-s[s.length-2].avancement;
    if(delta>2){tendAv=`+${delta.toFixed(1)}% vs Q-1`;tendCol="var(--green)";}
    else if(delta<-2){tendAv=`${delta.toFixed(1)}% vs Q-1`;tendCol="var(--red)";}
    else{tendAv=`stable vs Q-1`;tendCol="var(--text3)";}
  }

  return`
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px">

      ${jauge(tauxDiff,100,"var(--red)","Taux en difficulté",`${last.nbDiff||0} projets`)}
      ${jauge(nbBloc,Math.max(nbBloc,10),"var(--amber)","Blocages actifs","cette quinzaine")}
    </div>
    <div class="grid2">

      <div class="card">
        <div class="card-title">évolution taux en difficulté</div>
        ${hasHist
          ?svgChart(s,x=>x.tauxDiff,"var(--red)","difficulté","%")
          :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// disponible dès 2 quinzaines</div>`}
      </div>
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-title">blocages & décisions par quinzaine</div>
        ${hasHist
          ?`<div style="margin-bottom:8px">`+svgChart(s,x=>x.nbBlocages,"var(--amber)","blocages","",120)+`</div>
            <div style="font-size:9px;color:var(--amber);font-family:var(--font-mono);margin-bottom:4px">▲ Blocages</div>
            <div>`+svgChart(s,x=>x.nbDecisions,"var(--green)","décisions","",120)+`</div>
            <div style="font-size:9px;color:var(--green);font-family:var(--font-mono)">▲ Décisions</div>`
          :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// disponible dès 2 quinzaines</div>`}
      </div>
      <div class="card">
        <div class="card-title">nouveaux projets par quinzaine</div>
        ${st.serieNouveaux&&st.serieNouveaux.length>=2
          ?`<div style="margin-bottom:6px">`+
            svgChart(st.serieNouveaux,x=>x.nbNew,"var(--cyan)","nouveaux","",110)+
            `</div><div style="font-size:9px;color:var(--cyan);font-family:var(--font-mono);margin-bottom:10px">▲ Nouveaux projets par quinzaine</div>`+
            svgChart(st.serieNouveaux,x=>x.nbCumul,"var(--violet)","cumulés","",110)+
            `<div style="font-size:9px;color:var(--violet);font-family:var(--font-mono);margin-top:4px">▲ Projets cumulés (portefeuille total)</div>`
          :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// disponible dès 2 quinzaines</div>`}
      </div>
    <div class="card">
        <div class="card-title" style="display:flex;align-items:center;justify-content:space-between">
          <span>répartition statuts — quinzaine courante</span>
          <div style="display:flex;gap:4px">
            <span class="fchip active" id="rep-toggle-dom" onclick="toggleRep('dom')" style="font-size:9px;padding:2px 8px">Par domaine</span>
            <span class="fchip" id="rep-toggle-col" onclick="toggleRep('col')" style="font-size:9px;padding:2px 8px">Par collaborateur</span>
          </div>
        </div>
        <div id="rep-content">
          ${buildRepDomaine(last)}
        </div>
      </div>
    </div>`;

  window.toggleRep=function(mode){
    document.getElementById("rep-toggle-dom")?.classList.toggle("active", mode==="dom");
    document.getElementById("rep-toggle-col")?.classList.toggle("active", mode==="col");
    const el=document.getElementById("rep-content");
    if(el) el.innerHTML=mode==="dom"?buildRepDomaine(last):buildRepCollab(last);
  };
}

// ── Onglet Vélocité ─────────────────────────────────────────────────────

function renderVelocite(st,s,last,hasHist){
  const velItems=Object.entries(st.velociteDomaine)
    .filter(([,v])=>v!=null)
    .map(([d,v])=>{return{label:d,val:Math.max(v,0),rawVal:v,unit:"%/Q",color:domColor(d)};  });

  const respItems=Object.entries(last.parResp||{})
    .map(([r,d])=>{return{label:r,val:d.total,unit:" proj"};  });

  return`
    <div class="card" style="margin-bottom:12px">
      <div class="card-title">vélocité par domaine (Δ avancement moyen / quinzaine)</div>
      ${velItems.length
        ?barChart(velItems,"var(--cyan)")
        :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// disponible dès 2 quinzaines</div>`}
      ${velItems.length?`<div style="font-size:9px;color:var(--text3);font-family:var(--font-mono);margin-top:8px">
        Domaine le plus rapide : <span style="color:var(--green)">
        ${velItems.sort((a,b)=>b.val-a.val)[0]?.label||"—"}</span>
        · Domaine le plus lent : <span style="color:var(--amber)">
        ${velItems.sort((a,b)=>a.val-b.val)[0]?.label||"—"}</span>
      </div>`:"" }
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-title">charge par responsable</div>
        ${barChart(respItems,"var(--violet)")}
        ${st.concentrations.length
          ?`<div style="margin-top:10px;padding:8px;background:var(--amber-dim);border-radius:var(--radius);border:1px solid rgba(245,158,11,.2)">
              <div style="font-size:9px;color:var(--amber);font-family:var(--font-mono);font-weight:600;margin-bottom:4px">⚠ Concentration détectée</div>
              ${st.concentrations.map(c=>`<div style="font-size:10px;color:var(--text2)">${esc(c.resp)} porte ${c.pct}% des projets actifs</div>`).join("")}
            </div>`
          :`<div style="font-size:9px;color:var(--green);font-family:var(--font-mono);margin-top:8px">✓ Charge bien répartie</div>`}
      </div>
      <div class="card">
        <div class="card-title">évolution projets actifs</div>
        ${hasHist
          ?svgChart(s,x=>x.nbActifs,"var(--violet)","actifs","")
          :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">// disponible dès 2 quinzaines</div>`}
      </div>
    </div>`;
}

// ── Onglet Livraisons ───────────────────────────────────────────────────

function renderLivraisons(st,s,last,hasHist){
  const avecData=s.filter(x=>x.avecLivrable>0);
  const hasTaux=avecData.length>0;
  const dernierTaux=hasTaux?avecData[avecData.length-1].tauxLivre:null;

  return`
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px">
      ${jauge(dernierTaux!=null?dernierTaux:0,100,"var(--green)","Taux livré",dernierTaux!=null?`${last.livres||0} / ${last.avecLivrable||0}`:"données insuffisantes")}
      ${jauge(last.reportes||0,Math.max(last.avecLivrable||1,1),"var(--amber)","Reportés",`${last.reportes||0} livrable(s)`)}
      ${jauge(last.nonLivres||0,Math.max(last.avecLivrable||1,1),"var(--red)","Non livrés",`${last.nonLivres||0} livrable(s)`)}
    </div>
    <div class="card" style="margin-bottom:12px">
      <div class="card-title">évolution taux de livraison</div>
      ${hasTaux&&hasHist
        ?svgChart(avecData,x=>x.tauxLivre,"var(--green)","livraison","%")
        :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">
          // ${hasTaux?"disponible dès 2 quinzaines avec données":"livrable_statut non renseigné dans les fiches"}</div>`} }
    </div>
    <div class="card">
      <div class="card-title">répartition livrables — quinzaine courante</div>
      ${last.avecLivrable>0
        ?barChart([
            {label:"Livré",    val:last.livres||0,    unit:"",color:"var(--green)"},
            {label:"En cours", val:(last.avecLivrable-(last.livres||0)-(last.nonLivres||0)-(last.reportes||0)),unit:"",color:"var(--cyan)"},
            {label:"Non livré",val:last.nonLivres||0, unit:"",color:"var(--red)"},
            {label:"Reporté",  val:last.reportes||0,  unit:"",color:"var(--amber)"},
          ].filter(x=>x.val>0),"var(--green)")
        :`<div style="font-size:10px;color:var(--text3);font-family:var(--font-mono);padding:8px">
            // livrable_statut non renseigné — les données apparaîtront dès que les fiches sont remplies</div>`}
    </div>`;
}

// ── Onglet Signaux faibles ──────────────────────────────────────────────

function renderSignaux(st,last){
  const TYPE_SF={
    STAGNATION:{label:"Stagnation",     color:"var(--amber)",icon:"≈"},
    OSCILLATION:{label:"Instabilité",    color:"var(--violet)",icon:"~"},
    TRAINARD:   {label:"Cas persistant", color:"var(--red)",  icon:"!"},
  };

  const parType={};
  st.signauxFaibles.forEach(s=>{
    if(!parType[s.type])parType[s.type]=[];
    parType[s.type].push(s);
  });

  const hasSignaux=st.signauxFaibles.length>0;

  return`
    ${!hasSignaux?`
      <div class="card" style="text-align:center;padding:32px">
        <div style="font-size:24px;margin-bottom:8px">✓</div>
        <div style="font-size:13px;font-weight:600;color:var(--green);font-family:var(--font-mono)">Aucun signal faible détecté</div>
        <div style="font-size:10px;color:var(--text3);margin-top:6px;font-family:var(--font-mono)">// disponible dès 2+ quinzaines avec données</div>
      </div>`:""}
    ${Object.entries(parType).map(([type,items])=>{
      const cfg=TYPE_SF[type]||{};
      return`<div class="card" style="margin-bottom:10px">
        <div class="card-title" style="color:${cfg.color}">${cfg.icon} ${cfg.label} (${items.length})</div>
        <div class="proj-list">
          ${items.map(sig=>`<div class="proj-item" onclick="openModal('${esc(sig.pid)}')" style="flex-direction:column;align-items:flex-start;gap:3px">
            <div style="display:flex;align-items:center;gap:7px;width:100%">
              <span class="proj-dot" style="background:${cfg.color}"></span>
              <span class="proj-name" style="font-size:11px">${esc(sig.nom)}</span>
              ${badge(sig.statut)}
            </div>
            <div style="font-size:9px;color:var(--text3);font-family:var(--font-mono);padding-left:13px">${esc(sig.detail)}</div>
          </div>`).join("")}
        </div>
      </div>`;
    }).join("")}
    <div class="card">
      <div class="card-title">à propos des signaux faibles</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
        ${Object.entries(TYPE_SF).map(([,cfg])=>`
          <div style="background:var(--bg3);border-radius:var(--radius);padding:10px">
            <div style="font-size:11px;font-weight:600;color:${cfg.color};margin-bottom:4px">${cfg.icon} ${cfg.label}</div>
            <div style="font-size:9px;color:var(--text3);line-height:1.5">${
              cfg.label==="Stagnation"?"Δ avancement < 5% sur 2 quinzaines consécutives, projet non terminé":
              cfg.label==="Instabilité"?"Statut change ≥ 3 fois sur l'historique":
              "≥ 3 quinzaines consécutives À risque ou En retard"
            }</div>
          </div>`).join("")}
      </div>
    </div>`;
}



function renderEvolutions(){
  const delta=(DATA.delta || []).filter(d => {
  const statutChange = d.statut_avant && d.statut_apres && d.statut_avant !== d.statut_apres;
  const avancementChange = d.delta_avancement && Math.abs(d.delta_avancement) >= 5;
  const phaseChange = d.phase_avant && d.phase_apres && d.phase_avant !== d.phase_apres;
  return statutChange || avancementChange || phaseChange;
});

  const sub=DATA.q_prev?`delta :: ${DATA.q_prev} → ${DATA.quinzaine}`:`snapshot initial :: ${DATA.quinzaine}`;
  let html=`<div style="font-size:10px;color:var(--text3);margin-bottom:14px;font-family:var(--font-mono)"># ${sub}</div>`;
  html+=`<div class="card"><div class="card-title">changements détectés (${delta.length})</div>`;
  if(!delta.length){
    html+=`<div style="font-size:11px;color:var(--text3);padding:8px;font-family:var(--font-mono)">// ${DATA.q_prev?"aucun changement":"premier snapshot"}</div>`;
  } else {
    html+='<div>'+delta.map(d=>{
      const dv=d.delta_avancement||0;
      const sign=dv>0?"+":"";
      const dc=dv>0?"var(--green)":dv<0?"var(--red)":"var(--text3)";
      const vide=v=>!v||["nan","None","undefined",""].includes(String(v).trim());

      // Tag avancement
      const dvTag=dv!==0
        ?`<span style="font-size:9px;font-family:var(--font-mono);color:${dc}">${sign}${Math.round(dv)}%</span>`
        :"";

      // Tag statut
      const stTag=d.statut_avant&&d.statut_apres&&d.statut_avant!==d.statut_apres
        ?`<span style="font-size:9px;color:var(--text3);font-family:var(--font-mono)">${d.statut_avant} → ${d.statut_apres}</span>`
        :"";

      // Tags autres champs avec valeurs avant/après
         const LABELS={
          phase:               {label:"phase",    truncate:12},
          points_blocage:      {label:"blocage",  truncate:0},
          livrable_statut:     {label:"livrable", truncate:0},
          responsable_principal:{label:"resp.",   truncate:10},
        };
        const champs=Object.keys(LABELS).filter(c=>d[c+"_avant"]!==undefined||d[c+"_apres"]!==undefined);
        const autresTags=champs.map(c=>{
          const av=d[c+"_avant"], ap=d[c+"_apres"];
          const cfg=LABELS[c];
          const fmt=v=>cfg.truncate>0?String(v).trim().slice(0,cfg.truncate)+(String(v).trim().length>cfg.truncate?"…":""):String(v).trim();
        
          if(c==="points_blocage"){
            if(vide(av)&&!vide(ap)) return`<span style="font-size:9px;font-family:var(--font-mono);color:var(--red)">⚠ blocage</span>`;
            if(!vide(av)&&vide(ap)) return`<span style="font-size:9px;font-family:var(--font-mono);color:var(--green)">✓ blocage résolu</span>`;
            return"";
          }
          if(vide(av)&&!vide(ap))
            return`<span style="font-size:9px;font-family:var(--font-mono);color:var(--green)">+${cfg.label}: ${fmt(ap)}</span>`;
          if(!vide(av)&&vide(ap))
            return`<span style="font-size:9px;font-family:var(--font-mono);color:var(--red)">-${cfg.label}: ${fmt(av)}</span>`;
          if(!vide(av)&&!vide(ap)&&String(av).trim()!==String(ap).trim())
            return`<span style="font-size:9px;font-family:var(--font-mono);color:var(--amber)">${cfg.label}: ${fmt(av)} → ${fmt(ap)}</span>`;
          return"";
        }).filter(Boolean).join(" ");

      const dotCol=d.statut_avant!==d.statut_apres?(SC[d.statut_apres]||"var(--text3)"):dc||"var(--text3)";
      const meta=[stTag,dvTag,autresTags].filter(Boolean).join(" ");

      return`<div class="tl-item">
        <div class="tl-dot" style="background:${dotCol}"></div>
        <div class="tl-body">
          <div class="tl-title" onclick="openModal('${esc(d.projet_id||d.ref_sujet)}')">${esc(d.projet_nom||d.sujet||(()=>{const m=(DATA.meta||[]).find(x=>(x.projet_id||x.ref_sujet)===(d.projet_id||d.ref_sujet));return m?(m.projet_nom||m.sujet||d.projet_id):d.projet_id;})())}</div>
          <div class="tl-meta" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
            ${meta}
            ${badge(d.statut_apres||"Stand by")}
          </div>
        </div>
      </div>`;
    }).join('')+'</div>';
  }
  html+='</div>';
  const alertes=DATA.projets.filter(p=>p.points_blocage||p.statut==="En retard");
  if(alertes.length)html+=`<div class="card"><div class="card-title">points d'attention (${alertes.length})</div><div class="proj-list">${alertes.map(projItem).join("")}</div></div>`;
  document.getElementById("page-evolutions").innerHTML=html;
}
function renderCalendrier(){
  const el=document.getElementById("page-calendrier");
  if(!el)return;
  const AGENDA=DATA.agenda||[];
  const TYPES_CAL={
    VIE_ENTREPRISE:  {label:"Vie d'entreprise",   bg:"rgba(37,99,235,.12)",  border:"#2563eb",text:"#2563eb"},
    COMITES:{label:"Comités", bg:"rgba(5,150,105,.12)",  border:"#059669",text:"#059669"},
    VIE_EQUIPE:{label:"Vie d'équipe", bg:"rgba(217,119,6,.12)",  border:"#d97706",text:"#d97706"},
    EVENT:    {label:"Event",     bg:"rgba(124,58,237,.12)", border:"#7c3aed",text:"#7c3aed"},
    PROJET:{label:"Projet", bg:"rgba(244,63,94,.12)",  border:"#f43f5e",text:"#f43f5e"},
    AUTRE:    {label:"Autre",     bg:"rgba(107,104,96,.12)", border:"#6b6860",text:"#6b6860"},
  };
  const MFR_LONG=["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"];
  const MFR_SHORT=["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];
  const now=new Date();
  let curY=now.getFullYear(),curM=now.getMonth();
  let activeTypes=new Set(Object.keys(TYPES_CAL));
  let calView="day";
 
  function evtsForDate(y,m,d){
    const key=`${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    return AGENDA.filter(e=>e.date===key&&activeTypes.has(e.type));
  }
 
  function openEvt(idx){
    const e=AGENDA[idx];if(!e)return;
    const t=TYPES_CAL[e.type]||TYPES_CAL.AUTRE;
    const dt=new Date(e.date);
    const dateStr=dt.toLocaleDateString("fr-FR",{weekday:"long",day:"numeric",month:"long",year:"numeric"});
    const projLie=e.projet_ref?(DATA.projets.find(p=>(p.projet_id||p.ref_sujet)===e.projet_ref)||null):null;
    document.getElementById("modal-body").innerHTML=`
      <button class="modal-close" onclick="closeModal()">x</button>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:10px;height:10px;border-radius:50%;background:${t.border};flex-shrink:0"></div>
        <span class="badge" style="background:${t.bg};color:${t.text};border:1px solid ${t.border};font-family:var(--font-mono);font-size:9px">${t.label}</span>
      </div>
      <div class="modal-title">${esc(e.titre)}</div>
      <div class="modal-id" style="color:var(--text3)">${dateStr}</div>
      ${e.description&&e.description!=="nan"?`<div class="modal-sec"><div class="modal-stitle">description</div><div class="modal-text">${esc(e.description)}</div></div>`:""}
      ${projLie?`<div class="modal-sec"><div class="modal-stitle">projet lié</div>
        <div class="proj-item" onclick="closeModal();openModal('${esc(projLie.projet_id||projLie.ref_sujet)}')" style="cursor:pointer">
          <span class="proj-dot" style="background:${SC[projLie.statut]||'#475569'}"></span>
          <span class="proj-name">${esc(projLie.projet_nom||projLie.sujet||"")}</span>
          ${badge(projLie.statut)}
          <span class="proj-pct">${projLie.avancement_pct||0}%</span>
        </div></div>`:
        e.projet_ref&&e.projet_ref!=="nan"?`<div class="modal-sec"><div class="modal-stitle">projet lié</div>
          <div class="modal-text" style="color:var(--text3);font-family:var(--font-mono)">${esc(e.projet_ref)}</div></div>`:""}
    `;
    document.getElementById("modal-overlay").classList.add("open");
  }
 
  function buildDay(){
    const todayStr=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
    const first=new Date(curY,curM,1);
    const startDow=(first.getDay()+6)%7;
    const daysInMonth=new Date(curY,curM+1,0).getDate();
    const daysInPrev=new Date(curY,curM,0).getDate();
    const upcoming=AGENDA.filter(e=>e.date>=todayStr&&activeTypes.has(e.type))
      .sort((a,b)=>a.date.localeCompare(b.date)).slice(0,6);
    const titre=`<span style="cursor:pointer;border-bottom:1px dashed var(--border2)" onclick="calSwitchView('month')">${MFR_LONG[curM]}</span> <span style="cursor:pointer;border-bottom:1px dashed var(--border2)" onclick="calSwitchView('year')">${curY}</span>`;
    let html=`
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        <button onclick="calNav(-1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8249;</button>
        <span style="flex:1;text-align:center;font-size:14px;font-weight:600;font-family:var(--font-mono);color:var(--text)">${titre}</span>
        <button onclick="calNav(1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8250;</button>
      </div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px" id="cal-type-filters">
        ${Object.entries(TYPES_CAL).map(([k,v])=>`
          <span class="fchip${activeTypes.has(k)?" active":""}"
            style="${activeTypes.has(k)?'color:'+v.text+';border-color:'+v.border+';background:'+v.bg:''}"
            onclick="calToggleType('${k}')" data-t="${k}">
            <span style="width:6px;height:6px;border-radius:50%;background:${v.border};display:inline-block;margin-right:4px"></span>${v.label}
          </span>`).join("")}
      </div>
      <div style="display:grid;grid-template-columns:1fr 260px;gap:12px">
        <div class="card" style="padding:10px">
          <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--border);border-radius:6px;overflow:hidden">
            ${["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"].map(d=>`
              <div style="background:var(--bg3);padding:5px;text-align:center;font-size:9px;font-weight:600;color:var(--text3);font-family:var(--font-mono)">${d}</div>`).join("")}`;
    for(let i=0;i<startDow;i++){
      html+=`<div style="background:var(--bg2);min-height:76px;padding:5px;opacity:.25">
        <div style="font-size:10px;color:var(--text3);font-family:var(--font-mono)">${daysInPrev-startDow+1+i}</div></div>`;
    }
    for(let d=1;d<=daysInMonth;d++){
      const isToday=d===now.getDate()&&curM===now.getMonth()&&curY===now.getFullYear();
      const evts=evtsForDate(curY,curM,d);
      const show=evts.slice(0,3);const more=evts.length-3;
      html+=`<div style="background:${isToday?'rgba(37,99,235,.05)':'var(--bg2)'};min-height:76px;padding:5px;border:${isToday?'1px solid rgba(37,99,235,.25)':'1px solid transparent'};transition:background .12s;cursor:${evts.length?'pointer':'default'}" ${evts.length?`onclick="calOpenDay(${curY},${curM},${d})"`:''}>`;
      html+=`<div style="font-size:10px;font-weight:600;margin-bottom:3px;font-family:var(--font-mono);color:${isToday?'var(--cyan)':'var(--text3)'}">
        ${isToday?`<span style="background:var(--cyan);color:var(--bg);border-radius:50%;width:17px;height:17px;display:inline-flex;align-items:center;justify-content:center;font-size:9px">${d}</span>`:d}</div>`;
      html+=show.map(e=>{const t=TYPES_CAL[e.type]||TYPES_CAL.AUTRE;const idx=AGENDA.indexOf(e);
        return`<div style="font-size:9px;padding:2px 5px;border-radius:3px;margin-bottom:2px;background:${t.bg};border-left:2px solid ${t.border};color:${t.text};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer" onclick="event.stopPropagation();openEvt(${idx})" title="${esc(e.titre)}">${esc(e.titre)}</div>`;
      }).join("");
      if(more>0)html+=`<div style="font-size:8px;color:var(--text3);font-family:var(--font-mono);padding:1px 4px">+${more} autre${more>1?'s':''}</div>`;
      html+=`</div>`;
    }
    const total=startDow+daysInMonth;const rem=(7-total%7)%7;
    for(let i=1;i<=rem;i++){
      html+=`<div style="background:var(--bg2);min-height:76px;padding:5px;opacity:.25">
        <div style="font-size:10px;color:var(--text3);font-family:var(--font-mono)">${i}</div></div>`;
    }
    html+=`</div></div>
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="card">
            <div class="card-title">prochains événements</div>
            ${upcoming.length?upcoming.map(e=>{
              const dt=new Date(e.date);const t=TYPES_CAL[e.type]||TYPES_CAL.AUTRE;
              const idx=AGENDA.indexOf(e);
              const diffJ=Math.ceil((dt-now)/(1000*60*60*24));
              return`<div class="proj-item" style="cursor:pointer;flex-direction:column;align-items:flex-start;gap:4px" onclick="openEvt(${idx})">
                <div style="display:flex;align-items:center;gap:7px;width:100%">
                  <div style="min-width:30px;text-align:center;background:var(--bg3);border-radius:5px;padding:3px 0;flex-shrink:0">
                    <div style="font-size:12px;font-weight:600;color:var(--text);font-family:var(--font-mono);line-height:1">${dt.getDate()}</div>
                    <div style="font-size:8px;color:var(--text3);text-transform:uppercase">${MFR_SHORT[dt.getMonth()]}</div>
                  </div>
                  <span class="proj-name" style="font-size:11px">${esc(e.titre)}</span>
                  <span class="badge" style="background:${t.bg};color:${t.text};border:1px solid ${t.border};margin-left:auto;font-size:8px">${t.label}</span>
                </div>
                <div style="font-size:9px;color:var(--text3);font-family:var(--font-mono);padding-left:37px">
                  ${diffJ===0?"aujourd'hui":diffJ===1?"demain":"dans "+diffJ+" j"}
                  ${e.projet_ref&&e.projet_ref!=="nan"?" · "+e.projet_ref:""}
                </div>
              </div>`;
            }).join(""):`<div style="font-size:11px;color:var(--text3);padding:8px 0;font-family:var(--font-mono)">// aucun événement à venir</div>`}
          </div>
          <div class="card">
            <div class="card-title">légende</div>
            ${Object.entries(TYPES_CAL).map(([,v])=>
              `<div style="display:flex;align-items:center;gap:7px;margin-bottom:7px;font-size:11px;color:var(--text2)">
                <span style="width:8px;height:8px;border-radius:50%;background:${v.border};flex-shrink:0"></span>
                ${v.label}
              </div>`).join("")}
          </div>
        </div>
      </div>`;
      
    html+=`<div class="card" style="margin-top:14px">
  <div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
    <span style="font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-family:var(--font-mono)">▸ jalons projets — 12 mois glissants</span>
    <select id="jalons-f-trim" onchange="buildJalonsTable()" style="font-size:10px;padding:3px 7px;border:1px solid var(--border2);border-radius:var(--radius);background:var(--bg3);color:var(--text);font-family:var(--font-mono)">
      <option value="">Tous trimestres</option>
      <option value="T1">T1</option>
      <option value="T2">T2</option>
      <option value="T3">T3</option>
      <option value="T4">T4</option>
    </select>
  </div>
  <div id="jalons-table-body"></div>
</div>`;

el.innerHTML=html;
setTimeout(buildJalonsTable, 0);

  }
 
  function buildMonth(){
    const titre=`<span style="cursor:pointer;border-bottom:1px dashed var(--border2)" onclick="calSwitchView('year')">${curY}</span>`;
    let html=`
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        <button onclick="calNav(-1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8249;</button>
        <span style="flex:1;text-align:center;font-size:14px;font-weight:600;font-family:var(--font-mono);color:var(--text)">${titre}</span>
        <button onclick="calNav(1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8250;</button>
      </div>
      <div class="card"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">`;
    for(let m=0;m<12;m++){
      const isCurrentM=m===curM&&curY===now.getFullYear();
      const isTodayM=m===now.getMonth()&&curY===now.getFullYear();
      const nbEvts=AGENDA.filter(e=>{const d=new Date(e.date);return d.getMonth()===m&&d.getFullYear()===curY&&activeTypes.has(e.type);}).length;
      html+=`<div onclick="calSelectMonth(${m})" style="padding:12px 8px;text-align:center;border-radius:var(--radius);cursor:pointer;background:${isCurrentM?'var(--cyan-dim)':'var(--bg3)'};border:1px solid ${isCurrentM?'var(--cyan)':isTodayM?'var(--border2)':'transparent'};transition:all .12s">
        <div style="font-size:12px;font-weight:${isCurrentM?'600':'400'};color:${isCurrentM?'var(--cyan)':'var(--text)'};font-family:var(--font-mono)">${MFR_SHORT[m]}</div>
        <div style="font-size:8px;color:var(--text3);margin-top:4px;font-family:var(--font-mono)">${nbEvts>0?nbEvts+" evt":"—"}</div>
      </div>`;
    }
    html+=`</div></div>`;
    el.innerHTML=html;
  }
 
  function buildYear(){
    const decBase=Math.floor(curY/10)*10;
    let html=`
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
        <button onclick="calNavDec(-1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8249;</button>
        <span style="flex:1;text-align:center;font-size:13px;font-weight:600;font-family:var(--font-mono);color:var(--text3)">${decBase} — ${decBase+11}</span>
        <button onclick="calNavDec(1)" style="font-size:14px;padding:4px 14px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--radius);color:var(--text);cursor:pointer;font-family:var(--font-mono)">&#8250;</button>
      </div>
      <div class="card"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">`;
    for(let i=0;i<12;i++){
      const yr=decBase+i;
      const isCurY=yr===curY;
      const isTodayY=yr===now.getFullYear();
      const nbEvts=AGENDA.filter(e=>new Date(e.date).getFullYear()===yr&&activeTypes.has(e.type)).length;
      html+=`<div onclick="calSelectYear(${yr})" style="padding:14px 8px;text-align:center;border-radius:var(--radius);cursor:pointer;background:${isCurY?'var(--cyan-dim)':'var(--bg3)'};border:1px solid ${isCurY?'var(--cyan)':isTodayY?'var(--border2)':'transparent'};transition:all .12s">
        <div style="font-size:13px;font-weight:${isCurY?'600':'400'};color:${isCurY?'var(--cyan)':isTodayY?'var(--text)':'var(--text2)'};font-family:var(--font-mono)">${yr}</div>
        <div style="font-size:8px;color:var(--text3);margin-top:4px;font-family:var(--font-mono)">${nbEvts>0?nbEvts+" evt":"—"}</div>
      </div>`;
    }
    html+=`</div></div>`;
    el.innerHTML=html;
  }
 
  function calSwitchView(v){calView=v;buildCal();}
  window.calSwitchView=calSwitchView;
  window.calSelectMonth=function(m){curM=m;calView="day";buildCal();};
  window.calSelectYear=function(y){curY=y;calView="month";buildCal();};
 
  function buildCal(){
    if(calView==="month")buildMonth();
    else if(calView==="year")buildYear();
    else buildDay();
  }

  function buildJalonsTable(){

  const AGENDA=DATA.agenda||[];
  const now=new Date();
  const cutoff=new Date(now.getFullYear(),now.getMonth()+12,now.getDate());
  const MFR=["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];
  const TRIM_C={
    T1:{bg:"rgba(0,149,255,.12)",color:"#0095ff"},
    T2:{bg:"rgba(16,217,148,.12)",color:"#10d994"},
    T3:{bg:"rgba(245,158,11,.12)",color:"#f59e0b"},
    T4:{bg:"rgba(139,92,246,.12)",color:"#8b5cf6"},
  };

  function parseD(s){
    if(!s||s==="nan")return null;
    const p=s.split("-");
    if(p.length===3)return new Date(+p[0],+p[1]-1,+p[2]);
    return null;
  }
  function trimOf(d){return"T"+(Math.floor(d.getMonth()/3)+1)+" "+d.getFullYear();}
  function formatD(d){return d.getDate()+" "+MFR[d.getMonth()]+" "+d.getFullYear();}
  function daysUntil(d){return Math.ceil((d-now)/(1000*60*60*24));}

  // Filtrer PROJET dans les 12 prochains mois
  const jalons=AGENDA
    .filter(e=>e.type==="PROJET")
    .map(e=>{const d=parseD(e.date);return{...e,d};  })
    .filter(e=>e.d)
    .sort((a,b)=>a.d-b.d);

  const el=document.getElementById("jalons-table-body");
  if(!el)return;

  if(!jalons.length){
    el.innerHTML=`<div style="padding:14px;font-size:11px;color:var(--text3);font-family:var(--font-mono)">// aucun jalon sur les 12 prochains mois</div>`;
    return;
  }

  // Grouper par trimestre
  const byTrim={};
  jalons.forEach(j=>{
    const t=trimOf(j.d);
    if(!byTrim[t])byTrim[t]=[];
    byTrim[t].push(j);
  });

  // Filtre projet
  const fTrim=document.getElementById("jalons-f-trim")?.value||"";
  const projets=[...new Set(jalons.map(j=>j.projet_ref||"").filter(Boolean))].sort();

  let html=`<table class="jalon-table" style="width:100%;table-layout:fixed">
  <thead><tr>
    <th style="width:18%">Date</th>
    <th style="width:34%">Projet</th>
    <th style="width:34%">Description</th>
    <th style="width:14%">Délai</th>
  </tr></thead><tbody>`;

Object.entries(byTrim).forEach(([trim,items])=>{
  const tkey=trim.split(" ")[0];
  const tc=TRIM_C[tkey]||TRIM_C.T1;
  if(fTrim&&tkey!==fTrim)return;
  const filtered=items;
  if(!filtered.length)return;
  html+=`<tr><td colspan="4" style="padding:6px 12px;background:var(--bg3);border-top:1px solid var(--border);border-bottom:1px solid var(--border)">
    <span class="trim-badge-cal" style="background:${tc.bg};color:${tc.color}">${trim}</span>
    <span style="font-size:9px;color:var(--text3);margin-left:8px;font-family:var(--font-mono)">${filtered.length} jalon${filtered.length>1?"s":""}</span>
  </td></tr>
  ${filtered.map(j=>{
    const days=daysUntil(j.d);
    const isPast=days<0;
    const isSoon=days>=0&&days<=14;
    const isClose=days>14&&days<=30;
    const dc=isPast?"var(--text3)":isSoon?"var(--red)":isClose?"var(--amber)":"var(--cyan)";
    const delai=isPast?"il y a "+Math.abs(days)+" j":days===0?"Aujourd'hui":days===1?"Demain":"J+"+days;
    const nomProjet=(DATA.meta||[]).find(m=>(m.projet_id||m.ref_sujet)===j.projet_ref);
    const rowOpacity=isPast?"opacity:.5;":"";
    const nomStr=nomProjet?(nomProjet.projet_nom||nomProjet.sujet||j.projet_ref):j.projet_ref||"—";
    return`<tr style="${rowOpacity}">
      <td style="white-space:nowrap;font-size:10px;color:${isSoon?"var(--red)":isClose?"var(--amber)":"var(--text2)"};font-weight:500">${formatD(j.d)}</td>
      <td style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px" title="${esc(nomStr)}">
        <span style="height:6px;border-radius:50%;background:var(--violet);display:inline-block;margin-right:5px;width:6px"></span>${esc(nomStr)}
      </td>
      <td style="font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(j.description||"")}">${esc(j.description||"—")}</td>
      <td style="text-align:right;font-size:11px;font-weight:600;color:${dc};font-family:var(--font-mono);white-space:nowrap">${delai}</td>
    </tr>`;
  }).join("")}`;
});

html+=`</tbody></table>`;
el.innerHTML=html;
  html += '</tbody></table>';
  window.buildJalonsTable=buildJalonsTable;
}
 
  window.calNav=function(dir){
    if(calView==="day"){curM+=dir;if(curM>11){curM=0;curY++;}if(curM<0){curM=11;curY--;}}
    else if(calView==="month"){curY+=dir;}
    buildCal();
  };
  window.calNavDec=function(dir){curY+=dir*10;buildCal();};
 
  window.calOpenDay=function(y,m,d){
    const key=`${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const evts=AGENDA.filter(e=>e.date===key&&activeTypes.has(e.type));
    if(evts.length===1){openEvt(AGENDA.indexOf(evts[0]));return;}
    const dt=new Date(y,m,d);
    const dateStr=dt.toLocaleDateString("fr-FR",{weekday:"long",day:"numeric",month:"long"});
    document.getElementById("modal-body").innerHTML=`
      <button class="modal-close" onclick="closeModal()">x</button>
      <div class="modal-title">${dateStr}</div>
      <div class="modal-id">${evts.length} événement(s)</div>
      <div class="proj-list" style="margin-top:12px">
        ${evts.map(e=>{const t=TYPES_CAL[e.type]||TYPES_CAL.AUTRE;const idx=AGENDA.indexOf(e);
          return`<div class="proj-item" onclick="closeModal();setTimeout(()=>openEvt(${idx}),150)">
            <span class="proj-dot" style="background:${t.border}"></span>
            <span class="proj-name">${esc(e.titre)}</span>
            <span class="badge" style="background:${t.bg};color:${t.text};border:1px solid ${t.border};font-size:8px">${t.label}</span>
          </div>`;
        }).join("")}
      </div>`;
    document.getElementById("modal-overlay").classList.add("open");
  };
 
  window.calToggleType=function(t){
    if(activeTypes.has(t)){if(activeTypes.size>1)activeTypes.delete(t);}
    else activeTypes.add(t);
    document.querySelectorAll("#cal-type-filters .fchip").forEach(c=>{
      const tt=c.dataset.t;const v=TYPES_CAL[tt];
      c.className="fchip"+(activeTypes.has(tt)?" active":"");
      c.style.cssText=activeTypes.has(tt)?"color:"+v.text+";border-color:"+v.border+";background:"+v.bg:"";
    });
    buildDay();
  };
 
  window.openEvt=openEvt;
  buildCal();
}

function openModalHistorique(id, quinzaine){
  // Cherche le projet dans le snapshot de la quinzaine donnée
  const snap=DATA.snapshots[quinzaine];
  const p=(snap?.projets||[]).find(x=>(x.projet_id||x.ref_sujet)===id);
  if(!p){openModal(id);return;}
  const m=(DATA.meta||[]).find(x=>(x.projet_id||x.ref_sujet)===id)||{};
  // Injecter temporairement dans DATA.projets pour que openModal fonctionne
  const ancien=DATA.projets;
  DATA.projets=[p,...ancien.filter(x=>(x.projet_id||x.ref_sujet)!==id)];
  openModal(id);
  DATA.projets=ancien;
}



function openModal(id){
  const p=DATA.projets.find(x=>pid(x)===id);if(!p)return;
  const hist=(DATA.historiques||{})[id]||[];
  const pv=pp(p);const col=SC[p.statut]||"#475569";
  const metaById={};(DATA.meta||[]).forEach(m=>{metaById[m.projet_id||m.ref_sujet]=m;});
  const m=metaById[id]||{};
  const descUnique = m.description && m.description !== "nan" ? m.description : (p.description && p.description !== "nan" ? p.description : "");
  const metaItems=[["ref/id",id],["domaine",p.domaine||m.domaine],["entite",p.entite_concerne||m.entite_concerne],["priorite",p.priorite||m.priorite],["budget j/sem",p.budget_jours||m.budget_jours],["date debut",p.date_debut||m.date_debut],["date prévisionnelle",p.date_prevision||m.date_prevision],["date fin prev.",p.date_fin||m.date_fin],["effectifs",p.effectifs||m.effectifs],["type",m.type]].filter(([,v])=>v&&v!=="undefined");
  document.getElementById("modal-body").innerHTML=`
    <button class="modal-close" onclick="closeModal()">x</button>
    <div class="modal-title">${esc(nom(p))}</div>
    <div class="modal-id">${esc(id)}</div>
    <div class="modal-row">${badge(p.statut)}${(p.domaine||m.domaine)?`<span class="badge bON_HOLD">${esc(p.domaine||m.domaine)}</span>`:""}${p.phase?`<span class="badge bON_HOLD">${esc(p.phase)}</span>`:""}${(p.priorite||m.priorite)?`<span class="badge bON_HOLD">prio:${esc(p.priorite||m.priorite)}</span>`:""}</div>
    <div class="modal-sec"><div class="modal-stitle">avancement — ${pv}%</div><div class="prog-track"><div class="prog-fill" style="width:${pv}%;background:${col}"></div></div></div>
    <div class="modal-sec"><div class="modal-stitle">informations projet</div><div class="meta-grid">${metaItems.map(([k,v])=>`<div class="meta-item"><div class="meta-key">${esc(k)}</div><div class="meta-val">${esc(v)}</div></div>`).join("")}</div></div>
    ${(()=>{
  const faits=(DATA.agenda||[]).filter(e=>
    e.type==="PROJET"&&e.projet_ref===(p.projet_id||p.ref_sujet||id)
  ).sort((a,b)=>a.date.localeCompare(b.date));
  if(!faits.length)return"";
  const MFR=["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];
  return`<div class="modal-sec"><div class="modal-stitle">faits marquants</div>
    ${faits.map(e=>{
      const dt=new Date(e.date);
      const dateStr=dt.getDate()+" "+MFR[dt.getMonth()]+" "+dt.getFullYear();
      return`<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);align-items:flex-start">
        <span style="font-size:9px;font-family:var(--font-mono);color:var(--cyan);white-space:nowrap;min-width:80px">${dateStr}</span>
        <span style="font-size:11px;color:var(--text2)">${esc(e.description||"—")}</span>
      </div>`;
    }).join("")}
  </div>`;
})()}
    
    
    ${p.actions_realises?`<div class="modal-sec"><div class="modal-stitle">actions realisees</div><div class="modal-text">${esc(p.actions_realises)}</div></div>`:""}
    ${p.actions_a_mener?`<div class="modal-sec"><div class="modal-stitle">actions a mener</div><div class="modal-text">${esc(p.actions_a_mener)}${p.actions_echeance?`<br><span style="font-size:10px;color:var(--amber);font-family:var(--font-mono)">// echeance : ${esc(p.actions_echeance)}</span>`:""}</div></div>`:""}
    ${p.risques?`<div class="modal-sec"><div class="modal-stitle">risques</div><div class="modal-text" style="color:var(--amber)">${esc(p.risques)}${p.risque_niveau?` ${badge("À risque")}`:""} </div></div>`:""}
    ${p.points_blocage?`<div class="modal-sec"><div class="modal-stitle">blocages</div><div class="modal-text" style="color:var(--red)">${esc(p.points_blocage)}</div></div>`:""}
    ${(p.commentaire_libre||p.commentaire)?`<div class="modal-sec"><div class="modal-stitle">commentaire</div><div class="modal-text">${esc(p.commentaire_libre||p.commentaire)}</div></div>`:""}
    ${descUnique?`<div class="modal-sec"><div class="modal-stitle">description</div><div class="modal-text" style="color:var(--text3)">${esc(descUnique)}</div></div>`:""}
    ${hist.length>1?`<div class="modal-sec"><div class="modal-stitle">historique (${hist.length} quinzaines)</div>${hist.map(h=>`<div class="hist-row"><span class="hist-q">${esc(h.quinzaine)}</span>${badge(h.statut)}<span style="font-weight:600;font-family:var(--font-mono);font-size:10px">${h.avancement_pct||0}%</span><span style="color:var(--text3);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px">${esc(h.actions_realises||h.livrable_quinzaine||"")}</span></div>`).join("")}</div>`:""}`;
  document.getElementById("modal-overlay").classList.add("open");
}
function closeModal(){document.getElementById("modal-overlay").classList.remove("open");}


function toggleTheme(){
  const dark= document.body.classList.toggle('dark');
  const b=  document.getElementById('btn-theme')
  if(b) b.textContent = dark ?  '☀️' :'🌙';
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  }

(function(){
  if(localStorage.getItem('theme')==='dark'){
  document.body.classList.add('dark');}

  document.addEventListener('DOMContentLoaded', function(){
  const b= document.getElementById('btn-theme');
   if(b) b.textContent= document.body.classList.contains('dark') ? '☀️':'🌙' ;
  });
    const statsBody = document.getElementById("stats-body");
    if(statsBody && statsBody.innerHTML !== "") {
  const activeTab = document.querySelector(".stat-tab.active")?.dataset?.tab;
  if(activeTab === "carte") renderCarteOnglet();
}
  })();

"""


# ── HTML ──────────────────────────────────────────────────────────────────────

def generer_html(donnees, llm_cache=None, llm_syntheses= None):
    if llm_syntheses:
        donnees=dict(donnees)
        donnees["syntheses"]= llm_syntheses
    data_js = json.dumps(donnees, ensure_ascii=False)
    llm_js  = json.dumps(llm_cache or {}, ensure_ascii=False)
    q_label = donnees.get("quinzaine", "")
    llm_cfg=donnees.get("config_llm", {})


    head = (
        '<!DOCTYPE html>\n<html lang="fr">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        f'<title>MONITORING:: {q_label}</title>\n'
        '<style>' + CSS + '</style>\n</head>\n<body>'
    )

    html = ""
    html += '<div class="shell">'
    html += '<aside class="sidebar">'
    html += '<div class="logo">'
    html += '<div class="logo-title">Equipe data science</div>'
    html += '<div class="logo-sub">Outil de monitoring</div>'
    html += '<div class="logo-date" id="logo-date"></div>'
    html += '</div>'
    html += '<div class="q-selector-wrap">'
    html += '<div class="q-selector-label">Quinzaine</div>'
    html += '<select class="q-selector" id="q-selector" onchange="switchQuinzaine(this.value)"></select>'
    html += '</div>'
    html += '<div class="nav-section">Navigation</div>'
    html += '<div class="nav-item active" data-page="overview"><span class="nav-icon">&#9672;</span>Vue d\'ensemble<span class="nav-badge" id="nb-overview">&#8212;</span></div>'
    html += '<div class="nav-item" data-page="domaines"><span class="nav-icon">&#11041;</span>Par domaine</div>'
    html += '<div class="nav-item" data-page="collabs"><span class="nav-icon">&#9678;</span>Collaborateurs</div>'
    html += '<div class="nav-item" data-page="gantt"><span class="nav-icon">&#9636;</span>Roadmap Gantt</div>'
    html += '<div class="nav-item" data-page="evolutions"><span class="nav-icon">&#9651;</span>Evolutions<span class="nav-badge" id="nb-evol">&#8212;</span></div>'
    html += '<div class="sidebar-footer" id="sidebar-footer"></div>'
    html += '</aside>'
    html += '<div class="main">'
    html += '<div class="topbar">'
    html += '<span class="page-title" id="page-title">overview</span>'
    html += '<span class="snap-info" id="snap-info"></span>'
    html += '<div class="spacer"></div>'
    html += '<span class="gen-at" id="gen-at"></span>'
    html += '<button class="btn-theme" id="btn-theme" onclick="toggleTheme()">🌙️</button>'
    html += '</div>'
    html += '<div class="content">'
    html += '<div class="page active" id="page-overview"></div>'
    html += '<div class="page" id="page-domaines"></div>'
    html += '<div class="page" id="page-collabs"></div>'
    html += '<div class="page" id="page-gantt"></div>'
    html += '<div class="page" id="page-evolutions"></div>'
    html += '</div>'
    html += '</div>'
    html += '</div>'
    html += '<div class="modal-overlay" id="modal-overlay"><div class="modal" id="modal-body"></div></div>'
    html += '\n<script>\n'
    html += 'const DATA=' + data_js + ';\n'
    html += 'const LLM=' + llm_js + ';\n'
    html += SCRIPT
    html += '\n</script>\n</body>\n</html>'

    return head + html


# ── Entrypoint ────────────────────────────────────────────────────────────────

def generer_dashboard(config_path="config.yaml", quinzaine=None, llm_reponses=None,llm_syntheses=None, output=None):
    import yaml
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) if Path(config_path).exists() else {}
    chemin_out = output or cfg.get("paths", {}).get("dashboard_out", "frontend/dashboard.html")
    try:
        from storage.storage import StorageManager as SM
    except ImportError:
        from storage import StorageManager as SM  # type: ignore
    sm = SM(config_path)
    donnees = preparer_donnees(sm, quinzaine)
    if not donnees:
        return None
    chemin = Path(chemin_out)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(generer_html(donnees, llm_reponses or {},llm_syntheses or {}), encoding="utf-8")
    log.info(f"Dashboard -> {chemin}")
    print(f"\nOuvre : {chemin.resolve()}\n")
    return str(chemin.resolve())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quinzaine", default=None, help="Ex: T1_2026_R1")
    parser.add_argument("--output",    default=None)
    parser.add_argument("--config",    default="config.yaml")
    parser.add_argument("--llm",       action="store_true")
    args = parser.parse_args()
    llm_cache = {}
    if args.llm:
        try:
            from rag_engine import enrichir_html_generator
            llm_cache = enrichir_html_generator(args.config, quinzaine=args.quinzaine)
        except ImportError:
            try:
                from query.rag_engine import enrichir_html_generator
                llm_cache = enrichir_html_generator(args.config, quinzaine=args.quinzaine)
            except Exception as e:
                log.warning(f"LLM indisponible : {e}")
    generer_dashboard(config_path=args.config, quinzaine=args.quinzaine,
                      llm_reponses=llm_cache,llm_syntheses=None, output=args.output)


if __name__ == "__main__":
    main()