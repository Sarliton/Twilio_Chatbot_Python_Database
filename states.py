from abc import ABC, abstractmethod
from database import db
from models import Contrato, Chamado
from context import ConversationContext
from twilio_helpers import send_auto_messages
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import os
class ChatBot:
    def __init__(self):
        # Guarda as conversas que o robô está tendo, cada uma com seu próprio telefone
        self.conversation_state = {}

    def handle_message(self, phone_number, message):
        # Verifica se já existe uma conversa com esse telefone
        if phone_number not in self.conversation_state:
            # Se não existir, começa uma nova conversa
            self.conversation_state[phone_number] = ConversationContext(StartState, phone_number)

        # Pede para o estado atual da conversa lidar com a mensagem e obter uma resposta
        response = self.conversation_state[phone_number].request(message)
        return response

class State(ABC):
    def __init__(self, context):
        self.context = context

    @abstractmethod
    def handle_request(self, message):
        pass

    def transition_to(self, new_state_class):
        self.context.state = new_state_class(self.context)
        if hasattr(self.context.state, 'auto_respond'):
            auto_response = self.context.state.auto_respond()
            if auto_response is None:
                auto_response = []
            return auto_response
        return []

class StartState(State):
    def handle_request(self, message):
        if message.lower() in ['ola', 'oi', 'oi, tudo bem?', 'ola, tudo bem?']:
            return ['Olá! Bem vindo à nossa empresa! Por favor, digite seu número de contrato.']
        else:
            contract_id = self.verify_contract(message)
            if contract_id:
                self.context.set_contract_id(contract_id)
                auto_responses = self.transition_to(SelectOptionState)
                return ['Contrato verificado! Por favor, escolha uma opção:\n1. Ver chamados\n2. Gerar relatório'] + auto_responses
            else:
                return ['Contrato não encontrado. Por favor, verifique e digite novamente.']

    def verify_contract(self, contract_number):
        contrato = Contrato.query.filter_by(numero_contrato=contract_number).first()
        return contrato.id if contrato else None

class SelectOptionState(State):
    def handle_request(self, message):
        if message.strip() == '1':
            auto_responses = self.transition_to(GetCallsState)
            return auto_responses
        elif message.strip() == '2':
            auto_responses = self.transition_to(GenerateReportState)
            return auto_responses
        else:
            return ['Opção inválida. Por favor, tente novamente.']

class GetCallsState(State):
    def handle_request(self, message):
        return self.auto_respond()
    
    def auto_respond(self):
        print("Auto-responding with calls list")
        response_messages = ["Por favor, aguarde enquanto obtemos os chamados..."]
        chamados = self.get_calls(self.context.contract_id)
        if chamados:
            chamados_msg = "\n".join([f"{chamado.id}: {chamado.descricao}" for chamado in chamados])
            response_messages.append(chamados_msg)
        else:
            response_messages.append("Não há chamados registrados.")
        response_messages.append("Por favor, digite o número do chamado desejado.")
        self.transition_to(SelectCallState)
        print("Final message to send:", response_messages)
        return response_messages

    def get_calls(self, contract_id):
        return Chamado.query.filter_by(contrato_id=contract_id).order_by(Chamado.data_chamado.desc()).all()

class SelectCallState(State):
    def handle_request(self, message):
        try:
            call_number = int(message)
            self.context.set_call_number(call_number)
            auto_response = self.transition_to(GetCallUpdatesState)
            return ['Número de chamado verificado!\nPor favor, aguarde enquanto obtemos as atualizações...'] + auto_response
        except ValueError:
            return ['Número inválido. Por favor, digite um número de chamado válido.']

