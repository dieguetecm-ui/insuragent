"""Generación del reporte técnico en PDF (entregable 2 del PRD §2).

Se abandonó Quarto: exigía instalar un CLI externo más una cadena LaTeX o
Chromium para llegar al PDF, y el reporte quedaba sin poder generarse en el
mismo entorno que corre la aplicación. Aquí el PDF se produce con las mismas
dependencias de Python del proyecto — HTML + CSS de impresión renderizados con
WeasyPrint — de modo que `make report` funciona en cualquier máquina donde
funcione `make test`.
"""

from insuragent.reporting.builder import build_pdf, render_html

__all__ = ["build_pdf", "render_html"]
