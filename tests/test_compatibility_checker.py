"""Unit tests for deterministic PC build compatibility checks (no I/O)."""

from __future__ import annotations

import unittest

from compatibility_checker import (
    check_cpu_motherboard,
    check_gpu_case,
    check_psu_wattage,
    check_ram_motherboard,
    validate_build,
)


def _minimal_build(**overrides: object) -> dict:
    base = {
        "cpu": {"socket": "AM5", "tdp": 65},
        "gpu": {"tdp": 200, "length_mm": 280},
        "motherboard": {"socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"ddr_gen": "DDR5"},
        "psu": {"wattage": 500},
        "case": {"max_gpu_length_mm": 300},
    }
    base.update(overrides)
    return base


class TestCpuMotherboard(unittest.TestCase):
    def test_match(self) -> None:
        self.assertTrue(check_cpu_motherboard({"socket": "AM5"}, {"socket": "AM5"}))

    def test_mismatch(self) -> None:
        self.assertFalse(check_cpu_motherboard({"socket": "AM5"}, {"socket": "LGA1700"}))


class TestRamMotherboard(unittest.TestCase):
    def test_dual_ddr_accepts_ddr4(self) -> None:
        mobo = {"ddr_support": "DDR4/DDR5"}
        self.assertTrue(check_ram_motherboard({"ddr_gen": "DDR4"}, mobo))

    def test_dual_ddr_accepts_ddr5(self) -> None:
        mobo = {"ddr_support": "DDR4/DDR5"}
        self.assertTrue(check_ram_motherboard({"ddr_gen": "DDR5"}, mobo))

    def test_single_gen_exact(self) -> None:
        self.assertTrue(check_ram_motherboard({"ddr_gen": "DDR5"}, {"ddr_support": "DDR5"}))

    def test_single_gen_mismatch(self) -> None:
        self.assertFalse(check_ram_motherboard({"ddr_gen": "DDR4"}, {"ddr_support": "DDR5"}))


class TestPsuWattage(unittest.TestCase):
    def test_passes_with_margin(self) -> None:
        b = _minimal_build(psu={"wattage": 475})
        self.assertTrue(check_psu_wattage(b))

    def test_fails_below_required(self) -> None:
        b = _minimal_build(psu={"wattage": 474})
        self.assertFalse(check_psu_wattage(b))


class TestGpuCase(unittest.TestCase):
    def test_fits(self) -> None:
        self.assertTrue(check_gpu_case({"length_mm": 280}, {"max_gpu_length_mm": 300}))

    def test_too_long(self) -> None:
        self.assertFalse(check_gpu_case({"length_mm": 301}, {"max_gpu_length_mm": 300}))


class TestValidateBuild(unittest.TestCase):
    def test_passes_clean_build(self) -> None:
        r = validate_build(_minimal_build())
        self.assertTrue(r["passed"])
        self.assertEqual(r["errors"], [])

    def test_socket_error(self) -> None:
        b = _minimal_build(motherboard={"socket": "LGA1700", "ddr_support": "DDR5"})
        r = validate_build(b)
        self.assertFalse(r["passed"])
        codes = {e["code"] for e in r["errors"]}
        self.assertIn("SOCKET_MISMATCH", codes)

    def test_ram_error(self) -> None:
        b = _minimal_build(
            ram={"ddr_gen": "DDR4"},
            motherboard={"socket": "AM5", "ddr_support": "DDR5"},
        )
        r = validate_build(b)
        self.assertFalse(r["passed"])
        self.assertTrue(any(e["code"] == "RAM_GEN_MISMATCH" for e in r["errors"]))

    def test_psu_error(self) -> None:
        b = _minimal_build(psu={"wattage": 400})
        r = validate_build(b)
        self.assertFalse(r["passed"])
        self.assertTrue(any(e["code"] == "INSUFFICIENT_POWER" for e in r["errors"]))

    def test_gpu_clearance_error(self) -> None:
        b = _minimal_build(gpu={"tdp": 200, "length_mm": 400})
        r = validate_build(b)
        self.assertFalse(r["passed"])
        self.assertTrue(any(e["code"] == "GPU_CLEARANCE_FAIL" for e in r["errors"]))


if __name__ == "__main__":
    unittest.main()
