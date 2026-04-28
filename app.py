from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'teste-secret-key'

@app.route('/')
def home():
    return "<h1>Space-Docx Funcionando!</h1><p>Servidor online. <a href='/planos'>Ver Planos</a></p>"

@app.route('/planos')
def planos():
    return "<h1>Planos Space-Docx</h1><p>✅ Básico: R$ 49/mês<br>✅ Profissional: R$ 149/mês<br>✅ Enterprise: R$ 349/mês</p><a href='/'>Voltar</a>"

@app.route('/login')
def login():
    return "<h1>Login Space-Docx</h1><p>Área de login em desenvolvimento.</p>"

@app.route('/dashboard')
def dashboard():
    return "<h1>Dashboard</h1><p>Bem-vindo ao Space-Docx!</p>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
