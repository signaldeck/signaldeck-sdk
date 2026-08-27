from dataclasses import dataclass


@dataclass(frozen=True)
class AliasDefinition:
    name: str
    value: str

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=str(data["name"]).strip(),
            value=str(data["value"]).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
        }
