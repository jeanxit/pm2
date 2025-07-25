from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import subprocess
import re
import os
import socket
import paramiko

app = Flask(__name__)
app.secret_key = "chave-muito-secreta"

# === Lista de servidores ===
SERVIDORES = [
    {"nome": "Localhost", "host": None, "user": None, "password": None},
    {"nome": "Servidor GAIZ", "host": "192.168.1.253", "user": "gaiz", "password": "Gaiz1#d4kota2025"},
    # Adicione outros servidores!
]

# Caminho do pm2 do usuário gaiz (ajuste para cada servidor, se quiser!)
PM2_EXPORT_PATH = "export PATH=$PATH:/home/gaiz/.nvm/versions/node/v20.19.3/bin; "

def remove_ansi(text):
    ansi_escape = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def run_cmd(cmd, servidor=None, cwd=None):
    if not servidor or not servidor.get('host'):  # Execução local
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=45,
                encoding="utf-8",
                errors="replace",
                cwd=cwd
            )
            output = (result.stdout or '') + (result.stderr or '')
            return remove_ansi(output)
        except Exception as e:
            return f"Erro: {e}"
    else:  # Execução remota via SSH
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=servidor['host'],
                username=servidor['user'],
                password=servidor['password'],
                timeout=20
            )
            export_path = PM2_EXPORT_PATH
            # Se precisar de cwd, use 'cd /diretorio && export ... && comando'
            if cwd:
                cmd = f"cd {cwd} && {export_path}{cmd}"
            else:
                cmd = export_path + cmd
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=45)
            output = stdout.read().decode("utf-8") + stderr.read().decode("utf-8")
            ssh.close()
            return remove_ansi(output)
        except Exception as e:
            return f"Erro SSH: {e}"

def get_servidor_idx():
    try:
        return int(request.args.get("servidor", 0))
    except Exception:
        return 0

def get_servidor_by_idx(idx):
    if 0 <= idx < len(SERVIDORES):
        return SERVIDORES[idx]
    return SERVIDORES[0]

def get_port_from_log(nome, servidor):
    log_txt = run_cmd(f"pm2 logs {nome} --lines 15 --nostream", servidor)
    match = re.search(r'Local:\s*http://[^\s:]+:(\d+)', log_txt)
    if match:
        return match.group(1)
    return "-"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def parse_pm2_list(pm2_output, servidor):
    lines = pm2_output.splitlines()
    headers = []
    rows = []
    header_found = False
    for line in lines:
        if not header_found and "│ id" in line and "│ name" in line:
            headers = [h.strip() for h in line.split("│")[1:-1]]
            if 'porta' not in headers:
                headers.append('porta')
            if 'endereco' not in headers:
                headers.append('endereco')
            header_found = True
        elif header_found and "│" in line and not line.strip().startswith("─"):
            values = [v.strip() for v in line.split("│")[1:-1]]
            if len(values) == len(headers) - 2:
                try:
                    idx_nome = headers.index("name")
                    idx_status = headers.index("status")
                except Exception:
                    idx_nome, idx_status = 1, 4
                nome = values[idx_nome]
                status = values[idx_status].lower()
                porta = get_port_from_log(nome, servidor) if "online" in status else "-"
                ip = get_local_ip() if not servidor.get("host") else servidor.get("host")
                endereco = f"{ip}:{porta}" if porta != "-" else "-"
                values.append(porta)
                values.append(endereco)
                rows.append(dict(zip(headers, values)))
    return headers, rows

def contar_status(processos):
    counts = {'online':0, 'stopped':0, 'errored':0, 'paused':0, 'unknown':0}
    for proc in processos:
        stat = (proc.get('status','') or '').lower()
        if 'online' in stat: counts['online'] += 1
        elif 'stop' in stat: counts['stopped'] += 1
        elif 'error' in stat: counts['errored'] += 1
        elif 'pause' in stat: counts['paused'] += 1
        else: counts['unknown'] += 1
    return counts

def get_host_port():
    host = request.host.split(':')[0]
    porta = request.host.split(':')[1] if ':' in request.host else "80"
    return host, porta