class GetCallUpdatesState(State):
    def handle_request(self, message):
        return self.auto_respond()
    
    def auto_respond(self):
        updates = self.get_call_updates(self.context.contract_id, self.context.call_number)
        response_messages = []
        if updates:
            response_messages.append(f"Últimas atualizações do chamado {self.context.call_number}: {updates}")
        else:
            response_messages.append("Não há atualizações disponíveis para este chamado.")
        self.transition_to(SelectReturnState)
        return response_messages

    def get_call_updates(self, contract_id, call_number):
        chamado = Chamado.query.filter_by(contrato_id=contract_id, id=call_number).first()
        if chamado:
            return f"Chamado {chamado.id}: {chamado.descricao} - \nÚltima atualização em {chamado.data_atualizacao.strftime('%d-%m-%y')}:\n {chamado.ultima_atualizacao}"
        else:
            return "Chamado não encontrado."

class SelectReturnState(State):
    def handle_request(self, message):
        if message.strip() == '1':
            auto_responses = self.transition_to(SelectOptionState)
            return ["Retornando ao menu principal..."] + ["Por favor, escolha uma opção:\n1. Ver chamados\n2. Gerar relatório"] + auto_responses

        elif message.strip() == '2':
            auto_responses = self.transition_to(EndState)
            return ["Encerrando a sessão. Obrigado!"] + auto_responses
        else:
            return ["Opção inválida. Por favor, digite 1 para retornar ao menu principal ou 2 para encerrar a sessão."]

    def auto_respond(self):
        return ["Opções: \n1. Retornar ao menu principal\n2. Encerrar a sessão."]
    
class GenerateReportState(State):
    def handle_request(self, message):
        buffer, msg = self.generate_report(self.context.contract_id)
        if buffer:
            # Salve o PDF em um arquivo temporário
            file_path = f'/tmp/report_{self.context.contract_id}.pdf'
            with open(file_path, 'wb') as f:
                f.write(buffer.getvalue())

            # Envie o link para download do relatório
            ngrok_url = os.getenv('NGROK_URL')  # Certifique-se de definir isso no seu .env
            file_url = f'{ngrok_url}/tmp/report_{self.context.contract_id}.pdf'
            self.transition_to(EndState)
            return [f"Relatório gerado com sucesso! Baixe aqui: {file_url}"]
        else:
            return [msg]

    def generate_report(self, contract_id):
            chamados = Chamado.query.filter_by(contrato_id=contract_id).order_by(Chamado.data_chamado.desc()).all()
            if not chamados:
                return None, "Não há chamados registrados para este contrato."

            # Converte os dados dos chamados para um DataFrame do pandas
            data = [{
                'ID Chamado': chamado.id,
                'Descrição': chamado.descricao,
                'Data Chamado': chamado.data_chamado.strftime('%Y-%m-%d'),
                'Data Atualização': chamado.data_atualizacao.strftime('%Y-%m-%d'),
                'Última Atualização': chamado.ultima_atualizacao
            } for chamado in chamados]
            df = pd.DataFrame(data)

            # Gera um PDF com os dados do DataFrame
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            p.drawString(100, 750, "Relatório de Chamados")

            x_offset = 50
            y_offset = 700
            p.drawString(x_offset, y_offset, "ID Chamado")
            p.drawString(x_offset + 100, y_offset, "Descrição")
            p.drawString(x_offset + 300, y_offset, "Data Chamado")
            p.drawString(x_offset + 400, y_offset, "Data Atualização")
            p.drawString(x_offset + 500, y_offset, "Última Atualização")

            y_offset -= 20
            for _, row in df.iterrows():
                p.drawString(x_offset, y_offset, str(row['ID Chamado']))
                p.drawString(x_offset + 100, y_offset, row['Descrição'])
                p.drawString(x_offset + 300, y_offset, row['Data Chamado'])
                p.drawString(x_offset + 400, y_offset, row['Data Atualização'])
                p.drawString(x_offset + 500, y_offset, row['Última Atualização'])
                y_offset -= 20

            p.save()
            buffer.seek(0)
            return buffer, "Relatório gerado com sucesso!"

class EndState(State):
    def handle_request(self, message):
        return ['Atendimento concluído. Obrigado por usar nossos serviços!']

    def auto_respond(self):
        # Reiniciar o contexto para o estado inicial, se necessário
        self.context.state = StartState(self.context)
        return []
