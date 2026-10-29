import unittest

from exporter.aligned_export_pipeline import _contract_range


class SamplingContractTests(unittest.TestCase):
    def contract(self, **changes):
        sampling = dict(version=1, index_origin=0, end_exclusive=True, source_start_sample=2,
                        source_end_sample=7, source_rate_hz=100, clock_scale=1)
        sampling.update(changes)
        return {"sampling": sampling}

    def test_new_contract_converts_exclusive_end_once(self):
        self.assertEqual(_contract_range(self.contract(), 9, 99, 30), (2, 6, 100))

    def test_legacy_contract_preserves_existing_numbering(self):
        self.assertEqual(_contract_range({}, 2, 7, 100), (2, 7, 100))

    def test_unimplemented_rate_edit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "clock-rate"):
            _contract_range(self.contract(clock_scale=1.01), 2, 7, 100)

    def test_unit_interpretation_does_not_rescale_original_mcp(self):
        data = self.contract()
        data["geometry"] = {"source_unit": "in", "output_unit": "cm", "permanent_transform_meters": {"scale": 1}}
        self.assertEqual(_contract_range(data, 2, 7, 100), (2, 6, 100))
