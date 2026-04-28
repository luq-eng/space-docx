from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
import pikepdf
import os
import hashlib
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'space-docx-secret-key-2026'
CORS(app)

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== BANCO DE DADOS SIMULADO ====================
USUARIOS = {
    'admin@space-docx.com': {
        'id': 1,
        'nome': 'Administrador',
        'senha': hashlib.sha256('Admin@2026'.encode()).hexdigest(),
        'plano': 'enterprise',
        'empresa': 'Space-Docx',
        'data_expiracao': (datetime.now() + timedelta(days=365)).isoformat()
    }
}

ANALISES = {}
CHAVES_TESTE = {'FREE-TRIAL-7DAYS': {'usos': 0, 'max_usos': 10, 'dias': 7}}

PLANOS = {
    'trial': {'nome': 'Teste Grátis', 'preco': 0, 'dias': 7, 'validacoes': 5},
    'basico': {'nome': 'Básico', 'preco': 49, 'dias': 30, 'validacoes': 50},
    'profissional': {'nome': 'Profissional', 'preco': 149, 'dias': 30, 'validacoes': 300},
    'enterprise': {'nome': 'Enterprise', 'preco': 349, 'dias': 30, 'validacoes': 999999}
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
    try:
        with pikepdf.Pdf.open(caminho) as pdf:
            producer = str(pdf.docinfo.get('/Producer', '')) if pdf.docinfo.get('/Producer') else ''
            creator = str(pdf.docinfo.get('/Creator', '')) if pdf.docinfo.get('/Creator') else ''
            texto = f"{producer} {creator}".lower()
            score = 70
            status = 'VERIFICAR'
            rastros = []
            if any(f in texto for f in ['canva', 'photoshop', 'illustrator', 'corel']):
                score = 0
                status = 'FRAUDE'
                rastros.append('❌ Documento criado em editor gráfico - FRAUDE')
            elif any(f in texto for f in ['quadient', 'gmc', 'inspire', 'itau', 'bradesco']):
                score = 100
                status = 'AUTÊNTICO'
                rastros.append('✅ Documento bancário legítimo')
            elif any(f in texto for f in ['pikepdf', 'exiftool']):
                score = 30
                status = 'SUSPEITO'
                rastros.append('⚠️ Metadados editados - SUSPEITO')
            else:
                rastros.append('⚠️ Ferramenta não identificada')
            if not pdf.is_linearized:
                score -= 10
                rastros.append('⚠️ PDF não linearizado')
            return {
                'score': max(0, min(100, score)),
                'status': status,
                'rastros': rastros,
                'metadados': {'producer': producer or 'N/A', 'creator': creator or 'N/A'},
                'estrutura': {'linearized': pdf.is_linearized, 'pages': len(pdf.pages)}
            }
    except Exception as e:
        return {'score': 0, 'status': 'ERRO', 'rastros': [str(e)], 'metadados': {}, 'estrutura': {}}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/planos')
def planos():
    return render_template('planos.html', planos=PLANOS)

@app.route('/politicas')
def politicas():
    return render_template('politicas.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        chave = request.form.get('chave', '')
        
        if chave and chave in CHAVES_TESTE:
            if CHAVES_TESTE[chave]['usos'] < CHAVES_TESTE[chave]['max_usos']:
                CHAVES_TESTE[chave]['usos'] += 1
                session['usuario_id'] = 999
                session['usuario_nome'] = 'Usuário Teste'
                session['usuario_email'] = 'teste@space-docx.com'
                session['plano'] = 'trial'
                session['data_expiracao'] = (datetime.now() + timedelta(days=CHAVES_TESTE[chave]['dias'])).isoformat()
                return redirect(url_for('dashboard'))
        
        if email in USUARIOS and USUARIOS[email]['senha'] == hash_senha(senha):
            session['usuario_id'] = USUARIOS[email]['id']
            session['usuario_nome'] = USUARIOS[email]['nome']
            session['usuario_email'] = email
            session['plano'] = USUARIOS[email]['plano']
            session['data_expiracao'] = USUARIOS[email]['data_expiracao']
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
                          plano=session.get('plano'))

@app.route('/api/analisar', methods=['POST'])
@login_required
def analisar():
    if 'pdf' not in request.files:
        return jsonify({'error': 'Nenhum arquivo'}), 400
    arquivo = request.files['pdf']
    if not arquivo.filename.endswith('.pdf'):
        return jsonify({'error': 'Formato inválido'}), 400
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
        'status': resultado['status'],
        'score': resultado['score'],
        'rastros': resultado['rastros'],
        'metadados': resultado['metadados'],
        'estrutura': resultado['estrutura'],
        'data': datetime.now().strftime('%d/%m/%Y %H:%M')
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
        'plano': session.get('plano')
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
    
    # Atualizar assinatura do usuário
    if usuario_email in USUARIOS:
        USUARIOS[usuario_email]['plano'] = plano_id
        USUARIOS[usuario_email]['data_expiracao'] = (datetime.now() + timedelta(days=plano['dias'])).isoformat()
        session['plano'] = plano_id
        session['data_expiracao'] = USUARIOS[usuario_email]['data_expiracao']
    
    return jsonify({
        'success': True,
        'message': f'Plano {plano["nome"]} ativado com sucesso!',
        'redirect': '/dashboard'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
