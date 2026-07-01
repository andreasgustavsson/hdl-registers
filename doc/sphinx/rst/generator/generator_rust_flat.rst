.. _generator_rust:

Rust flat generator
===================

Flat, ``no_std`` Rust code can be generated, containing all information about registers, register arrays, fields
and constants.
The code is generated from the :class:`.RustFlatGenerator` class by calling
the :meth:`.RegisterCodeGenerator.create` method.

.. literalinclude:: py/generator_rust.py
   :caption: Python code that parses the example TOML file and generates the flat Rust code we need.
   :language: Python
   :linenos:
   :lines: 10-

Read and/or write access to registers is provided based on each register's access mode.
Range-based validation of field values is always performed where necessary to ensure that only proper field values
are read from, or written to, register fields.

For registers which can be read, two types of read functions are generated: one that reads the
entire register and returns the raw ``u32`` value, and one for each field that reads the specific
field and returns a value of appropriate type (such as ``bool``, ``i32``, ``enum`` or ``f64`` for instance).
The latter type of function internally calls the first function to read the entire register, then it
invokes another (public) getter which can extract the field's value from any ``u32``.

For registers which can be written, two types of write functions are generated: one that writes the
entire register, and one that takes a value (such as ``bool``, ``i32``, ``enum`` or ``f64``, as appropriate)
and writes it to a specific field.
The latter type of function internally calls the first function to write the entire register - if
the register is also readable, then a read-modify-write is performed, otherwise, default values are
written to all other fields.

The generated Rust code provides the user with flexibility in how to implement safe register access.
The method of access is defined by the user by implementing a generated ``trait``.
An object of such an implementation is then supplied when creating an instance of the generated
struct representing the registers, and later used for accessing the registers.
This method also makes mocking the presence of the actual registers very easy.


Below is the resulting code from the :ref:`TOML format example <toml_format>`:

.. literalinclude:: ../../../../generated/sphinx_rst/register_code/generator/generator_rust/example_flat.rs
   :caption: example_flat.rs
   :language: Rust
   :linenos:
