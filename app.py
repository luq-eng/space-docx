from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
import pikepdf
import os
import hashlib
import re
import uuid
import random
import time
import base64
import requests
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'space-docx-super-secret-key-2026'
CORS(app)

# ==================== CONFIGURAÇÕES ====================
HYPERCASH_PUBLIC_KEY = "pk_b48f62cc1f920cdaaf9c7bea2cf1e0a20edba5f9"
HYPERCASH_SECRET_KEY = "sk_b4ed44b6073bae4aed687393a6b7baf8e0047746"
HYPERCASH_API_URL = "https://api.hypercashbrasil.com.br/api"

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== CONTROLE DE TESTES ====================
testes_utilizados_ip = defaultdict(list)
testes_utilizados_cpf = defaultdict(list)
testes_utilizados_cnpj = defaultdict(list)
testes_utilizados_email = defaultdict(list)
testes_utilizados_cep = defaultdict(list)

CHAVES_TESTE = {}
LIMITE_ANALISES_TESTE = 5
analises_teste_contador = defaultdict(int)

def obter_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr or '127.0.0.1'

def pode_gerar_teste(cpf, cnpj, email, cep, ip):
    if cpf and cpf in testes_utilizados_cpf and len(testes_utilizados_cpf[cpf]) > 0:
        return False, "Este CPF já utilizou o teste gratuito"
    if cnpj and cnpj in testes_utilizados_cnpj and len(testes_utilizados_cnpj[cnpj]) > 0:
        return False, "Este CNPJ já utilizou o teste gratuito"
    if email and email in testes_utilizados_email and len(testes_utilizados_email[email]) > 0:
        return False, "Este e-mail já utilizou o teste gratuito"
    if cep and cep in testes_utilizados_cep and len(testes_utilizados_cep[cep]) > 0:
        return False, "Este CEP já utilizou o teste gratuito"
    if ip and ip in testes_utilizados_ip and len(testes_utilizados_ip[ip]) > 0:
        return False, "Este IP já utilizou o teste gratuito"
    return True, "OK"

def registrar_teste(cpf, cnpj, email, cep, ip, chave):
    if cpf:
        testes_utilizados_cpf[cpf].append({'chave': chave, 'data': datetime.now().isoformat()})
    if cnpj:
        testes_utilizados_cnpj[cnpj].append({'chave': chave, 'data': datetime.now().isoformat()})
    if email:
        testes_utilizados_email[email].append({'chave': chave, 'data': datetime.now().isoformat()})
    if cep:
        testes_utilizados_cep[cep].append({'chave': chave, 'data': datetime.now().isoformat()})
    if ip:
        testes_utilizados_ip[ip].append({'chave': chave, 'data': datetime.now().isoformat()})

def gerar_chave_unica():
    return f"FREE-{uuid.uuid4().hex[:12].upper()}"

# ==================== BANCO DE DADOS ====================
USUARIOS = {
    'admin@space-docx.com': {
        'id': 1,
        'nome': 'Administrador',
        'senha': hashlib.sha256('Admin@2026'.encode()).hexdigest(),
        'plano': 'enterprise',
        'empresa': 'Space-Docx',
        'cpf': '',
        'cnpj': '00.000.000/0001-00',
        'cep': '00000-000',
        'telefone': '(11) 99999-9999',
        'data_expiracao': (datetime.now() + timedelta(days=365)).isoformat(),
        'status': 'ativo',
        'tipo': 'pago',
        'analises_restantes': 999999
    }
}
ANALISES = {}
PLANOS = {
    'basico': {'id': 1, 'nome': 'Básico', 'preco': 49, 'preco_centavos': 4900, 'dias': 30, 'validacoes': 50},
    'profissional': {'id': 2, 'nome': 'Profissional', 'preco': 149, 'preco_centavos': 14900, 'dias': 30, 'validacoes': 300},
    'enterprise': {'id': 3, 'nome': 'Enterprise', 'preco': 349, 'preco_centavos': 34900, 'dias': 30, 'validacoes': 999999}
}

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        
        # Verificar se o usuário está bloqueado
        if session.get('status') == 'bloqueado':
            flash('❌ Sua conta está bloqueada. Renove seu plano para continuar.', 'error')
            return redirect(url_for('planos'))
        
        # Verificar se expirou
        data_expiracao = session.get('data_expiracao')
        if data_expiracao and datetime.fromisoformat(data_expiracao) < datetime.now():
            session['status'] = 'bloqueado'
            flash('❌ Sua assinatura expirou. Renove seu plano.', 'error')
            return redirect(url_for('planos'))
        
        return f(*args, **kwargs)
    return decorated

