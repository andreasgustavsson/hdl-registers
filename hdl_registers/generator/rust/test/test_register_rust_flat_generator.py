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
    assert (
        "fn read32(&self, offset: usize) -> Result<u32, &'static str>;"
        in rust_test_toml_code
    )
    assert (
        "fn write32(&mut self, offset: usize, val: u32) -> Result<(), &'static str>;"
        in rust_test_toml_code
    )


def test_struct_presence(rust_test_toml_code):
    assert "pub struct TestFlat<A: TestFlatAccessor> {" in rust_test_toml_code
    assert "accessor: A," in rust_test_toml_code


def test_struct_impl_presence(rust_test_toml_code):
    assert "impl<A: TestFlatAccessor> TestFlat<A> {" in rust_test_toml_code
    assert "pub const fn new(accessor: A)" in rust_test_toml_code
    assert "Self { accessor }" in rust_test_toml_code


@pytest.mark.parametrize(
    "register_mode,field_type,field_width,field_default,val_min,val_max",
    [
        # Bit fields (bool) should not be range-checked at all
        ("r", "bit", 1, 1 * "0", None, None),
        ("w", "bit", 1, 1 * "0", None, None),
        # Integer fields should be checked against both limits on both reads and writes,
        # but not on reads if value range covers the entire field,
        # and lower limit should not be checked on writes of an unsigned int if limit i 0.
        ("r", "integer", None, 3, -34, 57),
        ("r", "integer", None, 0, 0, 255),
        ("r", "integer", None, 3, -256, 255),
        ("w", "integer", None, 3, -34, 57),
        ("w", "integer", None, 35, 34, 57),
        ("w", "integer", None, 35, 0, 255),
        ("w", "integer", None, 35, -256, 255),
        ("w", "integer", None, 35, -(1 << 31), (1 << 31) - 1),
        ("w", "integer", None, 35, 0, (1 << 32) - 1),
        ("w", "integer", None, 35, -(1 << 31), (1 << 31) - 2),
        ("w", "integer", None, 35, 0, (1 << 32) - 2),
        ("w", "integer", None, 35, -(1 << 31) + 1, (1 << 31) - 1),
        ("w", "integer", None, 35, 1, (1 << 32) - 1),
        # Bit vector (unsigned) fields should be checked against upper limit on write
        ("r", "bit_vector_unsigned", 4, 4 * "0", None, None),
        ("w", "bit_vector_unsigned", 4, 4 * "0", None, 15),
        ("w", "bit_vector_unsigned", 32, 32 * "0", None, None),
        # Bit vector (signed) fields should be checked against both limits on write
        ("r", "bit_vector_signed", 4, 4 * "0", None, None),
        ("w", "bit_vector_signed", 4, 4 * "0", -8, 7),
        ("w", "bit_vector_signed", 32, 32 * "0", None, None),
        # Enumeration fields should be checked against upper limits on reads,
        # but that is done by the enumeration's from_u32()
        # field_wdith = items
        ("r", "enumeration", {"aa": "", "bb": "", "cc": ""}, "bb", None, None),
        ("w", "enumeration", {"aa": "", "bb": "", "cc": ""}, "bb", None, None),
        # Bit vector floats should be range checked against both limits on writes
        # default = -numerical_interpretation.min_bit_index
        ("r", "bit_vector_unsigned_float", 4, 2, None, None),
        ("w", "bit_vector_unsigned_float", 4, 2, 0.0, 3.75),
        ("r", "bit_vector_signed_float", 4, 2, None, None),
        ("w", "bit_vector_signed_float", 4, 2, -2.0, 1.75),
    ],
)
def test_range_check(
    register_mode,
    field_type,
    field_width,
    field_default,
    val_min,
    val_max,
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
            minmax: tuple[Any, Any, Any, Any],
        ):
            field_var = "field_val"  # Must correspond to code from generator

            def _check(
                rust_code: str,
                val_min: Any,
                val_max: Any,
                min_check: Any,
                max_check: Any,
            ):
                min_check_str = f"if field_val < {val_min} {{"
                max_check_str = f"if {val_max} < field_val {{"
                if min_check:
                    assert f"{min_check_str}" in rust_code
                else:
                    assert f"{min_check_str}" not in rust_code

                if max_check:
                    assert f"{max_check_str}" in rust_code
                else:
                    assert f"{max_check_str}" not in rust_code

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
        test_min = val_min is not None
        test_max = val_max is not None
    elif field_type == "bit_vector_unsigned":
        field = checker.register.append_bit_vector(
            name="a",
            width=field_width,
            default_value=field_default,
            description="",
            numerical_interpretation=Unsigned(bit_width=field_width),
        )
        test_min = val_min is not None and val_min > 0
        test_max = val_max is not None and (
            field.width < 32 or val_max < (1 << field.width) - 1
        )
    elif field_type == "bit_vector_signed":
        field = checker.register.append_bit_vector(
            name="a",
            width=field_width,
            default_value=field_default,
            description="",
            numerical_interpretation=Signed(bit_width=field_width),
        )
        test_min = val_min is not None and (
            field.width < 32 or val_min > -(1 << (field.width - 1))
        )
        test_max = val_max is not None and (
            field.width < 32 or val_max < (1 << (field.width - 1)) - 1
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
        test_min = val_min is not None
        test_max = val_max is not None
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
        test_min = val_min is not None
        test_max = val_max is not None
    elif field_type == "enumeration":
        field = checker.register.append_enumeration(
            name="a",
            elements=field_width,
            default_value=field_default,
            description="",
        )
        test_min = False
        test_max = len(field_width).bit_count() == 1
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
        # Determine the hardware limits based on signedness and width
        if field.is_signed:
            # Two's complement limits for the specific field
            field_min = -(1 << (field.width - 1))
            field_max = (1 << (field.width - 1)) - 1
            # Two's complement limits for a full 32-bit register
            reg_min = -(1 << 31)
            reg_max = (1 << 31) - 1
        else:
            # Unsigned limits for the specific field
            field_min = 0
            field_max = (1 << field.width) - 1
            # Unsigned limits for a full 32-bit register
            reg_min = 0
            reg_max = (1 << 32) - 1

        # Evaluate the test conditions based on the register mode
        if register_mode == "w":
            test_max = field.width < 32 or val_max < reg_max
            if field.is_signed:
                test_min = field.width < 32 or val_min > reg_min
            else:
                test_min = val_min > field_min

        elif register_mode == "r":
            # On reads: test if the specified limit is stricter than what the field can physically hold
            test_max = val_max < field_max
            test_min = val_min > field_min

        else:
            raise ValueError(
                f"Cannot handle register mode (use 'r' or 'w'): {register_mode}"
            )
    else:
        raise ValueError(f"Unknown type: {field_type}")

    checker.check(field, (val_min, val_max, test_min, test_max))
