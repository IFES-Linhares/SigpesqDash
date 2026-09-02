import csv
import json
import os
import shutil
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# Pasta raiz dos arquivos de dados internos
PASTA_DADOS = Path(__file__).parent / "dados"
PASTA_DASHBOARD = Path(__file__).parent / "dashboard"

# Pasta pública (docs/) — usada pelo GitHub Pages (gh-pages ou docs branch)
PASTA_PUBLICA = Path(__file__).parent / "docs"

PASTA_DADOS.mkdir(exist_ok=True)
PASTA_DASHBOARD.mkdir(exist_ok=True)
PASTA_PUBLICA.mkdir(exist_ok=True)

URL_BASE = "https://sigpesq.ifes.edu.br"
URL_LOGIN = f"{URL_BASE}/Login.aspx"
URL_DASHBOARD = f"{URL_BASE}/web/Dashboard.aspx"

# Tela da Diretoria: TODOS os projetos da unidade (não só os coordenados)
URL_PROJETOS_UNIDADE = f"{URL_BASE}/web/projeto/listaUnidade.aspx"
URL_GRUPOS_UNIDADE = f"{URL_BASE}/web/GrupoPesquisa/listaUnidade.aspx"

# Pasta pública para o GitHub Pages (docs/ é o padrão do GitHub Pages)
PASTA_PUBLICA = Path(__file__).parent / "docs"
PASTA_PUBLICA.mkdir(exist_ok=True)

# Headless por padrão; defina SIGPESQ_HEADLESS=0 para ver o navegador
HEADLESS = os.environ.get("SIGPESQ_HEADLESS", "1") != "0"

# Colunas da tabela de projetos da unidade (listaUnidade.aspx)
# Índices das <td> dentro de cada <tr> de dados
COLUNAS_UNIDADE = {
    "anoInicio": 2,
    "id": 3,
    "nome": 4,
    "coordenador": 5,
    "campusLotacao": 6,
    "campusExecucao": 7,
    "area": 8,
    "financiamentos": 9,
    "atualizadoEm": 10,
    "parecer": 12,
}


