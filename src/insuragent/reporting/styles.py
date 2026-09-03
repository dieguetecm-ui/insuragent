"""Hoja de estilos de impresión del reporte.

CSS pensado para papel, no para pantalla: unidades absolutas, control explícito
de saltos de página y numeración en el pie. Se mantiene aparte del contenido
para que ajustar la presentación no obligue a tocar el texto.
"""

from __future__ import annotations

STYLESHEET = """
@page {
    size: A4;
    margin: 20mm 18mm 18mm 18mm;

    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "DejaVu Sans", sans-serif;
        font-size: 8pt;
        color: #8a8f98;
    }
    @bottom-left {
        content: "InsurAgent — Reporte Técnico de la PoC";
        font-family: "DejaVu Sans", sans-serif;
        font-size: 8pt;
        color: #8a8f98;
    }
}

/* La portada no lleva encabezado ni pie. */
@page :first {
    margin: 0;
    @bottom-center { content: ""; }
    @bottom-left { content: ""; }
}

:root {
    --tinta: #1a1d21;
    --tenue: #5c6470;
    --linea: #d8dce2;
    --acento: #1f5f8b;
    --acento-suave: #eef4f9;
    --alerta: #8b2f1f;
    --alerta-suave: #fbeeec;
    --aviso: #7a5b12;
    --aviso-suave: #fdf6e3;
    --ok: #1f6b45;
}

body {
    font-family: "DejaVu Sans", "Liberation Sans", sans-serif;
    font-size: 9.5pt;
    line-height: 1.55;
    color: var(--tinta);
}

/* ---------------------------------------------------------------- portada */

.portada {
    page-break-after: always;
    height: 297mm;
    padding: 45mm 22mm 18mm 22mm;
    box-sizing: border-box;
    background: linear-gradient(160deg, #14324a 0%, #1f5f8b 55%, #2b7fae 100%);
    color: #ffffff;
}
.portada .eyebrow {
    font-size: 9pt;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    opacity: 0.75;
}
.portada h1 {
    font-size: 34pt;
    line-height: 1.1;
    margin: 6mm 0 3mm 0;
    font-weight: 700;
    border: none;
    color: #ffffff;
}
.portada .subtitulo {
    font-size: 13pt;
    font-weight: 300;
    opacity: 0.92;
    max-width: 130mm;
}
.portada .regla {
    width: 28mm;
    height: 2.5pt;
    background: rgba(255, 255, 255, 0.85);
    margin: 10mm 0;
}
.portada dl {
    margin-top: 14mm;
    font-size: 9.5pt;
}
.portada dt {
    opacity: 0.7;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 7.5pt;
    margin-top: 4mm;
}
.portada dd { margin: 0.6mm 0 0 0; font-size: 10.5pt; }
.portada .pie {
    position: absolute;
    bottom: 18mm;
    font-size: 8pt;
    opacity: 0.7;
    max-width: 150mm;
}

/* ---------------------------------------------------------------- títulos */

h1 {
    font-size: 17pt;
    margin: 0 0 4mm 0;
    padding-bottom: 2mm;
    border-bottom: 1.5pt solid var(--acento);
    color: var(--acento);
    page-break-after: avoid;
}
h2 {
    font-size: 12.5pt;
    margin: 7mm 0 2.5mm 0;
    color: var(--tinta);
    page-break-after: avoid;
}
h3 {
    font-size: 10.5pt;
    margin: 5mm 0 2mm 0;
    color: var(--tenue);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    page-break-after: avoid;
}
section.capitulo { page-break-before: always; }
p { margin: 0 0 3mm 0; text-align: justify; }

/* ----------------------------------------------------------------- tablas */

table {
    width: 100%;
    border-collapse: collapse;
    margin: 3mm 0 5mm 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
}
thead { display: table-header-group; }
th {
    background: var(--acento-suave);
    color: var(--acento);
    text-align: left;
    font-weight: 600;
    padding: 1.8mm 2.5mm;
    border-bottom: 1pt solid var(--acento);
}
td {
    padding: 1.6mm 2.5mm;
    border-bottom: 0.5pt solid var(--linea);
    vertical-align: top;
}
tr:nth-child(even) td { background: #fafbfc; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.centro, th.centro { text-align: center; }
.ok { color: var(--ok); font-weight: 700; }
.fallo { color: var(--alerta); font-weight: 700; }

/* --------------------------------------------------------------- tarjetas */

.metricas {
    display: flex;
    flex-wrap: wrap;
    gap: 3mm;
    margin: 4mm 0 6mm 0;
}
.metrica {
    flex: 1 1 38mm;
    border: 0.75pt solid var(--linea);
    border-top: 2.5pt solid var(--acento);
    border-radius: 1.5mm;
    padding: 3mm;
    page-break-inside: avoid;
}
.metrica .valor {
    font-size: 17pt;
    font-weight: 700;
    color: var(--acento);
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}
.metrica .etiqueta {
    font-size: 7.5pt;
    color: var(--tenue);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 1mm;
}
.metrica .umbral { font-size: 7.5pt; color: var(--tenue); margin-top: 0.8mm; }

/* --------------------------------------------------------------- llamadas */

.callout {
    border-left: 3pt solid var(--acento);
    background: var(--acento-suave);
    padding: 3mm 4mm;
    margin: 4mm 0;
    page-break-inside: avoid;
    font-size: 9pt;
}
.callout .titulo { font-weight: 700; margin-bottom: 1.5mm; }
.callout.alerta { border-color: var(--alerta); background: var(--alerta-suave); }
.callout.alerta .titulo { color: var(--alerta); }
.callout.aviso { border-color: var(--aviso); background: var(--aviso-suave); }
.callout.aviso .titulo { color: var(--aviso); }

/* ----------------------------------------------------------------- código */

code {
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    background: #f2f4f7;
    padding: 0.3mm 1mm;
    border-radius: 0.8mm;
}
pre {
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    background: #f7f8fa;
    border: 0.5pt solid var(--linea);
    border-left: 2.5pt solid var(--tenue);
    padding: 2.5mm 3mm;
    margin: 3mm 0;
    white-space: pre-wrap;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; }

ul, ol { margin: 0 0 3mm 0; padding-left: 5mm; }
li { margin-bottom: 1.2mm; }

figure { margin: 4mm 0; page-break-inside: avoid; text-align: center; }
figcaption { font-size: 8pt; color: var(--tenue); margin-top: 2mm; }

.nota-pie {
    font-size: 8pt;
    color: var(--tenue);
    border-top: 0.5pt solid var(--linea);
    padding-top: 2mm;
    margin-top: 5mm;
}

/* ------------------------------------------------------------- contenidos */

/* ---------------------------------------------------- transcripciones */

.conversacion {
    border: 0.75pt solid var(--linea);
    border-radius: 2mm;
    padding: 4mm;
    margin: 4mm 0 6mm 0;
    background: #fcfcfd;
}
.conversacion > h3 { margin-top: 0; }

.ficha-asegurado {
    background: var(--acento-suave);
    border-radius: 1.5mm;
    padding: 2.5mm 3mm;
    margin-bottom: 3mm;
    font-size: 8.5pt;
    page-break-inside: avoid;
}
.ficha-asegurado b { color: var(--acento); }
.ficha-asegurado .previos {
    margin-top: 1.5mm;
    padding-top: 1.5mm;
    border-top: 0.5pt solid var(--linea);
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 7.5pt;
}

.turno {
    margin: 3mm 0;
    padding-left: 3mm;
    border-left: 2pt solid var(--linea);
    page-break-inside: avoid;
}
.turno-cabecera {
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--tenue);
    margin-bottom: 1.5mm;
}
.turno-cabecera .ruta {
    background: var(--acento);
    color: #ffffff;
    border-radius: 1mm;
    padding: 0.3mm 1.5mm;
    letter-spacing: 0.04em;
}

.burbuja {
    border-radius: 2mm;
    padding: 2.2mm 3mm;
    margin: 1.5mm 0;
    font-size: 9pt;
    page-break-inside: avoid;
}
.burbuja .quien {
    display: block;
    font-size: 7pt;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1mm;
    opacity: 0.7;
}
.burbuja.usuario {
    background: #eef1f5;
    border: 0.5pt solid var(--linea);
    margin-right: 18mm;
}
.burbuja.agente {
    background: #ffffff;
    border: 0.5pt solid var(--acento);
    margin-left: 18mm;
}

.traza {
    background: #f7f8fa;
    border: 0.5pt dashed var(--linea);
    border-radius: 1.5mm;
    padding: 2mm 2.5mm;
    margin: 1.5mm 0 1.5mm 6mm;
    font-size: 8pt;
    color: var(--tenue);
    page-break-inside: avoid;
}
.traza b { color: var(--tinta); }
.traza table { margin: 1.5mm 0 0 0; font-size: 7.5pt; }
.traza th { padding: 1mm 2mm; }
.traza td { padding: 0.9mm 2mm; }
.traza .destacado { color: var(--acento); font-weight: 700; }

/* ------------------------------------------------------------ credenciales */

.credenciales td, .credenciales th { font-family: "DejaVu Sans Mono", monospace; font-size: 7.5pt; }
.credenciales td:first-child, .credenciales th:first-child { font-family: "DejaVu Sans", sans-serif; }

/* ------------------------------------------------------------- contenidos */

.toc { page-break-after: always; }
.toc ol { list-style: none; padding-left: 0; counter-reset: cap; }
.toc li {
    counter-increment: cap;
    padding: 1.6mm 0;
    border-bottom: 0.5pt dotted var(--linea);
    font-size: 10pt;
}
.toc li::before {
    content: counter(cap) ".";
    color: var(--acento);
    font-weight: 700;
    display: inline-block;
    width: 8mm;
}
.toc li .desc { color: var(--tenue); font-size: 8.5pt; display: block; margin-left: 8mm; }
"""
