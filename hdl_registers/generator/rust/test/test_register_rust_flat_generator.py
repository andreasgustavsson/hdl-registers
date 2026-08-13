# --------------------------------------------------------------------------------------------------
# Copyright (c) Andreas Gustavsson. All rights reserved.
#
# This file is part of the hdl-registers project, an HDL register generator fast enough to run
# in real time.
# https://hdl-registers.com
# https://github.com/hdl-registers/hdl-registers
# --------------------------------------------------------------------------------------------------

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hdl_registers import HDL_REGISTERS_TESTS
from hdl_registers.field.numerical_interpretation import (Signed,
                                                          SignedFixedPoint,
                                                          Unsigned,
                                                          UnsignedFixedPoint)
from hdl_registers.generator.rust.rust_flat import RustFlatGenerator
from hdl_registers.parser.toml import from_toml
from hdl_registers.register_list import RegisterList
from hdl_registers.register_modes import REGISTER_MODES

if TYPE_CHECKING:
    from hdl_registers.field.register_field import RegisterField


@pytest.fixture
def rust_test_toml_code(tmp_path, name: str = "test"):
    registers = from_toml(name, HDL_REGISTERS_TESTS / "regs_test.toml")
    generator = RustFlatGenerator(register_list=registers, output_folder=tmp_path)
    return generator.get_code()


def test_read_only_register_has_no_setters(rust_test_toml_code):
    # getters
    assert "read_status" in rust_test_toml_code
    assert "get_status_c_from" in rust_test_toml_code
    assert "read_status_c" in rust_test_toml_code
    # setters
    assert "write_status" not in rust_test_toml_code
    assert "set_status_c_in" not in rust_test_toml_code
    assert "write_status_c" not in rust_test_toml_code


def test_write_only_register_has_no_getters(rust_test_toml_code):
    # setters
    assert "write_command" in rust_test_toml_code
    assert "set_command_abort_in" in rust_test_toml_code
    assert "write_command_abort" in rust_test_toml_code
    # getters
    assert "read_command" not in rust_test_toml_code
    assert "get_command_abort_from" not in rust_test_toml_code
    assert "read_command_abort" not in rust_test_toml_code


def test_accessor_trait(rust_test_toml_code):
    assert "pub trait TestFlatAccessor {" in rust_test_toml_code
    assert "type Error;" in rust_test_toml_code
    assert (
        "fn read32(&self, offset: usize) -> Result<u32, Self::Error>;"
        in rust_test_toml_code
    )
    assert (
        "fn write32(&mut self, offset: usize, val: u32) -> Result<(), Self::Error>;"
        in rust_test_toml_code
    )


def test_error_enum(rust_test_toml_code):
    assert f"pub enum TestFlatError<E> {{" in rust_test_toml_code
    assert "Accessor(E)," in rust_test_toml_code
    assert (
        "EnumFromRaw { got: u32, max: u32, name: &'static str }," in rust_test_toml_code
    )
    assert "Signed { got: i32, min: i32, max: i32 }," in rust_test_toml_code
    assert "Unsigned { got: u32, min: u32, max: u32 }," in rust_test_toml_code
    assert "Float { got: f64, min: f64, max: f64 }," in rust_test_toml_code
    assert "ArrayIndex { got: usize, max: usize }," in rust_test_toml_code
    assert "impl<E> From<E> for TestFlatError<E> {" in rust_test_toml_code
    assert "fn from(e: E) -> Self {" in rust_test_toml_code
    assert "TestFlatError::Accessor(e)" in rust_test_toml_code


def test_struct_presence(rust_test_toml_code):
    assert "pub struct TestFlat<A>" in rust_test_toml_code
    assert " A: TestFlatAccessor," in rust_test_toml_code
    assert " accessor: A," in rust_test_toml_code


def test_struct_impl_presence(rust_test_toml_code):
    assert "impl<A> TestFlat<A>" in rust_test_toml_code
    assert " A: TestFlatAccessor," in rust_test_toml_code
    assert "pub const fn new(accessor: A)" in rust_test_toml_code
    assert " Self { accessor }" in rust_test_toml_code


def test_enum_irq_status_d(rust_test_toml_code):
    assert "UnknownIrqStatusDError" in rust_test_toml_code
    assert "impl TryFrom<u32> for IrqStatusD" in rust_test_toml_code


