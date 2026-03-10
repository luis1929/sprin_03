import requests
import json

url = "https://graph.facebook.com/v22.0/965957446610330/messages"

headers = {
    "Authorization": "Bearer TU_TOKEN_AQUI",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": "573012484718",  
    "type": "text",
    "text": {
        "body": "Hola, este es un mensaje de prueba desde Python 🚀"
    }
}

response = requests.post(url, headers=headers, json=data)

print(response.status_code)
print(response.text)