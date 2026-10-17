from pathlib import Path
from types import SimpleNamespace

from news.models import Region
from sources.models import Source

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def make_source(name="Test Orlando", url="https://example-orlando.test/rss", **kw) -> Source:
    defaults = {
        "kind": Source.Kind.RSS, "source_type": Source.SourceType.MEDIA,
        "region": Region.objects.get(slug="orlando"), "is_active": True, "is_verified": True,
    }
    defaults.update(kw)
    return Source.objects.create(name=name, url=url, **defaults)


class FakeResponse:
    def __init__(self, content=b"", status=200, headers=None, json_data=None):
        self.content = content
        self.text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        self.status_code = status
        self.headers = headers or {}
        self._json = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    """requests.Session-заглушка: url -> FakeResponse или исключение. robots.txt — 404."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers = {}

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers or {}))
        if url.endswith("/robots.txt"):
            return FakeResponse(b"", status=404)
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        return value


def fake_ai_response(parsed, input_tokens=1000, output_tokens=200, stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
        _request_id="req_test",
    )


def fake_deepseek_response(content: str, prompt_tokens=1500, hit=1200, completion_tokens=300, finish_reason="stop"):
    """Ответ в форме OpenAI-совместимого API DeepSeek."""
    return SimpleNamespace(
        id="ds_test",
        choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                              prompt_cache_hit_tokens=hit, prompt_cache_miss_tokens=prompt_tokens - hit),
    )
