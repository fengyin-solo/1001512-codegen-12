"""观测记录成批导入与统计口径的回归测试（仅依赖标准库，./run.sh 同款 venv 即可跑）。"""
from __future__ import annotations

import unittest

from app.services.observation import ObservationService
from app.store import store

HEADER = "记录编号,所属站点,观测要素,观测时刻,观测数值,数值单位"


def csv_text(*rows: str) -> str:
    return HEADER + "\n" + "\n".join(rows) + "\n"


class ObservationImportTests(unittest.TestCase):
    def setUp(self) -> None:
        store.rows("observation").clear()
        self.service = ObservationService()

    def test_success_rows_grouped_by_station(self) -> None:
        result = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
            ",STAT-0002,气压,2026-09-27 08:00:00,1013,hPa",
        ))
        self.assertEqual((result["success"], result["failed"], result["duplicated"]), (2, 0, 0))
        self.assertEqual(result["groups"], [
            {"station": "STAT-0001", "success": 1, "failed": 0, "duplicated": 0},
            {"station": "STAT-0002", "success": 1, "failed": 0, "duplicated": 0},
        ])
        self.assertEqual(self.service.summarize()["total"], 2)

    def test_bad_number_and_time_listed_with_reason_without_rollback(self) -> None:
        result = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
            ",STAT-0001,风速,2026-09-27 08:00:00,abc,m/s",
            ",STAT-0001,降水,2026/9/27 九点,0.2,mm",
        ))
        self.assertEqual((result["success"], result["failed"]), (1, 2))
        reasons = {item["line"]: item["reason"] for item in result["results"] if not item["ok"]}
        self.assertIn("不是数字", reasons[3])
        self.assertIn("格式不对", reasons[4])
        # 单行失败不回滚：合法行仍已落库
        self.assertEqual(self.service.summarize()["total"], 1)

    def test_missing_required_fields_fail(self) -> None:
        result = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,,℃",
            ",,气温,2026-09-27 08:00:00,18,℃",
        ))
        self.assertEqual(result["failed"], 2)
        joined = " ".join(item["reason"] for item in result["results"])
        self.assertIn("观测数值", joined)
        self.assertIn("所属站点", joined)

    def test_duplicate_in_file_kept_once(self) -> None:
        result = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
            ",STAT-0001,气温,2026-09-27 08:00,22.0,℃",
        ))
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["duplicated"], 1)
        dup = [item for item in result["results"] if item["duplicated"]][0]
        self.assertIn("重复记录只保留一条", dup["reason"])
        self.assertIn("第 2 行", dup["reason"])
        self.assertEqual(self.service.summarize()["total"], 1)

    def test_duplicate_against_existing_rows(self) -> None:
        self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
        ))
        again = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
        ))
        self.assertEqual((again["success"], again["duplicated"]), (0, 1))
        self.assertEqual(self.service.summarize()["total"], 1)

    def test_auto_record_code_when_blank(self) -> None:
        result = self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
        ))
        entry = result["results"][0]["entry"]
        self.assertTrue(entry["记录编号"].startswith("OBSE-"))
        self.assertEqual(entry["数值单位"], "℃")
        self.assertEqual(entry["质控标识"], "待质控")

    def test_code_conflict_on_different_key_fails(self) -> None:
        result = self.service.import_rows(csv_text(
            "OBSE-9001,STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
            "OBSE-9001,STAT-0002,气压,2026-09-27 08:00:00,1013,hPa",
        ))
        self.assertEqual(result["success"], 1)
        fail = [item for item in result["results"] if not item["ok"]][0]
        self.assertIn("记录编号", fail["reason"])

    def test_stats_share_filter_scope_with_list(self) -> None:
        self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
            ",STAT-0001,气压,2026-09-27 09:00:00,1013,hPa",
            ",STAT-0002,气温,2026-09-27 08:00:00,18.4,℃",
        ))
        items, total = self.service.list_entries(station="STAT-0001", page=1, size=200)
        stats = self.service.summarize(station="STAT-0001")
        self.assertEqual(total, len(items))
        self.assertEqual(stats["total"], total)
        self.assertEqual(stats["total"], 2)

    def test_action_keeps_quality_flags_consistent(self) -> None:
        self.service.import_rows(csv_text(
            ",STAT-0001,气温,2026-09-27 08:00:00,21.6,℃",
        ))
        entry_id = store.rows("observation")[0]["id"]
        entry, _ = self.service.run_action(entry_id, "提交质控")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "质控通过")
        self.assertEqual(entry["质控标识"], "质控通过")
        self.assertEqual(entry["记录状态"], "质控通过")
        self.assertEqual(self.service.summarize(status="质控通过")["total"], 1)

    def test_bad_header_and_empty_file(self) -> None:
        with self.assertRaises(ValueError):
            self.service.import_rows("")
        with self.assertRaises(ValueError):
            self.service.import_rows("a,b\n1,2\n")


if __name__ == "__main__":
    unittest.main()
