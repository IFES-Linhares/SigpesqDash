#!/usr/bin/env python3
"""Gera docs/index.html (versão pública) a partir de dashboard/index.html.

O dashboard local usa o backend do server.py (botão "Atualizar dados");
a versão pública é estática e lê os JSONs gerados pelo coletor via GitHub Pages.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ORIGEM = RAIZ / "dashboard" / "index.html"
DESTINO = RAIZ / "docs" / "index.html"

h = ORIGEM.read_text(encoding="utf-8")

# 1) carregarDados(): ler também meta.json
antes = h
h = h.replace(
    """const resp = await fetch('dados.json');""",
    """let meta = {};
                try { meta = await (await fetch('meta.json')).json(); } catch {}
                const resp = await fetch('dados.json');"""
)
assert h != antes, "trecho do carregarDados() não encontrado"

# 2) Atualizar timestamp com metadados
antes = h
h = h.replace(
    """document.getElementById('lastUpdate').innerText = 'Atualizado em ' + new Date().toLocaleTimeString();""",
    """document.getElementById('lastUpdate').innerText =
                    (meta.geradoEm || '') + ' | ' + (meta.totalProjetos || projetos.length) + ' projetos';"""
)
assert h != antes, "trecho do lastUpdate não encontrado"

# 3) atualizarDados() — modo estático (sem backend).
#    Mantém o "async" para que o "await" interno continue válido no JS.
antes = h
h = h.replace(
    """                const resp = await fetch('/atualizar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });""",
    """                const resp = { ok: true, json: async () => ({}) };"""
)
assert h != antes, "trecho do fetch('/atualizar') não encontrado"

antes = h
h = h.replace(
    """                const dados = await resp.json();
                if (resp.ok) {
                    alert('Atualização iniciada!\\n\\nAguarde 30 segundos e depois:\\n1. Clique em "Recarregar" no navegador (F5)\\n2. Ou clique em "Atualizar dados" novamente');
                } else {
                    alert('Erro: ' + (dados.erro || 'Não foi possível atualizar'));
                }""",
    """                await new Promise(r => setTimeout(r, 300));
                alert('Esta é uma visão pública. Os dados são atualizados pela diretoria.');
                carregarDados();"""
)
assert h != antes, "trecho do alert de atualização não encontrado"

antes = h
h = h.replace(
    """            } catch (e) {
                alert('Erro ao conectar com o servidor.\\n\\nVerifique se o servidor está rodando:\\npython3 server.py\\n\\nDetalhes: ' + e.message);
            } finally {""",
    """            } catch (e) {
            } finally {"""
)
assert h != antes, "trecho do catch de atualização não encontrado"

DESTINO.write_text(h, encoding="utf-8")
print(f"OK: {DESTINO.relative_to(RAIZ)} gerado a partir de {ORIGEM.relative_to(RAIZ)}")
