#!/usr/bin/env python3
# Gera publica/index.html a partir de dashboard/index.html, modo estático
with open('/home/joao/Documentos/codigos/python/homero/dashboard/index.html') as f:
    h = f.read()

# 1) carregarDados(): ler também meta.json
h = h.replace(
    """const resp = await fetch('dados.json');""",
    """let meta = {};
                try { meta = await (await fetch('meta.json')).json(); } catch {}
                const resp = await fetch('dados.json');"""
)

# 2) Atualizar timestamp com metadados
h = h.replace(
    """document.getElementById('lastUpdate').innerText = 'Atualizado em ' + new Date().toLocaleTimeString();""",
    """document.getElementById('lastUpdate').innerText =
                    (meta.geradoEm || '') + ' | ' + (meta.totalProjetos || projetos.length) + ' projetos';"""
)

# 3) atualizarDados() — modo estático (sem backend)
h = h.replace(
    """async function atualizarDados() {""",
    """function atualizarDados() {"""
)
h = h.replace(
    """                const resp = await fetch('/atualizar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });""",
    """                const resp = { ok: true, json: async () => ({}) };"""
)
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
h = h.replace(
    """            } catch (e) {
                alert('Erro ao conectar com o servidor.\\n\\nVerifique se o servidor está rodando:\\npython3 server.py\\n\\nDetalhes: ' + e.message);
            } finally {""",
    """            } catch (e) {
            } finally {"""
)

with open('/home/joao/Documentos/codigos/python/homero/publica/index.html', 'w') as f:
    f.write(h)
print('OK')