def analisar_pdf(caminho):
    try:
        with pikepdf.Pdf.open(caminho) as pdf:
            producer = str(pdf.docinfo.get('/Producer', '')) if pdf.docinfo.get('/Producer') else ''
            creator = str(pdf.docinfo.get('/Creator', '')) if pdf.docinfo.get('/Creator') else ''
            texto = f"{producer} {creator}".lower()
            score = 70
            status = 'VERIFICAR'
            status_icon = '🟡'
            status_color = '#f59e0b'
            
            if any(f in texto for f in ['canva', 'photoshop', 'illustrator', 'corel', 'gimp']):
                score, status, status_icon, status_color = 0, 'FRAUDE', '🔴', '#ef4444'
            elif any(f in texto for f in ['quadient', 'gmc', 'inspire']):
                score, status, status_icon, status_color = 100, 'AUTÊNTICO', '🟢', '#22c55e'
            elif any(f in texto for f in ['itau', 'bradesco', 'santander', 'caixa', 'nubank']):
                score, status, status_icon, status_color = 95, 'AUTÊNTICO', '🟢', '#22c55e'
            elif any(f in texto for f in ['pikepdf', 'exiftool']):
                score, status, status_icon, status_color = 30, 'SUSPEITO', '🟠', '#f97316'
            else:
                score, status, status_icon, status_color = 50, 'VERIFICAR', '🟡', '#f59e0b'
            
            if not pdf.is_linearized:
                score -= 10
            
            if score < 0:
                score = 0
            
            return {
                'score': score,
                'status': status,
                'status_icon': status_icon,
                'status_color': status_color,
                'data': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
    except Exception as e:
        return {
            'score': 0,
            'status': 'ERRO',
            'status_icon': '❌',
            'status_color': '#ef4444',
            'data': datetime.now().strftime('%d/%m/%Y %H:%M')
        }

# ==================== ROTAS ====================
@app.route('/')
def home():
    return render_template('index.html', planos=PLANOS)

@app.route('/planos')
def planos():
    return render_template('planos.html', planos=PLANOS)

@app.route('/politicas')
def politicas():
    return render_template('politicas.html')

@app.route('/gerar-chave-teste', methods=['GET', 'POST'])
def gerar_chave_teste():
    mensagem = None
    erro = None
    chave_gerada = None
    ip = obter_ip()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        cpf = request.form.get('cpf')
        cnpj = request.form.get('cnpj')
        cep = request.form.get('cep')
        
        pode, msg = pode_gerar_teste(cpf, cnpj, email, cep, ip)
        
        if not pode:
            erro = msg
        else:
            chave_gerada = gerar_chave_unica()
            registrar_teste(cpf, cnpj, email, cep, ip, chave_gerada)
            CHAVES_TESTE[chave_gerada] = {
                'usos': 0,
                'max_usos': 1,
                'dias': 7,
                'descricao': f'Teste para {nome}',
                'dono': {'cpf': cpf, 'cnpj': cnpj, 'email': email, 'cep': cep, 'ip': ip}
            }
            mensagem = f"✅ Chave gerada com sucesso! Guarde-a: {chave_gerada}"
    
    return render_template('gerar_chave.html', mensagem=mensagem, erro=erro, chave_gerada=chave_gerada)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        chave_teste = request.form.get('chave_teste', '').strip()
        
        # Tentar usar chave de teste
        if chave_teste and chave_teste in CHAVES_TESTE:
            chave_info = CHAVES_TESTE[chave_teste]
            if chave_info['usos'] >= chave_info['max_usos']:
                flash('❌ Chave de teste já utilizada', 'error')
            else:
                CHAVES_TESTE[chave_teste]['usos'] += 1
                session['usuario_id'] = 999
                session['usuario_nome'] = chave_info['descricao'].replace('Teste para ', '')
                session['usuario_email'] = chave_info['dono']['email'] or f"teste_{chave_teste}@temp.com"
                session['plano'] = 'trial'
                session['tipo'] = 'teste'
                session['status'] = 'ativo'
                session['data_expiracao'] = (datetime.now() + timedelta(days=chave_info['dias'])).isoformat()
                session['analises_restantes'] = LIMITE_ANALISES_TESTE
                analises_teste_contador[session['usuario_email']] = 0
                flash(f'✅ Teste gratuito de {chave_info["dias"]} dias ativado! Você tem {LIMITE_ANALISES_TESTE} análises.', 'success')
                return redirect(url_for('dashboard'))
        
        # Login normal
        if email in USUARIOS and USUARIOS[email]['senha'] == hash_senha(senha):
            usuario = USUARIOS[email]
            
            # Verificar bloqueio
            if usuario.get('status') == 'bloqueado':
                flash('❌ Sua conta está bloqueada. Renove seu plano.', 'error')
            elif datetime.fromisoformat(usuario['data_expiracao']) < datetime.now():
                flash('❌ Sua assinatura expirou. Renove seu plano.', 'error')
                USUARIOS[email]['status'] = 'bloqueado'
            else:
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                session['usuario_email'] = email
                session['plano'] = usuario['plano']
                session['tipo'] = 'pago'
                session['status'] = 'ativo'
                session['data_expiracao'] = usuario['data_expiracao']
                session['analises_restantes'] = usuario.get('analises_restantes', 999999)
                return redirect(url_for('dashboard'))
        else:
            flash('❌ E-mail ou senha inválidos', 'error')
    
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        if email in USUARIOS:
            flash('E-mail já cadastrado', 'error')
        else:
            novo_id = max([u['id'] for u in USUARIOS.values()] + [0]) + 1
            USUARIOS[email] = {
                'id': novo_id,
                'nome': request.form.get('nome'),
                'senha': hash_senha(request.form.get('senha')),
                'plano': 'trial',
                'empresa': request.form.get('empresa'),
                'cpf': request.form.get('cpf_cnpj'),
                'cnpj': request.form.get('cpf_cnpj'),
                'cep': request.form.get('cep'),
                'telefone': request.form.get('telefone'),
                'data_expiracao': (datetime.now() + timedelta(days=7)).isoformat(),
                'status': 'ativo',
                'tipo': 'teste',
                'analises_restantes': LIMITE_ANALISES_TESTE
            }
            flash('Cadastro realizado! Faça login.', 'success')
            return redirect(url_for('login'))
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', 
                          nome=session.get('usuario_nome'),
                          email=session.get('usuario_email'),
                          plano=session.get('plano'),
                          tipo=session.get('tipo'),
                          analises_restantes=session.get('analises_restantes', 'Ilimitado'),
                          expiracao=session.get('data_expiracao'),
                          status=session.get('status'))

