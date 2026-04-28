import os
import re
import uuid
import time
import hmac
import json
import requests
import hashlib
from flask import *
from flask_cors import CORS
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.utils import secure_filename

# 1. CONFIGURAÇÕES GERAIS
# ----------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'uma-chave-muito-segura-para-sessao')
CORS(app)

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 2. CONTROLE DE ACESSO (BANCO DE DADOS SIMULADO)
# ----------------------------------------------------------------------
# Armazena informações de cada usuário
USUARIOS = {
    'admin@space-docx.com': {
        'id': 1,
        'nome': 'Administrador',
        'senha': hashlib.sha256('Admin@2026'.encode()).hexdigest(),
        'plano': 'enterprise',
        'empresa': 'Space-Docx',
        'cpf_cnpj': '00.000.000/0001-00',
        'cep': '00000-000',
        'telefone': '(11) 99999-9999',
        'data_expiracao': (datetime.now() + timedelta(days=365)).isoformat(),
        'status': 'ativo'
    }
}
# Armazena tentativas de teste por identificador (CPF, CNPJ, CEP, IP)
testes_utilizados = defaultdict(list)
analises_realizadas = defaultdict(list)

def obter_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr or '127.0.0.1'

def pode_usar_teste(cpf_cnpj, cep, ip, email):
    """Verifica se um novo teste pode ser gerado para os dados fornecidos"""
    for chave in [cpf_cnpj, cep, ip, email]:
        if chave and chave in testes_utilizados and len(testes_utilizados[chave]) > 0:
            return False, f"O teste gratuito já foi utilizado para este(a) {chave}."
    return True, "OK"

def registrar_teste(cpf_cnpj, cep, ip, email, chave):
    """Registra o uso do teste para todos os identificadores"""
    for chave_id in [cpf_cnpj, cep, ip, email]:
        if chave_id:
            testes_utilizados[chave_id].append({'chave': chave, 'data': datetime.now().isoformat()})

# 3. FUNÇÕES AUXILIARES E ANÁLISE DE PDF
# ----------------------------------------------------------------------
def analisar_pdf_simplificado(caminho_pdf):
    """Versão simplificada para o usuário final, sem detalhes técnicos"""
    # Simula uma análise de 30 a 45 segundos
    time.sleep(random.randint(30, 45))
    resultado_base = {
        "score": random.randint(0, 100),
        "status": random.choice(["AUTÊNTICO", "FRAUDE", "SUSPEITO"]),
        "mensagem": "Análise concluída com sucesso."
    }
    # Lógica real (mantida do código anterior, mas sem exibir os rastros ao usuário)
    # ... (aqui você mantém a lógica que já tem usando pikepdf, mas sem retornar os rastros)
    return resultado_base

# 4. ROTAS DO SITE (APENAS AS PRINCIPAIS E MODIFICADAS)
# ----------------------------------------------------------------------
@app.route('/gerar-chave-teste', methods=['GET', 'POST'])
def gerar_chave_teste():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        cpf_cnpj = request.form.get('cpf_cnpj')
        cep = request.form.get('cep')
        ip = obter_ip()

        pode, mensagem = pode_usar_teste(cpf_cnpj, cep, ip, email)
        if not pode:
            flash(mensagem, 'error')
            return redirect(url_for('gerar_chave_teste'))

        chave_gerada = f"FREE-{uuid.uuid4().hex[:8].upper()}"
        registrar_teste(cpf_cnpj, cep, ip, email, chave_gerada)

        # Armazenar a chave válida
        from app import CHAVES_TESTE # Importação local para evitar circularidade
        CHAVES_TESTE[chave_gerada] = {
            'usos': 0,
            'max_usos': 1,
            'dias': 7,
            'descricao': f'Teste para {nome}',
            'dono': {'cpf_cnpj': cpf_cnpj, 'cep': cep, 'email': email, 'ip': ip}
        }
        flash(f'Chave gerada com sucesso: {chave_gerada}', 'success')
        return redirect(url_for('login'))
    return render_template('gerar_chave.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        chave_teste = request.form.get('chave_teste', '').strip()

        if chave_teste and chave_teste in CHAVES_TESTE:
            # Lógica de ativação da chave de teste...
            chave_info = CHAVES_TESTE[chave_teste]
            if chave_info['usos'] < chave_info['max_usos']:
                # ... ativa o teste
                pass

        # Lógica de login normal...
    return render_template('login.html')

# ROTA DE CHECKOUT LIVRE E CRIAÇÃO DE PAGAMENTO
@app.route('/checkout/<plano_id>')
def checkout(plano_id):
    if plano_id not in PLANOS:
        return redirect(url_for('planos'))
    return render_template('checkout.html', plano=PLANOS[plano_id], plano_id=plano_id)

@app.route('/api/criar-pagamento', methods=['POST'])
def criar_pagamento():
    data = request.json
    plano_id = data.get('plano')
    metodo = data.get('metodo')
    email = data.get('email')
    cpf_cnpj = data.get('cpf_cnpj')

    if plano_id not in PLANOS:
        return jsonify({'error': 'Plano inválido'}), 400

    plano = PLANOS[plano_id]

    # Integração REAL com a API HyperCash
    # 1. Obter credenciais das variáveis de ambiente
    hypercash_token = os.environ.get('HYPERCASH_TOKEN')
    if not hypercash_token:
        return jsonify({'error': 'Gateway de pagamento não configurado'}), 500

    # 2. Construir o payload da transação
    transaction_payload = {
        "amount": plano['preco_centavos'],
        "currency": "BRL",
        "payment_method": metodo, # 'credit_card' ou 'pix'
        "customer": {
            "email": email,
            "document": cpf_cnpj
        },
        "metadata": {
            "plano": plano_id,
            "plano_nome": plano['nome']
        }
    }

    # 3. Adicionar dados do cartão, se for o caso
    if metodo == 'credit_card':
        transaction_payload["card"] = {
            "number": data.get('card_number'),
            "holder_name": data.get('card_holder'),
            "exp_month": data.get('card_exp_month'),
            "exp_year": data.get('card_exp_year'),
            "cvv": data.get('card_cvv')
        }

    # 4. Fazer a chamada para a API
    auth_string = base64.b64encode(f"x:{hypercash_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{HYPERCASH_API_URL}/transactions",
            headers=headers,
            json=transaction_payload,
            timeout=30
        )
        response_data = response.json()

        if response.status_code in [200, 201]:
            # Pagamento aprovado! Ativar o plano para o usuário.
            # 5. Salvar/Atualizar o usuário no seu sistema (USUARIOS)
            # ... (código para criar ou atualizar a conta do cliente)
            return jsonify({'success': True, 'transaction_id': response_data.get('id'), 'redirect': '/dashboard'})
        else:
            return jsonify({'success': False, 'error': response_data.get('message', 'Falha no pagamento')}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro de comunicação: {str(e)}'}), 500

# ... (as demais rotas permanecem iguais, com pequenos ajustes)
