# --------------------------------------------------------------------------------------------------
# Copyright (c) Andreas Gustavsson. All rights reserved.
#
# This file is part of the hdl-registers project, an HDL register generator fast enough to run
# in real time.
# https://hdl-registers.com
# https://github.com/hdl-registers/hdl-registers
# --------------------------------------------------------------------------------------------------

from __future__ import annotations

# if TYPE_CHECKING:
from pathlib import Path
from typing import TYPE_CHECKING

from hdl_registers.field.bit import Bit
from hdl_registers.field.bit_vector import BitVector
from hdl_registers.field.enumeration import Enumeration
from hdl_registers.field.integer import Integer
from hdl_registers.field.numerical_interpretation import (Signed,
                                                          SignedFixedPoint,
                                                          Unsigned,
                                                          UnsignedFixedPoint)
from hdl_registers.field.register_field import RegisterField
from hdl_registers.generator.register_code_generator import \
    RegisterCodeGenerator
from hdl_registers.register import Register
from hdl_registers.register_array import RegisterArray
from hdl_registers.register_list import RegisterList


class RustGeneratorCommon(RegisterCodeGenerator):
    """
    Class with methods for generating common Rust code.
    """

    COMMENT_START = "//"

    def __init__(self, register_list: RegisterList, output_folder: Path) -> None:
        super().__init__(register_list=register_list, output_folder=output_folder)

        self._struct_name = self.to_pascal_case(snake_string=self.name)
        # self._constants_prefix = self.name.upper()
        self._constants_prefix = ""
        self._found_f64_get_field = False
        self._found_f64_set_field = False

    def _get_indentation_per_level_count(self) -> int:
        """
        Returns the number of indentation characters per indentation level.
        """
        return 4

    def _get_indentation_per_level(self) -> str:
        """
        Returns a one-level indentation string.
        """
        return self._get_indentation_per_level_count() * " "

    def _get_indentation(self, indentation_level: int) -> str:
        """
        Returns an indentation string for an arbitrary number of indentation levels.
        """
        return indentation_level * self._get_indentation_per_level()

    def _get_comment_header_field(self, line: str, indentation_level: int = 0) -> str:
        """
        Returns field-header `line` surrounded by comment marks and proper indentation.
        """
        ind = self._get_indentation(indentation_level)
        line = line.replace("\r\n", f"\r\n{ind}// ")
        line = line.replace("\n", f"\n{ind}// ")
        n = 77 - indentation_level * self._get_indentation_per_level_count()
        char = "-"
        return f"""
{ind}// {n * char}
{ind}// {line}
{ind}// {n * char}"""

    def _newline(self) -> str:
        return """
"""

    def _get_comment_header(self, line: str, indentation_level: int = 0) -> str:
        """
        Returns `line` surrounded by standard/register comment marks and proper indentation.
        """
        ind = self._get_indentation(indentation_level)
        line = line.replace("\r\n", f"\r\n{ind}// ")
        line = line.replace("\n", f"\n{ind}// ")
        n = 77 - indentation_level * self._get_indentation_per_level_count()
        char = "="
        return f"""\
{ind}// {n * char}
{ind}// {line}
{ind}// {n * char}"""

    def _get_common_header(self) -> str:
        """
        Defines a trait that is used for accessing the registers in the register
        file. The user must implement this trait and supply that implementation
        when creating an instance of the register-file struct.
        """
        ind = self._get_indentation(1)
        return f"""\
#![allow(unused)]

"""

    def _get_trait(self) -> str:
        """
        Defines a trait that is used for accessing the registers in the register
        file. The user must implement this trait and supply that implementation
        when creating an instance of the register-file struct.
        """
        ind = self._get_indentation(1)
        return f"""\
{self._get_comment_header("32-bit Register Accessor Trait")}

/// An implementation of this trait must be supplied when instantiating
/// the register field struct.
/// # Safety
/// The implementer must ensure the safety of the implementation.
pub trait {self._struct_name}Accessor {{
{ind}type Error;

{ind}fn read32(&self, offset: usize) -> Result<u32, Self::Error>;
{ind}fn write32(&mut self, offset: usize, val: u32) -> Result<(), Self::Error>;
}}
"""

    def _get_helper_functions(
        self, base_ind_level: int = 0, public: bool = False
    ) -> str:
        code: [str] = []
        if self._found_f64_get_field:
            code.append(self._newline())
            code.append(
                self._get_helper_function_bit_field_to_fixedpoint(
                    base_ind_level, public
                )
            )
        if self._found_f64_set_field:
            code.append(self._newline())
            code.append(
                self._get_helper_function_fixedpoint_to_bit_field(
                    base_ind_level, public
                )
            )
        return "".join(code)

    def _get_helper_function_fixedpoint_to_bit_field(
        self, base_ind_level: int = 0, public: bool = False
    ):
        base_ind = self._get_indentation(base_ind_level)
        ind = self._get_indentation(1)
        access = f"""{"Public" if public else "Private"} helper function:
"""
        return f"""\
{self._get_comment_header(f"{access}Fixed-point rounding (ties are rounded to the even integer), f64 -> f64", base_ind_level)}

{base_ind}/// Rounds a 64-bit floating-point number to the nearest integer value.
{base_ind}/// Ties are rounded toward the even integer.
{base_ind}///
{base_ind}/// * `x`: The floating-point number to round.
{base_ind}{"pub " if public else ""}fn round_ties_even(x: f64) -> f64 {{
{base_ind}{ind}let bits = x.to_bits();
{base_ind}{ind}let sign = bits & (1u64 << 63);
{base_ind}{ind}let exp = ((bits >> 52) & 0x7ff) as i32;
{base_ind}{ind}let frac = bits & ((1u64 << 52) - 1);
{base_ind}{ind}// NaN and infinity.
{base_ind}{ind}if exp == 0x7ff {{
{base_ind}{ind}{ind}return x;
{base_ind}{ind}}}
{base_ind}{ind}// |x| >= 2^52: all representable values are already integers.
{base_ind}{ind}if exp >= 1023 + 52 {{
{base_ind}{ind}{ind}return x;
{base_ind}{ind}}}
{base_ind}{ind}// |x| < 0.5: rounds to signed zero.
{base_ind}{ind}//
{base_ind}{ind}// Normal numbers with exp < 1022 are < 0.5.
{base_ind}{ind}// All subnormals (exp == 0) are also < 0.5.
{base_ind}{ind}if exp < 1022 {{
{base_ind}{ind}{ind}return f64::from_bits(sign);
{base_ind}{ind}}}
{base_ind}{ind}// 0.5 <= |x| < 1.0.
{base_ind}{ind}if exp == 1022 {{
{base_ind}{ind}{ind}// Exactly 0.5: tie between 0 and 1.
{base_ind}{ind}{ind}// Zero is even, so return signed zero.
{base_ind}{ind}{ind}if frac == 0 {{
{base_ind}{ind}{ind}{ind}return f64::from_bits(sign);
{base_ind}{ind}{ind}}}
{base_ind}{ind}{ind}// Strictly greater than 0.5 -> 1.0.
{base_ind}{ind}{ind}return if sign == 0 {{ 1.0 }} else {{ -1.0 }};
{base_ind}{ind}}}
{base_ind}{ind}// 1.0 <= |x| < 2^52.
{base_ind}{ind}//
{base_ind}{ind}// Number of fractional bits.
{base_ind}{ind}let shift = (1023 + 52 - exp) as u32;
{base_ind}{ind}let mask = (1u64 << shift) - 1;
{base_ind}{ind}let fractional = bits & mask;
{base_ind}{ind}let integer_bits = bits & !mask;
{base_ind}{ind}let halfway = 1u64 << (shift - 1);
{base_ind}{ind}// Ties go toward the even integer.
{base_ind}{ind}let round_up =
{base_ind}{ind}{ind}fractional > halfway ||
{base_ind}{ind}{ind}(fractional == halfway && (integer_bits & (1u64 << shift)) != 0);
{base_ind}{ind}if !round_up {{
{base_ind}{ind}{ind}return f64::from_bits(integer_bits);
{base_ind}{ind}}}
{base_ind}{ind}let magnitude = f64::from_bits(integer_bits & !(1u64 << 63));
{base_ind}{ind}let rounded = magnitude + 1.0;
{base_ind}{ind}if sign == 0 {{
{base_ind}{ind}{ind}rounded
{base_ind}{ind}}} else {{
{base_ind}{ind}{ind}-rounded
{base_ind}{ind}}}
{base_ind}}}

{self._get_comment_header(f"{access}Fixed-point conversion, f64 -> bit field", base_ind_level)}

{base_ind}/// Converts a floating-point number to a fixed-point bit representation.
{base_ind}///
{base_ind}/// * `value`: The floating-point number to convert.
{base_ind}/// * `total_bits`: The total number of bits the fixed-point number uses (up to 32).
{base_ind}/// * `frac_bits`: The number of bits reserved for the fractional part.
{base_ind}/// * `is_signed`: True if the destination format is 2's complement signed.
{base_ind}{"pub " if public else ""}fn to_fixed_point_field(
{base_ind}{ind}value: f64,
{base_ind}{ind}total_bits: u32,
{base_ind}{ind}frac_bits: u32,
{base_ind}{ind}is_signed: bool,
{base_ind}) -> u32 {{
{base_ind}{ind}assert!(
{base_ind}{ind}{ind}total_bits > 0 && total_bits <= 32,
{base_ind}{ind}{ind}"BUG: total_bits must be in 1..=32"
{base_ind}{ind});
{base_ind}{ind}assert!(
{base_ind}{ind}{ind}frac_bits <= total_bits,
{base_ind}{ind}{ind}"BUG: frac_bits cannot exceed total_bits"
{base_ind}{ind});
{base_ind}{ind}let scale_factor = (1_u64 << frac_bits) as f64;
{base_ind}{ind}// Calculate the exact Floating-Point bounds
{base_ind}{ind}// Use u64 for shifts to safely handle total_bits = 32 without overflowing
{base_ind}{ind}let (min_val, max_val) = if is_signed {{
{base_ind}{ind}{ind}let max_raw = (1_u64 << (total_bits - 1)) - 1;
{base_ind}{ind}{ind}let min_raw = -((1_u64 << (total_bits - 1)) as f64);
{base_ind}{ind}{ind}(min_raw / scale_factor, max_raw as f64 / scale_factor)
{base_ind}{ind}}} else {{
{base_ind}{ind}{ind}let max_raw = (1_u64 << total_bits) - 1;
{base_ind}{ind}{ind}(0.0, max_raw as f64 / scale_factor)
{base_ind}{ind}}};
{base_ind}{ind}// Strict Bounds Checking
{base_ind}{ind}assert!(
{base_ind}{ind}{ind}value >= min_val && value <= max_val,
{base_ind}{ind}{ind}"BUG: Value {{}} out of bounds for {{}} fixed-point ({{}} total, {{}} frac). Min: {{}}, Max: {{}}",
{base_ind}{ind}{ind}value,
{base_ind}{ind}{ind}if is_signed {{ "signed" }} else {{ "unsigned" }},
{base_ind}{ind}{ind}total_bits,
{base_ind}{ind}{ind}frac_bits,
{base_ind}{ind}{ind}min_val,
{base_ind}{ind}{ind}max_val
{base_ind}{ind});
{base_ind}{ind}// Scale and Round
{base_ind}{ind}let scaled_value = value * scale_factor;
{base_ind}{ind}let rounded_value = Self::round_ties_even(scaled_value);
{base_ind}{ind}// Bit-cast based on signedness
{base_ind}{ind}// Since we bounds-checked, these casts are guaranteed to be safe and accurate
{base_ind}{ind}let raw_bits = if is_signed {{
{base_ind}{ind}{ind}rounded_value as i64 as u32
{base_ind}{ind}}} else {{
{base_ind}{ind}{ind}rounded_value as u64 as u32
{base_ind}{ind}}};
{base_ind}{ind}// Mask the result
{base_ind}{ind}let mask = if total_bits == 32 {{
{base_ind}{ind}{ind}u32::MAX
{base_ind}{ind}}} else {{
{base_ind}{ind}{ind}(1_u32 << total_bits) - 1
{base_ind}{ind}}};
{base_ind}{ind}raw_bits & mask
{base_ind}}}
"""

    def _get_helper_function_bit_field_to_fixedpoint(
        self, base_ind_level: int = 0, public: bool = False
    ):
        base_ind = self._get_indentation(base_ind_level)
        ind = self._get_indentation(1)
        access = f"""{"Public" if public else "Private"} helper function:
"""
        return f"""\
{self._get_comment_header(f"{access}Fixed-point conversion, bit field -> f64", base_ind_level)}

{base_ind}/// Converts a fixed-point bit representation back to a floating-point number.
{base_ind}///
{base_ind}/// * `raw_bits`: The u32 containing the (down-shifted) fixed-point bits.
{base_ind}/// * `total_bits`: The total number of bits the fixed-point number uses (up to 32).
{base_ind}/// * `frac_bits`: The number of bits reserved for the fractional part.
{base_ind}/// * `is_signed`: True if the number is 2's complement signed, false if unsigned.
{base_ind}{"pub " if public else ""}fn from_fixed_point_field(
{base_ind}{ind}raw_bits: u32,
{base_ind}{ind}total_bits: u32,
{base_ind}{ind}frac_bits: u32,
{base_ind}{ind}is_signed: bool,
{base_ind}) -> f64 {{
{base_ind}{ind}assert!(
{base_ind}{ind}{ind}total_bits > 0 && total_bits <= 32,
{base_ind}{ind}{ind}"BUG: total_bits must be in 1..=32"
{base_ind}{ind});
{base_ind}{ind}assert!(
{base_ind}{ind}{ind}frac_bits <= total_bits,
{base_ind}{ind}{ind}"BUG: frac_bits cannot exceed total_bits"
{base_ind}{ind});
{base_ind}{ind}let float_val = if is_signed {{
{base_ind}{ind}{ind}// SIGNED: Propagate the sign bit using arithmetic shifting
{base_ind}{ind}{ind}let shift_amount = 32 - total_bits;
{base_ind}{ind}{ind}let sign_extended_int = ((raw_bits << shift_amount) as i32) >> shift_amount;
{base_ind}{ind}{ind}sign_extended_int as f64
{base_ind}{ind}}} else {{
{base_ind}{ind}{ind}// UNSIGNED: Mask out any garbage bits above `total_bits`
{base_ind}{ind}{ind}let mask = if total_bits == 32 {{
{base_ind}{ind}{ind}{ind}u32::MAX
{base_ind}{ind}{ind}}} else {{
{base_ind}{ind}{ind}{ind}(1_u32 << total_bits) - 1
{base_ind}{ind}{ind}}};
{base_ind}{ind}{ind}let clean_unsigned_int = raw_bits & mask;
{base_ind}{ind}{ind}clean_unsigned_int as f64
{base_ind}{ind}}};
{base_ind}{ind}// Divide by 2^(fractional bits) to restore the radix point
{base_ind}{ind}let scale_factor = (1_u64 << frac_bits) as f64;
{base_ind}{ind}float_val / scale_factor
{base_ind}}}
"""

    def _get_constants_mod(self, base_ind_level: int = 0) -> str:
        """
        Returns a mod(ule) block containing all constants
        """
        constants = self._get_constants_code_block(base_ind_level + 1)
        if constants:
            base_ind = self._get_indentation(base_ind_level)
            return f"""\
{self._get_comment_header("Constants", base_ind_level)}

{base_ind}pub mod consts {{
{base_ind}{constants}\
{base_ind}}}
"""
        else:
            return ""

    def _get_constants_code_block(self, base_ind_level: int = 0) -> str:
        """
        Returns a block of code (with header comment) for all defined constants.
        """
        base_ind = self._get_indentation(base_ind_level)
        code_block = ""
        for constant in self.iterate_constants():
            code_block += self._get_constant_code(constant, base_ind)
        return code_block

    def _get_constant_code(self, constant: Any, base_ind: str) -> str:
        """
        Returns code for a single constant.
        """
        name_upper = constant.name.upper()
        type_name = constant.__class__.__name__

        if type_name == "StringConstant":
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: &str = "{constant.value}";
"""
        elif type_name == "BitVectorConstant":
            clean_val = constant.value_without_separator
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: u32 = {constant.prefix}{clean_val};
"""
        elif type_name == "BooleanConstant":
            lowercase_val = str(constant.value).lower()
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: bool = {lowercase_val};
"""
        elif type_name == "UnsignedVectorConstant":
            bitlen = int(f"{constant.prefix}{constant.value}", 0).bit_length()
            if bitlen > 128:
                const_line = f"""\
