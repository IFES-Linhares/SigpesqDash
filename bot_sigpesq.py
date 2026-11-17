import csv
import json
import os
import re
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

# Modal "Visualizar projeto" (btnResumoProjeto) — única tela que expõe a
# vigência do projeto (campos Início/Fim) na lista da unidade
SEL_MODAL_CODIGO = "#ContentPlaceHolder_ModalConsultaProjeto_Consulta_Projeto_lblCodigo"
SEL_MODAL_INICIO = "#ContentPlaceHolder_ModalConsultaProjeto_Consulta_Projeto_lblInicio"
SEL_MODAL_FIM = "#ContentPlaceHolder_ModalConsultaProjeto_Consulta_Projeto_lblFim"
SEL_MODAL_FECHAR = "#ContentPlaceHolder_ModalConsultaProjeto_btnModal_Fechar"
SEL_MODAL_PAINEL = "#ContentPlaceHolder_ModalConsultaProjeto_pnlModal"

# Abre um modal por projeto; pode ser desativado com SIGPESQ_VIGENCIA=0
COLETAR_VIGENCIA = os.environ.get("SIGPESQ_VIGENCIA", "1") != "0"

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
        return False

    # Sanidade: evita sobrescrever os dados públicos com uma coleta parcial
    anterior = 0
    arquivo_publico = PASTA_PUBLICA / "dados.json"
    if arquivo_publico.exists():
        try:
            anterior = len(json.loads(arquivo_publico.read_text(encoding="utf-8")))
        except Exception:
            anterior = 0
    if (
        anterior
        and len(projetos) < anterior * 0.5
        and os.environ.get("SIGPESQ_FORCAR_SALVAR") != "1"
    ):
        print(
            f"[ERRO] A coleta retornou {len(projetos)} projetos, menos da metade dos "
            f"{anterior} já publicados. Nada foi salvo para não degradar o site "
            f"(use SIGPESQ_FORCAR_SALVAR=1 para forçar)."
        )
        return False

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

    return True


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
    print(f"[DEBUG] senha recebida: len={len(senha)} último_char={senha[-1:]!r} contém_$={'$' in senha}")
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


def _texto(page, seletor):
    """inner_text tolerante a elemento ausente."""
    el = page.query_selector(seletor)
    return el.inner_text().strip() if el else ""


def codigos_pagina(page):
    """Códigos (PJ xxxx) das linhas visíveis na página atual da gvwLista."""
    tabela = page.query_selector("#ContentPlaceHolder_gvwLista")
    if not tabela:
        return []

    codigos = []
    for linha in tabela.query_selector_all("tr")[1:]:
        colunas = linha.query_selector_all("td")
        if len(colunas) < 13:
            continue
        texto = linha.inner_text()
        if "Mostrando de" in texto or "registro(s)" in texto:
            continue
        codigos.append(colunas[3].inner_text().strip())
    return codigos


def _fechar_modal(page):
    """Fecha o modal de consulta e espera ele sumir (evita bloquear a paginação)."""
    try:
        fechar = page.query_selector(SEL_MODAL_FECHAR)
        if fechar and fechar.is_visible():
            fechar.click(timeout=5000)
    except Exception:
        pass
    try:
        page.wait_for_selector(SEL_MODAL_PAINEL, state="hidden", timeout=5000)
    except Exception:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass


def coletar_vigencia_pagina(page, projetos_pagina, numero_pagina=1):
    """Lê Início/Fim de cada projeto da página abrindo o modal 'Visualizar'.

    O SIGPESQ não mostra as datas de vigência na listagem; elas só aparecem no
    modal de resumo do projeto (postback por linha). Os valores são gravados
    nos próprios dicionários de ``projetos_pagina``, casando pelo código do
    projeto (o postback pode devolver uma linha diferente da esperada).
    """
    if not COLETAR_VIGENCIA or not projetos_pagina:
        return

    def normalizar(valor):
        return str(valor or "").replace(" ", "").upper()

    por_codigo = {normalizar(p.get("id")): p for p in projetos_pagina if p.get("id")}
    codigos = codigos_pagina(page)
    print(f"[INFO] Vigência: {len(projetos_pagina)} projeto(s) na pág {numero_pagina}...")

    for indice, codigo in enumerate(codigos):
        try:
            link = page.query_selector(
                f"#ContentPlaceHolder_gvwLista_btnResumoProjeto_{indice}"
            )
            if not link:
                print(f"[AVISO] {codigo}: botão 'Visualizar' não encontrado")
                continue

            link.click(timeout=8000)
            try:
                page.wait_for_selector(SEL_MODAL_PAINEL, state="visible", timeout=10000)
                page.wait_for_function(
                    "(sel) => { const el = document.querySelector(sel); "
                    "return el && el.innerText.trim() !== ''; }",
                    arg=SEL_MODAL_CODIGO,
                    timeout=10000,
                )
            except PWTimeout:
                print(f"[AVISO] {codigo}: modal de vigência não carregou")

            codigo_modal = normalizar(_texto(page, SEL_MODAL_CODIGO))
            alvo = por_codigo.get(codigo_modal) or por_codigo.get(normalizar(codigo))
            if not alvo:
                print(f"[AVISO] {codigo}: projeto não encontrado na página; ignorando")
                continue
            if codigo_modal and codigo_modal != normalizar(codigo):
                print(f"[INFO] {codigo}: modal abriu {codigo_modal}; gravando no projeto correto")

            inicio = _texto(page, SEL_MODAL_INICIO)
            fim = _texto(page, SEL_MODAL_FIM)
            alvo["inicio"] = "" if inicio.startswith("lbl") else inicio
            alvo["fim"] = "" if fim.startswith("lbl") else fim
            print(
                f"[INFO] {alvo.get('id')}: vigência "
                f"{alvo['inicio'] or '?'} até {alvo['fim'] or '?'}"
            )
        except Exception as e:
            print(f"[AVISO] {codigo}: falha ao ler vigência ({e})")
        finally:
            _fechar_modal(page)


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


