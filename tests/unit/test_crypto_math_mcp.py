from __future__ import annotations

from pathlib import Path

import importlib.util

import pytest

pytest.importorskip("sympy")


def _load_crypto_module():
    module_path = Path(__file__).resolve().parents[2] / "images" / "ctf-agent-sandbox" / "crypto_math_mcp.py"
    spec = importlib.util.spec_from_file_location("crypto_math_mcp_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load crypto_math_mcp module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_factorint_and_modinv() -> None:
    module = _load_crypto_module()
    factors = module._factorint(12)
    assert factors == {"2": 2, "3": 1}
    inv = module._modinv(3, 11)
    assert inv == 4


def test_crt_solution() -> None:
    module = _load_crypto_module()
    result = module._crt([3, 5, 7], [2, 3, 2])
    assert result["ok"] is True
    assert result["modulus"] == 105
    assert result["x"] % 3 == 2
    assert result["x"] % 5 == 3
    assert result["x"] % 7 == 2


def test_sympy_eval_runs(tmp_path) -> None:
    module = _load_crypto_module()
    res = module._sympy_eval("print(2+2)", cwd=tmp_path)
    assert res.ok is True
    assert "4" in res.stdout