// Constant {constant.name} cannot fit in u128
"""
            utype = (
                "u8"
                if bitlen <= 8
                else (
                    "u16"
                    if bitlen <= 16
                    else "u32" if bitlen <= 32 else "u64" if bitlen <= 64 else 128
                )
            )
            clean_val = constant.value_without_separator
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: {utype} = {constant.prefix}{clean_val};
"""
        elif type_name == "FloatConstant" or isinstance(constant.value, float):
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: f64 = {constant.value};
"""
        elif type_name == "IntegerConstant":
            int_bits = 32
            int_type = "u"
            if constant.value < 0:
                if constant.value < -(2**127):
                    const_line = f"""\
// Integer constant {constant.name} does not fit within 128 bits; smaller than {-(2**127)}
"""
                int_bits = (
                    8
                    if constant.value >= -(2**7)
                    else (
                        16
                        if constant.value >= -(2**15)
                        else (
                            32
                            if constant.value >= -(2**31)
                            else 64 if constant.value >= -(2**63) else 128
                        )
                    )
                )
                int_type = "i"
            else:
                if constant.value >= (2**128) - 1:
                    const_line = f"""\
// Unsigned Integer constant {constant.name} does not fit within 128 bits; larger than {(2**128)-1}
"""
                int_bits = (
                    8
                    if constant.value < 2**8
                    else (
                        16
                        if constant.value < 2**16
                        else (
                            32
                            if constant.value < 2**32
                            else 64 if constant.value < 2**64 else 128
                        )
                    )
                )
                int_type = "u"
            const_line = f"""\
