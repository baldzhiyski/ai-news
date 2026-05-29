from src.link_extractor import extract_links, is_probably_useful_link


import unittest


class LinkExtractorTests(unittest.TestCase):
    def test_duplicate_links_are_removed_after_normalization(self):
        text = """
        https://example.com/ai-agents?utm_source=newsletter#section
        https://example.com/ai-agents
        https://EXAMPLE.com/ai-agents?fbclid=123
        """

        links = extract_links(text, max_links=10)

        self.assertEqual(links, ["https://example.com/ai-agents"])

    def test_skips_unsafe_tracking_and_irrelevant_links(self):
        text = """
        mailto:hello@example.com
        http://localhost/admin
        https://newsletter.example.com/unsubscribe?id=1
        https://example.com/login
        https://example.com/sports/highlights
        https://research.example.com/llm-agents-breakthrough
        """

        links = extract_links(text, max_links=10)

        self.assertEqual(links, ["https://research.example.com/llm-agents-breakthrough"])
        self.assertFalse(is_probably_useful_link("https://example.com/payment/checkout"))


if __name__ == "__main__":
    unittest.main()
