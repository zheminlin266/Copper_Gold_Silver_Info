import math
import unittest

from scripts.pipeline_contracts import (
    AnalysisDecision,
    Candidate,
    ContractError,
    EvidenceClaim,
    RawDocument,
)


class PipelineContractTests(unittest.TestCase):
    def test_raw_text_is_not_trimmed_or_truncated(self):
        text = "  raw text " + ("x" * 10000)
        document = RawDocument("doc-1", "https://example.com/a", "Title", text)
        self.assertEqual(document.text, text)

    def test_rejects_missing_ids_dates_urls_and_enums(self):
        with self.assertRaises(ContractError):
            RawDocument("", "https://example.com/a", "Title", "text")
        with self.assertRaises(ContractError):
            RawDocument("doc-1", "file:///tmp/a", "Title", "text")
        with self.assertRaises(ContractError):
            RawDocument("doc-1", "https://example.com/a", "Title", "text", "2024-02-30")
        with self.assertRaises(ContractError):
            Candidate("c-1", "d-1", "https://example.com/a", "Title", metal="platinum")
        with self.assertRaises(ContractError):
            Candidate("c-1", "d-1", "https://example.com/a", "Title", direction="neutral")
        with self.assertRaises(ContractError):
            AnalysisDecision("c-1", decision="maybe")
        with self.assertRaises(ContractError):
            AnalysisDecision("c-1", confidence=math.inf)

    def test_evidence_claim_requires_http_source(self):
        with self.assertRaises(ContractError):
            EvidenceClaim("claim", "evidence", "ftp://example.com", "report", "2024", "t", 1)

    def test_grok_discovery_and_pending_decisions_round_trip(self):
        candidate = Candidate.from_dict({"id": "grok-1", "document_id": "doc-1", "source_id": "newsfile",
                                         "source_url": "https://example.com/a", "title": "Title", "collector": "grok_bot"})
        self.assertEqual(Candidate.from_dict(candidate.to_dict()).source_id, "newsfile")
        decision = AnalysisDecision.from_dict({"candidate_id": "grok-1", "decision": "pending_verification",
                                               "reason": "Awaiting body", "evidence_documents": []})
        self.assertEqual(AnalysisDecision.from_dict(decision.to_dict()).decision, "pending_verification")


if __name__ == "__main__":
    unittest.main()
