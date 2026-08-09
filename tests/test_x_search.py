import asyncio
import unittest

from scripts.x_search import parse_x_datetime, search_account


class FakeResponse:
    status = 200


class FakeLocator:
    async def count(self):
        return 1


class FakeElement:
    def __init__(self, *, datetime_value=None, text=None, href=None):
        self.datetime_value = datetime_value
        self.text = text
        self.href = href

    async def get_attribute(self, name):
        if name == "datetime":
            return self.datetime_value
        if name == "href":
            return self.href
        return None

    async def inner_text(self):
        return self.text or ""


class FakeArticle:
    def __init__(self, *, has_time=True, datetime_value="2026-07-14T10:00:00Z", text=None, href=None):
        self.elements = {}
        if has_time:
            self.elements["time"] = FakeElement(datetime_value=datetime_value)
        if text is not None:
            self.elements['[data-testid="tweetText"]'] = FakeElement(text=text)
        if href is not None:
            self.elements['a[href*="/status/"]'] = FakeElement(href=href)

    async def query_selector(self, selector):
        return self.elements.get(selector)


class FakePage:
    url = "https://x.com/search"

    def __init__(self, articles):
        self.articles = articles

    async def goto(self, *args, **kwargs):
        return FakeResponse()

    async def wait_for_timeout(self, *args, **kwargs):
        return None

    async def query_selector_all(self, selector):
        return self.articles

    def locator(self, selector):
        return FakeLocator()


class XSearchTests(unittest.TestCase):
    def test_parse_x_datetime_rejects_naive_datetime(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_x_datetime("2026-07-14T10:00:00")

    def test_missing_time_is_an_extraction_error(self):
        tweets, error = asyncio.run(
            search_account(FakePage([FakeArticle(has_time=False)]), "example", "Example", "2026-07-14")
        )

        self.assertEqual(tweets, [])
        self.assertIn("missing time element", error or "")

    def test_missing_text_or_status_url_is_an_extraction_error(self):
        cases = [
            (FakeArticle(text="", href="/example/status/1"), "empty tweet text"),
            (FakeArticle(text="Copper production update"), "missing status URL"),
        ]
        for article, expected in cases:
            with self.subTest(expected=expected):
                tweets, error = asyncio.run(
                    search_account(FakePage([article]), "example", "Example", "2026-07-14")
                )
                self.assertEqual(tweets, [])
                self.assertIn(expected, error or "")


if __name__ == "__main__":
    unittest.main()
