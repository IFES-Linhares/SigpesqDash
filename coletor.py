#!/usr/bin/env python3
"""
Coletor SIGPESQ — automação agendada

Uso:
  1. Defina credenciais via variáveis de ambiente
     (não use argumentos de linha de comando):

       export SIGPESQ_CPF="68408781472"
       export SIGPESQ_SENHA="sua_senha"
       python3 coletor.py

  2. Ou rode com script .bat/.sh conforme exemplo abaixo.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bot_sigpesq import scraper


def coletar() -> bool:
    cpf = os.environ.get("SIGPESQ_CPF", "").strip()
    senha = os.environ.get("SIGPESQ_SENHA", "").strip()

    if not cpf or not senha:
        print("[ERRO] Defina SIGPESQ_CPF e SIGPESQ_SENHA no ambiente antes de rodar.")
        print()
        print("Exemplo (Linux/macOS):")
        print('  export SIGPESQ_CPF="68408781472"')
        print('  export SIGPESQ_SENHA="sua_senha"')
        print("  python3 coletor.py")
        print()
        print("Exemplo (Windows - CMD):")
        print('  set SIGPESQ_CPF=68408781472')
        print('  set SIGPESQ_SENHA=sua_senha')
        print("  python coletor.py")
        return False

    print("=" * 50)
    print("  COLETOR SIGPESQ - INICIANDO")
    print("=" * 50)
    inicio = time.time()
    print(f"Projeto: Linhares (diretoria)")
    print(f"Hora do início: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    print()

    projetos, grupos, dashboard = scraper(cpf, senha)

    tempo = time.time() - inicio
    print()
    print("=" * 50)
    if projetos:
        print(f"  SUCESSO - {len(projetos)} projetos e {len(grupos)} grupos coletados")
        print(f"  Tempo total: {tempo:.1f} segundos")
        print(f"  Dados salvos em: dados/, docs/ (pronto para GitHub)")
    else:
        print("  FALHA - nenhum projeto coletado")
    print("=" * 50)
    return bool(projetos)


if __name__ == "__main__":
    sucesso = coletar()
    sys.exit(0 if sucesso else 1)