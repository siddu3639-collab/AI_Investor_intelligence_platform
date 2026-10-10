from types import SimpleNamespace

import httpx
import openai
import pytest

from app.clients import azure_openai


def _bad_request(message):
    response = httpx.Response(400, request=httpx.Request("POST", "https://x/chat"))
    return openai.BadRequestError(message, response=response, body=None)


class FakeCompletions:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error and "temperature" in kwargs:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])


def _install(monkeypatch, completions):
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(azure_openai, "get_client", lambda: client)
    monkeypatch.setattr(azure_openai, "_skip_temperature", False)


def test_gpt5_style_model_retries_without_temperature_then_remembers(monkeypatch):
    fake = FakeCompletions(error=_bad_request("Unsupported value: 'temperature' does not support 0.2"))
    _install(monkeypatch, fake)

    assert azure_openai.generate_answer("s", "u") == "ok"
    assert "temperature" in fake.calls[0] and "temperature" not in fake.calls[1]

    azure_openai.generate_answer("s", "u")          # third call goes straight through
    assert len(fake.calls) == 3 and "temperature" not in fake.calls[2]


def test_normal_model_keeps_temperature(monkeypatch):
    fake = FakeCompletions()
    _install(monkeypatch, fake)
    azure_openai.generate_answer("s", "u", temperature=0.0)
    assert fake.calls[0]["temperature"] == 0.0


def test_other_bad_requests_are_not_swallowed(monkeypatch):
    _install(monkeypatch, FakeCompletions(error=_bad_request("content filter triggered")))
    with pytest.raises(openai.BadRequestError):
        azure_openai.generate_answer("s", "u")
