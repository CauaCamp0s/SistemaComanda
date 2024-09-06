from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from decimal import Decimal

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:140610@localhost/bar2'
app.secret_key = '9b38642251354f1646fa06e7bd64f4eb8ca1072a4c5e6a85'
db = SQLAlchemy(app)

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    pedidos = db.relationship('Pedido', backref='cliente', lazy=True)

class Operador(db.Model):
    __tablename__ = 'operadors'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    pedidos = db.relationship('Pedido', backref='operador', lazy=True)

class Produto(db.Model):
    __tablename__ = 'produtos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    preco = db.Column(db.Numeric(10, 2), nullable=False)

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'))
    operador_id = db.Column(db.Integer, db.ForeignKey('operadors.id'))
    data = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))
    pedidos_produtos = db.relationship('PedidosProdutos', backref='pedido', lazy=True)

class PedidosProdutos(db.Model):
    __tablename__ = 'pedidos_produtos'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'))
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'))
    quantidade = db.Column(db.Integer)

    produto = db.relationship('Produto')

@app.route('/')
def index():
    produtos = Produto.query.all()
    clientes = Cliente.query.all()
    operadores = Operador.query.all()
    return render_template('index.html', produtos=produtos, clientes=clientes, operadores=operadores)

@app.route('/fazer_pedido', methods=['POST'])
def fazer_pedido():
    cliente_nome = request.form['cliente']
    operador_id = request.form['operador']
    produtos = request.form.getlist('produtos')
    quantidades_str = request.form['quantidades']
    quantidades = quantidades_str.split(',')

    if len(produtos) != len(quantidades):
        return "Número de produtos e quantidades não correspondem", 400

    cliente = Cliente.query.filter_by(nome=cliente_nome).first()
    if not cliente:
        cliente = Cliente(nome=cliente_nome)
        db.session.add(cliente)
        db.session.commit()

    cliente_id = cliente.id

    pedido = Pedido(cliente_id=cliente_id, operador_id=operador_id)
    db.session.add(pedido)
    db.session.commit()

    for produto_id, quantidade in zip(produtos, quantidades):
        pedido_produto = PedidosProdutos(pedido_id=pedido.id, produto_id=produto_id, quantidade=int(quantidade))
        db.session.add(pedido_produto)
    db.session.commit()

    return redirect(url_for('imprimir_comanda', pedido_id=pedido.id))

@app.route('/imprimir_comanda/<int:pedido_id>')
def imprimir_comanda(pedido_id):
    try:
        pedido = db.session.query(Pedido).get(pedido_id)
        if not pedido:
            flash('Pedido não encontrado', 'danger')
            return redirect(url_for('pedidos_anteriores'))

        cliente = db.session.query(Cliente).get(pedido.cliente_id)
        operador = db.session.query(Operador).get(pedido.operador_id)

        produtos_pedido = db.session.query(PedidosProdutos).filter_by(pedido_id=pedido.id).all()
        produtos = {p.id: p for p in db.session.query(Produto).all()}

        total = sum(produtos[pedido_produto.produto_id].preco * pedido_produto.quantidade for pedido_produto in produtos_pedido)
        comissao = total * Decimal('0.1')
        total_completo = total + comissao

        total = total.quantize(Decimal('0.01'))
        comissao = comissao.quantize(Decimal('0.01'))
        total_completo = total_completo.quantize(Decimal('0.01'))

        return render_template('comanda.html', pedido=pedido, cliente=cliente, operador=operador,
                               produtos_pedido=produtos_pedido, produtos=produtos, total=total,
                               comissao=comissao, total_completo=total_completo)
    except Exception as e:
        flash(f'Ocorreu um erro ao imprimir a comanda: {str(e)}', 'danger')
        return redirect(url_for('pedidos_anteriores'))

@app.route('/pedidos_anteriores')
def pedidos_anteriores():
    pedidos = Pedido.query.all()
    return render_template('pedidos_anteriores.html', pedidos=pedidos)

@app.route('/cadastrar_produto', methods=['POST'])
def cadastrar_produto():
    nome = request.form.get('nome')
    preco = request.form.get('preco')

    produto_existente = Produto.query.filter_by(nome=nome).first()
    if produto_existente:
        return jsonify({'error': 'Produto já existe'}), 400

    try:
        preco_decimal = Decimal(preco).quantize(Decimal('0.01'))
        novo_produto = Produto(nome=nome, preco=preco_decimal)
        db.session.add(novo_produto)
        db.session.commit()
        return jsonify({'message': 'Produto cadastrado com sucesso'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erro ao cadastrar produto'}), 500

@app.route('/excluir_pedido/<int:pedido_id>', methods=['POST'])
def excluir_pedido(pedido_id):
    try:
        produtos = db.session.query(PedidosProdutos).filter_by(pedido_id=pedido_id).all()
        for produto in produtos:
            db.session.delete(produto)

        pedido = db.session.query(Pedido).get(pedido_id)
        if pedido:
            db.session.delete(pedido)
            db.session.commit()
            flash('A comanda foi excluída com sucesso.', 'success')
        else:
            flash('Comanda não encontrada.', 'error')

    except Exception as e:
        db.session.rollback()
        flash('Ocorreu um erro ao excluir a comanda: {}'.format(str(e)), 'error')

    return redirect(url_for('pedidos_anteriores'))

@app.route('/editar_pedido/<int:pedido_id>', methods=['GET', 'POST'])
def editar_pedido(pedido_id):
    if request.method == 'POST':
        cliente_id = request.form.get('cliente')
        operador_id = request.form.get('operador')
        status = request.form.get('status')
        quantidades = {int(k.split('_')[1]): int(v) for k, v in request.form.items() if k.startswith('quantidade_')}

        pedido = db.session.query(Pedido).get(pedido_id)
        if not pedido:
            flash('Pedido não encontrado!', 'danger')
            return redirect(url_for('pedidos_anteriores'))

        pedido.cliente_id = cliente_id
        pedido.operador_id = operador_id
        pedido.status = status

        for produto_id, quantidade in quantidades.items():
            pedido_produto = db.session.query(PedidosProdutos).filter_by(pedido_id=pedido_id, produto_id=produto_id).first()
            if pedido_produto:
                pedido_produto.quantidade = quantidade
            else:
                novo_pedido_produto = PedidosProdutos(pedido_id=pedido_id, produto_id=produto_id, quantidade=quantidade)
                db.session.add(novo_pedido_produto)

        db.session.commit()
        flash('Pedido atualizado com sucesso!', 'success')
        return redirect(url_for('pedidos_anteriores'))

    pedido = db.session.query(Pedido).get(pedido_id)
    if not pedido:
        flash('Pedido não encontrado!', 'danger')
        return redirect(url_for('pedidos_anteriores'))

    clientes = db.session.query(Cliente).all()
    operadores = db.session.query(Operador).all()
    produtos = db.session.query(Produto).all()
    quantidades = {pp.produto_id: pp.quantidade for pp in pedido.pedidos_produtos}

    return render_template('editar_pedido.html', pedido=pedido, clientes=clientes, operadores=operadores, produtos=produtos, quantidades=quantidades)

@app.route('/atualizar_pedido/<int:pedido_id>', methods=['POST'])
def atualizar_pedido(pedido_id):
    pedido = db.session.query(Pedido).get(pedido_id)
    if pedido:
        pedido.status = request.form['status']
        db.session.commit()
        flash('Pedido atualizado com sucesso!', 'success')
    else:
        flash('Pedido não encontrado.', 'danger')
    return redirect(url_for('pedidos_anteriores'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
