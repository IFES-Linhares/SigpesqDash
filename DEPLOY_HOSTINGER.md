# Hospedagem no Hostinger (Rota B — opcional)

> Este guia é apenas documentação. O site público atual usa o **GitHub Pages** (Rota A),
> que entrega os MESMOS arquivos de `docs/`. Se no futuro quiser o Hostinger como host
> oficial, siga os passos abaixo. Nenhuma alteração no código é necessária — o site é
> 100% estático (HTML + JSON), então qualquer servidor web serve.

## Como funciona
- O GitHub Actions coleta os dados e gera/atualiza a pasta `docs/` (HTML + JSON puros).
- Para o Hostinger, basta **enviar o conteúdo de `docs/`** para a pasta pública (`public_html`)
  da hospedagem. Não há Python/Playwright rodando no servidor.

## Forma 1 — Deploy automático por FTP no mesmo workflow
Adicione ao final do job em `.github/workflows/coleta.yml` um passo usando `git-ftp`:

```yaml
      - name: Deploy para Hostinger via FTP
        env:
          FTP_HOST: ${{ secrets.FTP_HOST }}
          FTP_USER: ${{ secrets.FTP_USER }}
          FTP_PASS: ${{ secrets.FTP_PASS }}
        run: |
          git config ftp.user "$FTP_USER"
          git config ftp.password "$FTP_PASS"
          git ftp push --user "$FTP_USER" --passwd "$FTP_PASS" --syncroot docs/ \
            ftp://"$FTP_HOST"/public_html
```

Pré-requisitos:
- Criar secrets `FTP_HOST`, `FTP_USER`, `FTP_PASS` no repositório
  (Settings → Secrets and variables → Actions).
- O `git-ftp` precisa estar instalado no runner (adicionar `sudo apt-get install git-ftp`
  no `run` de instalação de dependências).

## Forma 2 — Upload manual
1. Rode a coleta localmente: `python3 coletor.py` (gera `docs/` atualizado).
2. Envie o conteúdo de `docs/` para `public_html` via FTP (FileZilla, por exemplo).
3. Confira que o site abra em `https://SEU_SITE/public_html` (ou domínio configurado).

## Apontar o DNS/URL do site IFES
Depois de alguma das formas acima, o site do IFES pode linkar para seu domínio/URL do
Hostinger em vez da URL do GitHub Pages — sem mudar nada no projeto, apenas trocando o link.

## Lembrete
Enquanto a Rota B não for adotada, **não remova** o passo de `git push` do workflow —
ele é o que mantém o GitHub Pages atualizado (Rota A).