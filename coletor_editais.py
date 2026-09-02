#!/usr/bin/env python3
"""
Coletor de Editais de Fomento (FAPES, CNPq, CAPES, FINEP).

Fontes públicas — não precisa de login.
Gera docs/editais.json e dados/editais.json
"""
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PASTA_BASE = Path(__file__).parent
PASTA_DADOS = PASTA_BASE / "dados"
PASTA_PUBLICA = PASTA_BASE / "docs"
PASTA_DADOS.mkdir(exist_ok=True)
PASTA_PUBLICA.mkdir(exist_ok=True)


def br_para_iso(data_br):
    """Converte '30/09/2026', '30/09/26' ou '30-09-2026' para '2026-09-30'."""
    if not data_br:
        return None
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", data_br.strip())
    if not m:
        return None
    d, mo, y = m.groups()
    ano = int(y)
    if ano < 100:
        ano += 2000
    return f"{ano}-{int(mo):02d}-{int(d):02d}"


# ============================================================
# FAPES — https://fapes.es.gov.br/ (página pública, sem login)
# ============================================================
def coletar_fapes(page):
    editais = []
    url = "https://fapes.es.gov.br/"
    print(f"[INFO] FAPES: {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    page.wait_for_timeout(2500)

    headings = page.query_selector_all("h1, h2, h3, h4, h5")
    for h in headings:
        titulo = h.inner_text().strip()
        if not re.search(r"(EDITAL|CHAMADA)", titulo, re.IGNORECASE):
            continue

        bloco = page.evaluate(
            "el => { let p = el; for (let i=0;i<2 && p.parentElement;i++) p=p.parentElement; return p.innerText; }",
            h,
        )
        link = page.evaluate(
            "el => { let p = el; for (let i=0;i<2 && p.parentElement;i++) p=p.parentElement; const a=p.querySelector('a[href]'); return a ? a.href : ''; }",
            h,
        )

        prazo_br = None
        m = re.search(r"(?:Inscri[çc][õo]es\s*(?:at[ée]|até)|at[ée])\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", bloco, re.IGNORECASE)
        if m:
            prazo_br = m.group(1)
        fluxo = bool(re.search(r"fluxo\s*cont[ií]nuo", bloco, re.IGNORECASE))

        if titulo.lower() in (e.get("titulo", "").lower() for e in editais):
            continue

        prazo_iso = br_para_iso(prazo_br)
        editais.append({
            "agencia": "FAPES",
            "titulo": titulo,
            "prazoFim": prazo_iso or "",
            "prazoTexto": prazo_br or ("Fluxo contínuo" if fluxo else ""),
            "situacao": "Fluxo contínuo" if fluxo else "Aberto",
            "url": link or url,
            "fonte": url,
        })

    print(f"[OK] FAPES: {len(editais)} editais coletados")
    return editais


# ============================================================
# CNPq — https://www.gov.br/cnpq/pt-br/chamadas/abertas-para-submissao
# ============================================================
def coletar_cnpq(page):
    editais = []
    url = "https://www.gov.br/cnpq/pt-br/chamadas/abertas-para-submissao"
    print(f"[INFO] CNPq: {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    page.wait_for_timeout(2500)

    # H1 = títulos das chamadas clicáveis; extrai texto do bloco para datas
    itens = page.query_selector_all("h1, h2, h3 a")
    vistos = set()
    for h1 in itens:
        texto = h1.inner_text().strip()
        if not texto or not re.search(r"Chamada|EDITAL|Edital", texto, re.IGNORECASE):
            continue

        link_el = h1.query_selector("a")
        link = link_el.get_attribute("href") if link_el else ""
        if link and link.startswith("/"):
            link = "https://www.gov.br" + link

        # bloco com datas
        bloco = h1.evaluate(
            "el => { let p=el; for(let i=0;i<2&&p.parentElement;i++)p=p.parentElement; return p.innerText; }"
        )

        # prazo: "Inscrições: 19/08/2026 a 09/10/2026"
        m = re.search(
            r"(?:Inscri[çc][õo]es?|inscri[çc][õo]es\s*abertas)\s*[:.\s]*[^.]*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:a|até|até|ate|-|—|-|—)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            bloco, re.IGNORECASE | re.DOTALL
        )
        prazo_iso = None
        prazo_ini = None
        if m:
            prazo_ini = br_para_iso(m.group(1))
            prazo_iso = br_para_iso(m.group(2))
        else:
            m2 = re.search(r"at[ée]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", bloco, re.IGNORECASE)
            if m2:
                prazo_iso = br_para_iso(m2.group(1))

        if texto.lower() in vistos:
            continue
        vistos.add(texto.lower())

        editais.append({
            "agencia": "CNPq",
            "titulo": texto,
            "prazoFim": prazo_iso or "",
            "prazoTexto": prazo_iso or "",
            "situacao": "Aberto",
            "url": link or url,
            "fonte": url,
        })

    print(f"[OK] CNPq: {len(editais)} editais coletados")
    return editais


# ============================================================
# FINEP — usa API JSON: /o/c/chamadapublicas
# ============================================================
def coletar_finep():
    """FINEP tem API JSON headless via Liferay — sem JS pesado."""
    import requests
    editais = []
    api = "https://www.finep.gov.br/o/c/chamadapublicas?sort=dataDePublicacao:desc"
    print(f"[INFO] FINEP (API): {api}")

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(api, timeout=20, headers=headers)
        dados = resp.json()

        items = dados.get("items", dados) if isinstance(dados, dict) else dados
        if not isinstance(items, list):
            items = []

        for e in items:
            situacao = e.get("situacao", {}).get("label", "") if isinstance(e.get("situacao"), dict) else str(e.get("situacao", ""))

            if "Aberta" not in situacao and "aberta" not in situacao.lower():
                continue

            prazo = e.get("prazoDeInscricao", "")
            prazo_iso = ""
            if prazo:
                m = re.match(r"(\d{4}-\d{2}-\d{2})", str(prazo))
                prazo_iso = m.group(1) if m else str(prazo)[:10]

            editais.append({
                "agencia": "FINEP",
                "titulo": e.get("titulo", ""),
                "prazoFim": prazo_iso,
                "prazoTexto": prazo or prazo_iso,
                "situacao": situacao,
                "url": f"https://www.finep.gov.br/e/chamada-publica/{e.get('id', '')}",
                "fonte": api,
            })

    except Exception as ex:
        print(f"[AVISO] FINEP falhou: {ex}")

    print(f"[OK] FINEP: {len(editais)} editais coletados")
    return editais


# ============================================================
# CAPES — https://www.gov.br/capes/pt-br/assuntos/editais-e-resultados-capes
# ============================================================
def coletar_capes(page):
    editais = []
    url = "https://www.gov.br/capes/pt-br/assuntos/editais-e-resultados-capes"
    print(f"[INFO] CAPES: {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    page.wait_for_timeout(2500)

    # Extrai todos os links que parecem ser editais / chamadas
    links = page.query_selector_all("a")
    vistos = set()
    for a in links:
        texto = a.inner_text().strip()
        href = a.get_attribute("href") or ""

        if len(texto) < 15 or not texto.lower().startswith(("edital", "chamada", "programa")):
            continue

        if href.startswith("/"):
            href = "https://www.gov.br" + href

        if texto in vistos:
            continue
        vistos.add(texto)

        editais.append({
            "agencia": "CAPES",
            "titulo": texto.replace("\n", " ").strip(),
            "prazoFim": "",
            "prazoTexto": "",
            "situacao": "Aberto",
            "url": href,
            "fonte": url,
        })

    print(f"[OK] CAPES: {len(editais)} editais coletados")
    return editais


# ============================================================
# MAIN
# ============================================================
def main():
    editais = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # FAPES e CNPq usam Playwright (JS-side)
        for nome, func in [("FAPES", coletar_fapes), ("CNPq", coletar_cnpq)]:
            try:
                editais.extend(func(page))
            except Exception as e:
                print(f"[ERRO] {nome}: {e}")

        # FINEP pode usar requests (mais rápido)
        try:
            editais.extend(coletar_finep())
        except Exception as e:
            print(f"[ERRO] FINEP: {e}")

        # CAPES — links genéricos
        try:
            editais.extend(coletar_capes(page))
        except Exception as e:
            print(f"[ERRO] CAPES: {e}")

        browser.close()

    salvar_editais_no_final(editais)
    return editais


def salvar_editais_no_final(editais):
    path_pub = PASTA_PUBLICA / "editais.json"
    path_int = PASTA_DADOS / "editais.json"
    for p in (PASTA_PUBLICA, PASTA_DADOS):
        p.mkdir(exist_ok=True)
        with open(p / "editais.json", "w", encoding="utf-8") as f:
            json.dump(editais, f, ensure_ascii=False, indent=2)

    # Meta
    meta_path = PASTA_PUBLICA / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except Exception:
        meta = {}
    meta["geradoEm"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    meta["totalEditais"] = len(editais)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()