@app.route('/api/analisar', methods=['POST'])
@login_required
def analisar():
    # Verificar se usuário não está bloqueado
    if session.get('status') == 'bloqueado':
        return jsonify({'error': 'Conta bloqueada. Renove seu plano.', 'bloqueado': True, 'redirect': '/planos'}), 403
    
    tipo = session.get('tipo')
    email = session.get('usuario_email')
    
    # Verificar expiração
    data_expiracao = session.get('data_expiracao')
    if data_expiracao and datetime.fromisoformat(data_expiracao) < datetime.now():
        session['status'] = 'bloqueado'
        return jsonify({'error': 'Assinatura expirada. Renove seu plano.', 'bloqueado': True, 'redirect': '/planos'}), 403
    
    # Verificar análises restantes para usuário teste
    if tipo == 'teste':
        analises_restantes = session.get('analises_restantes', 0)
        if analises_restantes <= 0:
            session['status'] = 'bloqueado'
            return jsonify({'error': 'Seu teste gratuito acabou! Adquira um plano para continuar.', 'bloqueado': True, 'redirect': '/planos'}), 403
        
        # Decrementar análises restantes
        session['analises_restantes'] = analises_restantes - 1
        analises_teste_contador[email] = analises_teste_contador.get(email, 0) + 1
    
    if 'pdf' not in request.files:
        return jsonify({'error': 'Nenhum arquivo'}), 400
    
    arquivo = request.files['pdf']
    if not arquivo.filename.endswith('.pdf'):
        return jsonify({'error': 'Formato inválido. Apenas PDF'}), 400
    
    # Simular tempo de análise
    tempo_analise = random.randint(20, 35)
    time.sleep(tempo_analise)
    
    arquivo_bytes = arquivo.read()
    hash_pdf = hashlib.sha256(arquivo_bytes).hexdigest()
    caminho = os.path.join(UPLOAD_FOLDER, f"{hash_pdf[:16]}.pdf")
    with open(caminho, 'wb') as f:
        f.write(arquivo_bytes)
    
    resultado = analisar_pdf(caminho)
    analise_id = str(uuid.uuid4())
    ANALISES[analise_id] = {
        'id': analise_id,
        'usuario': session.get('usuario_email'),
        'arquivo': arquivo.filename,
        'resultado': resultado,
        'data': datetime.now().isoformat()
    }
    os.remove(caminho)
    
    return jsonify({
        'success': True,
        'id': analise_id,
        'status': resultado['status'],
        'status_icon': resultado['status_icon'],
        'status_color': resultado['status_color'],
        'score': resultado['score'],
        'data': resultado['data'],
        'analises_restantes': session.get('analises_restantes', 'Ilimitado')
    })

