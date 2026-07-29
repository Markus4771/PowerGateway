#!/usr/bin/env python3
"""Kleine Regressionstests für die Backup-Erweiterungen 1.3.8."""
from __future__ import annotations

import unittest


class BackupV138StaticTests(unittest.TestCase):
    def test_upload_limit_is_512_mib(self) -> None:
        import backup_center_v138
        self.assertEqual(backup_center_v138.MAX_UPLOAD_BYTES, 512 * 1024 * 1024)

    def test_manifest_summary_handles_empty_input(self) -> None:
        import backup_center_v138
        result = backup_center_v138._manifest_summary({})
        self.assertEqual(result['file_count'], 0)
        self.assertEqual(result['payload_size'], 0)
        self.assertEqual(result['components'], [])

    def test_manifest_summary_totals_payload(self) -> None:
        import backup_center_v138
        result = backup_center_v138._manifest_summary({
            'manifest': {
                'product_version': '1.3.8-dev',
                'components': ['configuration'],
                'files': [{'size': 10}, {'size': 15}],
            }
        })
        self.assertEqual(result['product_version'], '1.3.8-dev')
        self.assertEqual(result['payload_size'], 25)
        self.assertEqual(result['file_count'], 2)


if __name__ == '__main__':
    unittest.main()
