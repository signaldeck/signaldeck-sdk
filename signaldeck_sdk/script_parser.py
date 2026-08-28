from __future__ import annotations

from .script_statement import (
    CommandStatement,
    IfStatement,
    SetStatement,
    WhileStatement,
)


class ScriptSyntaxError(ValueError):
    pass


class ScriptParser:
    def parse(self, commands: list[str]) -> list[object]:
        statements, index, terminator = self._parse_block(commands, 0, set())
        if terminator is not None:
            raise ScriptSyntaxError(
                f"Unexpected '{terminator}' at line {index + 1}"
            )
        return statements

    def _parse_block(
        self,
        commands: list[str],
        start: int,
        terminators: set[str],
    ) -> tuple[list[object], int, str | None]:
        statements: list[object] = []
        index = start

        while index < len(commands):
            raw = str(commands[index])
            text = raw.strip()
            line = index + 1

            if not text:
                index += 1
                continue

            keyword = text.split(maxsplit=1)[0]
            if keyword in terminators:
                return statements, index, keyword

            if keyword in {"else", "end"}:
                raise ScriptSyntaxError(
                    f"Unexpected '{keyword}' at line {line}"
                )

            if keyword == "set":
                parts = text.split(maxsplit=2)
                if len(parts) < 3 or not parts[1]:
                    raise ScriptSyntaxError(
                        f"Invalid set statement at line {line}; "
                        "expected: set <variable> <value> or "
                        "set <variable> = <ValueCommand>"
                    )

                value = parts[2].strip()
                is_value_command = False
                if value.startswith("="):
                    value = value[1:].strip()
                    is_value_command = True
                    if not value:
                        raise ScriptSyntaxError(
                            f"Missing ValueCommand for set at line {line}"
                        )

                statements.append(
                    SetStatement(
                        name=parts[1],
                        value=value,
                        line=line,
                        is_value_command=is_value_command,
                    )
                )
                index += 1
                continue

            if keyword == "if":
                parts = text.split(maxsplit=1)
                if len(parts) != 2 or not parts[1].strip():
                    raise ScriptSyntaxError(
                        f"Missing condition for if at line {line}"
                    )

                then_body, end_index, terminator = self._parse_block(
                    commands,
                    index + 1,
                    {"else", "end"},
                )

                else_body: list[object] = []
                if terminator == "else":
                    else_body, end_index, terminator = self._parse_block(
                        commands,
                        end_index + 1,
                        {"end"},
                    )

                if terminator != "end":
                    raise ScriptSyntaxError(
                        f"Missing 'end' for if started at line {line}"
                    )

                statements.append(
                    IfStatement(
                        condition=parts[1].strip(),
                        then_body=then_body,
                        else_body=else_body,
                        line=line,
                    )
                )
                index = end_index + 1
                continue

            if keyword == "while":
                parts = text.split(maxsplit=1)
                if len(parts) != 2 or not parts[1].strip():
                    raise ScriptSyntaxError(
                        f"Missing condition for while at line {line}"
                    )

                body, end_index, terminator = self._parse_block(
                    commands,
                    index + 1,
                    {"end"},
                )
                if terminator != "end":
                    raise ScriptSyntaxError(
                        f"Missing 'end' for while started at line {line}"
                    )

                statements.append(
                    WhileStatement(
                        condition=parts[1].strip(),
                        body=body,
                        line=line,
                    )
                )
                index = end_index + 1
                continue

            statements.append(CommandStatement(command=text, line=line))
            index += 1

        return statements, index, None
