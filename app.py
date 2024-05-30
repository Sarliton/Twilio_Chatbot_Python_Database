from flask import Flask, request
from context import ConversationContext  # Assegure-se de que esta importação está correta
from states import ChatBot, StartState  # Assegure-se de que StartState está sendo importado corretamente
from database import db
import twilio_helpers

app = Flask(__name__)
app.config.from_object('database.Config')
db.init_app(app)

bot = ChatBot()

@app.route('/sms', methods=['POST'])
def sms_reply():
    phone_number = request.form['From']
    incoming_msg = request.form['Body']
    my_twilio_number = request.form['To']

    if phone_number not in bot.conversation_state:
        bot.conversation_state[phone_number] = ConversationContext(StartState, phone_number, my_twilio_number)

    response = bot.conversation_state[phone_number].request(incoming_msg)
    print(f"Response to send: {response}")  # Log da resposta antes de enviar

    if isinstance(response, list) and response:
        twilio_helpers.send_auto_messages(phone_number, response, my_twilio_number)
        return ('', 204)
    else:
        print("No valid message to send, received:", response)
        return ('', 204)

@app.route('/tmp/<path:filename>', methods=['GET'])
def download_file(filename):
    return send_file(f'/tmp/{filename}', as_attachment=True)
if __name__ == '__main__':
    app.run(debug=True)
