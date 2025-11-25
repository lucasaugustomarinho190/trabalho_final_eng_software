from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc
import os

# Configuração do App e Banco de Dados
app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'barbearia.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS ---
class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    def to_json(self): return {"id": self.id, "nome": self.nome, "cpf": self.cpf, "telefone": self.telefone, "email": self.email}

class Barbeiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    def to_json(self): return {"id": self.id, "nome": self.nome, "cpf": self.cpf, "telefone": self.telefone, "email": self.email}

class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    duracao_minutos = db.Column(db.Integer)
    def to_json(self): return {"id": self.id, "nome": self.nome, "preco": self.preco, "duracao_minutos": self.duracao_minutos}

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    quantidade = db.Column(db.Integer)
    fornecedor = db.Column(db.String(100))
    def to_json(self): return {"id": self.id, "nome": self.nome, "preco": self.preco, "quantidade": self.quantidade, "fornecedor": self.fornecedor}

class Agenda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, nullable=False)
    observacoes = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Agendado")
    
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    barbeiro_id = db.Column(db.Integer, db.ForeignKey('barbeiro.id'), nullable=False)
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'), nullable=False)

    cliente = db.relationship('Cliente', backref='agendamentos')
    barbeiro = db.relationship('Barbeiro', backref='agendamentos')
    servico = db.relationship('Servico', backref='agendamentos')

    def to_json(self):
        return {
            "id": self.id, "codigo": f"#{self.id}",
            "data_hora": self.data_hora.isoformat(),
            "status": self.status, "observacoes": self.observacoes,
            "cliente_nome": self.cliente.nome, "cliente_cpf": self.cliente.cpf,
            "barbeiro_nome": self.barbeiro.nome, "servico_nome": self.servico.nome
        }

# --- ROTAS ---

@app.route('/dashboard-data', methods=['GET'])
def get_dashboard_data():
    periodo = request.args.get('periodo', 'hoje')
    data_hoje = date.today()
    data_inicio = datetime.combine(data_hoje, datetime.min.time())
    
    if periodo == '7dias': data_inicio = datetime.combine(data_hoje - timedelta(days=7), datetime.min.time())
    elif periodo == 'mes': data_inicio = datetime.combine(data_hoje.replace(day=1), datetime.min.time())
    
    # 1. Faturamento
    faturamento = db.session.query(func.sum(Servico.preco)).join(Agenda, Servico.id == Agenda.servico_id).filter(Agenda.data_hora >= data_inicio).filter(Agenda.status == 'Concluido').scalar() or 0.0

    # 2. Serviços Populares
    servicos_pop = db.session.query(Servico.nome, func.count(Agenda.id)).join(Agenda, Servico.id == Agenda.servico_id).filter(Agenda.data_hora >= data_inicio).filter(Agenda.status == 'Concluido').group_by(Servico.nome).order_by(func.count(Agenda.id).desc()).limit(5).all()
    labels_servicos = [s[0] for s in servicos_pop]
    dados_servicos = [s[1] for s in servicos_pop]

    # 3. Desempenho Barbeiros
    barbeiros_db = db.session.query(Barbeiro.nome, func.count(Agenda.id)).join(Agenda, Barbeiro.id == Agenda.barbeiro_id).filter(Agenda.data_hora >= data_inicio).filter(Agenda.status == 'Concluido').group_by(Barbeiro.nome).all()
    lista_barbeiros = [{"nome": b[0], "cortes": b[1], "avaliacao": 5.0} for b in barbeiros_db]

    # 4. Taxa No-Show
    total = db.session.query(func.count(Agenda.id)).filter(Agenda.data_hora >= data_inicio).scalar() or 1
    cancelados = db.session.query(func.count(Agenda.id)).filter(Agenda.data_hora >= data_inicio, Agenda.status == 'Cancelado').scalar() or 0
    taxa = round((cancelados / total) * 100, 1)

    # 5. Estoque Completo (Ordenado por quantidade crescente)
    todos_produtos = Produto.query.order_by(Produto.quantidade.asc()).all()
    lista_estoque = [{"nome": p.nome, "qtd": p.quantidade} for p in todos_produtos]

    return jsonify({
        "faturamento": faturamento,
        "grafico_labels": labels_servicos,
        "grafico_data": dados_servicos,
        "barbeiros": lista_barbeiros,
        "taxa_noshow": taxa,
        "estoque_baixo": lista_estoque
    })

# CRUD Genérico
@app.route('/<entidade>', methods=['GET', 'POST'])
def gerenciar_entidade(entidade):
    modelo = {'cliente': Cliente, 'barbeiro': Barbeiro, 'servico': Servico, 'produto': Produto}.get(entidade)
    if not modelo: return jsonify({"error": "404"}), 404
    if request.method == 'GET': return jsonify([o.to_json() for o in modelo.query.all()])
    if request.method == 'POST':
        try:
            db.session.add(modelo(**request.json))
            db.session.commit()
            return jsonify({"msg": "ok"}), 201
        except Exception as e: return jsonify({"error": str(e)}), 400

@app.route('/<entidade>/<int:id>', methods=['PUT', 'DELETE'])
def alterar_entidade(entidade, id):
    modelo = {'cliente': Cliente, 'barbeiro': Barbeiro, 'servico': Servico, 'produto': Produto, 'agenda': Agenda}.get(entidade)
    obj = modelo.query.get(id)
    if not obj: return jsonify({"error": "404"}), 404
    if request.method == 'PUT':
        for k, v in request.json.items():
            if k == 'data_hora': v = datetime.strptime(v, '%Y-%m-%d %H:%M')
            setattr(obj, k, v)
        db.session.commit()
        return jsonify(obj.to_json())
    if request.method == 'DELETE':
        db.session.delete(obj)
        db.session.commit()
        return jsonify({"msg": "removido"})

@app.route('/agenda', methods=['GET', 'POST'])
def agenda():
    if request.method == 'GET': return jsonify([a.to_json() for a in Agenda.query.all()])
    if request.method == 'POST':
        d = request.json
        new_ag = Agenda(data_hora=datetime.strptime(d['data_hora'], '%Y-%m-%d %H:%M'), observacoes=d.get('observacoes',''), cliente_id=d['cliente_id'], barbeiro_id=d['barbeiro_id'], servico_id=d['servico_id'])
        if 'status' in d: new_ag.status = d['status']
        db.session.add(new_ag)
        db.session.commit()
        return jsonify(new_ag.to_json()), 201

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=5000)