pub const {self._constants_prefix}{name_upper}: {int_type}{int_bits} = {constant.value};
"""
        else:
            raise ValueError(f"Constant {constant.name} of unknown type")

        if constant.description:
            return f"""\
{base_ind}/// {constant.description.replace("\n", f"\n{base_ind}/// ")}
{base_ind}{const_line}"""
        else:
            return f"{base_ind}{const_line}"

    def _get_enums_mod(self, base_ind_level: int = 0) -> str:
        """
        Returns a mod(ule) block containing all enumerations
        """
        enums = self._get_enums_code_block(base_ind_level + 1)
        if enums:
            base_ind = self._get_indentation(base_ind_level)
            return f"""\
{self._get_comment_header("Enumerations", base_ind_level)}

{base_ind}pub mod enums {{
{base_ind}{enums}\
{base_ind}}}
"""
        else:
            return ""

    def _get_enums_code_block(self, base_ind_level: int = 0) -> str:
        """
        Returns a code block containing all enums
        """
        base_ind = self._get_indentation(base_ind_level)
        code_block = ""
        first_enum = True
        for register, register_array in self.iterate_registers():
            for field in register.fields:
                if isinstance(field, Enumeration):
                    if first_enum:
                        first_enum = False
                    else:
                        code_block += self._newline()
                    code_block += self._get_enum_code(
                        register, register_array, field, base_ind
                    )
        return code_block

    def _get_enum_code(
        self, register: Any, register_array: Any, field: Any, base_ind: str
    ) -> str:
        """
        Returns code for a single enum.
        """
        ind = self._get_indentation(1)
        enum_name = self._get_enum_name(register, register_array, field)
        enum_code = ""
        if field.description:
            enum_code += f"""\
{base_ind}/// {field.description.replace("\n", f"\n{base_ind}/// ")}
"""
        enum_code += f"""\
{base_ind}#[derive(Clone, Copy, Debug, PartialEq, Eq)]
{base_ind}#[repr(u32)]
{base_ind}pub enum {enum_name} {{
"""
        for element in field.elements:
            element_name = self.to_pascal_case(element.name)
            if element_name == "Error":
                raise ValueError(
                    f'An enumeration element cannot be named "Error" (\
{"" if register_array is None else register_array.name + "."}{register.name}.{field.name}.{element.name})'
                )
            enum_code += f"""\
{base_ind}{ind}{element_name} = {element.value},
"""
        enum_code += f"""\
{base_ind}}}
{base_ind}#[derive(Clone, Copy, Debug, PartialEq, Eq)]
{base_ind}pub struct Unknown{enum_name}Error(pub u32);
{base_ind}impl TryFrom<u32> for {enum_name} {{
{base_ind}{ind}type Error = Unknown{enum_name}Error;
{base_ind}{ind}fn try_from(val: u32) -> Result<Self, Self::Error> {{
{base_ind}{ind}{ind}match val {{
"""
        for element in field.elements:
            enum_code += f"""\
{base_ind}{ind}{ind}{ind}{element.value} => Ok(Self::{self.to_pascal_case(element.name)}),
"""
        enum_code += f"""\
{base_ind}{ind}{ind}{ind}_ => Err(Unknown{enum_name}Error(val)),
{base_ind}{ind}{ind}}}
{base_ind}{ind}}}
{base_ind}}}
"""
        return enum_code

    def _get_enum_name(self, register: Any, register_array: Any, field: Any) -> str:
        """
        Returns the enum name
        """
        if register_array is None:
            return self.to_pascal_case(f"{register.name}_{field.name}")
        return self.to_pascal_case(
            f"{register_array.name}_{register.name}_{field.name}"
        )
        # if register_array is None:
        #     return self.to_pascal_case(f"{self.name}_{register.name}_{field.name}")
        # return self.to_pascal_case(
        #     f"{self.name}_{register_array.name}_{register.name}_{field.name}"
        # )
