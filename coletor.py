#!/usr/bin/env python3
"""
Coletor unificado — modos:
  python3 coletor.py              → projetos+grupos (SIGPESQ) + editais (FAPES)
  python3 coletor.py --bot        → só SIGPESQ (login necessário)
  python3 coletor.py --edit        → só FAPES (sem login)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def run_bot():
    """Coleta projetos + grupos do SIGPESQ."""
    from bot_sigpesq import scraper

    cpf = os.environ.get("SIGPESQ_CPF", "").strip()
    senha = os.environ.get("SIGPESQ_SENHA", "").strip()

    if not cpf or not senha:
        print("[ERRO] Defina SIGPESQ_CPF e SIGPESQ_SENHA no ambiente.")
        return []

    projetos, grupos, _ = scraper(cpf, senha)
    print(f"\n[Bot] {len(projetos)} projetos + {len(grupos)} grupos\n")
    return projetos

def run_editais():
    """Coleta editais de FAPES, CNPq, CAPES e FINEP — uso público."""
    from coletor_editais import main as coletar_tudo
    return coletar_tudo()

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "full"
    projetos = []
    editais = []

    if modo == "--edit":
        run_editais()
        return
    elif modo == "--bot":
        run_bot()
        return

    # modo full — tudo
    print("=" * 50)
    print("  COLETOR UNIFICADO — SIGPESQ + FAPES")
    print("=" * 50)
    projetos = run_bot()
    try:
        editais = run_editais()
    except Exception as e:
        print(f"[AVISO] Editais FAPES: {e}")

    print()
    print("=" * 50)
    print("  COLETA FINALIZADA")
    print("=" * 50)
    if projetos:
        print(f"  ✔ Projetos SigPesq: {len(projetos)}")
    if editais:
        print(f"  ✔ Editais FAPES:    {len(editais)}")
    print("=" * 50)

if __name__ == "__main__":
    main()