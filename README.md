# SigpesqDash — Dashboard de Pesquisa IFES Campus Linhares

Sistema que coleta automaticamente dados de **projetos, grupos de pesquisa** (SIGPESQ) e
**editais de fomento** (FAPES, CNPq, CAPES, FINEP) e publica um dashboard estático,
visível publicamente via GitHub Pages.

Repositório: [IFES-Linhares/SigpesqDash](https://github.com/IFES-Linhares/SigpesqDash)

## O que o projeto faz

1. **Coleta automática**
   - `bot_sigpesq.py` — loga no SIGPESQ (login com CPF/senha via Playwright) e extrai projetos e grupos.
   - `coletor_editais.py` — baixa editais públicos de FAPES, CNPq (via Playwright) e FINEP (via API/requests).
   - `coletor.py` — orquestra tudo (`full`, `--bot`, `--edit`).

2. **Gera dados estruturados**
   - `docs/dados.json`, `docs/grupos.json`, `docs/editais.json`, `docs/meta.json` (públicos).
   - `dados/` e `dashboard/` (internos, ignorados pelo git).

3. **Publica um site estático**
   - `dashboard/index.html` — dashboard local (admin/preview).
   - `build_public.py` — gera `docs/index.html` (versão pública, sem backend).
   - `docs/` é servido pelo GitHub Pages (sem Python em produção).

4. **Atualiza sozinho na nuvem**
   - GitHub Action `Coleta diaria de dados` roda o coletor 1x/dia (06:00 em Brasília, ajustável) e faz push de `docs/` se houver mudança.

## Estrutura

- `server.py` — servidor local para preview/admin (dashboard + coleta manual). **Não** é usado em produção.
- `build_public.py` — transforma o dashboard em versão estática para páginas públicas.
- `requirements.txt` — dependências (Playwright, requests).

## Como rodar localmente

**Pré-requisitos:** Python 3.12, `pip install -r requirements.txt` e `playwright install chromium`.

- Preview do site: `python3 server.py` (abre http://127.0.0.1:8080 e coleta no início; use `--skip-coleta` para pular).
- Coletar tudo: `python3 coletor.py`
- Só SIGPESQ: `python3 coletor.py --bot` | Só editais: `python3 coletor.py --edit`

## Publicação (Rota A — GitHub Pages)

1. A coleta atualiza `docs/`.
2. Commit/push de `docs/` mantém o GitHub Pages do repositório em dia.
3. O site do IFES pode linkar a URL pública gerada pelo Pages.

## Automação na nuvem (GitHub Actions)

- Arquivo: `.github/workflows/coleta.yml`.
- **Secrets necessários** (Settings → Secrets and variables → Actions):
  - `SIGPESQ_CPF` e `SIGPESQ_SENHA` (credenciais do SIGPESQ; a senha é gravada literalmente, ex.: `HAgs3001$$`).
- Disparos: cron diário + `workflow_dispatch` (manual).
- Publica `docs/` usando `GITHUB_TOKEN` (sem expor PAT).

## Hospedagem alternativa (Rota B — Hostinger)

Veja [`DEPLOY_HOSTINGER.md`](DEPLOY_HOSTINGER.md). O site é estático, então basta enviar o conteúdo de `docs/`
para a pasta pública do Hostinger (via FTP). Não há runtime Python no servidor.

## Segurança

- Credenciais do SIGPESQ ficam **apenas** em secrets do GitHub (ou digitadas no prompt do `server.py`); nunca em arquivos/código.
- Tokens de acesso pessoal (PAT) não são usados na automação; só `GITHUB_TOKEN`.
- Evite expor PAT/senhas em chat/logs — revogue se vazarem.

## Observações

- **Cota**: o site é estático (sem API) → sem risco de sobrecarga por tráfego. As cotas do GitHub (minutos de Actions e banda do Pages) são folgadas para este uso.