def coletar_tabela_paginada(page, url, mapa_colunas, nome_colecao="tabela"):
    """Coleta todos os registros de uma tabela ASP.NET GridView com paginação."""
    todos = []
    print(f"[INFO] Acessando {nome_colecao}: {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    total_paginas = detectar_total_paginas(page)

    pagina = 1
    while True:
        tabela = page.query_selector("#ContentPlaceHolder_gvwLista")
        if not tabela:
            print(f"[AVISO] Tabela não encontrada em {nome_colecao}")
            break

        linhas = tabela.query_selector_all("tr")
        for linha in linhas[1:]:  # pular cabeçalho
            colunas = linha.query_selector_all("td")
            if len(colunas) < len(mapa_colunas):
                continue
            texto_linha = linha.inner_text()
            if "Mostrando de" in texto_linha or "registro(s)" in texto_linha:
                continue

            item = {}
            for campo, indice in mapa_colunas.items():
                item[campo] = colunas[indice].inner_text().strip()
            todos.append(item)

        print(f"[INFO] {nome_colecao} pág {pagina}: +{len([l for l in linhas if l.query_selector_all('td')])} | acumulado: {len(todos)}")

        if pagina >= total_paginas:
            break

        if not ir_para_pagina(page, pagina + 1):
            print("[AVISO] Interrompendo paginação")
            break
        pagina += 1

    print(f"[OK] {nome_colecao}: {len(todos)} registros coletados")
    return todos


def salvar_dados(projetos, grupos, dashboard=None, unidade=None):
    """Salva projetos, grupos e metadados nos formatos interno (dados/) e público (docs/)."""
    if not projetos and not grupos:
        print("[AVISO] Nenhum dado para salvar")
        return

    total_veículos = len(projetos)
    total_grupos = len(grupos)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Salvar em dados/ (interno)
    with open(PASTA_DADOS / "dados.json", "w", encoding="utf-8") as f:
        json.dump(projetos, f, ensure_ascii=False, indent=2)

    if grupos:
        with open(PASTA_DADOS / "grupos.json", "w", encoding="utf-8") as f:
            json.dump(grupos, f, ensure_ascii=False, indent=2)

    # Salvar também em docs/ (pasta pública para GitHub Pages)
    with open(PASTA_PUBLICA / "dados.json", "w", encoding="utf-8") as f:
        json.dump(projetos, f, ensure_ascii=False, indent=2)

    if grupos:
        with open(PASTA_PUBLICA / "grupos.json", "w", encoding="utf-8") as f:
            json.dump(grupos, f, ensure_ascii=False, indent=2)

    # CSV de projetos
    colunas = []
    for d in projetos:
        for chave in d:
            if chave not in colunas:
                colunas.append(chave)

    csv_path = PASTA_DADOS / "projetos_linhares.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(projetos)
    print(f"[OK] CSV salvo em {csv_path}")

    # Metadados para a dashboard pública
    meta = {
        "geradoEm": agora,
        "campus": unidade or "Linhares",
        "totalProjetos": total_veículos,
        "totalGrupos": total_grupos,
    }
    (PASTA_PUBLICA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] {total_veículos} projetos + {total_grupos} grupos salvos")

    # Copiar para pasta dados/ (para visualização local via server.py)
    for nome in ["dados.json", "grupos.json", "editais.json"]:
        src = PASTA_PUBLICA / nome
        if src.exists():
            shutil.copy2(src, PASTA_DASHBOARD / nome)

    # Resumo do dashboard
    if dashboard:
        resumo_path = PASTA_DADOS / "dashboard_resumo.json"
        with open(resumo_path, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, ensure_ascii=False, indent=2)
        print(f"[OK] Resumo do dashboard salvo em {resumo_path}")


def login(page, cpf, senha):
    print(f"[INFO] Acessando {URL_LOGIN}")
    page.goto(URL_LOGIN, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    page.screenshot(path=str(PASTA_DADOS / "debug_login.png"))

    # Verificar bloqueio
    conteudo = page.content()
    if "Muitas tentativas" in conteudo or "Aguarde alguns segundos" in conteudo:
        print("[AVISO] Site bloqueado por tentativas anteriores. Aguardando 60 segundos...")
        page.wait_for_timeout(60000)
        page.goto(URL_LOGIN, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)

    print("[INFO] Preenchendo CPF...")
    page.fill('#txtLogin', cpf)

    print("[INFO] Preenchendo senha...")
    page.fill('#txtSenha', senha)

    print("[INFO] Clicando em Entrar...")
    page.click('#btnLogin')
    page.wait_for_load_state("networkidle", timeout=30000)

    page.screenshot(path=str(PASTA_DADOS / "debug_apos_login.png"))
    print(f"[DEBUG] URL apos login: {page.url}")

    # Verificar bloqueio apos tentativa
    conteudo = page.content()
    if "Muitas tentativas" in conteudo:
        print("[AVISO] Bloqueado novamente. Aguardando 60 segundos...")
        page.wait_for_timeout(60000)
        page.goto(URL_LOGIN, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        page.fill('#txtLogin', cpf)
        page.fill('#txtSenha', senha)
        page.click('#btnLogin')
        page.wait_for_load_state("networkidle", timeout=30000)

    # Verificar mensagem de erro na pagina
    erro_msg = page.query_selector(".alert, .erro, .error, .mensagem-erro, #lblErro")
    if erro_msg:
        texto = erro_msg.inner_text().strip()
        if texto and "inden" not in texto.lower():
            print(f"[AVISO] Mensagem do site: {texto}")

    if "login" in page.url.lower():
        print("[ERRO] Login falhou - ainda na pagina de login")
        return False

    print("[OK] Login realizado com sucesso!")
    return True


def coletar_dashboard(page):
    dados = {}
    try:
        page.goto(URL_DASHBOARD, timeout=30000)
        page.wait_for_selector("#ContentPlaceHolder_lblMonitor_MeusProjetos", timeout=15000)
        dados["meusProjetos"] = page.inner_text("#ContentPlaceHolder_lblMonitor_MeusProjetos")
        dados["outrosProjetos"] = page.inner_text("#ContentPlaceHolder_lblMonitor_OutroProjetos")
        dados["orientacoes"] = page.inner_text("#ContentPlaceHolder_lblMonitor_Orientacoes")
        dados["certificados"] = page.inner_text("#ContentPlaceHolder_lblMonitor_Certificados")
        dados["laboratorios"] = page.inner_text("#ContentPlaceHolder_lblMonitor_Laboratorios")
        print(f"[OK] Dashboard: {dados}")
    except Exception as e:
        print(f"[AVISO] Dashboard: {e}")
    return dados


def extrair_pagina_projetos(page):
    """Extrai os projetos da página atual da tabela gvwLista."""
    resultados = []
    tabela = page.query_selector("#ContentPlaceHolder_gvwLista")
    if not tabela:
        print("[AVISO] Tabela gvwLista não encontrada na página atual")
        return resultados

    linhas = tabela.query_selector_all("tr")
    # Pular a linha de cabeçalho (índice 0)
    for linha in linhas[1:]:
        colunas = linha.query_selector_all("td")
        if len(colunas) < 13:
            continue
        # Ignorar linha de paginação (contém span com número de página / links)
        texto_linha = linha.inner_text()
        if "Mostrando de" in texto_linha or "registro(s)" in texto_linha:
            continue

        projeto = {}
        for campo, indice in COLUNAS_UNIDADE.items():
            valor = colunas[indice].inner_text().strip()
            projeto[campo] = valor
        resultados.append(projeto)

    return resultados


def detectar_total_paginas(page):
    """Lê 'Mostrando de X até Y de Z registro(s)' e calcula o total de páginas."""
    try:
        texto = page.inner_text("#ContentPlaceHolder_gvwLista")
        # Ex.: "Mostrando de 1 até 10 de 121 registro(s)"
        if "registro(s)" in texto:
            partes = texto.split("de ")[-1].split(" registro")
            total_registros = int(partes[0].strip())
            # Tamanho da página = 10 (padrão do GridView)
            total_paginas = (total_registros + 9) // 10
            print(f"[INFO] {total_registros} registros -> {total_paginas} páginas")
            return total_paginas
    except Exception as e:
        print(f"[AVISO] Não foi possível detectar total de páginas: {e}")
    return 1


def ir_para_pagina(page, numero):
    """Navega para a página N clicando no link de paginação."""
    try:
        link = page.query_selector(f"a[href*='Page${numero}']")
        if not link:
            print(f"[AVISO] Link 'Page${numero}' não encontrado; tentando 'Último'")
            link = page.query_selector("a[href*='Page$Last']")
            if not link:
                return False
        link.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        page.wait_for_timeout(800)
        return True
    except Exception as e:
        print(f"[AVISO] Falha ao ir para página {numero}: {e}")
        return False


def coletar_projetos_unidade(page):
    todos = []

    print(f"[INFO] Acessando {URL_PROJETOS_UNIDADE}")
    page.goto(URL_PROJETOS_UNIDADE, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Salvar HTML da primeira página para debug
    (PASTA_DADOS / "projetos_unidade.html").write_text(page.content(), encoding="utf-8")

    # Detectar total de páginas
    total_paginas = detectar_total_paginas(page)

    pagina = 1
    while True:
        projetos_pagina = extrair_pagina_projetos(page)
        todos.extend(projetos_pagina)
        print(f"[INFO] Página {pagina}: {len(projetos_pagina)} projetos (acumulado: {len(todos)})")

        if pagina >= total_paginas:
            break

        if not ir_para_pagina(page, pagina + 1):
            print("[AVISO] Interrompendo paginação")
            break
        pagina += 1

    # Remover duplicados por id+codigo
    vistos = set()
    unicos = []
    for p in todos:
        chave = (p.get("id"), p.get("nome"))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(p)

    print(f"[OK] Total: {len(unicos)} projetos únicos coletados")
    return unicos


def coletar_grupos_pesquisa(page):
    grupos = []

    print(f"[INFO] Acessando {URL_GRUPOS_UNIDADE}")
    page.goto(URL_GRUPOS_UNIDADE, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    total_paginas = detectar_total_paginas(page)

    pagina = 1
    while True:
        tabela = page.query_selector("#ContentPlaceHolder_gvwLista")
        if not tabela:
            print("[AVISO] Tabela de grupos não encontrada")
            break

        linhas = tabela.query_selector_all("tr")
        for linha in linhas[1:]:
            colunas = linha.query_selector_all("td")
            if len(colunas) < 8:
                continue
            texto = linha.inner_text()
            if "Mostrando de" in texto or "registro(s)" in texto:
                continue

            grupos.append({
                "nome": colunas[1].inner_text().strip(),
                "lider": colunas[2].inner_text().strip(),
                "campus": colunas[3].inner_text().strip(),
                "anoInicio": colunas[4].inner_text().strip(),
                "area": colunas[5].inner_text().strip(),
                "situacao": colunas[6].inner_text().strip(),
            })

        print(f"[INFO] Grupos pág {pagina}: acumulado {len(grupos)}")

        if pagina >= total_paginas:
            break
        if not ir_para_pagina(page, pagina + 1):
            break
        pagina += 1

    print(f"[OK] {len(grupos)} grupos coletados")
    return grupos


def listar_unidades(page):
    """Lê as opções de unidade/acesso disponíveis no modal 'Acesso'."""
    unidades = []
    try:
        page.click("#lbtnGrupoAcesso")
        page.wait_for_timeout(800)

        links = page.query_selector_all("a[id*='btnModalAcesso_MudarUnidade']")
        for link in links:
            campus_el = link.query_selector("span.float-left")
            nivel_el = link.query_selector("span.float-right")
            campus = campus_el.inner_text().strip() if campus_el else ""
            nivel = nivel_el.inner_text().strip() if nivel_el else ""
            if campus and not any(u["campus"] == campus and u["nivel"] == nivel for u in unidades):
                unidades.append({"campus": campus, "nivel": nivel})

        fechar = page.query_selector("#modalAcesso_btnModal_Fechar")
        if fechar:
            fechar.click()
            page.wait_for_timeout(500)
    except Exception as e:
        print(f"[AVISO] listar_unidades: {e}")
    return unidades


def trocar_unidade(page, nome_unidade):
    """Troca o contexto de unidade para o campus informado (prefere nível Diretoria)."""
    try:
        page.click("#lbtnGrupoAcesso")
        page.wait_for_timeout(800)

        alvo = None
        links = page.query_selector_all("a[id*='btnModalAcesso_MudarUnidade']")
        for link in links:
            campus_el = link.query_selector("span.float-left")
            nome = campus_el.inner_text().strip() if campus_el else ""
            if nome.lower() == nome_unidade.lower():
                nivel_el = link.query_selector("span.float-right")
                nivel = nivel_el.inner_text().strip() if nivel_el else ""
                if "diretoria" in nivel.lower():
                    alvo = link
                    break
                alvo = alvo or link

        fechar = page.query_selector("#modalAcesso_btnModal_Fechar")
        if not alvo:
            print(f"[AVISO] Unidade '{nome_unidade}' não encontrada no modal de acesso")
            if fechar:
                fechar.click()
            return False

        alvo.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        page.wait_for_timeout(800)
        print(f"[OK] Unidade trocada para '{nome_unidade}'")
        return True
    except Exception as e:
        print(f"[AVISO] trocar_unidade: {e}")
        return False


def scraper(cpf, senha, unidade=None):
    projetos = []
    grupos = []
    dashboard = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        try:
            if not login(page, cpf, senha):
                return [], [], {}

            dashboard = coletar_dashboard(page)

            if unidade:
                trocar_unidade(page, unidade)

            projetos = coletar_projetos_unidade(page)
            grupos = coletar_grupos_pesquisa(page)

        except PWTimeout as e:
            page.screenshot(path=str(PASTA_DADOS / "erro.png"))
            print(f"[ERRO] Timeout: {e}")

        except Exception as e:
            page.screenshot(path=str(PASTA_DADOS / "erro.png"))
            print(f"[ERRO] {e}")

        finally:
            browser.close()

    # Salvar projetos e grupos na mesma função
    if projetos or grupos:
        salvar_dados(projetos, grupos, dashboard, unidade)

    return projetos, grupos, dashboard


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python bot_sigpesq.py <CPF>")
        print("A senha será solicitada de forma segura (ou defina a variável SIGPESQ_SENHA).")
        sys.exit(1)

    cpf = sys.argv[1]
    if len(sys.argv) >= 3:
        print("[AVISO] Passar a senha como argumento a expõe no histórico do shell.")
        senha = sys.argv[2]
    else:
        senha = os.environ.get("SIGPESQ_SENHA") or getpass("Senha SIGPESQ: ")

    scraper(cpf, senha)