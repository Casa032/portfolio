const pptxgen = require("pptxgenjs");
const fs = require("fs");

const data = JSON.parse(fs.readFileSync("donnees_rapport.json", "utf-8"));

// Palette : "Ocean Gradient" sobre pour un livrable juridique/corporate
const NAVY = "21295C";
const DEEP = "065A82";
const TEAL = "1C7293";
const LIGHT = "F2F5F8";
const WHITE = "FFFFFF";
const MUTED = "64748B";
const INK = "1E293B";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Veille DPO";
pres.title = data.titre;

const W = 13.3, H = 7.5;
const shadow = () => ({ type: "outer", color: "000000", blur: 8, offset: 3, angle: 90, opacity: 0.12 });

// ---------- Slide de couverture ----------
const cover = pres.addSlide();
cover.background = { color: NAVY };
cover.addText(data.titre, {
  x: 0.9, y: 2.4, w: 11.5, h: 1.2, fontSize: 46, bold: true, color: WHITE,
  fontFace: "Cambria", align: "left", margin: 0,
});
cover.addText("Rapport de synthèse — articles les plus pertinents", {
  x: 0.9, y: 3.7, w: 11.5, h: 0.6, fontSize: 20, color: "CADCFC",
  fontFace: "Calibri", align: "left", margin: 0,
});
const dateStr = new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
cover.addText(dateStr, {
  x: 0.9, y: 4.4, w: 11.5, h: 0.5, fontSize: 15, italic: true, color: "8FA6C4",
  fontFace: "Calibri", align: "left", margin: 0,
});

// ---------- Pré-calcul des index de slides ----------
// Ordre des slides : 1=cover. Ensuite, pour chaque partie :
//   1 slide sommaire + 1 slide par article.
// On calcule l'index de départ de chaque partie et de chaque article.
let idx = 2; // prochaine slide après la cover (1-based)
const plan = data.parties.map((part) => {
  const sommaireSlide = idx;
  idx += 1;
  const articleSlides = part.articles.map((_, i) => sommaireSlide + 1 + i);
  idx += part.articles.length;
  return { sommaireSlide, articleSlides };
});

// ---------- Pour chaque partie : sommaire + slides articles ----------
data.parties.forEach((part, pIdx) => {
  const { articleSlides } = plan[pIdx];

  // --- Slide sommaire de la partie ---
  const som = pres.addSlide();
  som.background = { color: LIGHT };

  som.addText(`Partie ${part.num}`, {
    x: 0.9, y: 0.55, w: 11.5, h: 0.5, fontSize: 18, bold: true, color: TEAL,
    fontFace: "Calibri", charSpacing: 2, margin: 0,
  });
  som.addText(part.nom, {
    x: 0.9, y: 1.05, w: 11.5, h: 1.0, fontSize: 30, bold: true, color: NAVY,
    fontFace: "Cambria", margin: 0, valign: "top",
  });

  if (part.articles.length === 0) {
    som.addText("Aucun article retenu pour cette partie.", {
      x: 0.9, y: 2.6, w: 11.5, h: 0.6, fontSize: 16, italic: true, color: MUTED,
      fontFace: "Calibri", margin: 0,
    });
  } else {
    // liste cliquable : chaque ligne renvoie à la slide de l'article
    const startY = 2.5;
    const rowH = Math.min(0.62, (H - startY - 0.6) / part.articles.length);
    part.articles.forEach((art, i) => {
      const y = startY + i * rowH;
      // pastille numéro
      som.addShape(pres.shapes.OVAL, {
        x: 0.9, y: y + 0.04, w: 0.38, h: 0.38, fill: { color: DEEP },
      });
      som.addText(String(i + 1), {
        x: 0.9, y: y + 0.04, w: 0.38, h: 0.38, fontSize: 14, bold: true,
        color: WHITE, align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
      // titre cliquable -> slide article
      som.addText([
        { text: art.titre, options: { color: INK, bold: true } },
        { text: `   ${art.source}${art.date ? " · " + art.date : ""}`, options: { color: MUTED, fontSize: 11 } },
      ], {
        x: 1.45, y: y, w: 11.0, h: rowH - 0.05, fontSize: 14, fontFace: "Calibri",
        valign: "middle", margin: 0,
      });
    });
  }

  // --- Slides articles ---
  part.articles.forEach((art, i) => {
    const s = pres.addSlide();
    s.background = { color: WHITE };

    // bandeau haut : partie + retour sommaire
    s.addText(`PARTIE ${part.num} · ${part.source || ""}`.trim().replace(/·\s*$/, ""), {
      x: 0.9, y: 0.5, w: 9.0, h: 0.4, fontSize: 12, bold: true, color: TEAL,
      fontFace: "Calibri", charSpacing: 1, margin: 0,
    });
    s.addText("↑ Sommaire", {
      x: 11.0, y: 0.5, w: 1.4, h: 0.4, fontSize: 12, color: DEEP, align: "right",
      fontFace: "Calibri", margin: 0,
    });

    // titre de l'article
    s.addText(art.titre, {
      x: 0.9, y: 1.15, w: 11.5, h: 1.5, fontSize: 26, bold: true, color: NAVY,
      fontFace: "Cambria", valign: "top", margin: 0,
    });

    // méta : source + date + score
    s.addText([
      { text: art.source || "", options: { bold: true, color: DEEP } },
      { text: art.date ? "   ·   " + art.date : "", options: { color: MUTED } },
      { text: `   ·   score ${art.score}`, options: { color: MUTED } },
    ], {
      x: 0.9, y: 2.75, w: 11.5, h: 0.4, fontSize: 14, fontFace: "Calibri", margin: 0,
    });

    // carte "raison / résumé"
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.9, y: 3.4, w: 11.5, h: 2.4, fill: { color: LIGHT }, rectRadius: 0.08,
      shadow: shadow(),
    });
    s.addText(art.raison || "—", {
      x: 1.25, y: 3.7, w: 10.8, h: 1.8, fontSize: 15, color: INK, fontFace: "Calibri",
      valign: "top", margin: 0,
    });

    // lien vers l'article original
    if (art.url) {
      s.addText("Lire l'article original →", {
        x: 0.9, y: 6.05, w: 6.0, h: 0.5, fontSize: 14, bold: true, color: TEAL,
        fontFace: "Calibri", margin: 0,
      });
    }
  });
});

pres.writeFile({ fileName: "rapport_nolinks.pptx" }).then(() => console.log("pptx écrit"));
