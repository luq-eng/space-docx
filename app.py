from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
import pikepdf
import os
import hashlib
import re
import uuid
import random
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'space-docx-secret-key-2026'
CORS(app)

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== LIMITES E CONTROLES ====================
# Armazenar chaves de teste já usadas
chaves_teste_usadas_ip = defaultdict(list)      # {ip: [chaves]}
chaves_teste_usadas_cnpj = defaultdict(list)    # {cnpj: [chaves]}
chaves_teste_usadas_email = defaultdict(list)   # {email: [chaves]}

# Chaves de teste válidas
CHAVES_TESTE = {
    'FREE-TRIAL-7DAYS': {
        'usos': 0,
        'max_usos': 100,  # Max geral, mas cada IP/CNPJ/EMAIL só pode usar 1 vez
        'dias': 7,
        'descricao': 'Teste gratuito de 7 dias'
    }
}

# Limite de análises por IP (após o teste)
LIMITE_ANALISES_IP = 5  # 5 análises por dia para usuários sem plano

analises_por_ip = defaultdict(list)  # {ip: [timestamps]}

def obter_ip():
    """Obtém o IP do cliente"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr or '127.0.0.1'

def pode_usar_chave_teste(ip, cnpj, email):
    """Verifica se IP/CNPJ/EMAIL já usou chave de teste"""
    # Verificar IP
    if ip in chaves_teste_usadas_ip and len(chaves_teste_usadas_ip[ip]) > 0:
        return False, "Este IP já utilizou o teste gratuito"
    
    # Verificar CNPJ (se informado)
    if cnpj and cnpj in chaves_teste_usadas_cnpj and len(chaves_teste_usadas_cnpj[cnpj]) > 0:
        return False, "Este CNPJ já utilizou o teste gratuito"
    
    # Verificar EMAIL (se informado)
    if email and email in chaves_teste_usadas_email and len(chaves_teste_usadas_email[email]) > 0:
        return False, "Este e-mail já utilizou o teste gratuito"
    
    return True, "OK"

def registrar_uso_teste(ip, cnpj, email, chave):
    """Registra que IP/CNPJ/EMAIL usou a chave de teste"""
    chaves_teste_usadas_ip[ip].append({'chave': chave, 'data': datetime.now().isoformat()})
    if cnpj:
        chaves_teste_usadas_cnpj[cnpj].append({'chave': chave, 'data': datetime.now().isoformat()})
    if email:
        chaves_teste_usadas_email[email].append({'chave': chave, 'data': datetime.now().isoformat()})

def gerar_chave_unica():
    """Gera uma chave única para teste"""
    return f"FREE-{uuid.uuid4().hex[:8].upper()}"

def verificar_limite_analise_ip(ip):
    """Verifica se o IP já excedeu o limite de análises (para usuários sem plano)"""
    hoje = datetime.now().date()
    # Remover análises antigas (mais de 1 dia)
    analises_por_ip[ip] = [ts for ts in analises_por_ip[ip] if datetime.fromtimestamp(ts).date() == hoje]
    
    if len(analises_por_ip[ip]) >= LIMITE_ANALISES_IP:
        return False, f"Limite diário de {LIMITE_ANALISES_IP} análises atingido. Adquira um plano para continuar."
    return True, "OK"

def registrar_analise_ip(ip):
    """Registra uma análise para o IP"""
    analises_por_ip[ip].append(datetime.now().timestamp())

# ==================== BANCO DE DADOS SIMULADO ====================
USUARIOS = {
    'admin@space-docx.com': {
        'id': 1,
        'nome': 'Administrador',
        'senha': hashlib.sha256('Admin@2026'.encode()).hexdigest(),
        'plano': 'enterprise',
        'empresa': 'Space-Docx',
        'cnpj': '00.000.000/0001-00',
        'telefone': '(11) 99999-9999',
        'data_expiracao': (datetime.now() + timedelta(days=365)).isoformat()
    }
}

ANALISES = {}

PLANOS = {
    'trial': {'id': 1, 'nome': 'Teste Grátis', 'preco': 0, 'dias': 7, 'validacoes': 5},
    'basico': {'id': 2, 'nome': 'Básico', 'preco': 49, 'dias': 30, 'validacoes': 50},
    'profissional': {'id': 3, 'nome': 'Profissional', 'preco': 149, 'dias': 30, 'validacoes': 300},
    'enterprise': {'id': 4, 'nome': 'Enterprise', 'preco': 349, 'dias': 30, 'validacoes': 999999}
}

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def analisar_pdf(caminho):
    """Análise real do PDF com simulação de tempo"""
    try:
        with pikepdf.Pdf.open(caminho) as pdf:
            producer = str(pdf.docinfo.get('/Producer', '')) if pdf.docinfo.get('/Producer') else ''
            creator = str(pdf.docinfo.get('/Creator', '')) if pdf.docinfo.get('/Creator') else ''
            texto = f"{producer} {creator}".lower()
            score = 70
            status = 'VERIFICAR'
            status_icon = '🟡'
            status_color = '#f59e0b'
            rastros = []
            
            if any(f in texto for f in ['canva', 'photoshop', 'illustrator', 'corel', 'gimp']):
                score = 0
                status = 'FRAUDE'
                status_icon = '🔴'
                status_color = '#ef4444'
                rastros.append('❌ Documento criado/editado em editor gráfico - FRAUDE')
            elif any(f in texto for f in ['quadient', 'gmc', 'inspire']):
                score = 100
                status = 'AUTÊNTICO'
                status_icon = '🟢'
                status_color = '#22c55e'
                rastros.append('✅ Documento bancário legítimo (Quadient/GMC)')
            elif any(f in texto for f in ['itau', 'bradesco', 'santander', 'caixa', 'nubank']):
                score = 95
                status = 'AUTÊNTICO'
                status_icon = '🟢'
                status_color = '#22c55e'
                rastros.append(f'✅ Documento do banco {creator if creator else producer} - AUTÊNTICO')
            elif any(f in texto for f in ['pikepdf', 'exiftool']):
                score = 30
                status = 'SUSPEITO'
                status_icon = '🟠'
                status_color = '#f97316'
                rastros.append('⚠️ Metadados editados - SUSPEITO')
            elif any(f in texto for f in ['ilovepdf', 'smallpdf', 'aspose', 'itext']):
                score = 25
                status = 'SUSPEITO'
                status_icon = '🟠'
                status_color = '#f97316'
                rastros.append('⚠️ Documento processado online - SUSPEITO')
            else:
                rastros.append('⚠️ Ferramenta de criação não identificada')
            
            if not pdf.is_linearized:
                score -= 10
                rastros.append('⚠️ PDF não linearizado (recomendado para documentos oficiais)')
            else:
                rastros.append('✅ PDF linearizado (Fast Web View ativo)')
            
            if score < 0:
                score = 0
            
            return {
                'score': score,
                'status': status,
                'status_icon': status_icon,
                'status_color': status_color,
                'rastros': rastros,
                'metadados': {'producer': producer or 'N/A', 'creator': creator or 'N/A'},
                'estrutura': {'linearized': pdf.is_linearized, 'pages': len(pdf.pages), 'version': str(pdf.pdf_version)}
            }
    except Exception as e:
        return {
            'score': 0,
            'status': 'ERRO',
            'status_icon': '❌',
            'status_color': '#ef4444',
            'rastros': [f'Erro na análise: {str(e)}'],
            'metadados': {},
            'estrutura': {}
        }

# ==================== ROTAS PÚBLICAS ====================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/planos')
def planos():
    return render_template('planos.html', planos=PLANOS)

@app.route('/politicas')
def politicas():
    return render_template('politicas.html')

@app.route('/gerar-chave-teste', methods=['GET', 'POST'])
def gerar_chave_teste():
    """Página para gerar chave de teste gratuito"""
    mensagem = None
    erro = None
    chave_gerada = None
    ip = obter_ip()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        cnpj = request.form.get('cnpj')
        telefone = request.form.get('telefone')
        
        # Verificar se já usou teste
        pode, msg = pode_usar_chave_teste(ip, cnpj, email)
        
        if not pode:
            erro = msg
        else:
            # Gerar chave única
            chave_gerada = gerar_chave_unica()
            
            # Registrar uso
            registrar_uso_teste(ip, cnpj, email, chave_gerada)
            
            # Armazenar chave válida
            CHAVES_TESTE[chave_gerada] = {
                'usos': 0,
                'max_usos': 1,
                'dias': 7,
                'descricao': f'Teste gratuito para {nome}',
                'email': email,
                'cnpj': cnpj,
                'ip': ip,
                'criada_em': datetime.now().isoformat()
            }
            
            mensagem = f"Chave de teste gerada com sucesso! Sua chave: {chave_gerada}"
    
    return render_template('gerar_chave.html', mensagem=mensagem, erro=erro, chave_gerada=chave_gerada)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        chave = request.form.get('chave', '').strip()
        ip = obter_ip()
        
        # Tentar usar chave de teste
        if chave and chave in CHAVES_TESTE:
            chave_info = CHAVES_TESTE[chave]
            
            # Verificar se a chave ainda tem usos
            if chave_info['usos'] >= chave_info['max_usos']:
                flash('Chave de teste já utilizada', 'error')
            else:
                # Verificar se IP/CNPJ/EMAIL já usou teste (apenas para a chave padrão)
                if chave == 'FREE-TRIAL-7DAYS':
                    pode, msg = pode_usar_chave_teste(ip, None, email)
                    if not pode:
                        flash(msg, 'error')
                        return redirect(url_for('login'))
                    registrar_uso_teste(ip, None, email, chave)
                
                # Atualizar usos da chave
                CHAVES_TESTE[chave]['usos'] += 1
                
                # Criar sessão de teste
                session['usuario_id'] = 999
                session['usuario_nome'] = 'Usuário Teste'
                session['usuario_email'] = email or 'teste@space-docx.com'
                session['plano'] = 'trial'
                session['tipo'] = 'teste'
                session['data_expiracao'] = (datetime.now() + timedelta(days=chave_info['dias'])).isoformat()
                session['analises_restantes'] = 5
                
                flash(f'Teste gratuito de {chave_info["dias"]} dias ativado!', 'success')
                return redirect(url_for('dashboard'))
        
        # Login normal
        if email in USUARIOS and USUARIOS[email]['senha'] == hash_senha(senha):
            session['usuario_id'] = USUARIOS[email]['id']
            session['usuario_nome'] = USUARIOS[email]['nome']
            session['usuario_email'] = email
            session['plano'] = USUARIOS[email]['plano']
            session['tipo'] = 'pago'
            session['data_expiracao'] = USUARIOS[email]['data_expiracao']
            session['analises_restantes'] = 999999
            return redirect(url_for('dashboard'))
        
        flash('E-mail ou senha inválidos', 'error')
    
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
                'cnpj': request.form.get('cnpj'),
                'telefone': request.form.get('telefone'),
                'data_expiracao': (datetime.now() + timedelta(days=7)).isoformat()
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
                          expiracao=session.get('data_expiracao'))

@app.route('/api/analisar', methods=['POST'])
@login_required
def analisar():
    # Verificar limite de análises para usuários teste
    if session.get('tipo') == 'teste':
        analises_restantes = session.get('analises_restantes', 0)
        if analises_restantes <= 0:
            return jsonify({'error': 'Seu teste gratuito expirou. Adquira um plano para continuar.'}), 403
        session['analises_restantes'] = analises_restantes - 1
    
    # Verificar limite por IP (para todos)
    ip = obter_ip()
    pode, msg = verificar_limite_analise_ip(ip)
    if not pode:
        return jsonify({'error': msg}), 429
    
    if 'pdf' not in request.files:
        return jsonify({'error': 'Nenhum arquivo'}), 400
    
    arquivo = request.files['pdf']
    if not arquivo.filename.endswith('.pdf'):
        return jsonify({'error': 'Formato inválido. Apenas PDF'}), 400
    
    # Simular tempo de análise (30-45 segundos)
    tempo_analise = random.randint(30, 45)
    
    arquivo_bytes = arquivo.read()
    hash_pdf = hashlib.sha256(arquivo_bytes).hexdigest()
    caminho = os.path.join(UPLOAD_FOLDER, f"{hash_pdf[:16]}.pdf")
    with open(caminho, 'wb') as f:
        f.write(arquivo_bytes)
    
    # Registrar análise para IP
    registrar_analise_ip(ip)
    
    # Simular processamento com tempo real
    time.sleep(tempo_analise)
    
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
        'status': resultado['status'],
        'status_icon': resultado['status_icon'],
        'status_color': resultado['status_color'],
        'score': resultado['score'],
        'rastros': resultado['rastros'],
        'metadados': resultado['metadados'],
        'estrutura': resultado['estrutura'],
        'data': datetime.now().strftime('%d/%m/%Y %H:%M'),
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
                'data': d['data']
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
        'analises_restantes': session.get('analises_restantes', 'Ilimitado'),
        'expiracao': session.get('data_expiracao')
    })

@app.route('/checkout')
@login_required
def checkout():
    plano_id = request.args.get('plano', 'profissional')
    return render_template('checkout.html', 
                          plano=PLANOS.get(plano_id, PLANOS['profissional']),
                          plano_id=plano_id)

@app.route('/api/criar-pagamento', methods=['POST'])
@login_required
def criar_pagamento():
    data = request.json
    plano_id = data.get('plano')
    
    if plano_id not in PLANOS:
        return jsonify({'error': 'Plano inválido'}), 400
    
    plano = PLANOS[plano_id]
    usuario_email = session.get('usuario_email')
    
    if usuario_email in USUARIOS:
        USUARIOS[usuario_email]['plano'] = plano_id
        USUARIOS[usuario_email]['data_expiracao'] = (datetime.now() + timedelta(days=plano['dias'])).isoformat()
        session['plano'] = plano_id
        session['tipo'] = 'pago'
        session['data_expiracao'] = USUARIOS[usuario_email]['data_expiracao']
        session['analises_restantes'] = 999999
    
    return jsonify({
        'success': True,
        'message': f'Plano {plano["nome"]} ativado com sucesso!',
        'redirect': '/dashboard'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