@app.route("/")
def index():
    servidor_idx = get_servidor_idx()
    servidor = get_servidor_by_idx(servidor_idx)
    processos_txt = run_cmd("pm2 list", servidor)
    headers, processos = parse_pm2_list(processos_txt, servidor)
    status_counts = contar_status(processos)
    host, porta = get_host_port()
    return render_template(
        "index.html",
        processos_txt=processos_txt,
        headers=headers,
        processos=processos,
        status_counts=status_counts,
        host=host,
        porta=porta,
        servidores=SERVIDORES,
        servidor_idx=servidor_idx
    )
@app.route('/acao_pm2', methods=['POST'])
def acao_pm2():
    data = request.get_json()
    nome = data.get('nome')
    acao = data.get('acao')
    dir_projeto = data.get('dir_projeto')  # Pode vir None

    def arquivo_eco(projeto):
        eco_js = os.path.join(projeto, "ecosystem.config.js")
        eco_cjs = os.path.join(projeto, "ecosystem.config.cjs")
        if os.path.isfile(eco_js):
            return "ecosystem.config.js"
        elif os.path.isfile(eco_cjs):
            return "ecosystem.config.cjs"
        return None

    if not nome or not acao:
        return jsonify({'erro': 'Faltando parâmetros'}), 400

    # START
    if acao == 'start':
        # Se recebeu dir_projeto, tenta iniciar via ecosystem
        if dir_projeto:
            arquivo = arquivo_eco(dir_projeto)
            if not arquivo:
                return jsonify({'erro': 'Arquivo ecosystem.config.js ou .cjs não encontrado no diretório informado!'}), 400
            output = []
            output.append(f"**git pull**\n" + run_cmd("git pull", cwd=dir_projeto))
            output.append(f"**npm install**\n" + run_cmd("npm install", cwd=dir_projeto))
            output.append(f"**npm run build**\n" + run_cmd("npm run build", cwd=dir_projeto))
            output.append(f"**pm2 start {arquivo}**\n" + run_cmd(f"pm2 start {arquivo}", cwd=dir_projeto))
            output.append(f"**pm2 save**\n" + run_cmd("pm2 save"))
            return jsonify({'ok': True, 'saida': "\n\n".join(output)})
        # Senão, start simples (nome do processo)
        else:
            out = run_cmd(f'pm2 start {nome}')
            return jsonify({'ok': True, 'saida': out})

    # STOP
    elif acao == 'stop':
        out = run_cmd(f'pm2 stop {nome}')
        return jsonify({'ok': True, 'saida': out})

    # RESTART (pode receber dir_projeto para deploy completo)
    elif acao == 'restart':
        if dir_projeto:
            arquivo = arquivo_eco(dir_projeto)
            if not arquivo:
                return jsonify({'erro': 'Arquivo ecosystem.config.js ou .cjs não encontrado no diretório informado!'}), 400
            output = []
            output.append(f"**pm2 stop {nome}**\n" + run_cmd(f"pm2 stop {nome}"))
            output.append(f"**git pull**\n" + run_cmd("git pull", cwd=dir_projeto))
            output.append(f"**npm install**\n" + run_cmd("npm install", cwd=dir_projeto))
            output.append(f"**npm run build**\n" + run_cmd("npm run build", cwd=dir_projeto))
            output.append(f"**pm2 start {arquivo}**\n" + run_cmd(f"pm2 start {arquivo}", cwd=dir_projeto))
            output.append(f"**pm2 save**\n" + run_cmd("pm2 save"))
            return jsonify({'ok': True, 'saida': "\n\n".join(output)})
        else:
            out = run_cmd(f'pm2 restart {nome}')
            return jsonify({'ok': True, 'saida': out})

    # DELETE (opcional, adicione se quiser)
    elif acao == 'delete':
        out = run_cmd(f'pm2 delete {nome}')
        return jsonify({'ok': True, 'saida': out})

    else:
        return jsonify({'erro': 'Ação inválida'}), 400

from flask import jsonify, render_template, make_response

