"""Помощники тестов терминала: команды через клиент, как их шлёт браузер."""
import json

from django.urls import reverse


class TerminalClient:
    """Миксин тестового класса с self.client: run_command и answer (ответ на запрос пароля) возвращают разобранный ответ."""

    def send(self, payload):
        response = self.client.post(reverse("terminal:execute"), data=json.dumps(payload), content_type="application/json")
        return json.loads(response.content)

    def run_command(self, text):
        return self.send({"command": text})

    def answer(self, text):
        return self.send({"answer": text})
