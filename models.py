from database import db

class Contrato(db.Model):
    __tablename__ = 'contratos'
    id = db.Column(db.Integer, primary_key=True)
    numero_contrato = db.Column(db.String(255), unique=True, nullable=False)
    chamados = db.relationship('Chamado', backref='contrato', lazy=True)

class Chamado(db.Model):
    __tablename__ = 'chamados'
    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey('contratos.id'), nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    data_chamado = db.Column(db.DateTime, nullable=False)
    data_atualizacao = db.Column(db.DateTime, nullable=False)
    ultima_atualizacao = db.Column(db.String(255), nullable=False)