@pytest.mark.parametrize(
    "register_mode,field_type,field_width,field_default,val_min,val_max,assert_min,assert_max",
    [
        # Bit fields (type bool)
        ("r", "bit", 1, 1 * "0", None, None, False, False),
        ("w", "bit", 1, 1 * "0", None, None, False, False),
        # Enumeration
        # field_wdith is used for items
        (
            "r",
            "enumeration",
            {"aa": "", "bb": ""},
            "bb",
            0,
            1,
            False,
            False,
        ),
        (
            "w",
            "enumeration",
            {"aa": "", "bb": ""},
            "bb",
            0,
            1,
            False,
            False,
        ),
        (
            "r",
            "enumeration",
            {"aa": "", "bb": "", "cc": ""},
            "bb",
            0,
            2,
            False,
            False,
        ),
        (
            "w",
            "enumeration",
            {"aa": "", "bb": "", "cc": ""},
            "bb",
            0,
            2,
            False,
            False,
        ),
        # Integer fields
        ("r", "integer", None, 3, -34, 57, True, True),
        ("r", "integer", None, 0, -255, 255, True, False),
        ("r", "integer", None, 5, 1, 255, True, False),
        ("r", "integer", None, 0, -256, 254, False, True),
        ("r", "integer", None, 0, 0, 254, False, True),
        ("r", "integer", None, 0, -255, 254, True, True),
        ("r", "integer", None, 5, 1, 254, True, True),
        ("r", "integer", None, 0, 0, 255, False, False),
        ("r", "integer", None, 3, -256, 255, False, False),
        ("r", "integer", None, 35, -(1 << 31), (1 << 31) - 1, False, False),
        ("r", "integer", None, 35, 0, (1 << 32) - 1, False, False),
        ("r", "integer", None, 35, -(1 << 31), (1 << 31) - 2, False, True),
        ("r", "integer", None, 35, 0, (1 << 32) - 2, False, True),
        ("r", "integer", None, 35, -(1 << 31) + 1, (1 << 31) - 1, True, False),
        ("r", "integer", None, 35, 1, (1 << 32) - 1, True, False),
        ("r", "integer", None, 35, -(1 << 31) + 1, (1 << 31) - 2, True, True),
        ("r", "integer", None, 35, 1, (1 << 32) - 2, True, True),
        ("w", "integer", None, 3, -34, 57, True, True),
        ("w", "integer", None, 35, 34, 57, True, True),
        ("w", "integer", None, 35, 0, 255, False, True),
        ("w", "integer", None, 35, -256, 255, True, True),
        ("w", "integer", None, 35, -(1 << 31), (1 << 31) - 1, False, False),
        ("w", "integer", None, 35, 0, (1 << 32) - 1, False, False),
        ("w", "integer", None, 35, -(1 << 31), (1 << 31) - 2, False, True),
        ("w", "integer", None, 35, 0, (1 << 32) - 2, False, True),
        ("w", "integer", None, 35, -(1 << 31) + 1, (1 << 31) - 1, True, False),
        ("w", "integer", None, 35, 1, (1 << 32) - 1, True, False),
        ("w", "integer", None, 35, -(1 << 31) + 1, (1 << 31) - 2, True, True),
        ("w", "integer", None, 35, 1, (1 << 32) - 2, True, True),
        # Bit vector (unsigned)
        ("r", "bit_vector_unsigned", 4, 4 * "0", None, None, False, False),
        ("w", "bit_vector_unsigned", 4, 4 * "0", None, 15, False, True),
        ("w", "bit_vector_unsigned", 32, 32 * "0", None, None, False, False),
        # Bit vector (signed)
        ("r", "bit_vector_signed", 4, 4 * "0", None, None, False, False),
        ("w", "bit_vector_signed", 4, 4 * "0", -8, 7, True, True),
        ("w", "bit_vector_signed", 32, 32 * "0", None, None, False, False),
        # Bit vector fixed-point
        # default is used for -numerical_interpretation.min_bit_index
        ("r", "bit_vector_unsigned_float", 4, 2, None, None, False, False),
        ("w", "bit_vector_unsigned_float", 4, 2, 0.0, 3.75, True, True),
        ("r", "bit_vector_signed_float", 4, 2, None, None, False, False),
        ("w", "bit_vector_signed_float", 4, 2, -2.0, 1.75, True, True),
    ],
)
def test_range_check(
    register_mode,
    field_type,
    field_width,
    field_default,
    val_min,
    val_max,
    assert_min,
    assert_max,
):
    class Checker:
        def __init__(self, mode: str):
            self.register_list = RegisterList(name="test")
            self.register = self.register_list.append_register(
                name="register", mode=REGISTER_MODES[mode], description=""
            )
            self.register_mode_str = mode

            # Output folder does not matter, code is generated in memory for this test.
            self.generator = RustFlatGenerator(
                register_list=self.register_list,
                output_folder=HDL_REGISTERS_TESTS / "rust_test",
            )

        def get_rust(self, field: RegisterField):
            # Isolate the specific getter or setter method block from the generated Rust string.
            code = self.generator._get_register_methods(
                register=self.register, register_array=None
            )
            print(f"{code}")
            method_prefix = "set" if "w" in self.register_mode_str else "get"
            method_suffix = "_in" if "w" in self.register_mode_str else "_from"
            self_mode = "&mut self" if "w" in self.register_mode_str else "&self"
            method_start = f"pub fn {method_prefix}_{self.register.name}_{field.name}{method_suffix}({self_mode}"
            if method_start not in code:
                print(f"method start '{method_start}' is not in generated code")
                return ""

            # start_idx = code.find(method_start)
            # end_idx = code.find("    pub fn ", start_idx + 10)
            # if end_idx == -1:
            #     end_idx = len(code)

            # return code[start_idx:end_idx]
            return code

        def check(
            self,
            field: RegisterField,
            minmax: tuple[Any, Any, Bool, Bool],
        ):
            field_var = "field_val"  # Must correspond to code from generator

            def _check(
                rust_code: str,
                val_min: Any,
                val_max: Any,
                min_check: Bool,
                max_check: Bool,
            ):
                minmax_check_str = (
                    f"if !({val_min}..={val_max}).contains(&{field_var}) {{"
                )
                min_check_str = f"if {field_var} < {val_min} {{"
                max_check_str = f"if {val_max} < {field_var} {{"
                minmax_check = min_check and max_check
                if minmax_check:
                    assert minmax_check_str in rust_code
                else:
                    assert minmax_check_str not in rust_code
                    if min_check:
                        assert min_check_str in rust_code
                    else:
                        assert min_check_str not in rust_code

                    if max_check:
                        assert max_check_str in rust_code
                    else:
                        assert max_check_str not in rust_code

            code = self.get_rust(field=field)
            _check(
                rust_code=code,
                val_min=minmax[0],
                val_max=minmax[1],
                min_check=minmax[2],
                max_check=minmax[3],
            )

    checker = Checker(mode=register_mode)
    if field_type == "bit":
        field = checker.register.append_bit(
            name="a",
            default_value=field_default,
            description="",
        )
    elif field_type == "bit_vector_unsigned":
        field = checker.register.append_bit_vector(
            name="a",
            width=field_width,
            default_value=field_default,
            description="",
            numerical_interpretation=Unsigned(bit_width=field_width),
        )
    elif field_type == "bit_vector_signed":
        field = checker.register.append_bit_vector(
            name="a",
            width=field_width,
            default_value=field_default,
            description="",
            numerical_interpretation=Signed(bit_width=field_width),
        )
    elif field_type == "bit_vector_unsigned_float":
        field = checker.register.append_bit_vector(
            name="a",
            description="",
            width=field_width,
            default_value=field_width * "0",
            numerical_interpretation=UnsignedFixedPoint(
                max_bit_index=field_width - field_default - 1,
                min_bit_index=-field_default,
            ),
        )
    elif field_type == "bit_vector_signed_float":
        field = checker.register.append_bit_vector(
            name="a",
            description="",
            width=field_width,
            default_value=field_width * "0",
            numerical_interpretation=SignedFixedPoint(
                max_bit_index=field_width - field_default - 1,
                min_bit_index=-field_default,
            ),
        )
    elif field_type == "enumeration":
        field = checker.register.append_enumeration(
            name="a",
            elements=field_width,
            default_value=field_default,
            description="",
        )
    elif field_type == "integer":
        if val_min is None and val_max is None:
            field = checker.register.append_integer(
                name="a",
                default_value=field_default,
                description="",
            )
        elif val_min is None:
            field = checker.register.append_integer(
                name="a",
                default_value=field_default,
                max_value=val_max,
                description="",
            )
        elif val_max is None:
            field = checker.register.append_integer(
                name="a",
                default_value=field_default,
                min_value=val_min,
                description="",
            )
        else:
            field = checker.register.append_integer(
                name="a",
                default_value=field_default,
                min_value=val_min,
                max_value=val_max,
                description="",
            )
    else:
        raise ValueError(f"Unknown type: {field_type}")
    checker.check(field, (val_min, val_max, assert_min, assert_max))
