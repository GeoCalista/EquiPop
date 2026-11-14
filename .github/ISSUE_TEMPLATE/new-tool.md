---
name: New tool
about: Propose a new tool, or a new part of EquiPop. Decided by the board (GOVERNANCE.md, section 3).
title: "New tool: "
labels: new-tool, board
---

## What it computes, and for whom

## Method and sources
<!-- the estimator or model, and the literature or established program
     it follows -->

## Doors
<!-- which first (Python, Stata, QGIS, Pro), which later -->

## How it will be validated
<!-- reference results: the same analysis in an established program
     (Stata, R, statsmodels, ...) on the same data, agreeing to a
     stated tolerance. They will be tests, run on every push. -->

## Its own files
<!-- the folders and files it will create (GOVERNANCE.md, section 3):
     equipop/<tool>/, tests/test_<tool>_*.py, stata/equipop_<tool>.ado,
     qgis/equipop_qgis/alg_<tool>.py, docs/tools/<tool>.md -->

## Shared files it will need
<!-- dispatch() in stata_bridge.py, the QGIS provider, the Pro toolbox,
     stata.toc, pyproject.toml dependencies ... (CONTRIBUTING.md,
     section 9) -->

## Who
- Developer:
- Proposed area owner and backup:

## Board decision
<!-- accepted / changed / declined, the date, and the reason. Accepted:
     add the area label, and the owners to GOVERNANCE.md and CODEOWNERS. -->