@app.route("/tabela_pm2_todos")
def tabela_pm2_todos():
    try:
        # Pega processos locais
        processos_txt_local = run_cmd("pm2 list", SERVIDORES[0])
        headers, processos_local = parse_pm2_list(processos_txt_local, SERVIDORES[0])
        for p in processos_local:
            p['Servidor'] = 'Localhost'

        # Processos remotos
        processos_remotos = []
        for srv in SERVIDORES[1:]:
            processos_txt_remoto = run_cmd("pm2 list", srv)
            headers_rem, processos_srv = parse_pm2_list(processos_txt_remoto, srv)
            for p in processos_srv:
                p['Servidor'] = srv["nome"]
                processos_remotos.append(p)

        processos = processos_local + processos_remotos
        if "Servidor" not in headers:
            headers.append("Servidor")

        # Renderiza HTML da tabela
        tabela_html = render_template("tabela_pm2.html", headers=headers, processos=processos)

        # Conta status
        status_counts = {
            "online": sum(1 for p in processos if p["status"].lower() == "online"),
            "stopped": sum(1 for p in processos if p["status"].lower() == "stopped"),
            "errored": sum(1 for p in processos if p["status"].lower() == "errored"),
            "paused": sum(1 for p in processos if p["status"].lower() == "paused"),
            "unknown": sum(1 for p in processos if p["status"].lower() not in ["online", "stopped", "errored", "paused"])
        }

        # Retorna JSON
        return jsonify({
            "tabela_html": tabela_html,
            "status_counts": status_counts
        })

    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)


@app.route("/action", methods=["POST"])
def action():
    servidor_idx = int(request.form.get("servidor_idx", 0))
    servidor = get_servidor_by_idx(servidor_idx)
    tipo = request.form.get("tipo")
    dir_projeto = request.form.get("dir_projeto", "").strip()
    nome = request.form.get("nome", "").strip()
    eco_js = os.path.join(dir_projeto, "ecosystem.config.js")
    eco_cjs = os.path.join(dir_projeto, "ecosystem.config.cjs")

    if tipo == "start":
        arquivo = None
        # No remoto não verifica os.path.isfile (pois não faz sentido, então sempre tenta ecosystem.config.js)
        if (servidor.get('host')) or os.path.isfile(eco_js):
            arquivo = "ecosystem.config.js"
        elif os.path.isfile(eco_cjs):
            arquivo = "ecosystem.config.cjs"
        else:
            flash("Arquivo ecosystem.config.js ou ecosystem.config.cjs não encontrado no diretório informado!")
            return redirect(url_for("index", servidor=servidor_idx))
        output = []
        output.append(f"**git pull**\n" + run_cmd("git pull", servidor, cwd=dir_projeto))
        output.append(f"**npm install**\n" + run_cmd("npm install", servidor, cwd=dir_projeto))
        output.append(f"**npm run build**\n" + run_cmd("npm run build", servidor, cwd=dir_projeto))
        output.append(f"**pm2 start {arquivo}**\n" + run_cmd(f"pm2 start {arquivo}", servidor, cwd=dir_projeto))
        output.append(f"**pm2 save**\n" + run_cmd("pm2 save", servidor))
        flash("\n\n".join(output))
    elif tipo == "stop" and nome:
        saida = run_cmd(f"pm2 stop {nome}", servidor)
        flash(saida)
    elif tipo == "restart" and nome and dir_projeto:
        arquivo = None
        if (servidor.get('host')) or os.path.isfile(eco_js):
            arquivo = "ecosystem.config.js"
        elif os.path.isfile(eco_cjs):
            arquivo = "ecosystem.config.cjs"
        else:
            flash("Arquivo ecosystem.config.js ou ecosystem.config.cjs não encontrado no diretório do projeto!")
            return redirect(url_for("index", servidor=servidor_idx))
        output = []
        output.append(f"**pm2 stop {nome}**\n" + run_cmd(f"pm2 stop {nome}", servidor))
        output.append(f"**git pull**\n" + run_cmd("git pull", servidor, cwd=dir_projeto))
        output.append(f"**npm install**\n" + run_cmd("npm install", servidor, cwd=dir_projeto))
        output.append(f"**npm run build**\n" + run_cmd("npm run build", servidor, cwd=dir_projeto))
        output.append(f"**pm2 start {arquivo}**\n" + run_cmd(f"pm2 start {arquivo}", servidor, cwd=dir_projeto))
        output.append(f"**pm2 save**\n" + run_cmd("pm2 save", servidor))
        flash("\n\n".join(output))
    elif tipo == "restart" and not dir_projeto:
        flash("Para reiniciar, é obrigatório informar o diretório do projeto!")
    elif tipo == "delete" and nome:
        saida = run_cmd(f"pm2 delete {nome}", servidor)
        flash(saida)
    else:
        flash("Preencha os campos corretamente.")
    return redirect(url_for("index", servidor=servidor_idx))

