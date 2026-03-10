import requests

url = "https://graph.facebook.com/v22.0/965957446610330/messages"

headers = {
    "Authorization": "Bearer EAAiWkVZADneMBQ0NJyj1nLCRFwTd2E9W6UlB6HbCNv62A6ZAPiX0IqwVmkI3Vl4N2m1FYw09xtYCbSBwS4QE82wt5JuC1rt1UnWSTNT2H7Yqkqo2XlEzIVE75BnqDxZAfwQy7IR7Pw35PeAda7xugh3coLis9oV8pjJh6lgUmZCP6gdDrY6MtLz99ua3SliMlfSDMR86MAZCFfspKOrqxIH9SJT9ml6RBhltNrZBxOvmXhZA3WMghmAqEizYl3f8U5bCy4vhO93rDXSYk9IqKKhpAQYW7dEsX0ZD",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": "573046777379",
    "type": "text",
    "text": {
        "body": "Hola, este es un mensaje de prueba."
    }
}

response = requests.post(url, headers=headers, json=data)

print(response.status_code)
print(response.text)