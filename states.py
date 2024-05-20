from abc import ABC, abstractmethod
from database import db
from models import Contrato, Chamado
from context import ConversationContext
from twilio_helpers import send_auto_messages
import pandas as pd
import pdfkit
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
        response_messages = self.auto_respond()
        return response_messages
    
    def auto_respond(self):
        chamados = self.get_calls(self.context.contract_id)
        if not chamados:
            return ["Não há chamados registrados para este contrato."]
        
        excel_path = self.generate_excel(chamados)
        pdf_path = self.convert_excel_to_pdf(excel_path)
        self.send_pdf_via_twilio(pdf_path, self.context.phone_number)
        
        self.transition_to(SelectOptionState)
        return ["Relatório gerado e enviado para o seu número. Por favor, escolha uma opção:\n1. Ver chamados\n2. Gerar relatório"]
    
    def get_calls(self, contract_id):
        return Chamado.query.filter_by(contrato_id=contract_id).order_by(Chamado.data_chamado.desc()).all()
    
    def generate_excel(self, chamados):
        data = [(chamado.id, chamado.descricao, chamado.status, chamado.data_criacao) for chamado in chamados]
        df_chamados = pd.DataFrame(data, columns=['ID', 'Descrição', 'Status', 'Data de Criação'])
        excel_path = 'chamados.xlsx'
        df_chamados.to_excel(excel_path, index=False)
        return excel_path
    
    def convert_excel_to_pdf(self, excel_path):
        pdf_path = 'chamados.pdf'
        pdfkit.from_file(excel_path, pdf_path)
        return pdf_path
    
    def send_pdf_via_twilio(self, pdf_path, to_phone_number):
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        client = Client(account_sid, auth_token)
        
        media_url = f'http://your_domain.com/{pdf_path}'
        
        message = client.messages.create(
            body='Aqui está o relatório de chamados em PDF.',
            from_='+1234567890',  # Seu número Twilio
            to=to_phone_number,
            media_url=[media_url]
        )
        
        return message.sid
class EndState(State):
    def handle_request(self, message):
        return ['Atendimento concluído. Obrigado por usar nossos serviços!']

    def auto_respond(self):
        # Reiniciar o contexto para o estado inicial, se necessário
        self.context.state = StartState(self.context)
        return []