# ====== ROTAS DE NAVEGAÇÃO DA SIDEBAR ======

@app.route("/processos")
def processos():
    all_processes = []
    all_headers = None
    for idx, servidor in enumerate(SERVIDORES):
        processos_txt = run_cmd("pm2 list", servidor)
        headers, processos = parse_pm2_list(processos_txt, servidor)
        if not all_headers:
            all_headers = headers + ['Servidor']
        for p in processos:
            p = dict(p)  # garante dict
            p['Servidor'] = servidor['nome']
            all_processes.append(p)
    host, porta = get_host_port()
    return render_template(
        "processos.html",
        headers=all_headers,
        processos=all_processes,
        host=host,
        porta=porta,
        servidores=SERVIDORES,
        servidor_idx=get_servidor_idx()
    )

@app.route("/graficos")
def graficos():
    status_counts_all = {'online': 0, 'stopped': 0, 'errored': 0, 'paused': 0, 'unknown': 0}
    for servidor in SERVIDORES:
        processos_txt = run_cmd("pm2 list", servidor)
        headers, processos = parse_pm2_list(processos_txt, servidor)
        counts = contar_status(processos)
        for k in status_counts_all:
            status_counts_all[k] += counts.get(k, 0)
    host, porta = get_host_port()
    return render_template(
        "graficos.html",
        status_counts=status_counts_all,
        host=host,
        porta=porta,
        servidores=SERVIDORES,
        servidor_idx=get_servidor_idx()
    )

@app.route("/recursos")
def recursos():
    nomes = []
    cpus = []
    mems = []
    servidores_col = []
    for servidor in SERVIDORES:
        processos_txt = run_cmd("pm2 list", servidor)
        headers, processos = parse_pm2_list(processos_txt, servidor)
        for p in processos:
            nomes.append(p.get('name', '-'))
            servidores_col.append(servidor['nome'])
            cpu = p.get('cpu', '0').replace('%', '').replace(',', '.')
            mem = p.get('mem', '0').replace(',', '.').upper()
            match = re.match(r"([\d\.]+)\s*([A-Z]+)", mem)
            mem_mb = 0
            if match:
                num, unidade = match.groups()
                try:
                    num = float(num)
                    if unidade == 'GB':
                        mem_mb = num * 1024
                    elif unidade == 'MB':
                        mem_mb = num
                    elif unidade == 'KB':
                        mem_mb = num / 1024
                except Exception:
                    mem_mb = 0
            cpus.append(float(cpu) if cpu else 0)
            mems.append(round(mem_mb, 1))
    host, porta = get_host_port()
    return render_template(
        "recursos.html",
        host=host,
        porta=porta,
        nomes=nomes,
        cpus=cpus,
        mems=mems,
        servidores_col=servidores_col,  # Para mostrar de qual servidor veio
        servidores=SERVIDORES,
        servidor_idx=get_servidor_idx()
    )

@app.route("/logs")
def logs():
    logs_por_processo = {}
    for servidor in SERVIDORES:
        processos_txt = run_cmd("pm2 list", servidor)
        _, processos = parse_pm2_list(processos_txt, servidor)
        for p in processos:
            nome = p.get("name")
            if nome:
                chave = f"{servidor['nome']} | {nome}"
                log = run_cmd(f"pm2 logs {nome} --lines 50 --nostream", servidor)
                logs_por_processo[chave] = log
    host = request.host.split(':')[0]
    porta = request.host.split(':')[1] if ':' in request.host else "80"
    return render_template(
        "logs.html",
        logs_por_processo=logs_por_processo,
        host=host,
        porta=porta,
        servidores=SERVIDORES,
        servidor_idx=get_servidor_idx()
    )

# ===========================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