def _faixa_projetos(page):
    """Retorna (início, fim, total) do texto 'Mostrando de X até Y de Z'."""
    try:
        texto = page.inner_text("#ContentPlaceHolder_gvwLista")
        m = re.search(r"Mostrando de (\d+) até (\d+) de (\d+)", texto)
        if m:
            return tuple(int(g) for g in m.groups())
    except Exception:
        pass
    return None


def _clicar_paginacao(page, numero):
    """Clica no link da página (ou dispara o postback, se o clique for bloqueado)."""
    link = page.query_selector(f"a[href*='Page${numero}']")
    if not link:
        link = page.query_selector("a[href*='Page$Last']")
    if not link:
        return False

    try:
        link.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass

    try:
        link.click(timeout=8000)
        return True
    except Exception as e:
        href = link.get_attribute("href") or ""
        m = re.search(r"__doPostBack\('([^']*)','([^']*)'\)", href)
        if not m:
            print(f"[AVISO] Clique na paginação falhou: {e}")
            return False
        print(f"[AVISO] Clique bloqueado ({e}); disparando postback via JS")
        try:
            page.evaluate("([t, a]) => __doPostBack(t, a)", [m.group(1), m.group(2)])
            return True
        except Exception as e2:
            print(f"[AVISO] Postback da paginação falhou: {e2}")
            return False


def ir_para_pagina(page, numero):
    """Navega para a página N e confirma que a faixa de registros realmente mudou.

    O postback do GridView é assíncrono e às vezes o clique não surte efeito;
    sem essa confirmação o coletor relia a mesma página e perdia projetos.
    """
    antes = _faixa_projetos(page)
    esperado = (numero - 1) * 10 + 1

    for tentativa in range(1, 4):
        if not _clicar_paginacao(page, numero):
            return False

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            pass

        for _ in range(25):
            agora = _faixa_projetos(page)
            if agora and (agora[0] == esperado or (antes and agora[0] != antes[0])):
                return True
            page.wait_for_timeout(300)

        antes = _faixa_projetos(page) or antes
        print(f"[AVISO] Página {numero} não confirmou (tentativa {tentativa})")

    return False


def _coletar_lista_projetos(page):
    """Percorre todas as páginas da listagem e devolve os projetos (sem modal)."""
    todos = []

    print(f"[INFO] Acessando {URL_PROJETOS_UNIDADE}")
    page.goto(URL_PROJETOS_UNIDADE, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Salvar HTML da primeira página para debug
    (PASTA_DADOS / "projetos_unidade.html").write_text(page.content(), encoding="utf-8")

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

    # Remover duplicados por id+nome
    vistos = set()
    unicos = []
    for p in todos:
        chave = (p.get("id"), p.get("nome"))
        if chave not in vistos:
            vistos.add(chave)
            p.setdefault("inicio", "")
            p.setdefault("fim", "")
            unicos.append(p)

    print(f"[OK] Lista: {len(unicos)} projetos únicos")
    return unicos


def enriquecer_vigencia(page, todos):
    """Segunda passada: lê a vigência no modal de cada projeto (melhor esforço).

    A lista de projetos já foi coletada antes; se algo falhar aqui, os projetos
    são preservados e apenas as datas ficam vazias.
    """
    if not COLETAR_VIGENCIA or not todos:
        return

    print(f"[INFO] Lendo vigência de {len(todos)} projeto(s)...")
    page.goto(URL_PROJETOS_UNIDADE, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    total_paginas = detectar_total_paginas(page)

    por_id = {str(p.get("id")): p for p in todos if p.get("id")}
    pagina = 1
    while pagina <= total_paginas:
        projetos_pagina = extrair_pagina_projetos(page)
        coletar_vigencia_pagina(page, projetos_pagina, pagina)

        for lido in projetos_pagina:
            destino = por_id.get(str(lido.get("id")))
            if destino is not None:
                destino["inicio"] = lido.get("inicio", "")
                destino["fim"] = lido.get("fim", "")

        if pagina >= total_paginas:
            break
        if not ir_para_pagina(page, pagina + 1):
            print("[AVISO] Vigência interrompida; lista de projetos preservada")
            break
        pagina += 1

    com_datas = sum(1 for p in todos if p.get("inicio") or p.get("fim"))
    print(f"[OK] Vigência lida para {com_datas}/{len(todos)} projeto(s)")


def coletar_projetos_unidade(page):
    todos = _coletar_lista_projetos(page)
    try:
        enriquecer_vigencia(page, todos)
    except Exception as e:
        print(f"[AVISO] Vigência: {e}")
    return todos


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
                "campus": colunas[3].inner_text().strip(),
                "area": colunas[4].inner_text().strip(),
                "lider": colunas[5].inner_text().strip(),
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