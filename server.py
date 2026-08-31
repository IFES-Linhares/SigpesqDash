import http.server
import json
import os
import subprocess
import sys
import time
import threading
from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse

PORT = int(os.environ.get("SIGPESQ_PORT", "8080"))
PASTA_BASE = Path(__file__).parent
PASTA_DADOS = PASTA_BASE / "dados"
PASTA_DASHBOARD = PASTA_BASE / "dashboard"
ULTIMA_ATUALIZACAO = [0]
LOCK_ATUALIZACAO = threading.Lock()
INTERVALO_MINIMO = 3600


def executar_bot(cpf, senha):
    try:
        env = os.environ.copy()
        env["SIGPESQ_HEADLESS"] = "1"
        env["SIGPESQ_SENHA"] = senha

        resultado = subprocess.run(
            [sys.executable, str(PASTA_BASE / "bot_sigpesq.py"), cpf],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(f"[BOT] stdout: {resultado.stdout}")
        if resultado.stderr:
            print(f"[BOT] stderr: {resultado.stderr}")
        return resultado.returncode == 0
    except subprocess.TimeoutExpired:
        print("[BOT] Timeout ao executar bot")
        return False
    except Exception as e:
        print(f"[BOT] Erro: {e}")
        return False


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA_DASHBOARD), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dados":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            json_path = PASTA_DADOS / "dados.json"
            if json_path.exists():
                dados = json.loads(json_path.read_text(encoding="utf-8"))
            else:
                dados = []
            self.wfile.write(json.dumps(dados, ensure_ascii=False).encode())
        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            tempo_desde = time.time() - ULTIMA_ATUALIZACAO[0]
            pode_atualizar = tempo_desde >= INTERVALO_MINIMO
            segundos_restantes = max(0, INTERVALO_MINIMO - tempo_desde)
            status = {
                "pode_atualizar": pode_atualizar,
                "segundos_restantes": int(segundos_restantes),
                "ultima_atualizacao": ULTIMA_ATUALIZACAO[0],
            }
            self.wfile.write(json.dumps(status).encode())
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/atualizar":
            with LOCK_ATUALIZACAO:
                tempo_desde = time.time() - ULTIMA_ATUALIZACAO[0]
                if tempo_desde < INTERVALO_MINIMO:
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    segundos = int(INTERVALO_MINIMO - tempo_desde)
                    self.wfile.write(
                        json.dumps({"erro": f"Aguarde {segundos}s para atualizar"}).encode()
                    )
                    return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                dados_requisicao = json.loads(body) if body else {}
            except json.JSONDecodeError:
                dados_requisicao = {}

            cpf = dados_requisicao.get("cpf", os.environ.get("SIGPESQ_CPF", ""))
            senha = dados_requisicao.get("senha", os.environ.get("SIGPESQ_SENHA", ""))

            if not cpf or not senha:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"erro": "CPF e senha sao obrigatorios"}).encode()
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "atualizando"}).encode())

            def rodar():
                with LOCK_ATUALIZACAO:
                    ULTIMA_ATUALIZACAO[0] = time.time()
                executar_bot(cpf, senha)

            threading.Thread(target=rodar, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[SERVER] {args[0]}")


def pedir_credenciais():
    cpf = os.environ.get("SIGPESQ_CPF", "")
    senha = os.environ.get("SIGPESQ_SENHA", "")

    if cpf and senha:
        print(f"[OK] Credenciais carregadas do ambiente (CPF: {cpf[:3]}...{cpf[-2:]})")
        return cpf, senha

    print("=" * 50)
    print("  SIGPESQ - Configuracao de Acesso")
    print("=" * 50)
    print()
    print("Para atualizar os dados, precisamos do acesso ao SigPesq.")
    print("As credenciais serao usadas apenas para coletar dados.")
    print()

    if not cpf:
        cpf = input("CPF: ").strip()

    if not senha:
        senha = getpass("Senha: ").strip()

    if not cpf or not senha:
        print("[ERRO] CPF e senha sao obrigatorios!")
        sys.exit(1)

    print()
    print(f"[OK] Credenciais configuradas (CPF: {cpf[:3]}...{cpf[-2:]})")
    return cpf, senha


if __name__ == "__main__":
    cpf_config, senha_config = pedir_credenciais()

    os.environ["SIGPESQ_CPF"] = cpf_config
    os.environ["SIGPESQ_SENHA"] = senha_config

    print()
    print(f"Servidor rodando em http://localhost:{PORT}")
    print(f"Dashboard: http://localhost:{PORT}/")
    print(f"Pressione Ctrl+C para parar")
    print()

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor parado.")
        server.server_close()