@app.route('/api/historico')
@login_required
def obter_historico():
    usuario = session.get('usuario_email')
    historico = []
    for d in ANALISES.values():
        if d['usuario'] == usuario:
            historico.append({
                'id': d['id'],
                'arquivo': d['arquivo'],
                'status': d['resultado']['status'],
                'score': d['resultado']['score'],
                'data': d['resultado']['data']
            })
    return jsonify(historico)

@app.route('/api/usuario')
@login_required
def obter_usuario():
    return jsonify({
        'nome': session.get('usuario_nome'),
        'email': session.get('usuario_email'),
        'plano': session.get('plano'),
        'tipo': session.get('tipo'),
        'status': session.get('status'),
        'analises_restantes': session.get('analises_restantes', 'Ilimitado'),
        'expiracao': session.get('data_expiracao')
    })

@app.route('/checkout/<plano_id>')
def checkout(plano_id):
    if plano_id not in PLANOS:
        return redirect(url_for('planos'))
    return render_template('checkout.html', 
                          plano=PLANOS[plano_id], 
                          plano_id=plano_id,
                          public_key=HYPERCASH_PUBLIC_KEY)

@app.route('/api/criar-pagamento', methods=['POST'])
def criar_pagamento():
    data = request.json
    plano_id = data.get('plano')
    metodo = data.get('metodo')
    email = data.get('email')
    nome = data.get('nome')
    cpf = data.get('cpf')
    
    if plano_id not in PLANOS:
        return jsonify({'error': 'Plano inválido'}), 400
    
    plano = PLANOS[plano_id]
    
    # Atualizar usuário
    if email in USUARIOS:
        USUARIOS[email]['plano'] = plano_id
        USUARIOS[email]['data_expiracao'] = (datetime.now() + timedelta(days=plano['dias'])).isoformat()
        USUARIOS[email]['status'] = 'ativo'
        USUARIOS[email]['tipo'] = 'pago'
        USUARIOS[email]['analises_restantes'] = plano['validacoes']
    else:
        novo_id = max([u['id'] for u in USUARIOS.values()] + [0]) + 1
        USUARIOS[email] = {
            'id': novo_id,
            'nome': nome,
            'senha': hash_senha(uuid.uuid4().hex[:8]),
            'plano': plano_id,
            'empresa': data.get('empresa', ''),
            'cpf': cpf,
            'cnpj': '',
            'cep': data.get('cep', ''),
            'telefone': data.get('telefone', ''),
            'data_expiracao': (datetime.now() + timedelta(days=plano['dias'])).isoformat(),
            'status': 'ativo',
            'tipo': 'pago',
            'analises_restantes': plano['validacoes']
        }
    
    # Simular pagamento (modo demo até HyperCash liberar)
    if metodo == 'pix':
        pix_code = f"00020101021226930014BR.GOV.BCB.PIX2572pix-h.hypercashbrasil.com.br/qr/v2/{uuid.uuid4().hex[:16]}"
        return jsonify({'success': True, 'pix_code': pix_code, 'message': '✅ Pagamento via PIX gerado!'})
    else:
        return jsonify({'success': True, 'transaction_id': f"demo_{uuid.uuid4().hex[:16]}", 'redirect': '/dashboard', 'message': '✅ Pagamento aprovado!'})

@app.route('/api/webhook/hypercash', methods=['POST'])
def webhook_hypercash():
    print(f"Webhook recebido: {request.json}")
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("="*50)
    print("🚀 SPACE-DOCX - Servidor rodando")
    print("📍 http://localhost:5000")
    print("="*50)
    app.run(host='0.0.0.0', port=10000, debug=True)
