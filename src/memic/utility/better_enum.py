from collections.abc import Iterable, Iterator
from typing import Any, Generic, Protocol, TypeVar, _ProtocolMeta

T = TypeVar("T")


class _BetterEnumMeta(type):
    """Metaclass for BetterEnum which adds functionality on the BetterEnum class/subclass so it doesn't initialization."""

    def __iter__(cls) -> Iterator[T]:
        """Iterate over the values of the enum."""
        for key, value in cls.__dict__.items():
            if not key.startswith("_"):
                yield value

    def __len__(cls):
        """Return the number of values in the enum."""
        return len(cls.values())

    def __contains__(cls, item):
        """Return whether the item is a value in the enum."""
        return item in cls.values()

    def items(cls) -> list[tuple[str, Any]]:
        """Return a list of the items of the enum."""
        return zip(cls.keys(), cls.values())

    def keys(cls) -> list[str]:
        """Return a list of the keys of the enum."""
        return cls.names()

    def names(cls) -> list[str]:
        """Return a list of the names of the enum."""
        return [k for k in cls.__dict__ if not k.startswith("_")]

    def values(cls) -> list[Any]:
        """Return a list of the values of the enum."""
        return [v for k, v in cls.__dict__.items() if not k.startswith("_") and not isinstance(v, classmethod)]

    def get_name(cls, value: Any) -> str | None:
        """Return the name of the enum value (or None if the value is not found)."""
        for k, v in cls.__dict__.items():
            if not k.startswith("_") and v == value:
                return k

    def __getitem__(cls, item: str | type) -> Any:
        """Allow accessing the enum values using indexing by name."""
        return cls.__dict__.get(item)

    def repr(cls, max_lines=None, line_length=80):
        if max_lines == 1:
            full = cls.repr(max_lines=None, line_length=line_length)
            if len(full.splitlines()) <= 1:
                return full
        repr_strs = []
        n_keys = 0

        count = len(list(cls.items()))

        for key, value in cls.items():
            if max_lines is None or n_keys < max_lines:
                if hasattr(value, "repr"):
                    try:
                        value_str = value.repr(max([1, int(max_lines / count)]))
                    except Exception:
                        value_str = str(value)
                else:
                    value_str = str(value)
                value_str = "\n\t".join(value_str.splitlines())

                if max_lines is not None and (len(repr_strs) + len(value_str.splitlines())) > max_lines:
                    repr_strs.append(f"{key}: ...")
                else:
                    repr_strs.append(f"{key}: {value_str}")
                n_keys += 1
            else:
                repr_strs.append(f"{key}: ...")
                n_keys += 1
                if max_lines is not None and len(repr_strs) >= max_lines:
                    break

        content = ", ".join(repr_strs)
        s = f"{cls.__name__}({content})"
        if len(s) > line_length:
            content = "\t" + "\n\t".join(repr_strs)
            s = f"{cls.__name__}:\n{content}"
        if max_lines is not None and len(s.splitlines()) > max_lines:
            s = "\n".join(s.splitlines()[: max_lines - 1])
            s += "\n..."
        return s

    def print(cls, max_lines=None, line_length=80, func=print):
        func(cls.repr(max_lines, line_length))

    def __repr__(cls):
        return cls.repr(25)

    def __str__(cls):
        return cls.repr()


class BetterEnumMeta(_BetterEnumMeta, _ProtocolMeta):
    pass


class BetterEnum(Iterable, Protocol[T], metaclass=BetterEnumMeta):
    """A class which can be used as an enum.

    Intended to solve the following problems with the standard enum module:
    - When accessing values on the enum, the values are not the same object as the enum values. This means that
        you always have to access MyEnum.RED.value to get the value
    - typehinting is not possible with the standard enum module
    """

    pass


if __name__ == "__main__":

    class Color(BetterEnum):
        RED = "red"
        BLUE = "blue"
        GREEN = "green"

    # Iterating over the values
    for val in Color:
        print(val)  # Prints 'red', 'blue', 'green'

    # Accessing by key
    print(Color["RED"])  # Prints 'red'

    # Representation
    print(Color)  # Prints 'Color(RED='red', BLUE='blue', GREEN='green

    x = Color.RED

    class Test:
        Shapes: BetterEnum[str]

        def print_shape_names(self):
            for value in self.Shapes:
                print(value)
