
response_messages = ["Por favor, aguarde enquanto obtemos os chamados...;"]
chamados_msg = "\n".join(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10;'])
response_messages.append(chamados_msg)
response_messages.append("Por favor, digite o número do chamado desejado.")
response_messages = " ".join(response_messages)
response = response_messages
responses = response.split(';')
print("Final message to send:", responses)

